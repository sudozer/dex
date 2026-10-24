from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt

import json
import sys
import socket
import time

import datetime
import pdb
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from packetDefinitionLib import PacketDefinitionUtility
from loadConfig import Configs
from decode import Decoder
from convert import Converter
from store import Storage
from liveTelemetry import LIVETLM
from malformedPacketHandler import MalformedPacketLogger, PacketProcessingError

from loadConfig import cfgLoader, GLOBAL_CONFIG

from dataStructures import PACKET_STRUCTURE_SIZES

TIMEOUT = 1
socket.setdefaulttimeout(TIMEOUT)

class PacketProcessor(QObject):
    queueSizeWarning = Signal(int)
    messageSignal = Signal(str,str)
    def __init__(self,receiverDict,packetQueue,processingFlag):
        super().__init__()
        self.processQueue = packetQueue
        self.processingFlag = processingFlag
        self.receiverDict = receiverDict
        self.acceptedPackets = 0
        self.rejectedPackets = 0
        self.decoder = Decoder(self.receiverDict['telemetryStructure'], self.msgFunction)
        self.converter = Converter(self.msgFunction)
        self.storage = Storage(self.msgFunction)
    
    @Slot()
    def processPacketQueue(self):
        while len(self.processQueue) > 0 and self.processingFlag.is_set():
            self.decodeConvertStore(self.processQueue.popleft())
        self.thread().quit()
        
    def msgFunction(self,msg,level="INFO"):
        self.messageSignal.emit(msg,level)

    def decodeConvertStore(self, packet):
            """
            This function interprets a raw pstacket from whichever packet interface,
            and then decodes and converts it to verify packet integrity
            and stores it upon completion.
            """
    
            #skipping malformed packet logging for now to cut processing time.
            #decode
            try:
                decodedPacket, order, packetTemplate = self.decoder.readPacket(packet)
                decodedPacket['metadata'] = { 'order': order,
                                            'groundTimestampUTC': datetime.datetime.now(datetime.UTC).strftime(GLOBAL_CONFIG['datetimeFormat']),
                                            'telemetryStructure': self.receiverDict['telemetryStructure']
                                            }
                self.msgFunction(f"Decoded packet successfully.","DEBUG")
            except Exception as exc:
                self.msgFunction(f"Failed to decode packet: {packet}. Error: {exc}","ERROR")
                #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "decode", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components)
                return
            
            #convert
            try:
                convertedPacket = self.converter.convertPacket(decodedPacket, packetTemplate)
                convertedPacket['metadata']['primaryTimestamp'] = decodedPacket['metadata'].get('groundTimestampUTC', datetime.datetime.now(datetime.UTC).strftime(GLOBAL_CONFIG['datetimeFormat']))
                self.msgFunction(f"Converted packet successfully.","DEBUG")
            except Exception as exc:
                self.msgFunction(f"Failed to convert packet. Error: {exc}","ERROR")
                #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "convert", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=decodedPacket.get('metadata', {}))
                return
            LIVETLM.pushPacket(convertedPacket)
            #store
            try:
                self.storage.storePacket(convertedPacket, packet)
            except Exception as exc:
                self.msgFunction(f"Failed to store packet. Error: {exc}","ERROR")
                #self.malformedPacketHandler.logMalformedPacket(packet, packetTemplate=packetTemplate, errors=[{"stage": "storage", "message": str(exc)}], packetStructure=self.packetStructure, packetType=self.packetType, components=components, metadata=convertedPacket.get('metadata', {}))
                return


class UDPRXPort(QObject):
    messageSignal = Signal(str,str)
    pktSignal = Signal()
   
    def __init__(self,IP,port,packetRXCallback,largestPacket, listeningFlag):
        super().__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.IP = IP
        self.port = port
        self.largestPacket = largestPacket
        self.packetRXCallback = packetRXCallback
        self.listeningFlag = listeningFlag
    
    def bind_(self):
        self.sock.bind((self.IP,self.port))
        self.messageSignal.emit(f'UDP RX Port initialized and bound to port {self.port} with receiver buffer size: {self.largestPacket} bytes.','INFO')

    def listen(self):
        self.messageSignal.emit(f'UDP RX Port listening for incoming packets on port: {self.sock.getsockname()[1]}','INFO')
        while self.listeningFlag.is_set():
            try:

                data, addr = self.sock.recvfrom(self.largestPacket)
                self.messageSignal.emit(f'Received packet from {addr}',"DEBUG")
                self.packetRXCallback(data)
                self.pktSignal.emit()
            except socket.timeout:
                pass

        self.messageSignal.emit(f'Closing UDP RX port: {self.sock.getsockname()[1]}','INFO')
        self.sock.close()

class PktReceiver(QObject):
    def __init__(self, receiverDict, msgFunction,listeningFlag):
        super().__init__()
        
        self.receiverDict = receiverDict
        self.msgFunction = msgFunction
        self.pktDefUtil = PacketDefinitionUtility()
        self.validatePacketType(self.receiverDict['telemetryStructure'])
        packetStructure = GLOBAL_CONFIG['telemetryStructures'][self.receiverDict['telemetryStructure']]

        self.packetStructure = packetStructure
        self.malformedPacketHandler = MalformedPacketLogger(msgFunction)
        self.listeningFlag = listeningFlag

        self.packetProcessingQueue = deque()
        self.processor = PacketProcessor(self.receiverDict,self.packetProcessingQueue,self.listeningFlag)
        self.findLargestPacket()
        self.openListener()

    def validatePacketType(self, packetType):
        cfg = GLOBAL_CONFIG
        if not packetType in cfg['telemetryStructures']:
            self.msgFunction(f"{packetType} not a recognized packet type.  Current packets types are: {GLOBAL_CONFIG['telemetryStructures'].keys()}","ERROR")
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

    def findLargestPacket(self):
        self.largestPacket = 0
        for packet,size_ in PACKET_STRUCTURE_SIZES[self.receiverDict['telemetryStructure']].items():
            self.largestPacket = size_ if size_ > self.largestPacket else self.largestPacket

    def openListener(self):
        clientType = self.receiverDict['protocol']
        self.listenThread = QThread()
        self.processThread = QThread()
        
        if clientType == "UDP":
            self.listener = UDPRXPort(self.receiverDict['IP'],self.receiverDict['port'],self.addToProcessingQueue,self.largestPacket,self.listeningFlag)
            self.listener.messageSignal.connect(self.message_, Qt.ConnectionType.QueuedConnection)
            self.listener.bind_()
        #TODO add tcp options

        self.listener.moveToThread(self.listenThread)
        self.processor.moveToThread(self.processThread)

        self.processThread.started.connect(self.processor.processPacketQueue)
        self.listenThread.started.connect(self.listener.listen)
        self.listener.pktSignal.connect(self.newPacketTrigger)
        self.processor.messageSignal.connect(self.message_, Qt.ConnectionType.QueuedConnection)
        self.listenThread.start()

    def closeAll(self):
        self.listenThread.quit()
        self.processThread.quit()

    def addToProcessingQueue(self,packet):
        self.packetProcessingQueue.append(packet)

    @Slot()
    def newPacketTrigger(self):
        if not self.processThread.isRunning():
            self.processThread.start()

    @Slot(str,str)
    def message_(self,msg,level):
        #exists to be decorated with Slot
        self.msgFunction(msg,level)