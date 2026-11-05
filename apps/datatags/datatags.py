from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtWidgets import (
    QDialog,
    QListWidgetItem,
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
        pdb.set_trace()
        for structure in COMMAND_STRUCTURE_COMPONENTS.keys():
            self.structureBox.addItem(structure)

    def populateCommandList(self):
        for command in COMMAND_STRUCTURE_COMPONENTS.keys():
            commandItem = CommandItem(command)
            self.ui.commandList.addItem(commandItem)

class CommandItem(QListWidgetItem):
    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.setText(command)

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

        self.ui.addCommandButton.clicked.connect(self.addCommand)
        self.ui.removeCommandButton.clicked.connect(self.removeCommand)
        self.ui.addTelemetryButton.clicked.connect(self.addTelemetry)
        self.ui.removeTelemetryButton.clicked.connect(self.removeTelemetry)
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
        self.populateTelemetryList()

    def setCommandLabel(self):
        if self.ui.tagAllCommandsBox.isChecked():
            self.ui.commandListLabel.setText("Excluded Commands:")
        else:
            self.ui.commandListLabel.setText("Tagged Commands:")

    def writeConfig(self):
        self.accept()
        pass

    def populateCommandList(self):

        pass

    def populateTelemetryList(self):
        pass

    def addCommand(self):
        structureSelector = CommandStructureDialog(self)
        if structureSelector.exec() == QDialog.Accepted:
            selectedStructure = structureSelector.structureBox.currentText()
            commandBuilder = CommandBuilder(selectedStructure, True)
            if commandBuilder.exec() == QDialog.Accepted:
                selectedCommand = commandBuilder.selectedCommand
                # Add the selected command to the list
                commandItem = CommandItem(selectedCommand)
                self.ui.commandList.addItem(commandItem)

    def removeCommand(self):
        pass

    def addTelemetry(self):
        selector = TelemetryFieldSelector()
        if selector.exec == QDialog.Accepted:
            telemetrySelection = selector.returnSelection
        pass

    def removeTelemetry(self):
        pass    
