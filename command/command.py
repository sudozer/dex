import socket
from socket import socket as sock
import pdb
import threading
from autofill import Autofiller
import struct
import logging

from loadConfig import cfgLoader, GLOBAL_CONFIG
from dataStructures import COMMAND_STRUCTURE_SIZES


LOGGER = logging.getLogger(__name__)
logging.basicConfig(filename=cfgLoader.getPath(GLOBAL_CONFIG['logBasepath']), encoding='utf-8', level=logging.INFO)

def defaultLog(msg,level):
    LOGGER.info(msg)

def buildCommandFromDict(commandList):
    commandBits = ''
    for field in commandList:
        commandBits = commandBits + returnBitstring(field)
    byte_length = len(commandBits)//8
    binary_data = int(commandBits, 2).to_bytes(byte_length, byteorder="big")
    return binary_data

def returnBitstring(field):
    #this is ai code cuz i couldn't be assed
    fieldType = field['type']
    value = field['value']
    bitLength = field['bitLength']
    if fieldType == 'char':
        bitstring = format(ord(value), '08b')
    elif fieldType in ('float', 'double'):
        format_ = '>f' if fieldType == 'float' else '>d'
        bitstring = ''.join(
            format(byte, '08b')
            for byte in struct.pack(format_, float(value))
        )
    else:
        convertedValue = int(value)
        if bitLength:
            bitstring = format(
                convertedValue & ((1 << bitLength) - 1),
                f'0{bitLength}b'
            )
        else:
            bitstring = format(convertedValue, 'b')

    return bitstring
    
class TCPCommandSocket(sock):
    def __init__(self,IP,Port,messageFunction='log',role='client'):
        super().__init__(socket.AF_INET,socket.SOCK_STREAM)
        self.role =role
        self.IP = IP
        self.Port = Port
        self.autofiller = Autofiller()
        
        if messageFunction == 'log':
            self.messageFunction = defaultLog
        self.messageFunction = messageFunction
        self.settimeout(10.0)
        self.establishTcpConnection()

    def establishTcpConnection(self):
        if self.role == 'client':
            #hit the ip and port for a connection
            try:
                self.connect((self.IP,self.Port))
            except socket.error as E:
                self.messageFunction(f"Unable to establish connection: {E}",'error')

        if self.role == 'server':
            try:
                self.bind((self.IP,self.Port))
                self.listen()
                self.conn,self.address = self.accept()
            except socket.error as E:
                self.messageFunction(f"Unable to establish connection: {E}",'error')

    def sendCommand(self,command):
        wrappedCommand = buildCommandFromDict(command)
        if self.role == "client":
            if GLOBAL_CONFIG['autofillCommands']:
                command = self.autofiller.autofillAllFields(command)
            pass


class UDPCommandSocket(sock):
    def __init__(self,IP,Port,messageFunction):
        super().__init__(socket.AF_INET,socket.SOCK_DGRAM)
        self.IP = IP
        self.Port = Port
        self.messageFunction = messageFunction
        self.autofill = Autofiller()

    def sendCommand(self,command):
        try:
            if GLOBAL_CONFIG['autofillCommands']:
                command = self.autofill.autofillAllFields(command)
                
            wrappedCommand = buildCommandFromDict(command)
            self.sendto(wrappedCommand,(self.IP,self.Port))
            self.messageFunction(f"Command sent:\n{wrappedCommand}\n To destination {(self.IP,self.Port)}", 'info')
        except Exception as E:
            self.messageFunction(f"Command Failed:\n{E}\n", 'error')

class CommandReceiver(sock):
    def __init__(self,IP,port,protocol,structure,messageFunction,commandCallback = None):
        super().__init__(socket.AF_INET,socket.SOCK_DGRAM)
    
        self.IP = IP
        self.port = port
        self.protocol = protocol
        self.structure = structure
        self.commandCallback = commandCallback
        self.messageFunction = messageFunction
        self.maxCommandSize = max(COMMAND_STRUCTURE_SIZES[structure].values())
        self.listeningFlag = threading.Event()
        self.listeningFlag.set()
        self.settimeout(1.0)
        self.bind((self.IP,self.port))
        self.commandQueue = []

    def openListeningPort(self):
        if self.protocol == 'UDP':
            self.listeningPort = self

        if self.protocol == 'TCP Server':
            #TODO
            pass

        if self.protocol == 'TCP Client':
            #TODO
            pass

    def listenThread(self):
        if self.protocol == 'UDP':
            self.messageFunction(f"Listening for UDP commands on {(self.IP,self.port)}",'info')
            while self.listeningFlag.is_set():
                try:
                    data, addr = self.listeningPort.recvfrom(self.maxCommandSize)
                except socket.timeout:
                    continue
                if self.listeningFlag.is_set():
                    self.messageFunction(f"Received command packet from {addr}: {data}")
                    self.processCommandPacket(data)

    def stopListening(self):
        self.listeningFlag.clear()

    def processThread(self):
        while True:
            if self.commandQueue:
                commandPacket = self.commandQueue.pop(0)
                self.processCommandPacket(commandPacket)

    def processCommandPacket(self, commandPacket):
        if self.commandCallback is not None:
            self.commandCallback(commandPacket)