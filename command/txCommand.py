import socket
from socket import socket as sock
import pdb
from autofill import Autofiller
import struct
import logging

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig
startingConfig = CONFIG()

LOGGER = logging.getLogger(__name__)
logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logging.INFO)

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
            if startingConfig['autofillCommands']:
                command = self.autofill.autofillAllFields(command)
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
            if startingConfig['autofillCommands']:
                command = self.autofill.autofillAllFields(command)
                
            wrappedCommand = buildCommandFromDict(command)
            self.sendto(wrappedCommand,(self.IP,self.Port))
            self.messageFunction(f"Command sent:\n{wrappedCommand}\n To destination {(self.IP,self.Port)}", 'info')
        except Exception as E:
            self.messageFunction(f"Command Failed:\n{E}\n", 'error')
