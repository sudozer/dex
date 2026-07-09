
import sys
import logging

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from utils.rxPorts import UDPRXPort
from packetReceiver import PktReceiver
class udpReciever(PktReceiver):
    def __init__(self,ip,port,packetType,logLevel=logging.WARNING):
        super().__init__(packetType,logLevel)
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CONFIG()['logBasepath'], encoding='utf-8', level=logLevel)
        self.UDPRX = UDPRXPort(ip,port,self.decodeConvertStore,logLevel)
        self.UDPRX.listen()
