
import sys
import logging
import pdb
from copy import deepcopy
import json
sys.path.append('../utils')

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from packetReceiver import PktReceiver
from dynamicLengthFields import findFieldLength

class HexDumpReader(PktReceiver):
    def __init__(self,packetType,hexTriggerSequences,logLevel=logging.WARNING):
        super().__init__(packetType,logLevel)
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.packetType = packetType
        self.structure = CONFIG()['telemetryStructures'][packetType]
        self.hexTriggerSequences = hexTriggerSequences
        self.decodedBytes = 0

    def readFromHexDump(self,filePath):
        self.logger.info(f"Reading packets from {filePath}\n\nParsing for trigger sequences:\n{self.hexTriggerSequences}")
        with open(filePath, 'rb') as f:
            data = f.read()
        #find the expected packet length
        #a little wacky hacky

        headerTemplate = self.decoder.assembleHeaderTemplate(CONFIG()['telemetryStructures'][self.packetType])
        #count bits in header to find packet id
        headerBitLength = 0
        for field in headerTemplate:
            headerBitLength += field['bitLength']

        headerByteLength = headerBitLength // 8 + 1
        dataIndex = 0
        while dataIndex < len(data):
            packetRead = False
            for trigger in self.hexTriggerSequences:

                if data[dataIndex:dataIndex + len(trigger)] == trigger:
                    hexHdr = data[dataIndex:dataIndex + headerByteLength]
                    pktTemplate, components = self.decoder.createPacketTemplate(deepcopy(self.structure),hexHdr)
                    if not pktTemplate:
                        self.logger.error(f"Unable to read packet at index: {dataIndex} with structure {self.structure} Logging malformed packet for analysis.")
                    pktLen = 0
                    for field in pktTemplate:
                        if 'variableLength' in field:
                            field = findFieldLength(data[dataIndex:dataIndex + pktLen],pktTemplate,field)
                        # pdb.set_trace()
                        pktLen += field['bitLength']
                    if pktLen % 8 != 0:
                        self.logger.warning(f"Packet length in bits {pktLen} is not a whole number of bytes. Check packet definitions for {self.packetType}.")
                        pktLenBytes = int(pktLen // 8 + 1)
                    else:
                        pktLenBytes = int(pktLen / 8)
                    packetHex = data[dataIndex:dataIndex + int(pktLenBytes)]
                    packet = self.decodeConvertStore(packetHex)
                    packetRead = True
                    break
            
            if packetRead:
                self.logger.debug(f"Decoded packet: {packet}")
                dataIndex += pktLenBytes
                self.decodedBytes += pktLenBytes
            else:
                self.logger.warning(f"Packet header not found at index {dataIndex}.  Looking for {self.hexTriggerSequences}. Found {data[dataIndex:dataIndex+len(trigger)]}. Searching for next packet header...\n\nSurrounding bytes, data index is byte 4: {data[dataIndex - 4:dataIndex + 5]}")
                try:
                    self.logger.warning(f"Previous successful packet:\n\n{json.dumps(packet,indent=4)}")
                except:
                    pass


                #parse for next trigger sequence
                nextPktFound = False
                while dataIndex < len(data) and not nextPktFound:
                    for trigger in self.hexTriggerSequences:
                        if data[dataIndex:dataIndex + len(trigger)] == trigger:
                            nextPktFound = True
                    if not nextPktFound:
                        dataIndex += 1

        self.logger.info(f"Finished reading hex dump: {filePath}. Total bytes decoded: {self.decodedBytes}. Total bytes in hex dump: {len(data)}. Percentage decoded: {self.decodedBytes/len(data)*100:.2f}%")