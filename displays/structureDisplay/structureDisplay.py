
from PySide6.QtWidgets import(
    QApplication,
    QWidget,
    QTabWidget,
    QLabel,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout
)

from telemetryDisplayField import TelemetryField
from dataStructures import PACKET_STRUCTURE_COMPONENTS
from liveTelemetry import LIVETLM
import pdb

PACKET_META_STATS_UPDATE = 2  #how often the packets received and last received fields update

class PacketTab():
    def __init__(self,structureDisplay,packetName,packet):
        self.structureDisplay = structureDisplay
        self.packetName = packetName
        self.packet = packet

        self.page = QWidget()
        self.pageLayout = QVBoxLayout()
        self.page.setLayout(self.pageLayout)
        self.structureDisplay.tabs.addTab(self.page,packetName)
        self.scrollWidget = QWidget()
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollLayout = QVBoxLayout(self.scrollWidget)
        self.pageLayout.addWidget(self.scrollArea)
        self.packetsReceivedLabel = QLabel("Packets Received: 0")
        self.lastPacketReceiptLabel = QLabel("Last Packet Received: N/A")
        self.scrollLayout.addWidget(self.packetsReceivedLabel)
        self.scrollLayout.addWidget(self.lastPacketReceiptLabel)
        self.packetFields = {}
        for component in packet:
            componentName = component['component']

            self.packetFields[componentName]=[]
            hline = QFrame()
            hline.setFrameShape(QFrame.Shape.HLine)
            hline.setFrameShadow(QFrame.Shadow.Sunken)
            self.scrollLayout.addWidget(hline)
            componentLabel = QLabel(componentName)
            font = componentLabel.font()
            font.setBold(True)
            componentLabel.setFont(font)
            self.scrollLayout.addWidget(componentLabel)
            
            for field in component['fields']:
                tField = TelemetryField(packetName,field)
                self.scrollLayout.addWidget(tField)
                self.packetFields[componentName].append(tField)

    def metaUpdate(self):
        #update packet count and packet latency timer
        pass


class StructureDisplay(QWidget):
    def __init__(self,structure):
        super().__init__()
        self.structureName = structure
        self.structure = PACKET_STRUCTURE_COMPONENTS[structure]
        self.setWindowTitle(f"{structure} Telemetry")
        self.tabs = QTabWidget(self)
        self.tabs.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.tabObjects = []
        self.addPacketTabs()
        self.show()
    
    def addPacketTabs(self):
        #create a tab for each packet type that can be transmitted
        for packetName,packet in self.structure.items():
            self.tabObjects.append(PacketTab(self,packetName,packet))

# if __name__ == "__main__":
#     app = QApplication([])
#     structureDisplay = StructureDisplay("sampleStructure1")
#     app.exec()