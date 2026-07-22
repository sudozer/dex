import sys
sys.path.append('../packetDefinitions')
from packetDefinitionLib import PacketDefinitionUtility
sys.path.append('../utils')
from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig

pktDefUtil = PacketDefinitionUtility()
for packetType in CONFIG()['telemetryStructures']:
    for pktDefFile in CONFIG()['telemetryStructures'][packetType]['format']:
        pktDefUtil.addBitstructStrings(CFGLOADER.getPath(pktDefFile))