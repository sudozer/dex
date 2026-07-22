import json
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import psycopg

from decode.decode import Decoder
from convert.convert import Converter
from loadConfig import Configs


class TelemetryRetrieval:
    """Retrieve telemetry data from transient storage, parquet files, or PostgreSQL."""

    def __init__(self):
        cfgLoader = Configs()
        self.CONFIG = cfgLoader.loadGlobalConfig()
        self.cfgLoader = cfgLoader
        self.pgInfo = self.CONFIG['storage']['postgres']
        self.datetimeFormat = self.CONFIG['datetimeFormat']
        self.connectionString = f"host={self.pgInfo['host']} dbname={self.pgInfo['dbName']} user={self.pgInfo['user']} password={self.pgInfo['password']}"
        self.decoder = Decoder('telemetry')
        self.converter = Converter()

    def _parse_timestamp(self, timestamp):
        if isinstance(timestamp, datetime):
            return timestamp
        if 'T' in str(timestamp):
            return datetime.fromisoformat(str(timestamp))
        return datetime.strptime(str(timestamp), self.datetimeFormat)

    def parseFieldKey(self, field_key):
        parts = field_key.split('__')
        if len(parts) == 2:
            return parts[0], parts[1], 'hd'
        if len(parts) == 3:
            return f"{parts[0]}__{parts[1]}", parts[2], 'pd'
        raise ValueError(f"Invalid field key format: {field_key}")

    def _flatten_packet(self, packet):
        flat = {}
        if not isinstance(packet, dict):
            return flat
        for key, value in packet.items():
            if key == 'metadata':
                continue
            if isinstance(value, dict):
                nested = self._flatten_packet(value)
                for nested_key, nested_value in nested.items():
                    flat[f"{key}__{nested_key}"] = nested_value
            else:
                flat[key] = value
        return flat

    def _decode_packet(self, raw_packet):
        if raw_packet is None:
            return {}
        if isinstance(raw_packet, (bytes, bytearray)):
            packet_bytes = bytes(raw_packet)
        else:
            packet_bytes = raw_packet.encode('utf-8') if isinstance(raw_packet, str) else raw_packet

        try:
            decoded_packet, _, _, _ = self.decoder.readPacket(packet_bytes)
            converted_packet = self.converter.convertPacket(decoded_packet)
            return converted_packet
        except Exception:
            return {}

    def _resolve_field_value(self, packet, field_key):
        if packet is None:
            return None
        if isinstance(packet, dict) and field_key in packet:
            return packet[field_key]
        if isinstance(packet, bytes):
            packet = self._decode_packet(packet)
        if isinstance(packet, dict) and field_key in packet:
            return packet[field_key]
        flat_packet = self._flatten_packet(packet)
        if field_key in flat_packet:
            return flat_packet[field_key]
        table_name, field_name, _ = self.parseFieldKey(field_key)
        for candidate_key, candidate_value in flat_packet.items():
            if candidate_key.endswith(f'__{field_name}') or candidate_key == field_name:
                return candidate_value
        return None

    def _iter_storage_records(self, start_dt=None, end_dt=None):
        records = []
        transient_path = self.cfgLoader.getPath(self.CONFIG['storage']['transientStoragePath'])
        if transient_path.exists():
            with open(transient_path, 'r', encoding='utf-8') as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    packet = entry.get('rawPacket')
                    metadata = entry.get('metadata', {})
                    timestamp_str = metadata.get('primaryTimestamp')
                    if not timestamp_str:
                        continue
                    timestamp_dt = self._parse_timestamp(timestamp_str)
                    if start_dt is not None and timestamp_dt < start_dt:
                        continue
                    if end_dt is not None and timestamp_dt > end_dt:
                        continue
                    records.append({'source': 'transient', 'primaryTimestamp': timestamp_dt, 'packet': packet})

        parquet_dir = self.cfgLoader.getPath(self.CONFIG['storage']['parquet']['parquetBaseDirectory'])
        if parquet_dir.exists():
            for parquet_file in sorted(parquet_dir.glob('*.parquet')):
                try:
                    dataframe = pl.read_parquet(parquet_file)
                except Exception:
                    continue
                for row in dataframe.to_dicts():
                    packet = row.get('rawPacket')
                    timestamp_str = row.get('primaryTimestamp') or (row.get('metadata', {}) if isinstance(row.get('metadata'), dict) else {}).get('primaryTimestamp')
                    if not timestamp_str:
                        continue
                    timestamp_dt = self._parse_timestamp(timestamp_str)
                    if start_dt is not None and timestamp_dt < start_dt:
                        continue
                    if end_dt is not None and timestamp_dt > end_dt:
                        continue
                    records.append({'source': 'parquet', 'primaryTimestamp': timestamp_dt, 'packet': packet})

        try:
            with psycopg.connect(self.connectionString) as conn:
                with conn.cursor() as cur:
                    if start_dt is not None and end_dt is not None:
                        query = """
                            SELECT pm.primaryTimestamp, pd.packet
                            FROM packetMetadata pm
                            JOIN packetData pd ON pd.packetUUID = pm.packetUUID
                            WHERE pm.primaryTimestamp BETWEEN %s AND %s
                            ORDER BY pm.primaryTimestamp
                        """
                        params = (start_dt, end_dt)
                    elif start_dt is not None:
                        query = """
                            SELECT pm.primaryTimestamp, pd.packet
                            FROM packetMetadata pm
                            JOIN packetData pd ON pd.packetUUID = pm.packetUUID
                            WHERE pm.primaryTimestamp >= %s
                            ORDER BY pm.primaryTimestamp
                        """
                        params = (start_dt,)
                    elif end_dt is not None:
                        query = """
                            SELECT pm.primaryTimestamp, pd.packet
                            FROM packetMetadata pm
                            JOIN packetData pd ON pd.packetUUID = pm.packetUUID
                            WHERE pm.primaryTimestamp <= %s
                            ORDER BY pm.primaryTimestamp
                        """
                        params = (end_dt,)
                    else:
                        query = """
                            SELECT pm.primaryTimestamp, pd.packet
                            FROM packetMetadata pm
                            JOIN packetData pd ON pd.packetUUID = pm.packetUUID
                            ORDER BY pm.primaryTimestamp
                        """
                        params = ()
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    for primary_timestamp, packet_data in rows:
                        packet = packet_data
                        records.append({'source': 'postgres', 'primaryTimestamp': primary_timestamp, 'packet': packet})
        except Exception:
            pass

        records.sort(key=lambda item: item['primaryTimestamp'])
        return records

    def getField(self, field_key, timestamp):
        timestamp_dt = self._parse_timestamp(timestamp)
        records = self._iter_storage_records(start_dt=None, end_dt=timestamp_dt)
        matching_record = None
        for record in reversed(records):
            value = self._resolve_field_value(record['packet'], field_key)
            if value is not None:
                matching_record = record
                break

        if matching_record is None:
            return {field_key: pl.DataFrame()}

        value = self._resolve_field_value(matching_record['packet'], field_key)
        frame = pl.DataFrame({
            'primaryTimestamp': [matching_record['primaryTimestamp']],
            'rawBits': [None],
            'decodedValue': [value],
            'convertedValue': [value],
        })
        return {field_key: frame}

    def getFields(self, field_keys, start_timestamp, end_timestamp):
        start_dt = self._parse_timestamp(start_timestamp)
        end_dt = self._parse_timestamp(end_timestamp)
        records = self._iter_storage_records(start_dt=start_dt, end_dt=end_dt)
        result = {}

        for field_key in field_keys:
            rows = []
            for record in records:
                value = self._resolve_field_value(record['packet'], field_key)
                if value is not None:
                    rows.append({
                        'primaryTimestamp': record['primaryTimestamp'],
                        'rawBits': None,
                        'decodedValue': value,
                        'convertedValue': value,
                    })
            if rows:
                result[field_key] = pl.DataFrame(rows)
            else:
                result[field_key] = pl.DataFrame({
                    'primaryTimestamp': [],
                    'rawBits': [],
                    'decodedValue': [],
                    'convertedValue': [],
                })

        return result
