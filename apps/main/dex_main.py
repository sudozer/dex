from pathlib import Path
import pdb
import json
import os
import copy
import csv

from PySide6.QtGui import QColor #for colors
from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, 
    QMainWindow,
    QMessageBox,
    QHeaderView,
    QDialog,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
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
from dataStructures import DataDictionaries

DATADICTS = DataDictionaries()

"""
Simulation classes
"""

class PacketBehavior(QTableWidgetItem):
    """
    list item of the whole packet behavior table
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
        self.setText(4,"Behavior")
        parent.parentTree.setItemWidget(self,3,self.behaviorComboBox)
        if not initBehavior is None:
            self.populateInitBehavior(initBehavior)

    def populateInitBehavior(self,initBehavior):
        #TODO populate init behaviors
        pass

    def triggerChanged(self, newTrigger):
        pass
    def behaviorChanged(self, newBehavior):
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

        # Set up layout to display the loaded form
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.addWidget(self.loaded_widget)

        self.setLayout(layout)
        self.setModal(True)
        self.packetName = packetName
        self.packetList = packetList
        
        self.setWindowTitle(f"{packetName}-Simulation Behaviors")

        self.loaded_widget.fieldwiseBehaviorTree.setColumnCount(5)
        self.loaded_widget.fieldwiseBehaviorTree.setHeaderLabels(['Enabled','Trigger Type','Trigger Parameters','Behavior Type','Behavior Parameters'])
        for column in range(self.loaded_widget.fieldwiseBehaviorTree.columnCount()):
            self.loaded_widget.fieldwiseBehaviorTree.resizeColumnToContents(column)

        self.loaded_widget.wholePacketPlaybackTable.setColumnCount(4)
        self.loaded_widget.wholePacketPlaybackTable.setHorizontalHeaderLabels(['enabled','Trigger Type','Trigger Parameters','Playback Start'])
        self.loaded_widget.wholePacketPlaybackTable.verticalHeader().setVisible(False)
        self.loaded_widget.wholePacketPlaybackTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

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
            for packet in DATADICTS.packetTemplates:
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

        self.behaviorsEditButton = QPushButton("Edit")
        self.behaviorsEditButton.clicked.connect(self.editBehaviors)

        self.parentWidget = parent
        parent.setItemWidget(self,2,self.hzSpinBox)
        parent.setItemWidget(self,3,self.behaviorsEditButton)

    def editBehaviors(self):
        behaviorEditor = SimBehaviorWidget(self.parentWidget,self.packetName,self.packetDict)
        result = behaviorEditor.exec()
        if result == QDialog.DialogCode.Accepted:
            #save the behaviors to the config
            pass
    
class DexMain():

    def __init__(self):
        self.mainGuiPath = cfgLoader.getPath('apps/main/ui/main.ui')
        self.pktDefUtil = PacketDefinitionUtility()
        ui_file = QFile(self.mainGuiPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        #TODO grab this from the config tab
        ui_file.close()
        
        #apply_stylesheet(self.window, theme=CONFIG()['guiTheme'])
        self.initGUI()
        self.ui.show()

    def initGUI(self):
        self.ui.setWindowTitle(f"Dex {CONFIG()['version']}")
        self.telemetryTab = self.ui.tabs.widget(0)
        self.commandingTab = self.ui.tabs.widget(1)
        self.dataExportTab = self.ui.tabs.widget(2)
        self.simulationTab = self.ui.tabs.widget(3)
        self.customWidgetsTab = self.ui.tabs.widget(4)
        self.configurationTab = self.ui.tabs.widget(5)
        self.ui.simulationPacketsTree.setColumnCount(4)     
        self.ui.simulationPacketsTree.setHeaderLabels(['Enabled','Packet','Simulation Rate (Hz)','Behaviors'])
        for column in range(self.ui.simulationPacketsTree.columnCount()):
            self.ui.simulationPacketsTree.resizeColumnToContents(column)
        self.populateSimPackets()

    def populateSimPackets(self):

        for packetName, packetDict in DATADICTS.packetTemplates.items():
            simItem = SimPacket(self.ui.simulationPacketsTree,packetName,packetDict)
    
if __name__ == "__main__":
    app = QApplication([])
    dexMain = DexMain()
    app.exec()