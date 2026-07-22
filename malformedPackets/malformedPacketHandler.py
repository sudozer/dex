from __future__ import annotations

from datetime import datetime
import json
import logging
import os
import subprocess
import sys
import pdb
from pathlib import Path

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig


class PacketProcessingError(Exception):
    def __init__(self, stage, message, raw_packet=None, packet_template=None, field_names=None, errors=None):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.raw_packet = raw_packet
        self.packet_template = packet_template or []
        self.field_names = list(field_names or [])
        self.errors = list(errors or [])
        if not self.errors:
            self.errors.append({"stage": stage, "message": message, "fieldNames": self.field_names})

    def to_error_list(self):
        return list(self.errors)

class MalformedPacketLogger():
    def __init__(self, logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        self.config = CONFIG()
        log_path = cfgLoader.getPath(self.config['logBasepath'])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=str(log_path), encoding='utf-8', level=logLevel)
        self.storage_path = cfgLoader.getPath(self.config['malformedPacketPath'])
        self.index_path = self.storage_path / "index.json"
        self.autoLaunch = bool(self.config.get("autoLaunchMalformedPacketHandler", self.config.get("autoLaunchmalformedPacketHandler", False)))
        self._handler_process = None
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _normalize_packet_bytes(self, rawPacket):
        if isinstance(rawPacket, bytes):
            return rawPacket
        if isinstance(rawPacket, bytearray):
            return bytes(rawPacket)
        if isinstance(rawPacket, str):
            try:
                return bytes.fromhex(rawPacket)
            except ValueError:
                return rawPacket.encode("utf-8")
        return str(rawPacket).encode("utf-8")

    def _normalize_raw_hex(self, rawPacket):
        packet_bytes = self._normalize_packet_bytes(rawPacket)
        if isinstance(packet_bytes, bytes):
            return packet_bytes.hex()
        return str(packet_bytes)

    def _normalize_errors(self, errors):
        normalized = []
        if not errors:
            return normalized
        for error in errors:
            if isinstance(error, PacketProcessingError):
                normalized.extend(error.to_error_list())
            elif isinstance(error, dict):
                normalized.append(error)
            else:
                normalized.append({"message": str(error)})
        return normalized

    def _read_index(self):
        if not self.index_path.exists():
            return []
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _write_index(self, index):
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _handler_running(self):
        pid_file = self.storage_path / ".viewer.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, ValueError, OSError):
            pid_file.unlink(missing_ok=True)
            return False

    def launchHandler(self):
        if self._handler_running():
            return None
        gui_path = Path(__file__).resolve().with_name("malformedPacketViewer.py")
        command = [sys.executable, str(gui_path), "--storage-path", str(self.storage_path)]
        self._handler_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        pid_file = self.storage_path / ".viewer.pid"
        pid_file.write_text(str(self._handler_process.pid), encoding="utf-8")
        return self._handler_process

    def logMalformedPacket(self, rawPacket, packetTemplate=None, errors=None, packetStructure=None, packetType=None, components=None, metadata=None, packet_template=None):
        if packet_template is not None and packetTemplate is None:
            packetTemplate = packet_template
        timestamp = datetime.now().strftime(self.config.get("datetimeFileFormat", "%Y-%m-%d_%H-%M-%S%Z"))
        normalized_errors = self._normalize_errors(errors)
        entry = {
            "timestamp": timestamp,
            "rawPacketHex": self._normalize_raw_hex(rawPacket),
            "packetTemplate": packetTemplate or [],
            "errors": normalized_errors,
            "packetStructure": packetStructure,
            "packetType": packetType,
            "components": components or [],
            "metadata": metadata or {},
            "storagePath": str(self.storage_path / f"{timestamp}_{packetType}.json"),
        }
        entry_path = Path(entry["storagePath"])
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        index = self._read_index()
        index.append({
            "timestamp": entry["timestamp"],
            "storagePath": str(entry_path),
            "packetType": entry["packetType"],
            "components": entry["components"],
        })
        self._write_index(index)
        if self.autoLaunch:
            self.launchHandler()
        return entry