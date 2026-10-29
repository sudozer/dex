from PySide6.QtCore import Qt, QThread, Signal, Slot
import pdb
import threading
from PySide6.QtWidgets import(
    QWidget,
    QTableWidgetItem,
    QComboBox,
    QHBoxLayout,
    QAbstractSpinBox,
    QSpinBox,
    QLineEdit,
    QLabel,
    QPushButton
)
from PySide6.QtGui import QIcon

import time

from loadConfig import cfgLoader, GLOBAL_CONFIG
from packetReceiver import PktReceiver
from structureDisplay import StructureDisplay
from guiProcess import launch_gui_process

COUNTER_UPDATE_DWELL = 2

class UpdateCountersThread(QThread):
    newValue = Signal(float,str)
    def __init__(self,receiverItem):
        super().__init__()
        self.receiverItem = receiverItem

    def run(self):
        self._running = True
        prevPackets = 0
        while self.receiverItem.listening.is_set():
        
            accepted = self.receiverItem.receiver.processor.acceptedPackets
            rejected = self.receiverItem.receiver.processor.rejectedPackets
            currentTotalPackets = accepted + rejected
            packetsPerSec = (currentTotalPackets - prevPackets) / COUNTER_UPDATE_DWELL

            self.newValue.emit(packetsPerSec,f"{accepted}/{rejected}")
            time.sleep(COUNTER_UPDATE_DWELL)
            prevPackets = currentTotalPackets
        self.newValue.emit(0.0,f"{accepted}/{rejected}")
        self._running = False

class PacketReceiverItem(QTableWidgetItem):
    def __init__(self,parentTable,row,dexMain,initConfig = None):
        self.parentTable = parentTable
        self.dexMain = dexMain
        self.parentTable.itemChanged.disconnect()
        super().__init__("New Receiver")

        self.structureViewer = None
        self.writeTelemetryConfig = self.dexMain.writeTelemetryConfig
        self.receiver = None
        self.listening = threading.Event()
        self.structureBox = QComboBox()
        for structure in GLOBAL_CONFIG['telemetryStructures']:
            self.structureBox.addItem(structure)

        self.protocolBox = QComboBox()
        self.protocolBox.addItems(["UDP","TCP Client", "TCP Server"])

        self.ipField = QLineEdit()
        self.ipField.setText("127.0.0.1")
        self.ipField.setEnabled(False)

        self.slashLabel = QLabel("/")

        self.portField = QSpinBox()
        self.portField.setRange(1,65535)
        self.portField.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5,2,5,2)
        layout.setSpacing(5)
        layout.addWidget(self.ipField)
        layout.addWidget(self.slashLabel)
        layout.addWidget(self.portField)

        self.listenButton = QPushButton("Listen")
        self.listenButton.clicked.connect(self.startListening)
        self.packetDisplayButton = QPushButton()
        self.packetDisplayButton.setIcon(QIcon(str(cfgLoader.getPath("graphics/listIcon.png"))))
        self.packetDisplayButton.clicked.connect(self.launchStructureDisplay)
        self.packetDisplayButton.setMaximumWidth(30)
        self.buttonWidget = QWidget()
        self.buttonLayout = QHBoxLayout(self.buttonWidget)
        self.buttonLayout.setContentsMargins(5,2,5,2)
        self.buttonLayout.setSpacing(5)
        self.buttonLayout.addWidget(self.listenButton)
        self.buttonLayout.addWidget(self.packetDisplayButton)
        self.buttonLayout.setStretch(6,1)

        self.packetsPerSecField = QTableWidgetItem('0.00')
        self.packetsPerSecField.setFlags(self.packetsPerSecField.flags() & ~Qt.ItemFlag.ItemIsEditable)
        
        self.countersField = QTableWidgetItem('0/0')
        self.countersField.setFlags(self.countersField.flags() & ~Qt.ItemFlag.ItemIsEditable)
        
        self.parentTable.insertRow(row)
        self.parentTable.setItem(row,0,self)
        self.parentTable.setCellWidget(self.row(),1,self.structureBox)
        self.parentTable.setCellWidget(self.row(),2,self.protocolBox)
        self.parentTable.setCellWidget(self.row(),3,container)
        self.parentTable.setCellWidget(self.row(),4,self.buttonWidget)
        self.parentTable.setItem(self.row(),5,self.packetsPerSecField)
        self.parentTable.setItem(self.row(),6,self.countersField)

        self.updateThread = None
        if not initConfig == None:
            self.initConfig = initConfig
            self.initializeFromConfig()

        self.portField.editingFinished.connect(self.writeTelemetryConfig)
        self.protocolBox.currentTextChanged.connect(self.protocolChanged)
        self.structureBox.currentTextChanged.connect(self.writeTelemetryConfig)

        self.parentTable.resizeColumnsToContents()
        self.parentTable.itemChanged.connect(self.writeTelemetryConfig)

    def initializeFromConfig(self):
        self.setText(self.initConfig['label'])
        self.structureBox.setCurrentText(self.initConfig['telemetryStructure'])
        self.protocolBox.setCurrentText(self.initConfig['protocol'])
        self.portField.setValue(self.initConfig['port'])
        if self.protocolBox.currentText() == 'TCP Client':
            self.ipField.setEnabled(True)
            self.ipField.setText(self.initConfig['IP'])
        if self.initConfig['listening'] and GLOBAL_CONFIG.get("telemetryLaunchReceiversOnStartup",False):
            self.startListening()

    def protocolChanged(self):
        if self.protocolBox.currentText() == "TCP Client":
            self.ipField.setText("")
            self.ipField.setEnabled(True)
        else:
            self.ipField.setText("127.0.0.1")
            self.ipField.setEnabled(False)
        self.writeTelemetryConfig()
    
    def startListening(self):
        self.listenButton.setEnabled(False)
        self.enableControls(False)
        self.listening.set()
        #spawn listener and write to telemetry database
        self.receiverDict = self.writeTelemetryConfig()[self.row()]
        self.receiver = PktReceiver(self.receiverDict,self.dexMain.telemetryMessage,self.listening)
        self.counterUpdater = UpdateCountersThread(self)
        self.counterUpdater.newValue.connect(self.updateCounters)
        self.counterUpdater.start()
        self.listenButton.setText("Stop")
        self.listenButton.clicked.disconnect()
        self.listenButton.clicked.connect(self.stopListening)
        self.listenButton.setEnabled(True)
        self.dexMain.activeTelemetryReceivers.append(self)

    def enableControls(self,enable):
        self.protocolBox.setEnabled(enable)
        self.ipField.setEnabled(enable)
        self.portField.setEnabled(enable)
        self.structureBox.setEnabled(enable)

    def stopListening(self):
        self.listening.clear()
        self.receiver.closeAll()
        self.listenButton.setText("Listen")
        self.listenButton.clicked.disconnect()
        self.listenButton.clicked.connect(self.startListening)
        self.counterUpdater.wait()
        self.dexMain.activeTelemetryReceivers.remove(self)
        self.writeTelemetryConfig()
        self.enableControls(True)

    @Slot(float,str)
    def updateCounters(self,packetsPerSec,count_):
        self.packetsPerSecField.setText(str(packetsPerSec))
        self.countersField.setText(count_)

    def launchStructureDisplay(self):
        structure = self.structureBox.currentText()
        self.structureViewer = launch_gui_process(StructureDisplay, structure)
