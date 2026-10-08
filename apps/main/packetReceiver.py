from PySide6.QtCore import Qt

from PySide6.QtWidgets import(
    QTableWidgetItem,
    QComboBox,
    QAbstractSpinBox,
    QSpinBox,
    QPushButton
)

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig
STARTINGCONFIG = CONFIG()

class PacketReceiverItem(QTableWidgetItem):
    def __init__(self,parentTable,row,dexMain,initConfig = None):
        super().__init__()
        self.parentTable = parentTable
        self.dexMain = dexMain
        self.writeTelemetryConfig = self.dexMain.writeTelemetryConfig
        
        self.structureBox = QComboBox()
        for structure in CONFIG()['telemetryStructures']:
            self.structureBox.addItem(structure)

        self.protocolBox = QComboBox()
        self.protocolBox.addItems(["UDP","TCP Client", "TCP Server"])

        self.portField = QSpinBox()
        self.portField.setRange(1,65535)
        self.portField.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        self.listenButton = QPushButton("Begin Listening")
        self.listenButton.setEnabled(False)
        self.listenButton.clicked.connect(self.startListening)
        
        self.portField.valueChanged.connect(self.writeTelemetryConfig)
        self.protocolBox.currentTextChanged.connect(self.writeTelemetryConfig)
        self.structureBox.currentTextChanged.connect(self.writeTelemetryConfig)

        self.packetsPerSecField = QTableWidgetItem('0.00')
        self.packetsPerSecField.setFlags(self.packetsPerSecField.flags() & ~Qt.ItemFlag.ItemIsEditable)
        
        self.parentTable.insertRow(row)
        self.parentTable.setItem(row,0,self)
        self.parentTable.setCellWidget(self.row(),0,self.structureBox)
        self.parentTable.setCellWidget(self.row(),1,self.protocolBox)
        self.parentTable.setCellWidget(self.row(),2,self.portField)
        self.parentTable.setCellWidget(self.row(),3,self.listenButton)
        self.parentTable.setItem(self.row(),4,self.packetsPerSecField)
        if not initConfig == None:
            self.initConfig = initConfig
            self.initializeFromConfig()

    def initializeFromConifg(self):
        pass

    def startListening(self):
        self.listening = True
        #spawn listener and write to telemetry database

        self.writeTelemetryConfig

    def stopListening(self):
        pass