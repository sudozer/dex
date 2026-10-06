import json
import pdb

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from dataStructures import PACKET_STRUCTURE_COMPONENTS, COMMAND_COMPONENTS
from liveTelemetry import live_telemetry as LIVETLM


class SimTelemetryReceiver():
    def __init__(self,simulationMessageFunction):
        self.simulationMessageFunction = simulationMessageFunction
        self.telemetryTriggerRegistry = {}

class SimCommandReceiver():
    def __init__(self,commandPort,commandProtocol,simulationMessageFunction):
        self.commandPort = commandPort
        self.commandProtocol = commandProtocol
        self.simulationMessageFunction = simulationMessageFunction
        self.commandTriggerRegistry = {}

class Field():
    def __init__(self,component,fieldName,simulationDict = None):
        self.component = component
        self.fieldName = fieldName
        self.simulationDict = simulationDict

    def register(self):
        pass

class SimulatedPacket():
    def __init__(self, simDict, commandReceiver, telemetryReceiver, simulationMessageFunction):
        self.fields=[]
        self.commandReceiver = commandReceiver
        self.telemetryReceiver = telemetryReceiver
        self.simulationMessageFunction = simulationMessageFunction


