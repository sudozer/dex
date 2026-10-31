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
    QTableWidgetItem,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QDateTimeEdit
)
import pdb

from dataStructures import PACKET_STRUCTURE_COMPONENTS
from loadConfig import Configs
cfgLoader = Configs()

class FieldItem(QTreeWidgetItem):
    def __init__(self, parent, fieldName):
        self.fieldName = fieldName
        super().__init__(parent)
        self.setText(0, fieldName)

class PacketItem(QTreeWidgetItem):
    def __init__(self, parent, packetName, packetList):
        super().__init__(parent)
        self.setText(0, packetName)
        for component in packetList:
            componentName = component['component']
            fieldList = component['fields']
            for field in fieldList:
                fieldItem = FieldItem(self, f"{componentName}.{field['fieldName']}")

class StructureItem(QTreeWidgetItem):
    def __init__(self,parent,structureName,structureDict):
        super().__init__(parent)
        self.setText(0,structureName)
        for packetName,packet in structureDict.items():
            packetItem = PacketItem(self,packetName,packet)


class TelemetryFieldSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__()

        # Load the UI from the .ui file
        loader = QUiLoader()
        self.guiPath = cfgLoader.getPath('apps/telemetrySelector/ui/telemetrySelector.ui')
        ui_file = QFile(self.guiPath)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file, self)
        ui_file.close()

        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)
        self.setModal(True)
        self.ui.okButton.clicked.connect(self.accept)
        self.ui.okButton.setEnabled(False)
        # Populate the tree widget with telemetry fields
        self.populateTelemetryFields()
        self.setWindowTitle("Select Telemetry Field")
        self.ui.telemetryTree.setHeaderHidden(True)
        self.ui.telemetryTree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.telemetryTree.itemClicked.connect(self.onItemClicked)
        self.show()

    def populateTelemetryFields(self):
        for structureName, structureDict in PACKET_STRUCTURE_COMPONENTS.items():
            structureItem = StructureItem(self.ui.telemetryTree, structureName, structureDict)

    def onItemClicked(self, item):
        if isinstance(item, FieldItem):
            self.selectedField = item.text(0)
            self.selectedPacket = item.parent().text(0)
            self.selectedStructure = item.parent().parent().text(0)
            self.returnSelection = f"{self.selectedStructure}.{self.selectedPacket}.{self.selectedField}"
            #field returns in the form telemetryStructure.packet.component.field
            self.ui.okButton.setEnabled(True)
        else:
            #packet item selected
            self.selectedField = None
            self.selectedPacket = None
            self.ui.okButton.setEnabled(False)