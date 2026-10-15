import json
import sys
import socket
import logging
import datetime
import pdb
import threading
from pathlib import Path

from packetDefinitionLib import PacketDefinitionUtility
from loadConfig import Configs
from decode import Decoder
from convert import Converter
from store import Storage
from liveTelemetry import LIVETLM
from malformedPacketHandler import MalformedPacketLogger, PacketProcessingError

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

TIMEOUT = 1
socket.setdefaulttimeout(TIMEOUT)

class UDPRXPort(socket.socket):
    def __init__(self,IP,port,packetRXCallback, msgFunction, listeningFlag=threading.Event()):
        super().__init__(socket.AF_INET, socket.SOCK_DGRAM)
        self.bind((IP, port))
        self.msgFunction = msgFunction
        self.msgFunction(f'UDP RX Port initialized and bound to port {port}')
        self.packetRXCallback = packetRXCallback
        self.listeningFlag = listeningFlag
        self.listenThread = threading.Thread(target=self.listen)
        self.listenThread.start()
   
    def listen(self):
        self.msgFunction(f'UDP RX Port listening for incoming packets on port: {self.getsockname()[1]}')
        while self.listeningFlag.is_set():
            try:
                data, addr = self.recvfrom(65536)  # buffer size is 4096 bytes
                self.msgFunction(f'Received packet from {addr}: {data}',"DEBUG")
                self.packetRXCallback(data)
            except socket.timeout:
                pass

        self.msgFunction(f'Closing UDP RX port: {self.getsockname()[1]}')
        self.close()

class PktReceiver():
    def __init__(self, receiverDict, msgFunction,listeningFlag):
        
        self.receiverDict = receiverDict
        self.msgFunction = msgFunction
        self.pktDefUtil = PacketDefinitionUtility()
        self.validatePacketType(self.receiverDict['telemetryStructure'])
        packetStructure = CONFIG()['telemetryStructures'][self.receiverDict['telemetryStructure']]
        self.decoder = Decoder(self.receiverDict['telemetryStructure'], msgFunction)
        self.converter = Converter(msgFunction)
        self.storage = Storage(msgFunction)
        self.packetStructure = packetStructure
        self.malformedPacketHandler = MalformedPacketLogger(msgFunction)
        self.listeningFlag = listeningFlag
        self.acceptedPackets = 0
        self.malformedPackets = 0

        self.openListener()

    def validatePacketType(self, packetType):
        cfg = CONFIG()
        if not packetType in cfg['telemetryStructures']:
            self.msgFunction(f"{packetType} not a recognized packet type.  Current packets types are: {CONFIG()['telemetryStructures'].keys()}","ERROR")
        validatedDataType = True
        
        #headers
        for pktDefPath in cfg['telemetryStructures'][packetType]['headers']:
            pktDefPath = cfgLoader.getPath(pktDefPath)
            if not self.pktDefUtil.validateDefinitionFile(pktDefPath):
                validatedDataType = False
                self.msgFunction(f"Invalid packet definition file: {pktDefPath} in {packetType} packet structure.","ERROR")
        #pktDef
        pktDefPath = cfg['telemetryStructures'][packetType]['packets']
        if len(pktDefPath) > 0:
            pktDefPath = cfgLoader.getPath(pktDefPath)
            if not self.pktDefUtil.validateDefinitionFile(pktDefPath):
                validatedDataType = False
                self.msgFunction(f"Invalid packet definition file: {pktDefPath} in {packetType} packet structure.","ERROR")
        #footers
        for pktDefPath in cfg['telemetryStructures'][packetType]['headers']:
            pktDefPath = cfgLoader.getPath(pktDefPath)
            if not self.pktDefUtil.validateDefinitionFile(pktDefPath):
                validatedDataType = False
                self.msgFunction(f"Invalid packet definition file: {pktDefPath} in {packetType} packet structure.","ERROR")
        
        if validatedDataType:
            self.msgFunction(f"Definition files for {packetType} fully validated.","INFO")
            return True
        return False

    def openListener(self):
        clientType = self.receiverDict['protocol']
        if clientType == "UDP":
            self.listener = UDPRXPort(self.receiverDict['IP'],self.receiverDict['port'],self.decodeConvertStore,self.msgFunction,self.listeningFlag)
        #TODO add tcp options

    def closeAll(self):
        self.listener.listenThread.join()

    def decodeConvertStore(self, packet, groundTimeStamp=True):
        """
        This function interprets a raw pstacket from whichever packet interface,
        and then decodes and converts it to verify packet integrity
        and stores it upon completion.  This is the core function of dex.
        """

        #skipping malformed packet logging for now to cut processing time.
        self.msgFunction(f"Received packet.","DEBUG")
        self.acceptedPackets += 1
        return
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
            self.msgFunction(f"Failed to decode packet: {packet}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate or exc.packet_template, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components)
            return
        except Exception as exc:
            self.msgFunction(f"Failed to decode packet: {packet}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "decode", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components)
            return
        
        #convert
        try:
            convertedPacket = self.converter.convertPacket(decodedPacket, packetTemplate=packetTemplate)
            convertedPacket['metadata']['primaryTimestamp'] = decodedPacket['metadata'].get('groundTimestampUTC', datetime.datetime.now(datetime.UTC).strftime(CONFIG()['datetimeFormat']))
            self.msgFunction(f"Converted packet:\n\n{convertedPacket}","DEBUG")
        except PacketProcessingError as exc:
            self.msgFunction(f"Failed to convert packet: {decodedPacket}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate or exc.packet_template, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=decodedPacket.get('metadata', {}))
            return
        except Exception as exc:
            self.msgFunction(f"Failed to convert packet: {decodedPacket}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "convert", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=decodedPacket.get('metadata', {}))
            return
        LIVETLM.pushPacket(convertedPacket)
        #store
        try:
            self.storage.storePacket(convertedPacket, packet)
        except PacketProcessingError as exc:
            self.msgFunction(f"Failed to store packet: {decodedPacket}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=exc.to_error_list(), packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=convertedPacket.get('metadata', {}))
            return
        except Exception as exc:
            self.msgFunction(f"Failed to store packet: {decodedPacket}. Error: {exc}","ERROR")
            #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "storage", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=convertedPacket.get('metadata', {}))
            return
