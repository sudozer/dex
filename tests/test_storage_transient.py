import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import store.store as store_module


class StorageTransientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.config = {
            "logBasepath": str(self.temp_root / "active.log"),
            "datetimeFormat": "%Y-%m-%d_%H:%M:%S.%f %Z",
            "telemetryDefinitionsBasepath": str(self.temp_root / "telemetryDefinitions"),
            "storage": {
                "activeStorageMethod": "parquet",
                "storageLevel": "warning",
                "transientWriteSizeBytes": 1,
                "transientStoragePath": str(self.temp_root / "transient" / "storage.jsonl"),
                "parquet": {"parquetBaseDirectory": str(self.temp_root / "parquet")},
                "postgres": {"host": "localhost", "user": "dex", "password": "easypass", "dbName": "o2o"},
            },
        }

    def test_init_recovers_leftover_transient_records(self):
        transient_path = Path(self.config["storage"]["transientStoragePath"])
        transient_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "packet": {"metadata": {"primaryTimestamp": "2026-01-01 00:00:00.000000 UTC"}},
            "rawPacket": "01",
        }
        transient_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        flushed = []

        with patch.object(store_module, "CONFIG", return_value=self.config):
            with patch.object(store_module.Storage, "storeParquetRecords", new=lambda self, records: flushed.extend(records)):
                store_module.Storage(logLevel=20)

        self.assertEqual(len(flushed), 1)
        self.assertEqual(flushed[0]["rawPacket"], "01")

    def test_store_packet_flushes_when_threshold_exceeded(self):
        flushed = []

        with patch.object(store_module, "CONFIG", return_value=self.config):
            with patch.object(store_module.Storage, "storeParquetRecords", new=lambda self, records: flushed.extend(records)):
                storage = store_module.Storage(logLevel=20)
                storage.storePacket({"metadata": {"primaryTimestamp": "2026-01-01 00:00:00.000000 UTC", "components": []}}, b"\x01")

                deadline = time.time() + 2
                while time.time() < deadline and len(flushed) < 1:
                    time.sleep(0.05)

        self.assertGreaterEqual(len(flushed), 1)


if __name__ == "__main__":
    unittest.main()
