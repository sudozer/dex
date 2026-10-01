from pathlib import Path
import pdb
import json
import os
import copy
import csv
import logging

from PySide6.QtGui import QColor #for colors
from PySide6.QtCore import QFile, Qt, QDateTime, QTimeZone
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, 
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QHeaderView,
    QDialog,
    QWidget,
    QHBoxLayout,
    QFileDialog,
    QTreeWidget,
    QListWidgetItem,
    QTreeWidgetItem,
    QTableWidget,
    QLineEdit,
    QTableWidgetItem,
    QPushButton,
    QAbstractSpinBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QDateTimeEdit
)
from qt_material import apply_stylesheet

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig
STARTING_CONFIG = CONFIG() #for when it's not necessary to reload the whole config

from packetDefinitionLib import PacketDefinitionUtility
from decode import Decoder
from dataStructures import PACKET_TEMPLATES, COMMAND_COMPONENTS, PACKET_STRUCTURES,PACKET_STRUCTURE_COMPONENTS

from packetDefinitionEditor import PacketDefinitionEditor
from telemetrySelector import TelemetryFieldSelector
from commandBuilder import CommandBuilder
from commandIDSelector import CommandIDSelector
from txCommand import TCPCommandSocket, UDPCommandSocket

# Colors
COMMAND_HEADER = QColor(132,197,227)
COMMAND_STRUCTURE = QColor(250,212,117)
COMMAND_STRUCTURE_BASE = (217,100,220) #this is correctly not set as a color

MESSAGE_ERROR = QColor(250,123,12)
MESSAGE_WARNING = QColor(247,239,74)

def colorGen(baseColor, hueStep=35):
    while True:
        yield QColor.fromHsv(*baseColor)
        baseColor = ((baseColor[0] + hueStep) % 360, baseColor[1], baseColor[2])

"""
Simulation classes
"""

class PacketBehavior(QTableWidgetItem):
    """
    list item of the whole packet playback behavior table
    """
    def __init__(self, parent,behaviorWidget,row):
        super().__init__()
        self.parentTable = parent
        self.behaviorWidget = behaviorWidget
        self.triggerComboBox = QComboBox()
        self.triggerComboBox.addItems(['Initial Condition','On Telemetry Value','On Command Received'])
        self.triggerComboBox.currentTextChanged.connect(self.triggerChanged)
        self.playbackTimeField = QDateTimeEdit()
        self.playbackTimeField.setCalendarPopup(True)
        self.playbackTimeField.setTimeZone(QTimeZone.UTC)
        self.playbackTimeField.setDisplayFormat(STARTING_CONFIG['qtDateFormat'])
        self.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        self.setCheckState(Qt.CheckState.Checked)

        self.parentTable.insertRow(row)
        self.parentTable.setItem(row, 0, self)
        self.parentTable.setCellWidget(self.row(),1,self.triggerComboBox)
        self.parentTable.setCellWidget(self.row(),3,self.playbackTimeField)

    def triggerChanged(self, newTrigger):
        if newTrigger == 'Initial Condition':
            self.parentTable.setItem(self.row(),3,QTableWidgetItem("N/A"))

        if newTrigger == 'On Telemetry Value':
            container = QWidget()
            cell_layout = QHBoxLayout(container)
        
            # Configure layout margins to fit nicely inside the cell
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(6)

            self.telemetryFieldButton = QPushButton("Telemetry Field")
            self.telemetryFieldButton.clicked.connect(self.selectTelemetryField)
            self.telemetryValue = QLineEdit()
            self.telemetryValue.setPlaceholderText("Value")

            cell_layout.addWidget(self.telemetryFieldButton)
            cell_layout.addWidget(self.telemetryValue)
            self.parentTable.setCellWidget(self.row(),2,container)

        if newTrigger == 'On Command Received':

            self.commandSelectButton = QPushButton("Command")
            self.commandSelectButton.clicked.connect(self.selectCommand)
            self.parentTable.setCellWidget(self.row(),2,self.commandSelectButton)

    def selectTelemetryField(self):
        selector = TelemetryFieldSelector()
        if selector.exec() == QDialog.Accepted:
            self.onTelemetryField = selector.selectedField
            self.onTelemetryPacket = selector.selectedPacket
            self.telemetryFieldButton.setText(f"{self.onTelemetryPacket}.{self.onTelemetryField}")

    def selectCommand(self):

        structureName = self.behaviorWidget.dexMainWidget.ui.simulationCommandStructureBox.currentText()
        structure = CONFIG()['commandStructures'][structureName]
        commandBuilder = CommandBuilder(structure,True)
        if commandBuilder.exec() == QDialog.Accepted:
            self.commandDict = {'structure':commandBuilder.commandStructure, 'commandList':commandBuilder.commandList}


    def loadInitialBehavior(self):
        pass

    def writeSimConfig(self):
        self.packetSimConfig = False
        packetSimConfig = {"trigger":{"triggerType":self.triggerComboBox.currentText(),"triggerArgs":{}},"behavior":{"behaviorType":"playback from telemetry","behaviorArgs":{}}}
        #write trigger args
        triggerArgs = packetSimConfig['trigger']['triggerArgs']
        match packetSimConfig['trigger']['triggerType']:
            case "Initial Condition":
                #no trigger arguments needed
                pass
            case "On Telemetry Value":
                #TODO validate that value matches telemetry Field type
                triggerArgs={"telemetryField":self.telemetryFieldButton.text(),"value":self.telemetryValue.text()}
            
            case "On Command Received":
                triggerArgs = {"commandList":self.commandList}


        packetSimConfig['behavior']['behaviorArgs'] = {"playbackTime":self.playbackTimeField.dateTime().toString(STARTING_CONFIG['qtDateFormat'])}
        self.packetSimConfig = packetSimConfig
        return packetSimConfig

class FieldItem(QTreeWidgetItem):
    """
    tree item of a single field in the fieldwise simulation tree
    """
    def __init__(self, parent,componentName, fieldName, fieldDict, initConfig, behaviorsWidget):
        self.fieldBehaviors = []
        self.behaviorsWidget = behaviorsWidget
        super().__init__(parent)
        self.parentTree = parent
        self.setText(0, f"{fieldName}")
        self.fieldName = fieldName
        self.componentName = componentName
        self.fieldDict = fieldDict
        self.addBehaviorButton = QPushButton("Add Behavior")
        self.removeBehaviorButton = QPushButton("Remove Behavior")
        self.addBehaviorButton.clicked.connect(self.addBehavior)
        self.removeBehaviorButton.clicked.connect(self.removeBehavior)
        parent.setItemWidget(self,1,self.addBehaviorButton)
        parent.setItemWidget(self,2,self.removeBehaviorButton)
        if len(initConfig) > 0:
            self.setInitConfigs(initConfig)

    def setInitConfigs(self,initConfig):
        for fieldBehavior in initConfig:
            self.fieldBehaviors.append(FieldBehavior(self,self.fieldName,fieldBehavior))

        self.setExpanded(True)

    def addBehavior(self):
        self.fieldBehaviors.append(FieldBehavior(self,self.fieldName))
        self.setExpanded(True)

    def removeBehavior(self):
        #remove the currently selected behavior
        removeItem = self.behaviorsWidget.removeBehavior
        if not removeItem.parent() == self:
            return
        self.removeChild(removeItem)
        self.fieldBehaviors.remove(removeItem)

class FieldBehavior(QTreeWidgetItem):
    """
    child item of a single field behavior in the fieldwise simulation tree
    """
    def __init__(self, parent,fieldName, initBehavior=None):
        super().__init__(parent)
        self.parentItem = parent
        self.fieldName = fieldName
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(0, Qt.CheckState.Checked)

        self.triggerComboBox = QComboBox()
        self.triggerComboBox.addItems(['Initial Condition','On Telemetry Value','On Command Received'])
        self.behaviorComboBox = QComboBox()
        self.behaviorComboBox.addItems(['Hold Static Value','Ramp To','Playback From Telemetry'])

        self.triggerComboBox.currentTextChanged.connect(self.triggerChanged)
        self.behaviorComboBox.currentTextChanged.connect(self.behaviorChanged)
        
        parent.parentTree.setItemWidget(self,1,self.triggerComboBox)
        self.setText(2,"N/A")

        self.behaviorParamsValue = QLineEdit()
        self.behaviorParamsValue.setPlaceholderText("Value")
        parent.parentTree.setItemWidget(self,4,self.behaviorParamsValue)
        parent.parentTree.setItemWidget(self,3,self.behaviorComboBox)
        if not initBehavior is None:
            self.populateInitBehavior(initBehavior)

    def populateInitBehavior(self,initBehavior):
        self.setCheckState(0,Qt.CheckState.Unchecked) 
        if initBehavior['enabled']:
            self.setCheckState(0,Qt.CheckState.Checked) 

        
        idx = self.triggerComboBox.findText(initBehavior['trigger']['triggerType'])
        self.triggerComboBox.setCurrentIndex(idx)
        idx = self.behaviorComboBox.findText(initBehavior['behavior']['behaviorType'])
        self.behaviorComboBox.setCurrentIndex(idx)
        
        triggerArgs = initBehavior['trigger']['triggerArgs']
        behaviorArgs = initBehavior['behavior']['behaviorArgs']
        match self.triggerComboBox.currentText():
            case "Initial Condition":
                #no trigger arguments needed
                pass

            case "On Telemetry Value":
                #triggerArgs={"telemetryField":self.telemetryFieldButton.text(),"value":self.telemetryValue.text()}
                self.telemetryFieldButton.setText(triggerArgs['telemetryField'])
                self.telemetryValue.setText(triggerArgs['value'])
            case "On Command Received":
                #triggerArgs = {"commandList":self.commandList}
                self.commandDict = triggerArgs['commandDict']
        
        match self.behaviorComboBox.currentText():
            case "Hold Static Value":
                #behaviorArgs = {'value':self.behaviorParamsValue.text()}
                self.behaviorParamsValue.setText(behaviorArgs['value'])
            case "Ramp To":
                #behaviorArgs = {'value':self.behaviorRampValue.text(),"rampSeconds":self.behaviorRampSeconds.text(),"rampType":self.behaviorRampType.currentText()}
                self.behaviorRampValue.setText(behaviorArgs['value'])
                self.behaviorRampSeconds.setText(behaviorArgs['rampSeconds'])
                idx = self.behaviorRampType.findText(behaviorArgs['rampType'])
                self.behaviorRampType.setCurrentIndex(idx)

            case "Playback From Telemetry":
                #behaviorArgs = {"playbackTime":self.behaviorPlaybackTime.dateTime().toString(STARTING_CONFIG['qtDateFormat'])}
                qDate = QDateTime.fromString(behaviorArgs['playbackTime'],STARTING_CONFIG['qtDateFormat'])
                qDate.setTimeZone(QTimeZone.utc())
                self.behaviorPlaybackTime.setDateTime(qDate)

    def triggerChanged(self, newTrigger):
        self.setText(2,"")

        if newTrigger == 'Initial Condition':
            self.setText(2,"N/A")

        if newTrigger == 'On Telemetry Value':
            self.setText(2,"")
            container = QWidget()
            cell_layout = QHBoxLayout(container)
        
            # Configure layout margins to fit nicely inside the cell
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(6)

            self.telemetryFieldButton = QPushButton("Telemetry Field")
            self.telemetryFieldButton.clicked.connect(self.selectTelemetryField)
            self.telemetryValue = QLineEdit()
            self.telemetryValue.setPlaceholderText("Value")

            cell_layout.addWidget(self.telemetryFieldButton)
            cell_layout.addWidget(self.telemetryValue)
            self.parentItem.parentTree.setItemWidget(self,2,container)

        if newTrigger == 'On Command Received':

            self.commandSelectButton = QPushButton("Command")
            self.commandSelectButton.clicked.connect(self.selectCommand)
            self.parentItem.parentTree.setItemWidget(self,2,self.commandSelectButton)

    def behaviorChanged(self, newBehavior):
        #['hold static value','playback from telemetry','ramp to','pseudorandom noise around']
        if newBehavior == 'Hold Static Value':
            self.behaviorParamsValue = QLineEdit()
            self.behaviorParamsValue.setPlaceholderText("Value")
            self.parentItem.parentTree.setItemWidget(self,4,self.behaviorParamsValue)

        if newBehavior == 'Playback From Telemetry':
            self.behaviorPlaybackTime = QDateTimeEdit()
            self.behaviorPlaybackTime.setCalendarPopup(True)
            self.behaviorPlaybackTime.setTimeZone(QTimeZone.UTC)
            self.behaviorPlaybackTime.setDisplayFormat(STARTING_CONFIG['qtDateFormat'])
            self.parentItem.parentTree.setItemWidget(self,4,self.behaviorPlaybackTime)

        if newBehavior == 'Ramp To':
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(6)
            self.behaviorRampValue = QLineEdit()
            self.behaviorRampValue.setPlaceholderText("Final Value")
            self.behaviorRampSeconds = QLineEdit()
            self.behaviorRampSeconds.setPlaceholderText("Ramp Time (s)")
            self.behaviorRampType = QComboBox()
            self.behaviorRampType.addItems(['Linear','Asymtotic'])
            layout.addWidget(self.behaviorRampValue)
            layout.addWidget(self.behaviorRampSeconds)
            layout.addWidget(self.behaviorRampType)
            self.parentItem.parentTree.setItemWidget(self,4,container)

    def selectTelemetryField(self):
        selector = TelemetryFieldSelector()
        if selector.exec() == QDialog.Accepted:
            self.onTelemetryField = selector.selectedField
            self.onTelemetryPacket = selector.selectedPacket
            self.telemetryFieldButton.setText(f"{self.onTelemetryPacket}.{self.onTelemetryField}")
    
    def selectCommand(self):

        structureName = self.parentItem.behaviorsWidget.dexMainWidget.ui.simulationCommandStructureBox.currentText()
        structure = CONFIG()['commandStructures'][structureName]
        commandBuilder = CommandBuilder(structure,True)
        if commandBuilder.exec() == QDialog.Accepted:
            self.commandDict = {'structure':commandBuilder.commandStructure,'commandList':commandBuilder.commandList}

        

    def writeSimConfig(self):

        self.fieldSimConfig = False
        #write trigger args
        match self.triggerComboBox.currentText():
            case "Initial Condition":
                #no trigger arguments needed
                triggerArgs = {}

            case "On Telemetry Value":
                triggerArgs={"telemetryField":self.telemetryFieldButton.text(),"value":self.telemetryValue.text()}
            
            case "On Command Received":
                relevantCmdList = []
                for field in self.commandDict['commandList']:
                    if field['relevant']:
                        relevantCmdList.append(field)
                triggerArgs = {"structure":self.commandDict['structure'],"commandList":relevantCmdList}
        
        match self.behaviorComboBox.currentText():
            case "Hold Static Value":
                behaviorArgs = {'value':self.behaviorParamsValue.text()}

            case "Ramp To":
                behaviorArgs = {'value':self.behaviorRampValue.text(),"rampSeconds":self.behaviorRampSeconds.text(),"rampType":self.behaviorRampType.currentText()}

            case "Playback From Telemetry":
                behaviorArgs = {"playbackTime":self.behaviorPlaybackTime.dateTime().toString(STARTING_CONFIG['qtDateFormat'])}
        
        fieldSimConfig={'trigger':{'triggerType':self.triggerComboBox.currentText(),'triggerArgs':triggerArgs},"behavior":{"behaviorType":self.behaviorComboBox.currentText(),"behaviorArgs":behaviorArgs}}
        fieldSimConfig['enabled'] = True if self.checkState(0) == Qt.Checked else False
        if self.validateFieldSimConfig(fieldSimConfig):
            self.fieldSimConfig = fieldSimConfig
        return fieldSimConfig

    def validateFieldSimConfig(self,fieldSimComfig):
        #TODO validate the sim config
        return True

class PacketSelector(QDialog):

    def __init__(self):

        super().__init__()
            # Open the .ui file
        self.guiPath = cfgLoader.getPath('apps/main/ui/packetSelector.ui')
        ui_file = QFile(self.guiPath)
        if not ui_file.open(QFile.ReadOnly):
            raise RuntimeError(f"Cannot open file: {ui_file.errorString()}")

        # Load widgets into this dialog
        loader = QUiLoader()
        self.ui = loader.load(ui_file, self)
        ui_file.close()
        # Set up layout to display the loaded form
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.addWidget(self.ui)
        self.setLayout(layout)
        self.setModal(True)
        self.populateStructures()
        self.populatePackets()

        self.ui.structureBox.currentTextChanged.connect(self.populatePackets)
        self.ui.okButton.clicked.connect(self.accept)
        self.show()

    def populateStructures(self):
        self.ui.structureBox.clear()
        for structure in PACKET_STRUCTURE_COMPONENTS:
            self.ui.structureBox.addItem(structure)
        
    def populatePackets(self):
        self.ui.packetBox.clear()
        packets = PACKET_STRUCTURE_COMPONENTS[self.ui.structureBox.currentText()]
        for packet in packets:
            self.ui.packetBox.addItem(packet)

class SimBehaviorWidget(QDialog):
    def __init__(self,parentTree,simItem,packetList,dexMain):
        self.parentTree = parentTree
        self.packetName = simItem.packet
        self.telemetryStructure = simItem.structure
        self.packetList = packetList
        self.dexMainWidget = dexMain
        self.row = self.parentTree.indexOfTopLevelItem(simItem)
        super().__init__()
            # Open the .ui file
        self.guiPath = cfgLoader.getPath('apps/main/ui/simBehaviorEditor.ui')
        ui_file = QFile(self.guiPath)
        if not ui_file.open(QFile.ReadOnly):
            raise RuntimeError(f"Cannot open file: {ui_file.errorString()}")

        # Load widgets into this dialog
        loader = QUiLoader()
        self.loaded_widget = loader.load(ui_file, self)
        ui_file.close()
        self.simParameterDict = CONFIG()['simulation'][self.row]

        # Set up layout to display the loaded form
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.addWidget(self.loaded_widget)
        self.setLayout(layout)
        self.setModal(True)
        
        self.setWindowTitle(f"{self.packetName} Simulation Behaviors")

        self.loaded_widget.fieldwiseBehaviorTree.setColumnCount(5)
        self.loaded_widget.fieldwiseBehaviorTree.setHeaderLabels(['Enabled','Trigger Type','Trigger Parameters','Behavior Type','Behavior Parameters'])
        for column in range(self.loaded_widget.fieldwiseBehaviorTree.columnCount()):
            self.loaded_widget.fieldwiseBehaviorTree.resizeColumnToContents(column)
        self.loaded_widget.fieldwiseBehaviorTree.setIndentation(0)
        self.loaded_widget.wholePacketPlaybackTable.setColumnCount(4)
        self.loaded_widget.wholePacketPlaybackTable.setHorizontalHeaderLabels(['enabled','Trigger Type','Trigger Parameters','Playback Start'])
        self.loaded_widget.wholePacketPlaybackTable.verticalHeader().setVisible(False)
        self.loaded_widget.wholePacketPlaybackTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.loaded_widget.wholePacketPlaybackTable.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)

        self.loaded_widget.addPlaybackTriggerButton.clicked.connect(self.addPacketPlaybackTrigger)
        self.loaded_widget.removePlaybackTriggerButton.clicked.connect(self.removePacketPlaybackTrigger)
        self.loaded_widget.okButton.clicked.connect(self.writeSimulationConfig)
        self.loaded_widget.fieldwiseBehaviorTree.itemSelectionChanged.connect(self.setRemoveBehaviorItem)

        self.packetSimItems = []
        self.fieldSimItems = []

        self.populateFields()
        self.populatePacketPlaybacks()
        self.show()

    def populateFields(self):
        #populate field list
        for component in self.packetList:
            componentName = component['component']
            for field in component['fields']:
                fieldName = field['fieldName']
                if fieldName in self.simParameterDict['fieldBehaviors'][componentName]:
                    initConfig = self.simParameterDict['fieldBehaviors'][componentName][fieldName]
                else:
                    initConfig = []
                self.fieldSimItems.append(FieldItem(self.loaded_widget.fieldwiseBehaviorTree,componentName,fieldName,field,initConfig,self))

    def populatePacketPlaybacks(self):
        pass

    def addPacketPlaybackTrigger(self):
        #add a new row to the packet playback table
        if self.loaded_widget.wholePacketPlaybackTable.selectedItems():
            selectedItem = self.loaded_widget.wholePacketPlaybackTable.selectedItems()[0]
            row = selectedItem.row() + 1
        else:
            row = self.loaded_widget.wholePacketPlaybackTable.rowCount()
        self.packetSimItems.insert(row,PacketBehavior(self.loaded_widget.wholePacketPlaybackTable,self,row))


    def removePacketPlaybackTrigger(self):
        #remove the currently selected row from the packet playback table

        selectedItem = self.loaded_widget.wholePacketPlaybackTable.currentItem()
        if not selectedItem == None:
            row = selectedItem.row()
            self.loaded_widget.wholePacketPlaybackTable.removeRow(row)
            del self.packetSimItems[row]

    def setRemoveBehaviorItem(self):
        if isinstance(self.loaded_widget.fieldwiseBehaviorTree.currentItem().parent(),FieldItem):
            self.removeBehavior = self.loaded_widget.fieldwiseBehaviorTree.currentItem()
    
    def writeSimulationConfig(self):
        self.packetBehaviors = []
        self.fieldBehaviors = {}
        for comp in PACKET_STRUCTURE_COMPONENTS[self.telemetryStructure][self.packetName]:
            self.fieldBehaviors[comp['component']] = {}
        
        for packetBehavior in self.packetSimItems:
            self.packetBehaviors.append(packetBehavior.writeSimConfig())
    
        for field in self.fieldSimItems:
            if len(field.fieldBehaviors) > 0:
                self.fieldBehaviors[field.componentName][field.fieldName]=[i.writeSimConfig() for i in field.fieldBehaviors]

        self.accept()
        pass

class SimPacket(QTreeWidgetItem):
    def __init__(self, parentWidget, dexMain, structure, packet, initConfig = None):
        self.dexMainWidget = dexMain
        super().__init__(parentWidget)

        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(0, Qt.CheckState.Checked)
        self.packetBehaviors = []
        self.fieldBehaviors = {}
        for comp in PACKET_STRUCTURE_COMPONENTS[structure][packet]:
            self.fieldBehaviors[comp['component']] = {}
        self.structure = structure
        self.packet = packet

        self.hzSpinBox = QDoubleSpinBox()
        self.hzSpinBox.setSingleStep(0.1)
        self.hzSpinBox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.portBox = QSpinBox()
        self.portBox.setRange(1,65535)
        self.portBox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.ipBox = QLineEdit()
        self.ipBox.setText("127.0.0.1")
        self.protocolBox = QComboBox()
        self.protocolBox.addItems(['UDP','TCP Client', 'TCP Server'])
        # self.structureBox = QComboBox()
        # for structure in CONFIG()['telemetryStructures']:
        #     self.structureBox.addItem(structure)
        # self.structureBox.currentTextChanged.connect(self.initPacketBox)
        # self.packetBox = QComboBox()
        # self.initPacketBox()

        self.behaviorsEditButton = QPushButton("Edit")
        self.behaviorsEditButton.clicked.connect(self.editBehaviors)
        
        self.parentWidget = parentWidget
        #parentWidget.setItemWidget(self,1,self.structureBox)
        #parentWidget.setItemWidget(self,2,self.packetBox)
        parentWidget.setItemWidget(self,3,self.hzSpinBox)
        parentWidget.setItemWidget(self,4,self.ipBox)
        parentWidget.setItemWidget(self,5,self.portBox)
        parentWidget.setItemWidget(self,6,self.protocolBox)
        parentWidget.setItemWidget(self,7,self.behaviorsEditButton)

        self.setText(1,self.structure)
        self.setText(2,self.packet)
        if not initConfig == None:
            self.initializeFromConfig(initConfig)
        else:
            self.addSimPacketConfig()

        self.hzSpinBox.valueChanged.connect(self.writeSimConfig)
        self.portBox.valueChanged.connect(self.writeSimConfig)
        self.ipBox.editingFinished.connect(self.writeSimConfig)
        self.protocolBox.currentTextChanged.connect(self.writeSimConfig)
        #self.structureBox.currentTextChanged.connect(self.writeSimConfig)
        #self.packetBox.currentTextChanged.connect(self.writeSimConfig)

    # def initPacketBox(self):
    #     self.packetBox.clear()
    #     structure = self.structureBox.currentText()
    #     for packet in PACKET_TEMPLATES:
    #         if packet[0:len(structure)] == structure:
    #             self.packetBox.addItem(packet)

    def editBehaviors(self):
        packetDict =PACKET_STRUCTURE_COMPONENTS[self.text(1)][self.text(2)]
        behaviorEditor = SimBehaviorWidget(self.parentWidget,self,packetDict,self.dexMainWidget)
        if behaviorEditor.exec() == QDialog.Accepted:
            self.packetBehaviors = behaviorEditor.packetBehaviors
            self.fieldBehaviors = behaviorEditor.fieldBehaviors
            self.writeSimConfig()

    def writeSimConfig(self):
        simConfig = self.simPacketDict()
        row = self.parentWidget.indexOfTopLevelItem(self)
        cfg = CONFIG()
        simList = cfg['simulation']
        simList[row] = simConfig
        cfgLoader.configWrite(cfg)

    def simPacketDict(self):
        simConfig = {
            "packetConfig":{
                "simulationRate":self.hzSpinBox.value(),
                "ip":self.ipBox.text(),
                "port":self.portBox.value(),
                "protocol":self.protocolBox.currentText(),
                "structure":self.text(1),
                "packet":self.text(2)
            },
            "packetBehaviors":self.packetBehaviors,
            "fieldBehaviors":self.fieldBehaviors
        }
        return simConfig

    def addSimPacketConfig(self):
        cfg = CONFIG()
        simList = cfg['simulation']
        simList.append(self.simPacketDict())
        cfgLoader.configWrite(cfg)
        
    def initializeFromConfig(self,initConfig):
        # self.structureBox.setCurrentText(str(initConfig['packetConfig']['structure']))
        # self.packetBox.setCurrentText(str(initConfig['packetConfig']['packet']))
        self.setText(1,self.structure)
        self.setText(2,self.packet)
        self.hzSpinBox.setValue(float(initConfig['packetConfig']['simulationRate']))
        self.ipBox.setText(str(initConfig['packetConfig']['ip']))
        self.portBox.setValue(int(initConfig['packetConfig']['port']))
        self.protocolBox.setCurrentText(str(initConfig['packetConfig']['protocol']))

        self.populateSimBehaviors(initConfig)

    def populateSimBehaviors(self,initConfig):

        pass



"""
Commanding Classes
"""
class StaticListItem(QListWidgetItem):
    #a header/footer definition file in the command components list
    def __init__(self,componentName,componentDict,parentList):
        self.componentName = componentName
        self.componentDict = componentDict
        self.parentList = parentList
        super().__init__(componentName)
        self.setBackground(COMMAND_HEADER)
        self.parentList.addItem(self)


class CommandListItem(QListWidgetItem):
    #the unique command objects in the command components list
    def __init__(self,componentName,componentDict,parentList):
        self.componentName = componentName
        self.componentDict = componentDict
        self.parentList = parentList
        super().__init__(componentName)
        self.setBackground(COMMAND_STRUCTURE)
        self.parentList.addItem(self)

class CommandStructureItem(QTreeWidgetItem):
    #a structured command Item in the command structure tree
    
    def __init__(self,parentTree,structureName):
        self.structureName = structureName
        super().__init__(parentTree)
        self.setText(0,self.structureName)
        self.commandIdField = None

class CommandStructureComponentItem(QTreeWidgetItem):
    #child component item of command structure item
    def __init__(self,parentItem,component,color):
        self.color = color
        self.parentItem = parentItem
        self.component = component
        super().__init__(parentItem)
        self.setBackground(0,self.color)
        self.setText(0,component.componentName)

class CommandField():
    #field-value pair for each field in a command
    def __init__(self,commandField,commandFieldTable):
        self.commandFieldTable = commandFieldTable
        self.nameCell = QTableWidgetItem(commandField['fieldName'])
        self.typeCell = QTableWidgetItem(commandField['type'])
        self.valueCell = QTableWidgetItem(commandField['value'])
        row = self.commandFieldTable.rowCount()
        self.commandFieldTable.insertRow(row)
        self.commandFieldTable.setItem(row,0,self.nameCell)
        self.commandFieldTable.setItem(row,1,self.typeCell)
        self.commandFieldTable.setItem(row,2,self.valueCell)

"""
Dex Main GUI
"""
    
class DexMain():

    def __init__(self,logLevel = logging.WARNING):
        self.logger = logging.getLogger(__name__)
        #TODO check config for log level
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.mainGuiPath = cfgLoader.getPath('apps/main/ui/main.ui')
        self.pktDefUtil = PacketDefinitionUtility()
        ui_file = QFile(self.mainGuiPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        ui_file.close()
        self.command = {}
        self.commandLink = None
        self.commandLinkParametersChanged = True
        
        self.initGUI()
        self.ui.show()

    def initGUI(self):
        self.ui.setWindowTitle(f"Dex {CONFIG()['version']}")
        self.currentlyBuiltStructure = None
        #simulation controls
        self.ui.simulationPacketsTree.setColumnCount(7)     
        self.ui.simulationPacketsTree.setHeaderLabels(['Enabled','Telemetry Structure','Packet','Simulation Rate (Hz)','IP','port','protocol','Behaviors'])
        self.ui.simulationPacketsTree.setColumnWidth(0,70)
        self.ui.simulationPacketsTree.setColumnWidth(1,70)
        self.ui.simulationPacketsTree.setColumnWidth(2,130)
        self.ui.simulationPacketsTree.setColumnWidth(3,120)
        self.ui.simulationPacketsTree.setColumnWidth(4,70)
        self.ui.simulationPacketsTree.setColumnWidth(5,70)
        self.ui.simulationPacketsTree.setColumnWidth(6,130)
        self.ui.simulationPacketsTree.setColumnWidth(7,70)

        self.ui.addSimPacketButton.clicked.connect(self.addPacketSimulation)
        self.ui.removeSimPacketButton.clicked.connect(self.removePacketSimulation)

        # for column in range(self.ui.simulationPacketsTree.columnCount()):
        #     self.ui.simulationPacketsTree.resizeColumnToContents(column)
        self.ui.simulationPacketsTree.setHeaderHidden(False)
        self.populateSimPackets()
        cfg = CONFIG()
        for commandStructure in cfg['commandStructures']:
            self.ui.simulationCommandStructureBox.addItem(commandStructure)
        self.ui.clearSimulationMessagesButton.clicked.connect(self.clearSimulationMessages)
            
        #command controls
        self.commandColorGen = colorGen(COMMAND_STRUCTURE_BASE)
        self.ui.newCommandStructureButton.clicked.connect(self.newCommandStructure)
        self.ui.addCommandComponentButton.clicked.connect(self.addCommandComponent)
        self.ui.removeCommandStructureButton.clicked.connect(self.removeCommand)
        self.ui.buildCommandButton.clicked.connect(self.buildCommand)
        self.ui.sendCommandButton.clicked.connect(self.sendCommand)
        self.ui.rawCommandDisplayFormat.currentTextChanged.connect(self.populateRawCommandBox)
        self.ui.commandFieldsTable.setHorizontalHeaderLabels(['field','type','value'])
        self.ui.commandFieldsTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ui.commandFieldsTable.verticalHeader().setVisible(False)
        self.ui.setDefaultCommandValuesButton.clicked.connect(self.writeDefaultCommandValues)
        self.ui.commandIPDestinationBox.editingFinished.connect(self.commandParameterChanged)
        self.ui.commandPortBox.valueChanged.connect(self.commandParameterChanged)
        self.ui.commandProtocolSelect.currentTextChanged.connect(self.commandParameterChanged)
        self.ui.clearCommandMessagesButton.clicked.connect(self.clearCommandMessageBox)

        self.populateCommandComponents()
        self.populateCommandStructures()

        #telemetry controls
        self.ui.telemetryDefinitionsButton.clicked.connect(self.editTelemetryDefinitions)


    """
    Simulation functions
    """

    def populateSimPackets(self):
        self.simPacketItems = []
        for simPacketConfig in CONFIG()['simulation']:
            structure = simPacketConfig['packetConfig']['structure']
            packet = simPacketConfig['packetConfig']['packet']
            self.simPacketItems.append(SimPacket(self.ui.simulationPacketsTree,self,structure,packet,simPacketConfig))

    def addPacketSimulation(self):
        #launchPacketSelector
        packetSelector = PacketSelector()
        if packetSelector.exec() == QDialog.Accepted:
            structure = packetSelector.ui.structureBox.currentText()
            packet = packetSelector.ui.packetBox.currentText()
            self.simPacketItems.append(SimPacket(self.ui.simulationPacketsTree,self,structure,packet))

    def removePacketSimulation(self):
        currentItem = self.ui.simulationPacketsTree.currentItem()
        if currentItem and currentItem.parent() is None:
            removeItem = currentItem
        else:
            return
        cfg = CONFIG()
        #remove from config
        row = self.ui.simulationPacketsTree.indexOfTopLevelItem(removeItem)
        del cfg['simulation'][row]
        cfgLoader.configWrite(cfg)
        self.ui.simulationPacketsTree.takeTopLevelItem(row)



    def simulationMessage(self,msg,type_="INFO"):
        self.ui.simulationMessageBox.setTextColor(QColor("black"))
        if type_.lower() == "warning":
            self.ui.simulationMessageBox.setTextColor(MESSAGE_WARNING)
            self.logger.warning(msg)
        if type_.lower() == "error":
            self.ui.simulationMessageBox.setTextColor(MESSAGE_ERROR)    
            self.logger.error(msg)

        self.ui.simulationMessageBox.append(msg)

    def clearSimulationMessages(self):
        self.ui.simulationMessageBox.clear()

    """
    Telemetry Functions
    """
    def editTelemetryDefinitions(self):
        packetDefinitionEditor = PacketDefinitionEditor()


    """
    Command functions
    """

    def populateCommandComponents(self):
        for component,componentDict in COMMAND_COMPONENTS['static components'].items():
            staticComponentItem = StaticListItem(component,componentDict,self.ui.commandComponentList)

        for component, componentDict in COMMAND_COMPONENTS['command definitions'].items():
            commandItem = CommandListItem(component,componentDict,self.ui.commandComponentList)
        
    def populateCommandStructures(self):
        #populate already built command structures from global config
        commandStructures = CONFIG()['commandStructures']
        for structureName,structureDict in commandStructures.items():
            componentList = []
            if len(structureDict['headers']) > 0:
                componentList.extend(structureDict['headers'])
            if len(structureDict['packets']) > 0:
                componentList.append(structureDict['packets'])
            if len(structureDict['footers']) > 0:
                componentList.extend(structureDict['footers'])
            structureItem = CommandStructureItem(self.ui.commandStructureTree,structureName)
            for componentName in componentList:
                j = 0
                componentAssigned = False
                while j < self.ui.commandComponentList.count():
                    componentItem = self.ui.commandComponentList.item(j)
                    if componentItem.componentName == componentName:
                        childItem = CommandStructureComponentItem(structureItem,componentItem,next(self.commandColorGen))
                        componentAssigned = True
                        break
                    j += 1
                    
                if not componentAssigned:
                    self.commandMessage(f"In command structure: {structureName} component: {componentName} not found.  If filenames in commandDefinitions folder have been changed they must be reverted.","ERROR")

    def commandMessage(self,msg,type_="INFO"):
        self.ui.commandMessageBox.setTextColor(QColor("black"))
        if type_.lower() == "warning":
            self.ui.commandMessageBox.setTextColor(MESSAGE_WARNING)
            self.logger.warning(msg)
        if type_.lower() == "error":
            self.ui.commandMessageBox.setTextColor(MESSAGE_ERROR)    
            self.logger.error(msg)

        self.ui.commandMessageBox.append(msg)

    def clearCommandMessageBox(self):
        self.ui.commandMessageBox.clear()
        
    def newCommandStructure(self):
        text, ok = QInputDialog.getText(None, "New Structure", "Enter Structure Name:", QLineEdit.Normal)
        if ok and text:
            CommandStructureItem(self.ui.commandStructureTree,text)
        self.writeCommandStructures()
        
    def addCommandComponent(self):
        #add selected command component to selected command structure
        component = self.ui.commandComponentList.currentItem()

        structureSelection = self.ui.commandStructureTree.currentItem()
        if component is None or structureSelection is None:
            return

        if isinstance(structureSelection,CommandStructureComponentItem):
            structureItem = structureSelection.parent()
        else:
            structureItem = structureSelection

        if isinstance(component,CommandListItem):
            componentList = []
            for i in range(structureItem.childCount()):
                componentList.append(structureItem.child(i).component)
            cmdIDSelector = CommandIDSelector(componentList)
            if cmdIDSelector.exec() == QDialog.Accepted:
                structureItem.commandIdField = cmdIDSelector.commandIdField
            else:
                return

        if isinstance(structureSelection,CommandStructureComponentItem):
            index = structureItem.indexOfChild(structureSelection)
            childItem = CommandStructureComponentItem(structureItem,component,next(self.commandColorGen))
            structureItem.insertChild(index,childItem)
        else:
            childItem = CommandStructureComponentItem(structureItem,component,next(self.commandColorGen))
            structureItem.addChild(childItem)
            structureItem.setExpanded(True)

        self.writeCommandStructures()

    def removeCommand(self):
        structureSelection = self.ui.commandStructureTree.currentItem()
        if structureSelection is None:
            return
        root = self.ui.commandStructureTree.invisibleRootItem()
        (structureSelection.parent() or root).removeChild(structureSelection)
        self.writeCommandStructures()

    def buildCommand(self):
        structureSelection =  self.ui.commandStructureTree.currentItem()
        if structureSelection is None:
            return
        if isinstance(structureSelection,CommandStructureComponentItem):
            structureName = structureSelection.parentItem.structureName
        else:
            structureName = structureSelection.structureName
        structure = CONFIG()['commandStructures'][structureName]
    
        commandBuilder = CommandBuilder(structure)
        if commandBuilder.exec() == QDialog.Accepted:
            self.command = commandBuilder.commandList
            self.commandId = commandBuilder.commandId
            self.currentlyBuiltStructure = structureName
            self.populateCommandFieldsTable()
            self.populateRawCommandBox()
            self.ui.sendCommandButton.setEnabled(True)
            self.ui.setDefaultCommandValuesButton.setEnabled(True)

    def sendCommand(self):
        if self.commandLinkParametersChanged:
            self.establishCommandLink()
        self.commandLink.sendCommand(self.command)

    def establishCommandLink(self):
        port = self.ui.commandPortBox.value()
        ip = self.ui.commandIPDestinationBox.text()
        linkType = self.ui.commandProtocolSelect.currentText()
        if linkType == "TCP client":
            self.commandLink = TCPCommandSocket(ip,port,self.commandMessage,'client')
        if linkType == "TCP server":
            self.commandLink = TCPCommandSocket(ip,port,self.commandMessage,'server')
        if linkType == "UDP":
            self.commandLink = UDPCommandSocket(ip,port,self.commandMessage)

    def commandParameterChanged(self):
        self.commandLinkParametersChanged = True

    def writeCommandStructures(self):
        numStructures = self.ui.commandStructureTree.topLevelItemCount()
        commandStructures = {}
        for i in range(numStructures):
            structureItem = self.ui.commandStructureTree.topLevelItem(i)
            commandStructures[structureItem.structureName] ={"headers":[],"commands":'',"footers":[]}
            headers = True
            for j in range(structureItem.childCount()):
                childItem = structureItem.child(j)
                if isinstance(childItem.component,CommandListItem):
                    commandStructures[structureItem.structureName]['packets'] = childItem.component.componentName
                    headers = False
                else:
                    if headers:
                        commandStructures[structureItem.structureName]['headers'].append(childItem.component.componentName)
                    else:
                        commandStructures[structureItem.structureName]['footers'].append(childItem.component.componentName)

            if not structureItem.commandIdField == None:
                commandStructures[structureItem.structureName]['packetIdField'] = structureItem.commandIdField
                
        currentConfig = CONFIG()
        currentConfig['commandStructures'] = commandStructures
        cfgLoader.configWrite(currentConfig)

    def populateCommandFieldsTable(self):

        self.commandFieldItems = []
        for field in self.command:
            self.commandFieldItems.append(CommandField(field,self.ui.commandFieldsTable))

        #find selected structure
        structureSelection =  self.ui.commandStructureTree.currentItem()
        if isinstance(structureSelection,CommandStructureComponentItem):
            structure = structureSelection.parentItem
        else:
            structure = structureSelection
        #iterate over component items

        commandTableRow = 0
        for i in range(structure.childCount()):
            component = structure.child(i)
            color = component.color
            for field in component.component.componentDict:
                for col in range(self.ui.commandFieldsTable.columnCount()):
                    self.ui.commandFieldsTable.item(commandTableRow,col).setBackground(color)
                commandTableRow += 1

    def populateRawCommandBox(self):
        if self.command == {}:
            return
        
        bitCommand = ''
        for field in self.command:
            bitCommand += field['bitstring']

        if self.ui.rawCommandDisplayFormat.currentText() == 'Binary':
            self.ui.rawPacketTextBox.setText(bitCommand)

        elif len(bitCommand)% 8 == 0:
            self.displayRawHex(bitCommand)
        else:
            self.ui.rawPacketTextBox.setText("Unable to display as hex, command is not a complete number of bytes.")

    def displayRawHex(self,bitCommand):
        num = int(bitCommand,2)
        numBytes = int(len(bitCommand)/8)
        result_bytes = num.to_bytes(numBytes, byteorder='big')      
        self.ui.rawPacketTextBox.setText(result_bytes.hex(' '))

    def writeDefaultCommandValues(self):
        commandStructure = CONFIG()['commandStructures'][self.currentlyBuiltStructure]
        fieldNum = 0
        #headers
        for hdr in commandStructure['headers']:
            filePath = cfgLoader.getPath(f'commandDefinitions/{hdr}.hd')
            with open(filePath,'r') as f:
                hdrDict = json.load(f)

            for field in hdrDict['fields']:
                strVal = self.commandFieldItems[fieldNum].valueCell.text()
                field['defaultValue'] = self.setDefaultValFromTable(strVal,field)
                fieldNum += 1

            with open(filePath,'w') as f:
                json.dump(hdrDict,f,indent=4)
        #command file

        commandPath = cfgLoader.getPath(f'commandDefinitions/{commandStructure['packets']}.cd')
        with open(commandPath,'r') as f:
            commandsDict = json.load(f)
        commandDict = commandsDict[self.commandId]
        if 'arguments' in commandDict:
            for arg in commandDict['arguments']:
                strVal = self.commandFieldItems[fieldNum].valueCell.text()
                arg['defaultValue'] = self.setDefaultValFromTable(strVal,arg)
                fieldNum += 1
        with open(commandPath,'w') as f:
            json.dump(commandsDict,f,indent=4)

        #footers
        for footer in commandStructure['footers']:
            filePath = cfgLoader.getPath(f'commandDefinitions/{footer}.hd')
            with open(filePath,'r') as f:
                footerDict = json.load(f)

            for field in footerDict['fields']:
                strVal = self.commandFieldItems[fieldNum].valueCell.text()
                field['defaultValue'] = self.setDefaultValFromTable(strVal,field)
                fieldNum += 1

            with open(filePath,'w') as f:
                json.dump(footerDict,f,indent=4)

    def setDefaultValFromTable(self,strVal,field):
        if 'int' in field['type']:
            return int(strVal)
        if field['type'] in ('float','double'):
            return float(strVal)
        if field['type'] == 'char':
            return strVal

if __name__ == "__main__":
    app = QApplication([])
    dexMain = DexMain()
    app.exec()