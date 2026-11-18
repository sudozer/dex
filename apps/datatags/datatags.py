from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QLabel,
    QMessageBox,
    QListWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLineEdit,
    QPushButton,
)
import pdb
from loadConfig import GLOBAL_CONFIG, cfgLoader
from commandBuilder import CommandBuilder, CommandStructureDialog
from telemetrySelector import TelemetryFieldSelector
from dataStructures import COMMAND_STRUCTURE_COMPONENTS, PACKET_STRUCTURE_COMPONENTS


def convertTelemetryValue(value, fieldType):
    if fieldType == "char":
        return value
    if fieldType in ("float", "double"):
        return float(value)
    if fieldType in ("int", "uint") or fieldType.endswith("_t"):
        return int(value)
    raise ValueError(f"Unsupported telemetry field type {fieldType!r}.")

class CommandItem(QTreeWidgetItem):
    def __init__(self, command, commandId, parent):
        super().__init__(parent)
        self.command = command
        self.commandId = commandId
        self.parentItem = parent
        cmdText = f"{self.commandId}: "
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
    def __init__(self, telemetryField):
        super().__init__()
        self.telemetryField = telemetryField
        self.containerWidget = QWidget()
        self.layout = QHBoxLayout()
        self.fieldLabel = QLabel(f"{telemetryField['packet']}.{telemetryField['field']}")
        self.comparatorBox = QComboBox()
        self.comparatorBox.addItems(['=','>=','<='])
        self.valueField = QLineEdit()
        self.valueField.setPlaceholderText("value")
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.addWidget(self.fieldLabel)
        self.layout.addWidget(self.comparatorBox)
        self.layout.addWidget(self.valueField)
        self.containerWidget.setLayout(self.layout)
        self.setSizeHint(self.containerWidget.sizeHint())

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
        self.ui.addTelemetryButton.clicked.connect(self.addTelemetry)
        self.ui.removeTelemetryButton.clicked.connect(self.removeTelemetry)
        self.ui.okButton.clicked.connect(self.writeConfig)
        self.ui.tagAllCommandsBox.stateChanged.connect(self.setCommandLabel)
        self.setWindowTitle("Configure Automatic Datatags")
        self.telemetryItems = []
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
        commandDict = {}
        for structureName,structureItem in self.structureItems.items():
            commandDict[structureItem.structure]={}
            for command in structureItem.commands:
                if not command.commandId in commandDict[structureItem.structure]:
                    commandDict[structureItem.structure][command.commandId] = [command.command]
                else:
                    commandDict[structureItem.structure][command.commandId].append(command.command)

        telemetry = []
        for item in self.telemetryItems:
            rawValue = item.valueField.text()
            if not rawValue:
                continue

            telemetryField = item.telemetryField
            fieldDefinition = None
            for component in PACKET_STRUCTURE_COMPONENTS[telemetryField["structure"]][telemetryField["packet"]]:
                for field in component["fields"]:
                    if f'{component["component"]}.{field["fieldName"]}' == telemetryField["field"]:
                        fieldDefinition = field
                        break
                if fieldDefinition is not None:
                    break

            if fieldDefinition is None:
                QMessageBox.warning(
                    self,
                    "Invalid telemetry field",
                    f"Could not find definition for {telemetryField['field']}.",
                )
                return

            fieldType = fieldDefinition.get("conversion", {}).get(
                "convertedType", fieldDefinition["type"]
            )
            try:
                value = convertTelemetryValue(rawValue, fieldType)
            except (TypeError, ValueError, OverflowError) as error:
                QMessageBox.warning(
                    self,
                    "Invalid telemetry value",
                    f"{rawValue!r} is not a valid {fieldType} value for "
                    f"{telemetryField['field']}: {error}",
                )
                return

            tDict = {
                "comparator": item.comparatorBox.currentText(),
                "value": value,
            }
            tDict.update(telemetryField)
            telemetry.append(tDict)
                
        dataTagCfg = {
            "tagStartup":self.ui.tagStartupBox.isChecked(),
            "tagShutdown":self.ui.tagShutdownBox.isChecked(),
            "tagAllCommands":self.ui.tagAllCommandsBox.isChecked(),
            "commands":commandDict,
            "telemetry":telemetry,
        }
        GLOBAL_CONFIG['storage']['dataTags'] = dataTagCfg
        cfgLoader.configWrite(GLOBAL_CONFIG)
        self.accept()

    def populateCommandList(self):
        self.structureItems = {}
        for structure in COMMAND_STRUCTURE_COMPONENTS.keys():
            self.structureItems[structure] = CommandStructureItem(structure,self.ui.commandTagTree)

        for structureName,structure in self.dataTagCfg['commands'].items():
            for commandId,commandIdList in structure.items():
                for command in commandIdList:
                    self.addCommandItem(structureName, commandId, command)
        
    def populateTelemetryList(self):
        for tlmItem in self.dataTagCfg['telemetry']:
            newTelemetry = TelemetryItem(tlmItem)
            self.telemetryItems.append(newTelemetry)
            self.ui.telemetryList.addItem(newTelemetry)
            self.ui.telemetryList.setItemWidget(newTelemetry, newTelemetry.containerWidget)
            newTelemetry.comparatorBox.setCurrentText(tlmItem['comparator'])
            newTelemetry.valueField.setText(str(tlmItem['value']))

    def addCommand(self):
        structureSelector = CommandStructureDialog(self)
        if structureSelector.exec() == QDialog.Accepted:
            selectedStructure = structureSelector.structureBox.currentText()
            commandBuilder = CommandBuilder(selectedStructure, True)
            if commandBuilder.exec() == QDialog.Accepted:
                commandId = commandBuilder.commandId
                commandList = [field for field in commandBuilder.commandList if field['relevant']]
                # Add the selected command to the list
                self.addCommandItem(selectedStructure,commandId,commandList)

    def addCommandItem(self,structure, commandId, command):
        structureItem = self.structureItems[structure]
        structureItem.commands.append(CommandItem(command,commandId, structureItem))
        structureItem.setExpanded(True)

    def removeCommand(self):
        selectedCommand = self.ui.commandTagTree.currentItem() 
        if isinstance(selectedCommand,CommandItem):
            selectedCommand.parentItem.commands.remove(selectedCommand)
            selectedCommand.parentItem.removeChild(selectedCommand)

    def addTelemetry(self):
        telemetrySelector = TelemetryFieldSelector()
        if telemetrySelector.exec() == QDialog.Accepted:
            newTelemetry = TelemetryItem(telemetrySelector.returnDict)
            self.telemetryItems.append(newTelemetry)
            self.ui.telemetryList.addItem(newTelemetry)
            self.ui.telemetryList.setItemWidget(newTelemetry, newTelemetry.containerWidget)

    def removeTelemetry(self):
        selection = self.ui.telemetryList.currentItem()
        if selection is not None:
            self.telemetryItems.remove(selection)
            self.ui.telemetryList.takeItem(self.ui.telemetryList.currentRow())