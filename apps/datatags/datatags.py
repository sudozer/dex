from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtWidgets import (
    QDialog,
    QListWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QComboBox,
    QPushButton,
)
import pdb
from loadConfig import GLOBAL_CONFIG, cfgLoader
from commandBuilder import CommandBuilder
from telemetrySelector import TelemetryFieldSelector
from dataStructures import COMMAND_STRUCTURE_COMPONENTS

class CommandStructureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Command Structure")
        self.setModal(True)
        self.layout = QVBoxLayout(self)
        self.structureBox = QComboBox(self)
        self.okButton = QPushButton("OK", self)
        self.okButton.clicked.connect(self.accept)
        self.layout.addWidget(self.structureBox)
        self.layout.addWidget(self.okButton)
        self.setLayout(self.layout)
        self.populateCommandStructures()
        self.setFixedWidth(500)
        self.show()

    def populateCommandStructures(self):
        self.structureBox.clear()
        for structure in COMMAND_STRUCTURE_COMPONENTS.keys():
            self.structureBox.addItem(structure)

    def populateCommandList(self):
        for command in COMMAND_STRUCTURE_COMPONENTS.keys():
            commandItem = CommandItem(command)
            self.ui.commandList.addItem(commandItem)

class CommandItem(QTreeWidgetItem):
    def __init__(self, command, parent):
        super().__init__(parent)
        self.command = command
        self.parentItem = parent
        cmdText = ""
        for field in self.command:
            cmdText = cmdText + f"{field['fieldName']}: {field['value']}; "
        self.setText(0,cmdText)

class CommandStructureItem(QTreeWidgetItem):
    def __init__(self, structure, parent=None):
        super().__init__(parent)
        self.commands = []
        self.structure = structure
        self.setText(0,structure)

class TelemetryItem(QListWidgetItem):
    def __init__(self, telemetry, parent=None):
        super().__init__(parent)
        self.telemetry = telemetry
        self.setText(telemetry)

class DataTagConfig(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.loader = QUiLoader()
        uiPath = cfgLoader.getPath('apps/datatags/ui/datatags.ui')
        uiFile = QFile(uiPath)
        uiFile.open(QFile.ReadOnly)
        self.ui = self.loader.load(uiFile, self)
        uiFile.close()
        self.ui.setWindowTitle("Data Tag Configuration")
        self.dataTagCfg = GLOBAL_CONFIG['storage']['dataTags']
        self.setModal(True)
        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)    

        self.ui.commandTagTree.setHeaderHidden(True)
        self.ui.addCommandButton.clicked.connect(self.addCommand)
        self.ui.removeCommandButton.clicked.connect(self.removeCommand)
        self.ui.okButton.clicked.connect(self.writeConfig)
        self.ui.tagAllCommandsBox.stateChanged.connect(self.setCommandLabel)
        self.setWindowTitle("Configure Automatic Datatags")
        self.show()
        self.initFromConfig()

    def initFromConfig(self):
        self.ui.tagStartupBox.setChecked(self.dataTagCfg['tagStartup'])
        self.ui.tagShutdownBox.setChecked(self.dataTagCfg['tagShutdown'])
        self.ui.tagAllCommandsBox.setChecked(self.dataTagCfg['tagAllCommands'])
        self.populateCommandList()

    def setCommandLabel(self):
        if self.ui.tagAllCommandsBox.isChecked():
            self.ui.commandListLabel.setText("Excluded Commands:")
        else:
            self.ui.commandListLabel.setText("Tagged Commands:")

    def writeConfig(self):
        commandDict = {}
        for structureName,structureItem in self.structureItems.items():
            commandDict[structureItem.structure]=[]
            for command in structureItem.commands:
                commandDict[structureItem.structure].append(command.command)
        dataTagCfg = {
            "tagStartup":self.ui.tagStartupBox.isChecked(),
            "tagShutdown":self.ui.tagShutdownBox.isChecked(),
            "tagAllCommands":self.ui.tagAllCommandsBox.isChecked(),
            "commands":commandDict
        }
        GLOBAL_CONFIG['storage']['dataTags'] = dataTagCfg
        cfgLoader.configWrite(GLOBAL_CONFIG)
        self.accept()

    def populateCommandList(self):
        self.structureItems = {}
        for structure in COMMAND_STRUCTURE_COMPONENTS.keys():
            self.structureItems[structure] = CommandStructureItem(structure,self.ui.commandTagTree)

        for structureName,structure in self.dataTagCfg['commands'].items():
            for command in structure:
                self.addCommandItem(structureName,command)
        
    def addCommand(self):
        structureSelector = CommandStructureDialog(self)
        if structureSelector.exec() == QDialog.Accepted:
            selectedStructure = structureSelector.structureBox.currentText()
            commandBuilder = CommandBuilder(selectedStructure, True)
            if commandBuilder.exec() == QDialog.Accepted:
                commandList = [field for field in commandBuilder.commandList if field['relevant']]
                # Add the selected command to the list
                self.addCommandItem(selectedStructure,commandList)

    def addCommandItem(self,structure,command):
        structureItem = self.structureItems[structure]
        structureItem.commands.append(CommandItem(command,structureItem))
        structureItem.setExpanded(True)
    def removeCommand(self):
        selectedCommand = self.ui.commandTagTree.currentItem() 
        if isinstance(selectedCommand,CommandItem):
            selectedCommand.parentItem.commands.remove(selectedCommand)
            selectedCommand.parentItem.removeChild(selectedCommand)
