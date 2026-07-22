import socket
import logging
import threading

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

TIMEOUT = 15
socket.setdefaulttimeout(TIMEOUT)

class UDPRXPort(socket.socket):
    def __init__(self,IP,port,packetRXCallback,logLevel=logging.WARNING, stopFlag=threading.Event()):
        super().__init__(socket.AF_INET, socket.SOCK_DGRAM)
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.bind((IP, port))
        self.logger.info(f'UDP RX Port initialized and bound to port {port}')
        self.packetRXCallback = packetRXCallback
        self.stopFlag = stopFlag

    def listen(self):
        self.logger.info(f'UDP RX Port listening for incoming packets on port {self.getsockname()[1]}')
        while not self.stopFlag.is_set():
            try:
                data, addr = self.recvfrom(4096)  # buffer size is 4096 bytes
                self.logger.debug(f'Received packet from {addr}: {data}')
                self.packetRXCallback(data)
            except socket.timeout:
                self.logger.warning('UDP RX Port timed out')

        if self.stopFlag.is_set():
            self.logger.info('Stop flag set, closing UDP RX Port')
            self.close()

class TCPClient(socket.socket):
    def __init__(self,host,port,packetRXCallback,logLevel=logging.WARNING, stopFlag=threading.Event()):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.logger.info(f'Attempting to connect to TCP server at {host}:{port}')
        self.connect((host, port))
        self.logger.info(f'Connected to TCP server at {host}:{port}')
        self.packetRXCallback = packetRXCallback
        self.stopFlag = stopFlag
        self.logger.info(f'TCP RX Port initialized and listening on port {port}')
        self.packetRXCallback = packetRXCallback
        self.stopFlag = stopFlag

    def listen(self):
        while not self.stopFlag.is_set():
            try:
                data = self.recv(4096)  # buffer size is 4096 bytes
                if not data:
                    self.logger.warning('TCP connection closed by server')
                    break
                self.logger.debug(f'Received packet: {data}')
                self.packetRXCallback(data)
            except socket.timeout:
                self.logger.warning('TCP RX Port timed out')
        
        if self.stopFlag.is_set():
            self.logger.info('Stop flag set, closing TCP RX Port')
            self.close()