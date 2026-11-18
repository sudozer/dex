from PySide6.QtCore import Slot, Qt

from PySide6.QtWidgets import (
    QListWidgetItem,
    QTableWidgetItem,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QLineEdit,
    QWidget,
    QHBoxLayout,
    QDialog,
    QWidget,
)

from commandBuilder import CommandBuilder, CommandStructureDialog
from telemetrySelector import TelemetryFieldSelector
from timestampDialog import TimestampDialog

class DataWindowItem(QTableWidgetItem):
    def __init__(self,parentTable,config=None):
        super().__init__("Data Window")
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(Qt.CheckState.Checked)
        self.openOptions = QComboBox()
        self.closeOptions = QComboBox()
        self.openOptions.addItems(['On Command','On Telemetry'])
        self.closeOptions.addItems(['On Command','On Telemetry','Duration (s)'])
        
        self.parentTable = parentTable
        row = self.parentTable.rowCount()
        self.parentTable.insertRow(row)
        self.parentTable.setItem(row,0,self)
        self.parentTable.setCellWidget(row,1,self.openOptions)
        self.parentTable.setCellWidget(row,3,self.closeOptions)
        self.setOpenOptions()
        self.setCloseOptions()
        if not config is None:
            self.config = config
            self.readConfig()

        self.openOptions.currentTextChanged.connect(self.setOpenOptions)
        self.closeOptions.currentTextChanged.connect(self.setCloseOptions)

    @Slot()
    def setOpenOptions(self):
        match self.openOptions.currentText():
            case "On Command":
                self.openCommandButton = QPushButton("Command")
                self.openCommandButton.clicked.connect(self.openCommandSelect)
                self.parentTable.setCellWidget(self.row(),2,self.openCommandButton)
            case "On Telemetry":
                self.openTlmValWidget = QWidget()
                self.openTlmLayout = QHBoxLayout()
                self.openTlmLayout.setContentsMargins(4, 4, 4, 4)
                self.openTlmLayout.setSpacing(6)
                self.openTelemetryButton = QPushButton("Telemetry")
                self.openTelemetryButton.clicked.connect(self.openTelemetrySelect)
                self.openComparatorBox = QComboBox()
                self.openComparatorBox.addItems(['==','>=','<='])
                self.openValField = QLineEdit()
                self.openValField.setPlaceholderText("value")

                self.openTlmLayout.addWidget(self.openTelemetryButton)
                self.openTlmLayout.addWidget(self.openComparatorBox)
                self.openTlmLayout.addWidget(self.openValField)
                self.openTlmValWidget.setLayout(self.openTlmLayout)
                self.parentTable.setCellWidget(self.row(),2,self.openTlmValWidget)

    @Slot()
    def setCloseOptions(self):
        match self.closeOptions.currentText():
            case "On Command":
                self.closeCommandButton = QPushButton("Command")
                self.closeCommandButton.clicked.connect(self.closeCommandSelect)
                self.parentTable.setCellWidget(self.row(),4,self.closeCommandButton)
            case "On Telemetry":
                self.closeTlmValWidget = QWidget()
                self.closeTlmLayout = QHBoxLayout()
                self.closeTlmLayout.setContentsMargins(4, 4, 4, 4)
                self.closeTlmLayout.setSpacing(6)
                self.closeTelemetryButton = QPushButton("Telemetry")
                self.closeTelemetryButton.clicked.connect(self.closeTelemetrySelect)
                self.closeComparatorBox = QComboBox()
                self.closeComparatorBox.addItems(['==','>=','<='])
                self.closeValField = QLineEdit()
                self.closeValField.setPlaceholderText("value")

                self.closeTlmLayout.addWidget(self.closeTelemetryButton)
                self.closeTlmLayout.addWidget(self.closeComparatorBox)
                self.closeTlmLayout.addWidget(self.closeValField)
                self.closeTlmValWidget.setLayout(self.closeTlmLayout)
                self.parentTable.setCellWidget(self.row(),4,self.closeTlmValWidget)
            case "Duration (s)":
                self.closeDuration = QDoubleSpinBox()
                self.closeDuration.setRange(0,9999)
                self.closeDuration.setValue(0)
                self.parentTable.setCellWidget(self.row(),4,self.closeDuration)

    def openCommandSelect(self):
        cmdStructureSelect = CommandStructureDialog(self)
        if cmdStructureSelect.exec() == QDialog.Accepted:
            structure = cmdStructureSelect.structureBox.currentText()
            cmdSelect = CommandBuilder(structure,True)
            if cmdSelect.exec() == QDialog.Accepted:
                self.openCmdStructure = structure
                self.openCmdId = cmdSelect.commandId
                self.openCommandList = [field for field in cmdSelect.commandList if field['relevant']]
    
    def closeCommandSelect(self):
        cmdStructureSelect = CommandStructureDialog(self)
        if cmdStructureSelect.exec() == QDialog.Accepted:
            structure = cmdStructureSelect.structureBox.currentText()
            cmdSelect = CommandBuilder(structure,True)
            if cmdSelect.exec() == QDialog.Accepted:
                self.closeCmdStructure = structure
                self.closeCmdId = cmdSelect.commandId
                self.CloseCommandList = [field for field in cmdSelect.commandList if field['relevant']]
    
    def openTelemetrySelect(self):
        tlmSelector = TelemetryFieldSelector()
        if tlmSelector.exec() == QDialog.Accepted:
            self.openTelemetryButton.setText(tlmSelector.returnSelection)
            self.openTelemetryField = tlmSelector.returnDict
    
    def closeTelemetrySelect(self):
        tlmSelector = TelemetryFieldSelector()
        if tlmSelector.exec() == QDialog.Accepted:
            self.closeTelemetryButton.setText(tlmSelector.returnSelection)
            self.closeTelemetryField = tlmSelector.returnDict
    
    def readConfig(self):
        self.openOptions.setCurrentText(self.config['open']['option'])
        self.closeOptions.setCurrentText(self.config['close']['option'])
        self.setOpenOptions()
        self.setCloseOptions()
        self.setText(self.config['label'])

        match self.openOptions.currentText():
            case "On Command":
                self.openCmdStructure = self.config['open']['commandStructure']
                self.openCmdId = self.config['open']['commandId']
                self.openCommandList = self.config['open']['commandList']
            case "On Telemetry":
                self.openTelemetryButton.setText(self.config['open']['tlmString'])
                self.openComparatorBox.setcurrentText(self.config['open']['comparator'])
                self.openValField.setText(str(self.config['open']['value']))

        match self.closeOptions.currentText():
            case "On Command":
                self.closeCmdStructure = self.config['close']['commandStructure']
                self.closeCmdId = self.config['close']['commandId']
                self.closeCommandList = self.config['close']['commandList']
            case "On Telemetry":
                self.closeTelemetryButton.setText(self.config['close']['tlmString'])
                self.closeComparatorBox.setcurrentText(self.config['close']['comparator'])
                self.closeValField.setText(str(self.config['close']['value']))
            case "Duration (s)":
                self.closeDuration.setValue(self.config['close']['duration'])

class ExportFieldItem(QTableWidgetItem):
    def __init__(self,timestamp = False):
        self.timestamp = timestamp

    