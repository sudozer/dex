from PySide6.QtCore import QFile,QRunnable, QThread, QObject, Qt, QDateTime, QTimeZone,Signal,Slot,QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QWidget,
    QHBoxLayout
)
import datetime

from liveTelemetry import LIVETLM
from loadConfig import GLOBAL_CONFIG

STALE = "(80,80,80)"
class ValueFetch(QObject):
    valueUpdate = Signal(dict,str)
    def __init__(self,telemetryField,refreshDelay):
        super().__init__(telemetryField)
        self.telemetryField = telemetryField
        self.packet = self.telemetryField.packet
        self.field = self.telemetryField.field
        self.valueUpdate.connect(self.telemetryField.updateValue)
        if refreshDelay > 0:
            #self-manage an updating thread
            self.updateTimer = QTimer(self)
            self.updateTimer.timeout.connect(self.fetchValue)
            self.updateTimer.start(refreshDelay * 1000)
        else:
            LIVETLM.registerCallback(self.packet,self.fetchValue)

    @Slot()
    def fetchValue(self):
        #print(LIVETLM.mostRecentPacket)
        try:
            newField = LIVETLM.mostRecentPacket[self.packet][self.field]
            updateTime = LIVETLM.mostRecentPacket[self.packet]['metadata_']['groundTimestampUTC']
            self.valueUpdate.emit(newField,updateTime)
        except:
            pass
        

class TelemetryField(QWidget):
    def __init__(self,packet,field,timerOverride = None):
        super().__init__()
        self.running = True
        self.packet = packet
        self.field = field
        self.prevField = field
        self.timerOverride = timerOverride
        self.nameLabel = QLabel(field['fieldName'])
        self.valueLabel = QLabel("N/A")
        self.valueLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lastUpdate = "N/A"
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4,4,4,4)
        self.layout.setSpacing(4)
        self.layout.addWidget(self.nameLabel)
        self.layout.addWidget(self.valueLabel)
        self.stale = True
        self.previousValue = None
        self.currentValue = None
        self.setStale()

        self.setRetrievalThread()

    def setRetrievalThread(self):
        if self.timerOverride == None:
            if GLOBAL_CONFIG['fieldDisplayUpdateDelay'] < 1:
                #just register fetcher to LIVETLM callback registry
                self.fetcher = ValueFetch(self,0)
            else:
                self.fetcher = ValueFetch(self,GLOBAL_CONFIG['fieldDisplayUpdateDelay'])
        else:
            self.fetcher = ValueFetch(self,self.timerOverride)

    @Slot()
    def updateValue(self,valueField,dateTime):
        self.prevField = self.field
        self.field = valueField
        self.lastUpdate = dateTime
        #calculate if data is stale
        self.updateDisplay()

    def updateDisplay(self):
        self.valueLabel.setText(self.field.get('convertedValue',self.field['rawvalue']))
        toolTipString = f"""
        Raw Value:\t\t{self.field['rawValue']}\n
        Converted Value:\t\t{self.field.get('convertedValue',"None")}\n
        Previous Value:\t\t{self.prevField.get('convertedValue',self.prevField.get('rawvalue',"N/A"))}\n
        Conversion Function:\t\t{self.field.get("conversion","None").get("conversionFuncion","None")}\n
        Packet Last Received:\t\t{self.lastUpdate}\n
        Double-click to graph.
        """
        self.setToolTip(toolTipString)
        self.setStale()

    def setStale(self):
        if self.stale:
            self.valueLabel.setStyleSheet(f"color:rgb{STALE}")
        else:
            self.valueLabel.setStyleSheet("color:black")

    def mouseDoubleClickEvent(self,event):
        #graph
        pass
