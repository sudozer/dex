import json
import sys
import logging
import datetime
import pdb
from pathlib import Path

from packetDefinitionLib import PacketDefinitionUtility
from loadConfig import Configs
from decode import Decoder
from convert import Converter
from store import Storage

from malformedPacketHandler import MalformedPacketLogger, PacketProcessingError

CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig


class PktReceiver():
    def __init__(self, packetType, logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CFGLOADER.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.packetType = packetType
        self.pktDefUtil = PacketDefinitionUtility(logLevel)
        self.validatePacketType(packetType)
        packetStructure = CONFIG()['telemetryStructures'][packetType]
        self.decoder = Decoder(packetType, logLevel)
        self.converter = Converter(logLevel)
        self.storage = Storage(logLevel)
        self.packetStructure = packetStructure
        self.malformedPacketHandler = MalformedPacketLogger(logLevel)

        self.printPacketCounts = True
        self.acceptedPackets = 0
        self.malformedPackets = 0

    def validatePacketType(self, packetType):
        if not packetType in CONFIG()['telemetryStructures']:
            self.logger.error(f"{packetType} not a recognized packet type.  Current packets types are: {CONFIG()['telemetryStructures'].keys()}")
        validatedDataType = True
        for pktDefPath in CONFIG()['telemetryStructures'][packetType]['format']:
            pktDefPath = Path(CFGLOADER.getPath(pktDefPath))
            if not self.pktDefUtil.validateDefinitionFile(pktDefPath):
                validatedDataType = False
                self.logger.error(f"Invalid packet definition file: {pktDefPath} in {packetType} packet structure.")
        if validatedDataType:
            self.logger.info(f"Definition files for {packetType} fully validated.")
            return True
        return False

    def decodeConvertStore(self, packet, groundTimeStamp=True):
        """
        This function interprets a raw packet from whichever packet interface,
        and then decodes and converts it to verify packet integrity
        and stores it upon completion.  This is the core function of dex.
        """

        #skipping malformed packet logging for now to cut processing time.
        self.logger.debug(f"Received packet: {packet}")
        errors = []
        packetTemplate = []
        components = []

        #decode
        try:
            decodedPacket, components, order, packetTemplate = self.decoder.readPacket(packet)
            decodedPacket['metadata'] = {'components': components, 'order': order}
            if decodedPacket:
                self.logger.debug(f"Decoded packet:\n\n{decodedPacket}")
                if groundTimeStamp:
                    decodedPacket['metadata']['groundTimestampUTC'] = datetime.datetime.now(datetime.UTC).strftime(CONFIG()['datetimeFormat'])
                decodedPacket['metadata']['telemetryStructure'] = self.packetType
        except PacketProcessingError as exc:
            self.logger.error(f"Failed to decode packet: {packet}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate or exc.packet_template, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components)
            self.rx_malformed_packet()
            return
        except Exception as exc:
            self.logger.error(f"Failed to decode packet: {packet}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "decode", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components)
            self.rx_malformed_packet()
            return
        
        #convert
        try:
            convertedPacket = self.converter.convertPacket(decodedPacket, packetTemplate=packetTemplate)
            convertedPacket['metadata']['primaryTimestamp'] = decodedPacket['metadata'].get('groundTimestampUTC', datetime.datetime.now(datetime.UTC).strftime(CONFIG()['datetimeFormat']))
            self.logger.debug(f"Converted packet:\n\n{convertedPacket}")
        except PacketProcessingError as exc:
            self.logger.error(f"Failed to convert packet: {decodedPacket}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate or exc.packet_template, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=decodedPacket.get('metadata', {}))
            self.rx_malformed_packet()
            return
        except Exception as exc:
            self.logger.error(f"Failed to convert packet: {decodedPacket}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "convert", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=decodedPacket.get('metadata', {}))
            self.rx_malformed_packet()
            return
        
        #store
        try:
            self.storage.storePacket(convertedPacket, packet)
        except PacketProcessingError as exc:
            self.logger.error(f"Failed to store packet: {decodedPacket}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=convertedPacket.get('metadata', {}))
            self.rx_malformed_packet()
            return
        except Exception as exc:
            self.logger.error(f"Failed to store packet: {decodedPacket}. Error: {exc}")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "storage", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=convertedPacket.get('metadata', {}))
            self.rx_malformed_packet()
            return
        self.rx_accepted_packet()

    def decodeConvertStoreList(self, packetList):
        for packet in packetList:
            self.decodeConvertStore(packet)

    def rx_malformed_packet(self):
        self.malformedPackets += 1
        msg = f"Malformed Packet Rejected: accepted packets: {self.acceptedPackets}, malformed packets: {self.malformedPackets}"
        self.logger.error(msg)
        if self.printPacketCounts:
            print(msg)

    def rx_accepted_packet(self):
        self.acceptedPackets += 1
        msg = f"Packet Received: accepted packets: {self.acceptedPackets}, malformed packets: {self.malformedPackets}"
        self.logger.debug(msg)
        if self.printPacketCounts:
            print(msg)
