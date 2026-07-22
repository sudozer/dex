#! /usr/bin/env python3
"""
This script ingests dataviewer packets into a new data construct
Only useful for ingesting dataviewer data
"""
from pathlib import Path
import pdb
import sys
import logging

from hexDumpReader import HexDumpReader

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

#wipe log
with open(cfgLoader.getPath(CONFIG()['logBasepath']),'w') as f:
    pass

dataPath = Path("../dataviewerData")
packetReader = HexDumpReader("dataviewer",[b'\x16\x37',b'\x0e\x37',b'\x08\x1b'],logLevel=logging.INFO)
print("running just one tid to extract opnav data")

tidpath=cfgLoader.getPath("dataviewerData/10602-2026-04-02-04.35.40-acquire_with_tmf/tlm_10602.bin")
#subdirs = [x for x in dataPath.iterdir() if x.is_dir()]
# for tid in subdirs:
#     tidNUM = tid.name.split('-')[0]
#     tidpath = tid / f"tlm_{tidNUM}.bin"

    # packetReader.readFromHexDump(tidpath)
packetReader.readFromHexDump(tidpath)

    