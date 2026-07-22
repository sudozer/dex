import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from malformedPackets.malformedPacketHandler import MalformedPacketLogger


class MalformedPacketLoggerTests(unittest.TestCase):
    def test_log_malformed_packet_writes_json_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir) / "malformed_storage"
            storage_path.mkdir(parents=True, exist_ok=True)

            logger = MalformedPacketLogger(logLevel=20)
            logger.storage_path = storage_path
            logger.index_path = storage_path / "index.json"
            logger.autoLaunch = False

            raw_packet = bytes.fromhex("0A0B0C")
            packet_template = [
                {"fieldName": "header", "bitLength": 8, "bitOffset": 0, "rawBits": "00001010", "rawValue": 10, "convertedValue": 10},
            ]
            errors = [{"stage": "decode", "message": "Packet too short"}]

            entry = logger.logMalformedPacket(
                raw_packet,
                packet_template=packet_template,
                errors=errors,
                packetStructure={"format": ["header"]},
                packetType="telemetry",
                components=["header"],
            )

            self.assertTrue(entry["storagePath"].exists())
            self.assertEqual(entry["packetType"], "telemetry")
            self.assertEqual(entry["errors"][0]["message"], "Packet too short")
            self.assertEqual(entry["rawPacketHex"], "0a0b0c")

            index_payload = json.loads(logger.index_path.read_text())
            self.assertEqual(len(index_payload), 1)


if __name__ == "__main__":
    unittest.main()
