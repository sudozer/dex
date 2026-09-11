from pathlib import Path
import pdb
import json
import os
import copy
import csv
import logging

from PySide6.QtGui import QColor #for colors
from PySide6.QtCore import QFile, Qt
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

from packetDefinitionLib import PacketDefinitionUtility
from decode import Decoder
from dataStructures import PACKET_TEMPLATES, COMMAND_COMPONENTS
from telemetrySelector import TelemetryFieldSelector
#from commandBuilder import CommandBuilder

"""
Simulation classes
"""

class PacketBehavior(QTableWidgetItem):
    """
    list item of the whole packet playback behavior table
    """
    def __init__(self, parent):
        super().__init__()
        self.parentTable = parent
        self.triggerComboBox = QComboBox()
        self.triggerComboBox.addItems(['Initial Condition','On Telemetry Value','On Command Recieved'])
        self.triggerComboBox.currentTextChanged.connect(self.triggerChanged)
        self.playbackTimeField = QDateTimeEdit()
        self.playbackTimeField.setCalendarPopup(True)
        self.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        self.setCheckState(Qt.CheckState.Checked)

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
            self.line_edit2 = QLineEdit()
            self.line_edit2.setPlaceholderText("Value")

            cell_layout.addWidget(self.telemetryFieldButton)
            cell_layout.addWidget(self.line_edit2)
            self.parentTable.setCellWidget(self.row(),2,container)

        if newTrigger == 'On Command Recieved':

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
        #TODO move these to utils
        pass

    def loadInitialBehavior(self):
        pass

class FieldItem(QTreeWidgetItem):
    """
    tree item of a single field in the fieldwise simulation tree
    """
    def __init__(self, parent, fieldName, fieldDict,initConfig):
        super().__init__(parent)
        self.parentTree = parent
        self.setText(0, f"{fieldName}")
        self.fieldName = fieldName
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
        for initBehavior in initConfig:
            #create a field Behavior
            item = FieldBehavior(self,self.fieldName, initBehavior)

    def addBehavior(self):
        #needs testing
        item = FieldBehavior(self,self.fieldName)
        if self.parentTree.selectedItems():
            selectedItem = self.parentTree.selectedItems()[0]
            if selectedItem.parent() == self:
                index = self.parentTree.indexOfTopLevelItem(selectedItem)
                item.parent().takeChild(item.parent().indexOfChild(item))
                self.insertChild(index + 1, item)

        self.setExpanded(True)

    def removeBehavior(self):
        #remove the currently selected behavior
        selectedItems = self.parentTree.selectedItems()
        if len(selectedItems) > 0:
            del selectedItems[0]

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
        self.triggerComboBox.addItems(['Initial Condition','On Telemetry Value','On Command Recieved'])
        self.behaviorComboBox = QComboBox()
        self.behaviorComboBox.addItems(['hold static value','playback from telemetry','ramp to','pseudorandom noise around'])

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
        #TODO populate init behaviors
        pass

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
            self.line_edit2 = QLineEdit()
            self.line_edit2.setPlaceholderText("Value")

            cell_layout.addWidget(self.telemetryFieldButton)
            cell_layout.addWidget(self.line_edit2)
            self.parentItem.parentTree.setItemWidget(self,2,container)

        if newTrigger == 'On Command Recieved':

            self.commandSelectButton = QPushButton("Command")
            self.commandSelectButton.clicked.connect(self.selectCommand)
            self.parentItem.parentTree.setItemWidget(self,2,self.commandSelectButton)

    def behaviorChanged(self, newBehavior):
        #['hold static value','playback from telemetry','ramp to','pseudorandom noise around']
        if newBehavior == 'hold static value':
            self.behaviorParamsValue = QLineEdit()
            self.behaviorParamsValue.setPlaceholderText("Value")
            self.parentItem.parentTree.setItemWidget(self,4,self.behaviorParamsValue)

        if newBehavior == 'playback from telemetry':
            self.behaviorPlaybackTime = QDateTimeEdit()
            self.behaviorPlaybackTime.setCalendarPopup(True)
            self.parentItem.parentTree.setItemWidget(self,4,self.behaviorPlaybackTime)

        if newBehavior == 'ramp to':
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(6)
            self.behaviorRampValue = QLineEdit()
            self.behaviorRampValue.setPlaceholderText("Final Value")
            self.behaviorRampSeconds = QLineEdit()
            self.behaviorRampSeconds.setPlaceholderText("Ramp Time (s)")
            layout.addWidget(self.behaviorRampValue)
            layout.addWidget(self.behaviorRampSeconds)
            self.parentItem.parentTree.setItemWidget(self,4,container)

        if newBehavior == 'pseudorandom noise around':
            self.behaviorPseudorandomValue = QLineEdit()
            self.behaviorPseudorandomValue.setPlaceholderText("Value")
            self.parentItem.parentTree.setItemWidget(self,4,self.behaviorPseudorandomValue)

    def selectTelemetryField(self):
        selector = TelemetryFieldSelector()
        if selector.exec() == QDialog.Accepted:
            self.onTelemetryField = selector.selectedField
            self.onTelemetryPacket = selector.selectedPacket
            self.telemetryFieldButton.setText(f"{self.onTelemetryPacket}.{self.onTelemetryField}")
    
    def selectCommand(self):
        pass

class SimBehaviorWidget(QDialog):
    def __init__(self, parent, packetName, packetList):
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

        self.simParameterDict = CONFIG()['simulation'][packetName]

        # Set up layout to display the loaded form
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.addWidget(self.loaded_widget)
        self.setLayout(layout)
        self.setModal(True)
        self.packetName = packetName
        self.packetList = packetList
        
        self.setWindowTitle(f"{packetName} Simulation Behaviors")

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
        self.loaded_widget.okButton.clicked.connect(self.accept)

        self.populateFields()
        self.populatePacketPlaybacks()
        self.show()

    def populateFields(self):
        #populate fieldwise tree with FieldBehaviors and packet behavior list with PacketBehaviors
        if not "simulation" in CONFIG():
            cfg = CONFIG()
            cfg['simulation'] = {}
            for packet in PACKET_TEMPLATES:
                cfg['simulation'][packet] = {}
            cfgLoader.configWrite(cfg)

        cfg = CONFIG()
        initConfigs = cfg['simulation'][self.packetName]
        #populate field list

        for field in self.packetList:
            fieldName = field['fieldName']
            fieldItem = FieldItem(self.loaded_widget.fieldwiseBehaviorTree,fieldName,field,initConfigs.get(fieldName,[]))

    def populatePacketPlaybacks(self):
        pass

    def addPacketPlaybackTrigger(self):
        #add a new row to the packet playback table
        item = PacketBehavior(self.loaded_widget.wholePacketPlaybackTable)
        if self.loaded_widget.wholePacketPlaybackTable.selectedItems():
            selectedItem = self.loaded_widget.wholePacketPlaybackTable.selectedItems()[0]
            row = selectedItem.row() + 1
        else:
            row = self.loaded_widget.wholePacketPlaybackTable.rowCount()

        self.loaded_widget.wholePacketPlaybackTable.insertRow(row)
        self.loaded_widget.wholePacketPlaybackTable.setItem(row, 0, item)
        self.loaded_widget.wholePacketPlaybackTable.setCellWidget(item.row(),1,item.triggerComboBox)
        self.loaded_widget.wholePacketPlaybackTable.setCellWidget(item.row(),3,item.playbackTimeField)

    def removePacketPlaybackTrigger(self):
        #remove the currently selected row from the packet playback table
        selectedItems = self.loaded_widget.wholePacketPlaybackTable.selectedItems()
        if len(selectedItems) > 0:
            row = selectedItems[0].row()
            self.loaded_widget.wholePacketPlaybackTable.removeRow(row)     

class SimPacket(QTreeWidgetItem):
    def __init__(self, parent, packetName, packetDict):
        self.packetName = packetName
        self.packetDict = packetDict
        super().__init__(parent)
        self.setText(1, packetName)
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(0, Qt.CheckState.Checked)

        self.hzSpinBox = QDoubleSpinBox()
        self.hzSpinBox.setSingleStep(0.1)
        self.hzSpinBox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.portBox = QSpinBox()
        self.portBox.setRange(1,65535)
        self.portBox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.ipBox = QLineEdit()
        self.protocolBox = QComboBox()
        self.protocolBox.addItems(['UDP','TCP'])

        self.behaviorsEditButton = QPushButton("Edit")
        self.behaviorsEditButton.clicked.connect(self.editBehaviors)

        self.parentWidget = parent
        parent.setItemWidget(self,2,self.hzSpinBox)
        parent.setItemWidget(self,3,self.ipBox)
        parent.setItemWidget(self,4,self.portBox)
        parent.setItemWidget(self,5,self.protocolBox)
        parent.setItemWidget(self,6,self.behaviorsEditButton)

    def editBehaviors(self):
        behaviorEditor = SimBehaviorWidget(self.parentWidget,self.packetName,self.packetDict)
        result = behaviorEditor.exec()
        if result == QDialog.DialogCode.Accepted:
            #write new sim behaviors to the config
            newCfg = CONFIG()
            newCfg['simulation'][self.packetName] = behaviorEditor.simParameterDict
            cfgLoader.configWrite(newCfg)

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
        self.parentList.addItem(self)


class CommandListItem(QListWidgetItem):
    #the unique command objects in the command components list
    def __init__(self,componentName,componentDict,parentList):
        self.componentName = componentName
        self.componentDict = componentDict
        self.parentList = parentList
        super().__init__(componentName)
        self.parentList.addItem(self)

class CommandStructureItem(QTreeWidgetItem):
    #a structured command Item in the command structure tree
    
    def __init__(self,parentTree,structureName):
        self.structureName = structureName
        super().__init__(parentTree)
        self.setText(0,self.structureName)

class CommandStructureComponentItem(QTreeWidgetItem):
    #child component item of command structure item
    def __init__(self,parentItem,component):
        self.parentItem = parentItem
        self.component = component
        super().__init__(parentItem)
        self.setText(0,component.componentName)



class CommandField():
    #field-value pair for each field in a command
    def __init__(self):
        pass

"""
Dex Main GUI
"""
    
class DexMain():

    def __init__(self):
        self.mainGuiPath = cfgLoader.getPath('apps/main/ui/main.ui')
        self.pktDefUtil = PacketDefinitionUtility()
        ui_file = QFile(self.mainGuiPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        ui_file.close()
        
        self.initGUI()
        self.ui.show()

    def initGUI(self):
        self.ui.setWindowTitle(f"Dex {CONFIG()['version']}")

        #simulation controls
        self.ui.simulationPacketsTree.setColumnCount(7)     
        self.ui.simulationPacketsTree.setHeaderLabels(['Enabled','Packet','Simulation Rate (Hz)','IP','port','protocol','Behaviors'])
        for column in range(self.ui.simulationPacketsTree.columnCount()):
            self.ui.simulationPacketsTree.resizeColumnToContents(column)
        self.populateSimPackets()
        for commandStructure in CONFIG()['commandStructures']:
            self.ui.simulationCommandStructureBox.addItem(commandStructure)
            

        #command controls
        self.ui.newCommandStructureButton.clicked.connect(self.newCommandStructure)
        self.ui.addCommandComponentButton.clicked.connect(self.addCommandComponent)
        self.ui.removeCommandStructureButton.clicked.connect(self.removeCommand)
        self.ui.buildCommandButton.clicked.connect(self.buildCommand)
        self.ui.sendCommandButton.clicked.connect(self.sendCommand)
        self.populateCommandComponents()
        self.populateCommandStructures()
        

    def populateCommandComponents(self):
        for component,componentDict in COMMAND_COMPONENTS['static components'].items():
            staticComponentItem = StaticListItem(component,componentDict,self.ui.commandComponentList)

        for component, componentDict in COMMAND_COMPONENTS['command definitions'].items():
            commandItem = CommandListItem(component,componentDict,self.ui.commandComponentList)
        
    def populateCommandStructures(self):
        #populate already built command structures from global config
        commandStructures = CONFIG()['commandStructures']
        for structureName,structureDict in commandStructures.items():
            componentList = structureDict['format']
            structureItem = CommandStructureItem(self.ui.commandStructureTree,structureName)
            for componentName in componentList:
                j = 0
                componentAssigned = False
                while j < self.ui.commandComponentList.count():
                    componentItem = self.ui.commandComponentList.item(j)
                    if componentItem.componentName == componentName:
                        childItem = CommandStructureComponentItem(structureItem,componentItem)
                        componentAssigned = True
                        break
                    j += 1
                    
                if not componentAssigned:
                    self.commandMessage(f"In command structure: {structureName} component: {componentName} not found.  If filenames in commandDefinitions folder have been changed they must be reverted.","ERROR")

    def commandMessage(self,msg,type="INFO"):
        pass
            
    def populateSimPackets(self):
        
        for packetName, packetDict in PACKET_TEMPLATES.items():
            simItem = SimPacket(self.ui.simulationPacketsTree,packetName,packetDict)

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
            index = structureItem.indexOfChild(structureSelection)
            childItem = CommandStructureComponentItem(structureItem,component)
            structureItem.insertChild(index,childItem)
        else:
            childItem = CommandStructureComponentItem(structureSelection,component)
            structureSelection.addChild(childItem)
            structureSelection.setExpanded(True)
        self.writeCommandStructures()

    def removeCommand(self):
        structureSelection = self.ui.commandStructureTree.currentItem()
        if structureSelection is None:
            return
        root = self.ui.commandStructureTree.invisibleRootItem()
        (structureSelection.parent() or root).removeChild(structureSelection)
        self.writeCommandStructures()

    def buildCommand(self):


        pass
    def sendCommand(self):
        pass

    def writeCommandStructures(self):
        numStructures = self.ui.commandStructureTree.topLevelItemCount()
        commandStructures = {}
        for i in range(numStructures):
            structureItem = self.ui.commandStructureTree.topLevelItem(i)
            commandStructures[structureItem.structureName] ={"format":[]}
            for j in range(structureItem.childCount()):
                childItem = structureItem.child(j)
                commandStructures[structureItem.structureName]['format'].append(childItem.component.componentName)

        currentConfig = CONFIG()
        currentConfig['commandStructures'] = commandStructures
        cfgLoader.configWrite(currentConfig) 

if __name__ == "__main__":
    app = QApplication([])
    dexMain = DexMain()
    app.exec()