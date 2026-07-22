
import sys
import logging

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from rxPorts import TCPClient
from packetReceiver import PktReceiver
class tcpReciever(PktReceiver):
    def __init__(self,ip,port,packetType,logLevel=logging.WARNING):
        super().__init__(packetType,logLevel)
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.TCPRX = TCPClient(ip,port,self.decodeConvertStore,logLevel)
        self.TCPRX.listen()
