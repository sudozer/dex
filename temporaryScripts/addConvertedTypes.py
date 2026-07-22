import sys

sys.path.append('../utils')
sys.path.append('../packetDefinitions')
from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig
from packetDefinitionLib import PacketDefinitionUtility


pktDefLib = PacketDefinitionUtility()
#validate all telemetry structures
fileList = []
telemetryStructures = CONFIG()['telemetryStructures']
for ts in telemetryStructures:
    format = telemetryStructures[ts]['format']
    for file_ in format:
        if not file_ in fileList:
            fileList.append(file_)

for file_ in fileList:
    pktDefLib.addConvertedTypes(CFGLOADER.getPath(file_))