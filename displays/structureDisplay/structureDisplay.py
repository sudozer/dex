
import datetime

from PySide6.QtCore import QTimer
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
from loadConfig import GLOBAL_CONFIG
import pdb

UPDATE_PACKET_META_STATS_SECONDS = 2  #how often the packets received and last received fields update

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

        self.metaStatsTimer = QTimer(self.page)
        self.metaStatsTimer.timeout.connect(self.metaUpdate)
        self.metaStatsTimer.start(
            max(1, int(UPDATE_PACKET_META_STATS_SECONDS * 1000))
        )

    def metaUpdate(self):
        packet = LIVETLM.mostRecentPacket.get(self.packetName)
        if packet is None:
            return

        metadata = packet.get('metadata_')
        if metadata is None:
            return

        packets_received = metadata.get('packetsOfThisTypeReceived')
        if packets_received is not None:
            self.packetsReceivedLabel.setText(
                f"Packets Received: {packets_received}"
            )

        last_packet_receipt = metadata.get('groundTimestampUTC')
        if last_packet_receipt is not None:
            packet_time = datetime.datetime.strptime(
                last_packet_receipt,
                GLOBAL_CONFIG['datetimeFormat'],
            ).replace(tzinfo=datetime.UTC)
            seconds_ago = max(
                0,
                int((datetime.datetime.now(datetime.UTC) - packet_time).total_seconds()),
            )
            self.lastPacketReceiptLabel.setText(
                f"Last Packet Received: {seconds_ago} seconds ago"
            )

class StructureDisplay(QWidget):
    def __init__(self, structure, telemetry_queue=None):
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
        if telemetry_queue is not None:
            LIVETLM.listenToQueue(telemetry_queue)
        self.show()
    
    def addPacketTabs(self):
        #create a tab for each packet type that can be transmitted
        for packetName,packet in self.structure.items():
            self.tabObjects.append(PacketTab(self,packetName,packet))

# if __name__ == "__main__":
#     app = QApplication([])
#     structureDisplay = StructureDisplay("sampleStructure1")
#     app.exec()