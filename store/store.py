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
    def __init__(self, msgFunction):
        cfg = CONFIG()
        self.msgFunction = msgFunction
        self.storageMethod = str(cfg['storage']['activeStorageMethod']).lower()
        self.transientStorageBytes = int(cfg['storage']['transientWriteSizeBytes'])
        self.transientStoragePath = cfgLoader.getPath(cfg['storage']['transientStoragePath'])
        self.dataStructureConversion = PolarsStructures(msgFunction)

        if self.storageMethod == 'parquet':
            self.parquetBaseDirectory = Path(cfgLoader.getPath(cfg['storage']['parquet']['parquetBaseDirectory']))
            self.parquetBaseDirectory.mkdir(parents=True, exist_ok=True)
            self.msgFunction(
                f"Storage Initiated: writing data to parquet files every {self.transientStorageBytes} bytes. Files will be written in: {self.parquetBaseDirectory}",
                "INFO"
            )

    def storePacket(self, packet, rawPacket):
        packet['metadata']['packetUUID'] = uuid.uuid4()
        self._append_transient_packet(packet, rawPacket)

