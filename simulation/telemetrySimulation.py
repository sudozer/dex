import json
import pdb
import socket
from socket import socket as sock
import serialize
from autofill import Autofiller
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot
 
from loadConfig import cfgLoader, GLOBAL_CONFIG

from dataStructures import PACKET_STRUCTURE_COMPONENTS, COMMAND_COMPONENTS
from liveTelemetry import LIVETLM
from command import CommandReceiver
from behaviorGenerators import *

class SimTelemetryTransmitter(sock):
    def __init__(self,packetConfig,simulationMessageFunction):
        self.packetConfig = packetConfig
        self.simulationMessageFunction = simulationMessageFunction
        self.createPacketTransmitter()

    def createPacketTransmitter(self):
        if self.packetConfig['protocol'] == 'UDP':
            super().__init__(socket.AF_INET,socket.SOCK_DGRAM)
            self.destinationTuple = (self.packetConfig['ip'],self.packetConfig['port'])
            self.sendFunc = self.sendUDP
            self.simulationMessageFunction.emit(f"UDP transmitter opened to IP:{self.packetConfig['ip']}, Port:{self.packetConfig['port']}", "INFO")

        if self.packetConfig['protocol'] == 'TCP Client':
            #TODO
            pass

        if self.packetConfig['protocol'] == 'TCP Server':
            #TODO
            pass

    def sendUDP(self,packet):
        self.simulationMessageFunction.emit(f"Sending {self.packetConfig['structure']}::{self.packetConfig['packet']} packet.","DEBUG")
        self.sendto(packet,self.destinationTuple)

    def send(self,packet):
        self.sendFunc(packet)

class SimTelemetryReceiver():
    def __init__(self,simulationMessageFunction):
        self.simulationMessageFunction = simulationMessageFunction
        self.telemetryTriggerRegistry = {}

class SimCommandReceiver(CommandReceiver):
    def __init__(self,commandPort,commandProtocol,commandStructure,simulationMessageFunction):
        super().__init__('127.0.0.1',commandPort,commandProtocol,commandStructure,simulationMessageFunction)

class Field():
    def __init__(self,component,fieldDict,packetConfig,packetBehaviors,initialConditions,fieldSimulationDict,simulatedPacket):
        self.simulatedPacket = simulatedPacket
        self.component = component
        self.fieldDict = fieldDict
        self.packetConfig = packetConfig
        self.packetBehaviors = packetBehaviors
        self.initialConditions = initialConditions
        self.fieldSimulationDict = fieldSimulationDict
        self.fieldDict['value'] = fieldDict.get('defalutValue',0)
        self.prevValue = fieldDict.get('defaultValue',0)
        self.initReturn()
        self.valueList = []

    def initReturn(self):
        #first enabled field behavior initial condition gets set
        for simPair in self.fieldSimulationDict:
            if simPair['trigger']['triggerType'] == "Initial COndition" and simPair['enabled']:
                self.changeBehavior(simPair['behavior'])
                return
        #first enabled packet behavior initial condition gets set
        for simPair in self.packetBehaviors:
            if simPair['trigger']['triggerType'] == "Initial Condition" and simPair['enabled']:
                self.changeBehavior(simPair['behavior'])
                return
        #global initial condition gets set
        if self.initialConditions.get("enabled",False):
            behaviorDict = {"behaviorType":"Playback From Telemetry","behaviorArgs":{"playbackDatabase":self.initialConditions.get("playbackDatabase"),"playbackTime":self.initialConditions.get("playbackTime")}}
            self.changeBehavior(behaviorDict)
            return

        #default value
        if 'defaultValue' in self.fieldDict:
            self.changeBehavior({"behaviorType":"Static Value","behaviorArgs":{"value":self.fieldDict['defaultValue']}})
            return

        #init to a default value
        if self.fieldDict['type'] == 'char':
            self.changeBehavior({"behaviorType":"Static Value","behaviorArgs":{"value":'0'}})
        else:
            self.changeBehavior({"behaviorType":"Static Value","behaviorArgs":{"value":0}})

    def changeBehavior(self,behaviorDict):
        self.currentBehavior = behaviorDict
        if self.currentBehavior['behaviorType'] == "Static Value":
            self.behaviorGenerator = behaviorStaticValue(self.currentBehavior['behaviorArgs']['value'])

        if self.currentBehavior['behaviorType'] == "Ramp Value":
            self.behaviorGenerator = behaviorRampValue(self.currentBehavior['behaviorArgs'],self.prevValue,self.packetConfig['simulationRate'])

        if self.currentBehavior['behaviorType'] == "Playback From Telemetry":
            self.behaviorGenerator = behaviorPlayBackTelemetry(self.fieldDict,self.currentBehavior['behaviorArgs']['playbackDatabase'],self.currentBehavior['behaviorArgs']['playbackTime'])
                    
    def buildValue(self):
        self.prevValue = self.fieldDict['value']
        val = next(self.behaviorGenerator)
        self.fieldDict['value'] = val
        rawBits,rawBytes = serialize.returnBitstring(self.fieldDict)
        return {'val':val,'rawBits':rawBits,'rawBytes':rawBytes}    

    def returnValue(self):
        valDict = self.buildValue()
        return self.fieldDict | valDict
    
    def registerTriggers(self):
        pass


class SimulatedPacket(QObject):
    messageSignal = Signal(str,str)
    def __init__(self, simDict, commandReceiver, telemetryReceiver,row):
        super().__init__()
        self.fields=[]
        self.row = row
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.queueLock = threading.Lock()
        self.autofiller = Autofiller()
        self.simDict = simDict
        self.period = 1 / self.simDict['packetConfig']['simulationRate']
        self.simCapacity = 100
        self.packetsSent = 0
        self.commandReceiver = commandReceiver
        self.telemetryReceiver = telemetryReceiver
        self.simulationMessageFunction = self.messageSignal
        self.packetTemplate = PACKET_STRUCTURE_COMPONENTS[simDict['packetConfig']['structure']][simDict['packetConfig']['packet']]
        self.telemetryTransmitter = SimTelemetryTransmitter(simDict['packetConfig'],self.simulationMessageFunction)
        self.buildFieldList()
        self.transmitThread = threading.Thread(target=self.packetSenderThread)

    def buildFieldList(self):
        if 'packetIdField' in GLOBAL_CONFIG['telemetryStructures'][self.simDict['packetConfig']['structure']]:
            pktIdField = GLOBAL_CONFIG['telemetryStructures'][self.simDict['packetConfig']['structure']]['packetIdField']
        else:
            pktIdField = False
        self.pktIdFieldIdx = None
        for i,component in enumerate(self.packetTemplate):

            componentName = component['component']
            #if a packet comes from a structure with multiple packet types the id field has to be filled
            if pktIdField and i == pktIdField['componentIndex']:
                self.pktIdFieldIdx = len(self.fields) + pktIdField['fieldIndex']
            for i,field in enumerate(component['fields']):
                self.fields.append(Field(component['component'],
                                         field,self.simDict['packetConfig'],
                                         self.simDict['packetBehaviors'],
                                         self.simDict['initialConditions'],
                                         self.simDict['fieldBehaviors'].get(componentName,{}).get(field['fieldName'],{}),
                                         self))
        if self.pktIdFieldIdx is not None:
            idField = self.fields[self.pktIdFieldIdx]
            if idField.fieldDict['type'] == 'char':
                idVal = str(self.simDict['packetConfig']['packet'])
            else:
                idVal = int(self.simDict['packetConfig']['packet'])
            idField.changeBehavior({'behaviorType':"Static Value",'behaviorArgs':{'value':idVal}})

    def buildPacket(self):
        packetList = []
        for field in self.fields:
            fieldVal = field.returnValue()
            packetList.append(fieldVal)
        return packetList
    
    def sendPacket(self,packet):
        if GLOBAL_CONFIG.get('autofillSimPackets'):
            packet = self.autofiller.autofillAllFields(packet)
        bitString = ''
        for field in packet:
            bitString = bitString + field['rawBits']
        #TODO packet must be a whole number of bytes
        packetBytes = int(bitString, 2).to_bytes(len(bitString)//8, byteorder="big")
        self.telemetryTransmitter.send(packetBytes)
    
    @Slot()        
    def packetSenderThread(self):
        currentPacket = self.buildPacket()
        self.simulationMessageFunction.emit(f"Launching simulation thread of structure: {self.simDict['packetConfig']['structure']} packet:{self.simDict['packetConfig']['packet']}","INFO")
        while not self.stopped.is_set():
            time.sleep(1) #unpause timer
            nextTime = time.time() + self.period
            while not self.paused.is_set() and not self.stopped.is_set():
                nextTime = nextTime + self.period
                with self.queueLock:
                    self.sendPacket(currentPacket)
                    self.packetsSent += 1
                currentPacket = self.buildPacket()
                if GLOBAL_CONFIG['simulationSendLimitedPackets']:
                    if GLOBAL_CONFIG['simulationNumberOfPackets'] <= self.packetsSent:
                        self.stopped.set()
                now = time.time()
                dwellPeriod = nextTime - now
                if dwellPeriod > 0:
                    time.sleep(dwellPeriod)
                else:
                    self.simulationMessageFunction.emit(f"Simulation falling behind: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']} ","ERROR")
                    nextTime = time.time()
        self.simulationMessageFunction.emit(f"Simulation thread completed: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")
        self.thread().quit()

    def pause(self):
        self.paused.set()
        self.simulationMessageFunction.emit(f"Simulation paused: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")
    
    def resume(self):
        self.paused.clear()
        self.simulationMessageFunction.emit(f"Simulation resuming: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")

    def stop(self):
        self.stopped.set()
        self.telemetryTransmitter.close()
        self.simulationMessageFunction.emit(f"Simulation terminated: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")

class SimulatedPacketContainer():
    def __init__(self,packet,simCommandReceiver,simTlmReceiver,row,simulationMessage):
        self.simPacket = SimulatedPacket(packet,simCommandReceiver,simTlmReceiver,row)
        self.transmitThread = QThread()
        self.simPacket.moveToThread(self.transmitThread)
        self.transmitThread.started.connect(self.simPacket.packetSenderThread)
        self.simPacket.messageSignal.connect(simulationMessage)
        self.transmitThread.start()