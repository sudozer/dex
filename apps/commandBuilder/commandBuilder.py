import json
import struct
import pdb
from PySide6.QtCore import QFile, Qt
from PySide6.QtGui import QColor,QBrush
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
from dataStructures import COMMAND_COMPONENTS
from loadConfig import Configs
from packetDefinitionLib import PacketDefinitionUtility
from autofill import Autofiller
ERROR_COLOR = QColor(237,71,59)

cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig
startingConfig = CONFIG()

class CommandItem(QListWidgetItem):
    def __init__(self,parentList,commandID,commandDict):
        self.parentList = parentList
        self.commandID = commandID
        self.commandDict = commandDict
        super().__init__(f"{commandID}: {commandDict['commandName']}")
        parentList.addItem(self)

class FieldItem():
    def __init__(self,argDict,fieldTable,commandItem=True,relevantFields=False):
        if relevantFields:
            self.relevant = commandItem
        
        self.commandItem = commandItem
        self.argDict = argDict
        self.fieldTable = fieldTable
        self.fieldCell = QTableWidgetItem(argDict['fieldName'])
        self.typeCell = QTableWidgetItem(argDict['type'])
        if relevantFields:
            self.fieldCell.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.fieldCell.setCheckState(Qt.CheckState.Unchecked)

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
    def __init__(self, commandStructure, relevantFields = False):
        super().__init__()
        self.fieldItems = []
        self.commandId = None
        self.relevantFields = relevantFields
        # Load the UI from the .ui file
        self.packetDefLib = PacketDefinitionUtility()
        self.validatingArgs = False
        self.autofiller = Autofiller()
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
        self.ui.okButton.clicked.connect(self.returnCommand)
        # Populate the tree widget with telemetry fields
        self.populateCommands()
        self.setWindowTitle(f"Build a command")
        self.ui.argumentTable.setColumnCount(3)
        self.ui.argumentTable.setHorizontalHeaderLabels(["field","type","value"])
        self.ui.argumentTable.horizontalHeader().setVisible(True)
        self.ui.argumentTable.verticalHeader().setVisible(False)
        self.ui.argumentTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ui.commandList.itemClicked.connect(self.populateArgumentTable)
        self.ui.showNoncommandFieldsCheckbox.checkStateChanged.connect(self.hiddenFields)
        self.show()

    def populateCommands(self):

        commandComponent = self.commandStructure['packets']
        if not commandComponent == '':
            commandBasePath = cfgLoader.getPath(f'commandDefinitions/{commandComponent}.cd')
            with open(commandBasePath, 'r') as f:
                commandsDict = json.load(f)
            for command,commandDict in commandsDict.items():
                commandItem = CommandItem(self.ui.commandList,command,commandDict)

        else:
            commandItem = CommandItem(self.ui.commandList,self.commandStructure,{'commandName':""})

    def populateArgumentTable(self):
        self.ui.argumentTable.clearContents()
        self.ui.argumentTable.setRowCount(0)
        self.fieldItems = []
        self.componentIndex = 0
        if self.validatingArgs:
            self.validatingArgs = False
            self.ui.argumentTable.itemChanged.disconnect()

        if self.ui.commandList.currentItem() == None:
            return
        commandItem = self.ui.commandList.currentItem()
        self.commandId = commandItem.commandID

        self.addStaticComponents('headers')
        if 'arguments' in commandItem.commandDict:
            self.fieldItems.append([])
            for argDict in commandItem.commandDict['arguments']:
                self.fieldItems[self.componentIndex].append(FieldItem(argDict,self.ui.argumentTable,True,self.relevantFields))
            self.componentIndex += 1
        self.addStaticComponents('footers')

        if not 'arguments' in commandItem.commandDict:
            self.ui.showNoncommandFieldsCheckbox.setChecked(True)
        else:
            self.ui.showNoncommandFieldsCheckbox.setChecked(False)


        #embed commandId in its appropriate location 
        if 'packedIdField' in self.commandStructure:
            componentIndex = self.commandStructure['packetIdField']['componentIndex']
            fieldIndex = self.commandStructure['packetIdField']['fieldIndex']
            self.fieldItems[componentIndex][fieldIndex].valueCell.setText(str(commandItem.commandID))
        
        if not self.validatingArgs:
            self.validatingArgs = True
            self.ui.argumentTable.itemChanged.connect(self.validateField)

        #autofill here
        if startingConfig['autofillCommands']:
            commandFieldList = []
            for comp in self.fieldItems:
                for field in comp:
                    commandFieldList.append(field.argDict)

            filledCommandFieldList = self.autofiller.autofillAllFields(commandFieldList)
            i=0
            for comp in self.fieldItems:
                for fieldItem in comp:
                    fieldItem.argDict = filledCommandFieldList[i]
                    i += 1
                    if 'autofill' in fieldItem.argDict:
                        fieldItem.valueCell.setText(str(fieldItem.argDict['value']))

        self.validateAllFields()
        self.checkAllFieldsValid()

    def hiddenFields(self):
        if self.ui.showNoncommandFieldsCheckbox.isChecked():
            for component in self.fieldItems:
                for fieldItem in component:
                    row = fieldItem.typeCell.row()
                    self.ui.argumentTable.setRowHidden(row,False)
        else:
            for component in self.fieldItems:
                for fieldItem in component:
                    if not fieldItem.commandItem:
                        row = fieldItem.typeCell.row()
                        self.ui.argumentTable.setRowHidden(row,True)


    def addStaticComponents(self,side):
        for commandComponent in self.commandStructure[side]:
            self.fieldItems.append([])
            componentPath = cfgLoader.getPath(f'commandDefinitions/{commandComponent}.hd')
            with open(componentPath,'r') as f:
                componentDict = json.load(f)
            for fieldDict in componentDict['fields']:
                self.fieldItems[self.componentIndex].append(FieldItem(fieldDict,self.ui.argumentTable,False,self.relevantFields))
                if not self.ui.showNoncommandFieldsCheckbox.isChecked():
                    self.ui.argumentTable.setRowHidden(self.ui.argumentTable.rowCount()-1,True)
            self.componentIndex += 1

    def validateAllFields(self):
        for row in range(self.ui.argumentTable.rowCount()):
            valueItem = self.ui.argumentTable.item(row,2)
            self.validateField(valueItem)

    def validateField(self,tableItem):
        if not tableItem.column() == 2:
            return
        self.ui.argumentTable.itemChanged.disconnect()
        row = tableItem.row()
        type_ = self.ui.argumentTable.item(row,1).text()
        if not self.packetDefLib.validateValue(type_,tableItem.text()):
            for col in range(self.ui.argumentTable.columnCount()):
                self.ui.argumentTable.item(row,col).setBackground(ERROR_COLOR)
        else:
            for col in range(self.ui.argumentTable.columnCount()):
                self.ui.argumentTable.item(row,col).setBackground(QBrush())

        self.ui.argumentTable.itemChanged.connect(self.validateField)
        self.checkAllFieldsValid()

               
    def checkAllFieldsValid(self):
        self.ui.okButton.setEnabled(True)
        self.errorRows = []
        for row in range(self.ui.argumentTable.rowCount()):
            color = self.ui.argumentTable.item(row,0).background().color()
            if color == ERROR_COLOR:
                self.ui.okButton.setEnabled(False)
                self.errorRows.append(row)
                      
    def returnCommand(self):
        #wrap up and return entire command
        knownTypeSizes = {
            "uint":0,
            "int":0,
            "uint8_t":8,
            "uint16_t":16,
            "uint32_t":32,
            "uint64_t":64,
            "uint128_t":128,
            "int8_t":8,
            "int16_t":16,
            "int32_t":32,
            "int64_t":64,
            "int128_t":128,
            "float":32,
            "double":64,
            "char":8
        }
        commandList = []
        for component in self.fieldItems:
            for item in component:
                fieldType = item.typeCell.text()
                value = item.valueCell.text()
                bitLength = item.argDict.get('bitLength', knownTypeSizes[fieldType])

                if fieldType == 'char':
                    bitstring = format(ord(value), '08b')
                elif fieldType in ('float', 'double'):
                    format_ = '>f' if fieldType == 'float' else '>d'
                    bitstring = ''.join(
                        format(byte, '08b')
                        for byte in struct.pack(format_, float(value))
                    )
                else:
                    convertedValue = int(value)
                    if bitLength:
                        bitstring = format(
                            convertedValue & ((1 << bitLength) - 1),
                            f'0{bitLength}b'
                        )
                    else:
                        bitstring = format(convertedValue, 'b')
                item.argDict['value'] = value
                item.argDict['bitstring'] = bitstring
                if self.relevantFields:
                    item.argDict['relevant'] = True if item.fieldCell.checkState() == Qt.CheckState.Checked else False
                commandList.append(item.argDict)
        self.commandList = commandList
        self.accept()


