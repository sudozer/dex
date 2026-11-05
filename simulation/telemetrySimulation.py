import json
import pdb
import socket
import struct
from socket import socket as sock
import serialize
from autofill import Autofiller
import threading
import time

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
 
from loadConfig import cfgLoader, GLOBAL_CONFIG

from dataStructures import (
    PACKET_STRUCTURE_COMPONENTS,
    COMMAND_COMPONENTS,
    COMMAND_STRUCTURE_SIZES,
)
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

    def registerTrigger(self,behaviorCallback,simPair):
        onTlmArgs = simPair['trigger']['triggerArgs']
        structure,packet,component,field = onTlmArgs['telemetryField'].split('.')

        packetType = packet
        if 'packetIdField' not in GLOBAL_CONFIG['telemetryStructures'][structure]:
            packetType = structure

        packetComponents = PACKET_STRUCTURE_COMPONENTS[structure][packet]
        selectedField = next(
            fieldDefinition
            for packetComponent in packetComponents
            if packetComponent['component'] == component
            for fieldDefinition in packetComponent['fields']
            if fieldDefinition['fieldName'] == field
        )
        fieldKey = f"{selectedField['definitionSource']}__{field}"
        behaviorChange = lambda: behaviorCallback(simPair['behavior'])
        triggerLock = threading.Lock()
        triggered = False

        def triggerCallback():
            nonlocal triggered
            with triggerLock:
                if triggered:
                    return

                packetData = LIVETLM.mostRecentPacket.get(packetType)
                if packetData is None:
                    return

                fieldData = packetData.get(fieldKey)
                if fieldData is None:
                    return

                fieldValue = fieldData.get('convertedValue', fieldData.get('rawValue'))
                if fieldValue is None:
                    return

                triggerValue = onTlmArgs['value']
                if isinstance(fieldValue, (int, float)) and not isinstance(fieldValue, bool):
                    try:
                        triggerValue = int(triggerValue)
                    except (TypeError, ValueError):
                        try:
                            triggerValue = float(triggerValue)
                        except (TypeError, ValueError):
                            self.simulationMessageFunction.emit(
                                f"Invalid telemetry trigger value for {onTlmArgs['telemetryField']}: {triggerValue}",
                                "ERROR",
                            )
                            return

                comparator = onTlmArgs['comparator']
                if comparator == '>=':
                    conditionMet = fieldValue >= triggerValue
                elif comparator == '<=':
                    conditionMet = fieldValue <= triggerValue
                else:
                    conditionMet = fieldValue == triggerValue

                if conditionMet:
                    self.simulationMessageFunction(f"Telemetry check trigger activated: {onTlmArgs}","DEBUG")
                    behaviorChange()
                    triggered = True
                    LIVETLM.removeCallback(packetType, triggerCallback)

        LIVETLM.registerCallback(packetType, triggerCallback)

class SimCommandReceiver(CommandReceiver):
    def __init__(self,commandPort,commandProtocol,commandStructure,simulationMessageFunction):
        self.commandTriggerRegistry = {}
        self.triggerLock = threading.Lock()
        self.simulationMessageFunction = simulationMessageFunction
        self.commandLayouts = self.buildCommandLayouts(commandStructure)
        super().__init__(
            '127.0.0.1',
            commandPort,
            commandProtocol,
            commandStructure,
            simulationMessageFunction,
            self.checkCommandTriggers,
        )
        self.openListeningPort()
        if commandProtocol == 'UDP':
            self.listenerThread = threading.Thread(target=self.listenThread, daemon=True)
            self.listenerThread.start()
        self.simulationMessageFunction("Simulation listening for commands.","INFO")

    def stopListening(self):
        super().stopListening()
        if hasattr(self, 'listenerThread'):
            self.listenerThread.join()
        self.close()

    def registerTrigger(self,behaviorCallback,simPair):
        triggerArgs = simPair['trigger']['triggerArgs']
        triggerStructure = triggerArgs['structure']
        if triggerStructure != self.structure:
            self.simulationMessageFunction(
                f"Command trigger structure {triggerStructure} does not match simulation listener structure {self.structure}.",
                "ERROR",
            )
            return
        if not triggerArgs['commandList']:
            self.simulationMessageFunction(
                f"Command trigger for {triggerStructure} has no fields to compare.",
                "ERROR",
            )
            return

        trigger = {
            'commandList': triggerArgs['commandList'],
            'behaviorCallback': behaviorCallback,
            'behavior': simPair['behavior'],
        }
        availableFields = {
            (field['component'], field['fieldName'])
            for layout in self.commandLayouts
            for field in layout['fields']
        }
        missingFields = [
            condition['fieldName']
            for condition in trigger['commandList']
            if (condition.get('component'), condition['fieldName']) not in availableFields
            or 'value' not in condition
        ]
        if missingFields:
            self.simulationMessageFunction(
                f"Command trigger fields are not present in structure {triggerStructure}: {missingFields}",
                "ERROR",
            )
            return
        try:
            for condition in trigger['commandList']:
                self.parseCommandValue(condition)
        except (KeyError, OverflowError, TypeError, ValueError) as error:
            self.simulationMessageFunction(
                f"Invalid command trigger value for structure {triggerStructure}: {error}",
                "ERROR",
            )
            return

        with self.triggerLock:
            self.commandTriggerRegistry.setdefault(triggerStructure, []).append(trigger)

    def buildCommandLayouts(self, commandStructure):
        structureConfig = GLOBAL_CONFIG['commandStructures'][commandStructure]
        layouts = []
        staticComponents = COMMAND_COMPONENTS['static components']

        def appendComponentFields(fields, componentName):
            return [
                field | {'component': componentName}
                for field in fields
            ]

        headerFields = [
            field
            for componentName in structureConfig['headers']
            for field in appendComponentFields(
                staticComponents[componentName], componentName
            )
        ]
        footerFields = [
            field
            for componentName in structureConfig['footers']
            for field in appendComponentFields(
                staticComponents[componentName], componentName
            )
        ]
        commandDefinitions = COMMAND_COMPONENTS['command definitions'].get(
            structureConfig['packets'], {}
        )

        if commandDefinitions:
            for commandId, commandDefinition in commandDefinitions.items():
                commandFields = appendComponentFields(
                    commandDefinition.get('arguments', []), commandId
                )
                fields = headerFields + commandFields + footerFields
                layouts.append({
                    'commandId': commandId,
                    'fields': fields,
                    'size': COMMAND_STRUCTURE_SIZES[commandStructure][commandId],
                })
        else:
            fields = headerFields + footerFields
            layouts.append({
                'commandId': None,
                'fields': fields,
                'size': COMMAND_STRUCTURE_SIZES[commandStructure][commandStructure],
            })

        return layouts

    @staticmethod
    def decodeCommandFields(commandPacket, fields):
        packetBits = format(int.from_bytes(commandPacket, byteorder='big'), f'0{len(commandPacket) * 8}b')
        decodedFields = {}
        bitOffset = 0

        for field in fields:
            bitLength = field['bitLength']
            fieldBits = packetBits[bitOffset:bitOffset + bitLength]
            bitOffset += bitLength
            if not fieldBits:
                continue

            fieldType = field['type']
            if fieldType == 'float':
                value = struct.unpack('>f', int(fieldBits, 2).to_bytes(4, 'big'))[0]
            elif fieldType == 'double':
                value = struct.unpack('>d', int(fieldBits, 2).to_bytes(8, 'big'))[0]
            elif fieldType == 'char':
                value = chr(int(fieldBits, 2))
            else:
                value = int(fieldBits, 2)
                if fieldType.startswith('int') and not fieldType.startswith('uint'):
                    if value & (1 << (bitLength - 1)):
                        value -= 1 << bitLength

            decodedFields[(field['component'], field['fieldName'])] = value
        
        return decodedFields

    def commandMatchesTrigger(self, commandPacket, trigger):
        for layout in self.commandLayouts:
            if len(commandPacket) != layout['size']:
                continue

            decodedFields = self.decodeCommandFields(commandPacket, layout['fields'])
            if layout['commandId'] is not None:
                packetIdField = GLOBAL_CONFIG['commandStructures'][self.structure].get('packetIdField')
                if packetIdField is not None:
                    idField = COMMAND_COMPONENTS['static components'][
                        GLOBAL_CONFIG['commandStructures'][self.structure]['headers'][
                            packetIdField['componentIndex']
                        ]
                    ][packetIdField['fieldIndex']]
                    idFieldKey = (
                        GLOBAL_CONFIG['commandStructures'][self.structure]['headers'][
                            packetIdField['componentIndex']
                        ],
                        idField['fieldName'],
                    )
                    if decodedFields.get(idFieldKey) != int(layout['commandId']):
                        continue

            if all(
                (condition.get('component'), condition['fieldName']) in decodedFields
                and decodedFields[
                    (condition.get('component'), condition['fieldName'])
                ] == self.parseCommandValue(condition)
                for condition in trigger['commandList']
            ):
                return True

        return False

    def commandTriggerPacketIds(self, trigger):
        structureConfig = GLOBAL_CONFIG['commandStructures'][self.structure]
        packetIdField = structureConfig.get('packetIdField')
        if packetIdField is not None:
            headerComponent = structureConfig['headers'][packetIdField['componentIndex']]
            idField = COMMAND_COMPONENTS['static components'][headerComponent][
                packetIdField['fieldIndex']
            ]
            idFieldKey = (headerComponent, idField['fieldName'])
            idCondition = next(
                (
                    condition
                    for condition in trigger['commandList']
                    if (condition.get('component'), condition['fieldName']) == idFieldKey
                ),
                None,
            )
            if idCondition is not None:
                expectedId = self.parseCommandValue(idCondition)
                return {
                    layout['commandId']
                    for layout in self.commandLayouts
                    if layout['commandId'] is not None
                    and int(layout['commandId']) == expectedId
                }

        targetedPacketIds = {
            str(layout['commandId'])
            for layout in self.commandLayouts
            if layout['commandId'] is not None
            and any(
                condition.get('component') == str(layout['commandId'])
                and (condition.get('component'), condition['fieldName'])
                in {
                    (field['component'], field['fieldName'])
                    for field in layout['fields']
                }
                for condition in trigger['commandList']
            )
        }
        if targetedPacketIds:
            return targetedPacketIds

        return {layout['commandId'] for layout in self.commandLayouts}

    def identifyCommandPacket(self, commandPacket):
        matchingSizeLayouts = [
            layout
            for layout in self.commandLayouts
            if len(commandPacket) == layout['size']
        ]
        if not matchingSizeLayouts:
            return None, {}, None

        structureConfig = GLOBAL_CONFIG['commandStructures'][self.structure]
        packetIdField = structureConfig.get('packetIdField')
        if packetIdField is None:
            if len(matchingSizeLayouts) == 1:
                layout = matchingSizeLayouts[0]
                return layout, self.decodeCommandFields(commandPacket, layout['fields']), None
            return None, {}, None

        headerComponent = structureConfig['headers'][packetIdField['componentIndex']]
        idField = COMMAND_COMPONENTS['static components'][headerComponent][
            packetIdField['fieldIndex']
        ]
        idFieldKey = (headerComponent, idField['fieldName'])
        decodedFields = self.decodeCommandFields(
            commandPacket, matchingSizeLayouts[0]['fields']
        )
        receivedPacketId = decodedFields.get(idFieldKey)
        for layout in matchingSizeLayouts:
            if (
                layout['commandId'] is not None
                and receivedPacketId == int(layout['commandId'])
            ):
                return layout, decodedFields, receivedPacketId

        return None, decodedFields, receivedPacketId

    def commandTriggerDifferences(self, decodedFields, trigger):
        differences = []
        for condition in trigger['commandList']:
            fieldKey = (condition.get('component'), condition['fieldName'])
            expectedValue = self.parseCommandValue(condition)
            receivedValue = decodedFields.get(fieldKey)
            if fieldKey not in decodedFields or receivedValue != expectedValue:
                differences.append(
                    f"{fieldKey[0]}.{fieldKey[1]}: received {receivedValue!r}, "
                    f"expected {expectedValue!r}"
                )
        return differences

    @staticmethod
    def parseCommandValue(field):
        value = field['value']
        fieldType = field['type']
        if fieldType == 'float':
            return struct.unpack('>f', struct.pack('>f', float(value)))[0]
        if fieldType == 'double':
            return struct.unpack('>d', struct.pack('>d', float(value)))[0]
        if fieldType == 'char':
            return str(value)
        return int(value)

    def checkCommandTriggers(self, commandPacket):
        with self.triggerLock:
            triggers = tuple(self.commandTriggerRegistry.get(self.structure, ()))

        if not triggers:
            self.simulationMessageFunction(
                f"WARNING: Received command for structure '{self.structure}', but no "
                f"command triggers are stored for that structure.",
                "WARNING",
            )
            return

        layout, decodedFields, receivedPacketId = self.identifyCommandPacket(commandPacket)
        if layout is None:
            if receivedPacketId is not None:
                self.simulationMessageFunction(
                    f"WARNING: Received command for structure '{self.structure}' with "
                    f"packet ID {receivedPacketId}, but no matching command packet "
                    f"layout exists (packet size: {len(commandPacket)} bytes).",
                    "WARNING",
                )
            else:
                self.simulationMessageFunction(
                    f"WARNING: Received command for structure '{self.structure}' with "
                    f"an unrecognized packet size ({len(commandPacket)} bytes); no "
                    f"stored command trigger can match it.",
                    "WARNING",
                )
            return

        packetTriggers = tuple(
            trigger
            for trigger in triggers
            if layout['commandId'] in self.commandTriggerPacketIds(trigger)
        )
        if not packetTriggers:
            storedPacketIds = sorted(
                {
                    str(packetId)
                    for trigger in triggers
                    for packetId in self.commandTriggerPacketIds(trigger)
                    if packetId is not None
                }
            )
            self.simulationMessageFunction(
                f"WARNING: Received command for structure '{self.structure}' with "
                f"packet ID '{layout['commandId']}', but no command triggers are "
                f"stored for that packet ID. Stored trigger packet IDs: "
                f"{storedPacketIds or 'none'}.",
                "WARNING",
            )
            return

        triggered = []
        for trigger in packetTriggers:
            if self.commandMatchesTrigger(commandPacket, trigger):
                trigger['behaviorCallback'](trigger['behavior'])
                triggered.append(trigger)

        if triggered:
            with self.triggerLock:
                registeredTriggers = self.commandTriggerRegistry.get(self.structure, [])
                for trigger in triggered:
                    if trigger in registeredTriggers:
                        registeredTriggers.remove(trigger)
        else:
            differences = [
                self.commandTriggerDifferences(decodedFields, trigger)
                for trigger in packetTriggers
            ]
            closestDifferences = min(differences, key=len)
            self.simulationMessageFunction(
                f"WARNING: Received command for structure '{self.structure}' with "
                f"packet ID '{layout['commandId']}' does not match its stored trigger "
                f"conditions. Closest field differences: "
                f"{'; '.join(closestDifferences) or 'no differing fields identified'}.",
                "WARNING",
            )

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
        self.simulatedPacket.simulationMessageFunction.emit(f"Initializing field simulation for {self.component}.{self.fieldDict['fieldName']}","DEBUG")
        self.initReturn()
        self.registerTriggers()
        self.valueList = []

    def initReturn(self):       
        #first enabled field behavior initial condition gets set
        for simPair in self.fieldSimulationDict:
            if simPair['trigger']['triggerType'] == "Initial Condition" and simPair['enabled']:
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
            self.changeBehavior({"behaviorType":"Hold Static Value","behaviorArgs":{"value":self.fieldDict['defaultValue']}})
            return

        #init to a default value
        if self.fieldDict['type'] == 'char':
            self.changeBehavior({"behaviorType":"Hold Static Value","behaviorArgs":{"value":'0'}})
        else:
            self.changeBehavior({"behaviorType":"Hold Static Value","behaviorArgs":{"value":0}})

    def changeBehavior(self,behaviorDict):
        self.simulatedPacket.simulationMessageFunction.emit(f"Changing behavior of {self.component}.{self.fieldDict['fieldName']} to {behaviorDict}","Info")
        self.currentBehavior = behaviorDict
        if self.currentBehavior['behaviorType'] == "Hold Static Value":
            match self.fieldDict['type']:
                case 'char':
                    val = str(self.currentBehavior['behaviorArgs']['value'])
                case 'float' | 'double':
                    val = float(self.currentBehavior['behaviorArgs']['value'])
                case _:
                    val = int(self.currentBehavior['behaviorArgs']['value'])
            self.behaviorGenerator = behaviorStaticValue(val)

        if self.currentBehavior['behaviorType'] == "Ramp To":
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
        try:
            valDict = self.buildValue()
        except Exception as E:
            self.simulatedPacket.simulationMessageFunction.emit(f"Unable to build simulated value:\n{self.fieldDict}\nError:\n{E}","ERROR")
        return self.fieldDict | valDict
    
    def registerTriggers(self):
        for simPair in self.fieldSimulationDict:
            if simPair['enabled']:
                if simPair['trigger']['triggerType'] == "On Telemetry Value":
                    self.simulatedPacket.telemetryReceiver.registerTrigger(self.changeBehavior,simPair)
                if simPair['trigger']['triggerType'] == "On Command Received":
                    self.simulatedPacket.commandReceiver.registerTrigger(self.changeBehavior,simPair)
        for simPair in self.packetBehaviors:
            if (
                simPair['enabled']
                and simPair['trigger']['triggerType'] == "On Command Received"
            ):
                self.simulatedPacket.commandReceiver.registerTrigger(
                    self.changeBehavior,simPair
                )

class SimulatedPacket(QObject):
    messageSignal = Signal(str,str)
    def __init__(self, simDict, commandReceiver, telemetryReceiver,row,simulationMessage):
        super().__init__()
        self.messageSignal.connect(
            simulationMessage, Qt.ConnectionType.QueuedConnection
        )
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
                                         field,
                                         self.simDict['packetConfig'],
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
            idField.changeBehavior({'behaviorType':"Hold Static Value",'behaviorArgs':{'value':idVal}})

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
        try:
            currentPacket = self.buildPacket()
            self.simulationMessageFunction.emit(f"Launching simulation thread of structure: {self.simDict['packetConfig']['structure']} packet:{self.simDict['packetConfig']['packet']}","INFO")
            while not self.stopped.wait(1):
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
                    dwellPeriod = nextTime - time.time()
                    if dwellPeriod > 0:
                        self.stopped.wait(dwellPeriod)
                    else:
                        self.simulationMessageFunction.emit(f"Simulation falling behind: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']} ","ERROR")
                        nextTime = time.time()
            self.simulationMessageFunction.emit(f"Simulation thread completed: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")
        finally:
            self.telemetryTransmitter.close()
            if self.thread() is not None:
                self.thread().quit()

    def pause(self):
        self.paused.set()
        self.simulationMessageFunction.emit(f"Simulation paused: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")
    
    def resume(self):
        self.paused.clear()
        self.simulationMessageFunction.emit(f"Simulation resuming: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")

    def stop(self):
        self.stopped.set()
        self.simulationMessageFunction.emit(f"Simulation terminated: {self.simDict['packetConfig']['structure']}::{self.simDict['packetConfig']['packet']}","INFO")

class SimulatedPacketContainer():
    def __init__(self,packet,simCommandReceiver,simTlmReceiver,row,simulationMessage):
        self.simPacket = SimulatedPacket(
            packet,simCommandReceiver,simTlmReceiver,row,simulationMessage
        )
        self.transmitThread = QThread()
        self.simPacket.moveToThread(self.transmitThread)
        self.transmitThread.started.connect(self.simPacket.packetSenderThread)
        self.transmitThread.start()