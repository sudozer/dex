
from PySide6.QtWidgets import(
    QWidget,
    QTabWidget,
    QLabel,
    QFrame,
    QHBoxLayout,
    QVBoxLayout
)

from telemetryDisplayField import TelemetryField
from dataStructures import PACKET_STRUCTURE_COMPONENTS
from liveTelemetry import LIVETLM

PACKET_META_STATS_UPDATE = 2  #how often the packets received and last received fields update

class PacketTab():
    def __init__(self,structureDisplay,packetName,packet):
        self.structureDisplay = structureDisplay
        self.packetName = packetName
        self.packet = packet

        self.page = QWidget()
        self.layout = QVBoxLayout()
        self.page.setLayout(self.layout)
        self.tabWidget.addTab(self.page,packetName)
        
        self.packetsReceivedLabel = QLabel("Packets Received: 0")
        self.lastPacketReceivedLabel = QLabel()
        
        self.packetFields = {}
        for componentName,component in packet.items():
            self.packetFields[componentName]=[]
            hline = QFrame()
            hline.setFrameShape(QFrame.Shape.HLine)
            hline.setFrameShadow(QFrame.Shadow.Sunken)
            self.layout.addWidget(hline)
            self.layout.addWidget(QLabel(componentName))
            
            for field in packet:
                self.packetFields[componentName].append(TelemetryField(packetName,field))

    def metaUpdate(self):
        #update packet count and packet latency timer
        pass


class StructureDisplay(QWidget):
    def __init__(self,structure,receiver):
        super().__init__()
        self.structureName = structure
        self.structure = PACKET_STRUCTURE_COMPONENTS[structure]
        self.receiver = receiver
        self.setWindowTitle(f"Packet Structure: {structure} Telemetry")
        self.tabs = QTabWidget()
        self.tabObjects = []
        self.addPacketTabs()
    
    def addPacketTabs(self):
        #create a tab for each packet type that can be transmitted
        for packetName,packet in self.structure.items():
            self.tabObjects.append(PacketTab(self.tabs,packetName,packet))