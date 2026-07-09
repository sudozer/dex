import json
import sys
import logging
import datetime
import pdb

from packetDefinitionLib import PacketDefinitionUtility
from loadConfig import Configs
from decode import Decoder
from convert import Converter
from store import Storage
from brokenPackets import BrokenPackets
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig

class PktReceiver():
    def __init__(self,packetType,logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CONFIG()['logBasepath'], encoding='utf-8', level=logLevel)
        self.packetType = packetType
        self.pktDefUtil = PacketDefinitionUtility(logLevel)
        self.validatePacketType(packetType)
        packetStructure = CONFIG()['telemetryStructures'][packetType]
        self.decoder = Decoder(packetType,logLevel)
        self.converter = Converter(logLevel)
        self.storage = Storage(logLevel)
        self.packetStructure = packetStructure
        self.brokenPacketHandler = BrokenPackets(logLevel)

    def validatePacketType(self,packetType):
        #throw a tantrum if databases fail validation
        if not packetType in CONFIG()['telemetryStructures']:
            self.logger.error(f"{packetType} not a recognized packet type.  Current packets types are: {CONFIG()['telemetryStructures'].keys()}")
        validatedDataType = True
        for pktDefPath in CONFIG()['telemetryStructures'][packetType]['format']:
            if not self.pktDefUtil.validateDefinitionFile(pktDefPath):
                validatedDataType = False
                self.logger.error(f"Invalid packet definition file: {pktDefPath} in {packetType} packet structure.")
        if validatedDataType:
            self.logger.info(f"Definition files for {packetType} fully validated.")
            return True
        else:
            return False
        
    def decodeConvertStore(self,packet,groundTimeStamp = True):
        """
        This function interprets a raw packet from whichever packet interface,
        and then decodes and converts it to verify packet integrity 
        and stores it upon completion.  This is the core function of dex.
        """
        self.logger.debug(f"Received packet: {packet}")
        try:
            decodedPacket, components, order = self.decoder.readPacket(packet)
            decodedPacket['metadata'] = {'components': components, 'order': order}
            if decodedPacket:
                self.logger.debug(f"Decoded packet:\n\n{decodedPacket}")

                if groundTimeStamp:
                    decodedPacket['metadata']['groundTimestampUTC'] = datetime.datetime.now(datetime.UTC).strftime(CONFIG()['datetimeFormat'])
                    
                decodedPacket['metadata']['telemetryStructure'] = self.packetType
        except Exception as e:
            self.logger.error(f"Failed to decode packet: {packet}. Error: {e}")
            self.brokenPacketHandler.logMalformedPacket(self.packetStructure,packet,'decode')


        try:    
            convertedPacket = self.converter.convertPacket(decodedPacket)
            #TODO fix primary timestamp in case user decides to use a different primary timestamp from the converted packets
            convertedPacket['metadata']['primaryTimestamp'] = decodedPacket['metadata']['groundTimestampUTC']
            self.logger.debug(f"Converted packet:\n\n{convertedPacket}")
        except Exception as e:
            self.logger.error(f"Failed to convert packet: {decodedPacket}. Error: {e}")
            self.brokenPacketHandler.logMalformedPacket(self.packetStructure,packet,'convert')
        
        
        try:
            self.storage.storePacket(convertedPacket,packet)
        except Exception as e:
            self.logger.error(f"Failed to store packet: {decodedPacket}. Error: {e}")
            self.brokenPacketHandler.logMalformedPacket(self.packetStructure,packet,'storage')

    
    def decodeConvertStoreList(self,packetList):
        for packet in packetList:
            self.decodeConvertStore(packet)
