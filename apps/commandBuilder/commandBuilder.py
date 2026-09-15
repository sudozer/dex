import json
from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox, 
    QMainWindow,
    QMessageBox,
    QHeaderView,
    QDialog,
    QWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QTableWidget,
    QLineEdit,
    QListWidgetItem,
    QTableWidgetItem,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QDateTimeEdit
)
import pdb

#from dataStructures import COMMAND_COMPONENTS
from loadConfig import Configs

cfgLoader = Configs()


class CommandItem(QListWidgetItem):
    def __init__(self,parentList,commandID,commandDict):
        self.parentList = parentList
        self.commandID = commandID
        self.commandDict = commandDict
        super().__init__(f"{commandID}: {commandDict['commandName']}")
        parentList.addItem(self)

class FieldItem():
    def __init__(self,argDict,fieldTable):
        self.argDict = argDict
        self.fieldTable = fieldTable
        self.fieldCell = QTableWidgetItem(argDict['fieldName'])
        self.typeCell = QTableWidgetItem(argDict['type'])
        if 'defaultValue' in argDict:
            val = argDict['defaultValue']
        else:
            val = 0
        self.valueCell = QTableWidgetItem(str(val))

        self.fieldCell.setFlags(self.fieldCell.flags() & ~Qt.ItemIsEditable)
        self.typeCell.setFlags(self.typeCell.flags() & ~Qt.ItemIsEditable)
        row = self.fieldTable.rowCount()
        self.fieldTable.insertRow(row)
        self.fieldTable.setItem(row,0,self.fieldCell)
        self.fieldTable.setItem(row,1,self.typeCell)
        self.fieldTable.setItem(row,2,self.valueCell)    

class CommandBuilder(QDialog):
    def __init__(self, commandStructure):
        super().__init__()

        # Load the UI from the .ui file
        loader = QUiLoader()
        self.guiPath = cfgLoader.getPath('apps/commandBuilder/ui/commandBuilder.ui')
        ui_file = QFile(self.guiPath)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file, self)
        ui_file.close()
        self.commandStructure = commandStructure

        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)
        self.setModal(True)
        self.ui.okButton.clicked.connect(self.accept)
        # Populate the tree widget with telemetry fields
        self.populateCommands()
        self.setWindowTitle(f"Build a command")
        self.ui.argumentTable.setColumnCount(3)
        self.ui.argumentTable.setHorizontalHeaderLabels(["field","type","value"])
        self.ui.argumentTable.horizontalHeader().setVisible(True)
        self.ui.argumentTable.verticalHeader().setVisible(False)
        self.ui.argumentTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ui.commandList.itemClicked.connect(self.populateArgumentTable)
        self.ui.showNoncommandFieldsCheckbox.checkStateChanged.connect(self.populateArgumentTable)
        self.show()

    def populateCommands(self):
        commandComponent = self.commandStructure['commands']
        commandBasePath = cfgLoader.getPath(f'commandDefinitions/{commandComponent}.cd')
        with open(commandBasePath, 'r') as f:
            commandsDict = json.load(f)
        for command,commandDict in commandsDict.items():
            commandItem = CommandItem(self.ui.commandList,command,commandDict)

    def populateArgumentTable(self):
        self.ui.argumentTable.clearContents()
        self.ui.argumentTable.setRowCount(0)
        self.ui.argumentTable.itemChanged.disconnect()

        if self.ui.commandList.currentItem() == None:
            return
        commandItem = self.ui.commandList.currentItem()

        if self.ui.showNoncommandFieldsCheckbox.isChecked():
            self.addStaticComponents('headers')

        commandBytesItem = FieldItem({"fieldName":"Command","type": "uint8_t","defaultValue":commandItem.commandID},self.ui.argumentTable)
        if 'arguments' in commandItem.commandDict:
            for argDict in commandItem.commandDict['arguments']:
                argItem = FieldItem(argDict,self.ui.argumentTable)

        if self.ui.showNoncommandFieldsCheckbox.isChecked():
            self.addStaticComponents('footers')

        self.ui.argumentTable.itemChanged.connect(self.validateField)

    def addStaticComponents(self,side):
        for commandComponent in self.commandStructure[side]:
            componentPath = cfgLoader.getPath(f'commandDefinitions/{commandComponent}.hd')
            with open(componentPath,'r') as f:
                componentDict = json.load(f)
            for fieldDict in componentDict['fields']:
                fieldItem = FieldItem(fieldDict,self.ui.argumentTable)

    def validateField(self):
        pass

    def returnCommand(self):
        pass

