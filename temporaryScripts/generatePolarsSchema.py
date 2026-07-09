import json
import sys
import pdb

from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig
from packetDefinitionLib import PacketDefinitionUtility

#generate polars schema for all fields in all files in every format of every telemetry structure
#lol
fieldDefFiles = []
cfg = CONFIG()
pktDefLib = PacketDefinitionUtility()

for tsname in cfg['telemetryStructures']:
    format = cfg['telemetryStructures'][tsname]['format']
    for fpath in format:
        if not fpath in fieldDefFiles:
            fieldDefFiles.append(fpath)

polarsSchema = {}
for fpath in fieldDefFiles:

    polarsSchema = polarsSchema | pktDefLib.writePolarSchema(fpath)

with open(cfg['storage']['polarsSchemaPath'],'w') as f:
    json.dump(polarsSchema,f,indent=4)

