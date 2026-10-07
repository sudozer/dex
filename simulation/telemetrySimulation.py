import json
import pdb
import socket
from socket import socket as sock
import serialize
 
from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from dataStructures import PACKET_STRUCTURE_COMPONENTS, COMMAND_COMPONENTS
from liveTelemetry import live_telemetry as LIVETLM
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

        if self.packetConfig['protocol'] == 'TCP Client':
            pass

        if self.packetConfig['protocol'] == 'TCP Server':
            pass

    def sendUDP(self,packet):
        self.sendTo(packet,self.destinationTuple)

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
    def __init__(self,component,fieldDict,packetConfig,packetBehaviors,initialConditions,fieldSimulationDict):
        self.component = component
        self.fieldDict = fieldDict
        self.packetConfig = packetConfig
        self.packetBehaviors = packetBehaviors
        self.initialConditions = initialConditions
        self.fieldSimulationDict = fieldSimulationDict
        self.transmitter = SimTelemetryTransmitter(packetConfig,simulationMessageFunction)
        self.prevValue = fieldDict.get('defaultValue',0)
        self.initReturn()

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

        self.changeBehavior({"behaviorType":"Static Value","behaviorArgs":{"value":0}})

    def changeBehavior(self,behaviorDict):
        self.currentBehavior = behaviorDict
        if self.currentBehavior['behaviorType'] == "Static Value":
            self.behaviorGenerator = behaviorStaticValue(self.currentBehavior['behaviorArgs']['value'])

        if self.currentBehavior['behaviorType'] == "Ramp Value":
            self.behaviorGenerator = behaviorRampValue(self.currentBehavior['behaviorArgs'],self.prevValue,self.packetConfig['simulationRate'])

        if self.currentBehavior['behaviorType'] == "Playback From Telemetry":
            self.behaviorGenerator = behaviorPlayBackTelemetry(self.fieldDict,self.currentBehavior['behaviorArgs']['playbackDatabase'],self.currentBehavior['behaviorArgs']['playbackTime'])

    def returnValue(self):
        self.prevValue = self.fieldDict['value']
        self.fieldDict['value'] = next(self.behaviorGenerator)
        self.fieldDict['rawBits'],self.fieldDict['rawBytes'] = serialize.returnBitstring(self.fieldDict)
        return self.fieldDict    
    
    def registerTriggers(self):
        pass

class SimulatedPacket():
    def __init__(self, simDict, commandReceiver, telemetryReceiver, simulationMessageFunction):
        self.fields=[]
        self.simDict = simDict
        self.commandReceiver = commandReceiver
        self.telemetryReceiver = telemetryReceiver
        self.simulationMessageFunction = simulationMessageFunction
        self.packetTemplate = PACKET_STRUCTURE_COMPONENTS[simDict['packetConfig']['structure']][simDict['packetConfig']['packetId']]
        self.telemetryTransmitter = SimTelemetryTransmitter(simDict['packetConfig'],simulationMessageFunction)
        self.buildFieldList()
        self.buildPacketList()
    def buildFieldList(self):
        for component in self.packetTemplate:
            componentName = component['component']
            for field in component['fields']:
                self.fields.append(Field(component['component'],
                                         field,self.simDict['packetConfig'],
                                         self.simDict['packetBehaviors'],
                                         self.simDict['initialConditions'],
                                         self.simDict['fieldBehaviors'].get(componentName,{}).get(field['fieldName'])))

    def buildPacket(self):
        packetList = []
        for field in self.fields:
            field.returnValue()
            packetList.append(field)
        return packetList
    
    def packPacket(self,packet):
        bitString = ''
        for field in packet:
            bitString = bitString + field['rawBits']
        #TODO packet must be a whole number of bytes
        packetBytes = int(bitString, 2).to_bytes(len(bitString)//8, byteorder="big")
        return packetBytes

    def pause(self):
        pass
    def resume(self):
        pass
    def stop(self):
        pass


