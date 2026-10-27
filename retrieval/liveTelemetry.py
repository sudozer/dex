from PySide6.QtCore import QObject, QThreadPool, QRunnable, Signal,Slot
from datetime import datetime
import pdb

class PacketCallback(QRunnable):
    def __init__(self,func_):    
        super().__init__()
        self.func_ = func_

    @Slot()
    def run(self):
        self.func_()

class LiveTelemetry(QObject):
    def __init__(self):
        super().__init__()
        self.registry = {}
        self.mostRecentPacket = {}
        self.threadPool = QThreadPool()
        self.msgFunctions = []

    def pushPacket(self,packet):
        """
        Accept a freshly decoded and converted packet to be 
        pushed to live displays.
        """
        self.mostRecentPacket[packet['metadata_']['packetType']] = packet

        if packet['metadata_']['packetType'] in self.registry:
            for callback in self.registry[packet['metadata_']['packetType']]:
                callbackWorker = PacketCallback(callback['func_'])
                self.threadPool.start(callbackWorker)
       
    def registerCallback(self,packetType,callback):
        """
        Register a field to be tracked in live telemetry
        component.
        """
        if not packetType in self.registry:
            self.registry[packetType] = [callback]
        else:
            self.registry[packetType].append(callback)

    def removeCallback(self,packetType,callback):
        """
        remove a previously registered callback
        """
        try:
            self.registry[packetType].remove(callback)
        except:
            pass

    def registerMessageFunction(self,msgFunction):
        """
        register a message function for printing errors or debugging info
        since LIVETLM is a shared object
        """
        self.msgFunctions.append(msgFunction)

    def removeMessageFunction(self,msgFunction):
        try:
            self.msgFunctions.remove(msgFunction)
        except:
            pass

    def msgFunction(self,msg,level="INFO"):
        for f in self.msgFunctions:
            f(msg,level)

LIVETLM = LiveTelemetry()