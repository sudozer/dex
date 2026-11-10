from PySide6.QtCore import QFile, QDateTime, QTimeZone, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QListWidgetItem,
    QCalendarWidget,
    QDialog,
    QVBoxLayout,
    QDateTimeEdit
)

from datetime import datetime, timezone
from loadConfig import cfgLoader, GLOBAL_CONFIG
from telemetryRetrieval import retrieveAllDatatags

MAX_DATATAGS = 100

CMD_COLOR=QColor(80,242,204)
SYS_COLOR=QColor(247,232,163)
MAN_COLOR=QColor(245,125,165)
TLM_COLOR=QColor(109,185,247)

def spawnDatatagViewer(destinationWidget,database = None):
    datatagViewer = DatatagView(destinationWidget,database)
    if datatagViewer.exec() == QDialog.Accepted:
        pass

class DatatagItem(QListWidgetItem):
    def __init__(self,datatag,listWidget):
        self.listWidget = listWidget
        self.datatag = datatag
        self.time_ = datetime.fromtimestamp(datatag[0], tz = timezone.utc)
        strTime = self.time_.isoformat(timespec='seconds')
        super().__init__(listWidget)
        self.setText(f"{strTime} :: {datatag[2]}")
        match datatag[1]:
            case "SYS":
                self.setBackground(SYS_COLOR)
            case "CMD":
                self.setBackground(CMD_COLOR)
            case "TLM":
                self.setBackground(TLM_COLOR)
            case "MAN":
                self.setBackground(MAN_COLOR)
            case _:
                pass

class DatatagView(QDialog):
    returnSelection = Signal(QDateTime)
    def __init__(self,destinationWidget,database = None):
        super().__init__()
        loader = QUiLoader()
        self.guiPath = cfgLoader.getPath('apps/datatagView/ui/datatagView.ui')
        ui_file = QFile(self.guiPath)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file, self)
        ui_file.close()
        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)
        self.setModal(True)
        self.ui.okButton.clicked.connect(self.returnDate)
        self.database = database
        self.populateDatabaseBox()
        self.ui.datatagList.itemClicked.connect(self.populateDateTimeField)
        self.ui.selectedDatetime.setTimeZone(QTimeZone.utc())
        self.ui.selectedDatetime.setDisplayFormat(GLOBAL_CONFIG['qtDateFormat'])
        self.returnSelection.connect(destinationWidget.setDateTime)

        self.ui.commandCheckBox.checkStateChanged.connect(self.filterDatatagsByType)
        self.ui.telemetryCheckBox.checkStateChanged.connect(self.filterDatatagsByType)
        self.ui.systemCheckBox.checkStateChanged.connect(self.filterDatatagsByType)
        self.ui.manualCheckBox.checkStateChanged.connect(self.filterDatatagsByType)

    def populateDatabaseBox(self):
        self.ui.selectedDatabaseBox.clear()
        databasePath = cfgLoader.getPath('databases')
        databases = [x.name for x in databasePath.iterdir() if x.is_file()]
        self.ui.selectedDatabaseBox.addItems(databases)
        if not self.database == None:
            self.ui.selectedDatabaseBox.setCurrentText(self.database)
            self.ui.selectedDatabaseBox.setEnabled(False)
        self.ui.selectedDatabaseBox.currentTextChanged.connect(self.populateDataTags)
        self.populateDataTags()
        
    def populateDataTags(self):
        self.ui.datatagList.clear()
        self.datatagItems = []
        allDatatags = retrieveAllDatatags(self.ui.selectedDatabaseBox.currentText())
        if len(allDatatags) > MAX_DATATAGS:
            allDatatags = allDatatags[-(MAX_DATATAGS):]
        for datatag in allDatatags:
            self.datatagItems.append(DatatagItem(datatag,self.ui.datatagList))

    def filterDatatagsByType(self):
        typefilter = {
            "CMD":self.ui.commandCheckBox.isChecked(),
            "TLM":self.ui.telemetryCheckBox.isChecked(),
            "MAN":self.ui.manualCheckBox.isChecked(),
            "SYS":self.ui.systemCheckBox.isChecked()
        }
        for datatag in self.datatagItems:
            datatag.setHidden(not typefilter[datatag.datatag[1]])

    def populateDateTimeField(self,datatagItem):
        guiDateTime = QDateTime.fromMSecsSinceEpoch(datatagItem.datatag[0] * 1000)
        self.ui.selectedDatetime.setDateTime(guiDateTime)

    def returnDate(self):
        self.returnSelection.emit(self.ui.selectedDatetime.dateTime())
        self.accept()