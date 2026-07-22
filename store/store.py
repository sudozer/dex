"""Transient and permanent storage management for telemetry packets."""

import base64
import json
import logging
import os
import sys
import pdb
import threading
import uuid
from datetime import datetime
from pathlib import Path

import polars

from dataStructures import PolarsStructures
from loadConfig import Configs
from postgresAdapter import PGConnection


from malformedPacketHandler import PacketProcessingError

cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig


class Storage():
    def __init__(self, logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logLevel)
        cfg = CONFIG()
        self.storageMethod = str(cfg['storage']['activeStorageMethod']).lower()
        self.transientStorageBytes = int(cfg['storage']['transientWriteSizeBytes'])
        self.transientStoragePath = cfgLoader.getPath(cfg['storage']['transientStoragePath'])
        self.dataStructureConversion = PolarsStructures(logLevel)
        self.useTransientStorage = self.storageMethod not in {'postgresdirect'}
        self.transientStorage = self.useTransientStorage
        self._transient_bytes = 0
        self._flush_lock = threading.Lock()
        self._flush_thread = None
        self._flush_active = False
        self._transient_file_path = Path(self.transientStoragePath)
        self._ensure_transient_storage_path()

        if self.storageMethod == 'parquet':
            self.parquetBaseDirectory = Path(cfgLoader.getPath(cfg['storage']['parquet']['parquetBaseDirectory']))
            self.parquetBaseDirectory.mkdir(parents=True, exist_ok=True)
            self.logger.info(
                f"Storage Initiated: writing data to parquet files every {self.transientStorageBytes} bytes. Files will be written in: {self.parquetBaseDirectory}"
            )
        elif self.storageMethod == 'postgres':
            self.database = PGConnection()
            self.database.openConnection()
        elif self.storageMethod == 'postgresdirect':
            self.database = PGConnection()
            self.database.openConnection()

        if self.useTransientStorage:
            self._recover_leftover_transient_storage()

    def _ensure_transient_storage_path(self):
        self._transient_file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._transient_file_path.exists():
            self._transient_file_path.touch(exist_ok=True)

    def _serialize_packet_record(self, rawPacket):
        if isinstance(rawPacket, (bytes, bytearray)):
            raw_payload = base64.b64encode(bytes(rawPacket)).decode('ascii')
        else:
            raw_payload = rawPacket
        return raw_payload

    def _deserialize_packet_record(self, record):
        packet = record.get('packet', {})
        raw_payload = record.get('rawPacket')
        if isinstance(raw_payload, str):
            try:
                return packet, base64.b64decode(raw_payload.encode('ascii'))
            except Exception:
                return packet, raw_payload.encode('utf-8')
        return packet, raw_payload

    def storePacket(self, packet, rawPacket):
        packet['metadata']['packetUUID'] = uuid.uuid4()
        try:
            if self.storageMethod == 'postgresdirect':
                self.database.addPacket(packet, rawPacket)
                return

            if self.useTransientStorage:
                self._append_transient_packet(packet, rawPacket)
            else:
                raise PacketProcessingError('storage', f'Unsupported storage method {self.storageMethod}')
        except PacketProcessingError:
            raise
        except Exception as exc:
            raise PacketProcessingError('storage', f'Failed to store packet: {exc}') from exc

    def _append_transient_packet(self, packet, rawPacket):
        serializedPkt = self._serialize_packet_record(rawPacket)
        record = {'packetUUID':packet['metadata']['packetUUID'], 'primaryTimestamp': packet['metadata']['primaryTimestamp'],'components':packet['metadata']['components'], 'telemetryStructure': packet['metadata']['telemetryStructure'], 'rawPacket': serializedPkt}
        payload = json.dumps(record, default=str)
        with self._flush_lock:
            with open(self._transient_file_path, 'a', encoding='utf-8') as handle:
                handle.write(payload + '\n')
            self._transient_bytes += len(payload.encode('utf-8')) + 1
        if self._transient_bytes >= self.transientStorageBytes:
            self._start_flush_thread()

    def _start_flush_thread(self):
        if self._flush_active or (self._flush_thread and self._flush_thread.is_alive()):
            return
        self._flush_active = True
        self._flush_thread = threading.Thread(target=self._flush_transient_storage, daemon=True)
        self._flush_thread.start()

    def _drain_transient_records(self):
        with self._flush_lock:
            if not self._transient_file_path.exists():
                return []

            with open(self._transient_file_path, 'r', encoding='utf-8') as handle:
                lines = [line.strip() for line in handle if line.strip()]

            empty_file_path = self._transient_file_path.with_suffix('.tmp')
            with open(empty_file_path, 'w', encoding='utf-8') as handle:
                handle.write('')
            os.replace(empty_file_path, self._transient_file_path)
            self._transient_bytes = 0

            records = []
            for line in lines:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    self.logger.warning(f'Unable to decode transient packet line: {exc}')
            return records

    def _restore_transient_records(self, records):
        if not records:
            return
        with self._flush_lock:
            with open(self._transient_file_path, 'a', encoding='utf-8') as handle:
                for record in records:
                    payload = json.dumps(record, default=str)
                    handle.write(payload + '\n')
                    self._transient_bytes += len(payload.encode('utf-8')) + 1

    def _flush_transient_storage(self):
        try:
            records = self._drain_transient_records()
            if not records:
                self._flush_active = False
                return

            self._write_records_to_permanent_storage(records)
        except Exception as exc:
            self.logger.exception(f'Failed to flush transient storage: {exc}')
            self._restore_transient_records(records if 'records' in locals() else [])
        finally:
            self._flush_active = False

    def _recover_leftover_transient_storage(self):
        if not self._transient_file_path.exists():
            return
        records = self._drain_transient_records()
        if records:
            self._write_records_to_permanent_storage(records)

    def _write_records_to_permanent_storage(self, records):
        if not records:
            return

        if self.storageMethod == 'postgres':
            for record in records:
                packet, rawPacket = self._deserialize_packet_record(record)
                self.database.addPacket(packet, rawPacket)
        elif self.storageMethod == 'parquet':
            self.storeParquetRecords(records)
        else:
            raise PacketProcessingError('storage', f'Unsupported storage method {self.storageMethod}')

    def initTransientStorage(self):
        self._ensure_transient_storage_path()
        self.transientStorage = True

    def writeTransientStorage(self, fields=None):
        if self.useTransientStorage:
            self._start_flush_thread()

    def writePermanentStorage(self, transientFilePath=None):
        if self.useTransientStorage:
            self._start_flush_thread()

    def storeParquetRecords(self, records):
        if not records:
            return
        rows = []
        for record in records:
            packet, rawPacket = self._deserialize_packet_record(record)
            metadata = packet.get('metadata', {})
            rows.append({
                'packetUUID': str(metadata.get('packetUUID', uuid.uuid4())),
                'primaryTimestamp': metadata.get('primaryTimestamp'),
                'telemetryStructure': metadata.get('telemetryStructure'),
                'components': json.dumps(metadata.get('components', []), default=str),
                'packet': json.dumps(packet, default=str),
                'rawPacket': rawPacket if isinstance(rawPacket, (bytes, bytearray)) else str(rawPacket),
            })

        if not rows:
            return

        dataframe = polars.DataFrame(rows)
        self.parquetBaseDirectory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = self.parquetBaseDirectory / f'packets_{timestamp}_{uuid.uuid4().hex[:8]}.parquet'
        dataframe.write_parquet(file_path)

    def storeParquet(self, transientFilePath):
        self.storeParquetRecords(self._drain_transient_records())