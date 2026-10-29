from html import escape

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

STALE = "(140,140,140)"
class ValueFetch(QObject):
    valueUpdate = Signal(dict,str)
    def __init__(self,telemetryField,refreshDelay):
        super().__init__(telemetryField)
        self.telemetryField = telemetryField
        self.packet = self.telemetryField.packet
        self.fieldKey = self.telemetryField.fieldKey
        self.valueUpdate.connect(
            self.telemetryField.updateValue,
            Qt.ConnectionType.QueuedConnection,
        )
        if refreshDelay > 0:
            #self-manage an updating thread
            self.updateTimer = QTimer(self)
            self.updateTimer.timeout.connect(self.fetchValue)
            self.updateTimer.start(max(1, int(refreshDelay * 1000)))
        else:
            LIVETLM.registerCallback(self.packet,self.fetchValue)

    @Slot()
    def fetchValue(self):
        packet = LIVETLM.mostRecentPacket.get(self.packet)
        if packet is None:
            return
        newField = packet.get(self.fieldKey)
        metadata = packet.get('metadata_')
        if newField is None or metadata is None:
            return
        updateTime = metadata.get('groundTimestampUTC')
        if updateTime is not None:
            self.valueUpdate.emit(newField, updateTime)
        

class TelemetryField(QWidget):
    def __init__(self,packet,field,timerOverride = None):
        super().__init__()
        self.running = True
        self.packet = packet
        self.field = field
        self.fieldKey = f"{field['definitionSource']}__{field['fieldName']}"
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

    @Slot(dict, str)
    def updateValue(self,valueField,dateTime):
        self.prevField = self.field
        self.field = valueField
        self.lastUpdate = dateTime
        self.lastUpdateDateTime = datetime.datetime.strptime(dateTime,GLOBAL_CONFIG['datetimeFormat']).replace(tzinfo=datetime.UTC)
        self.updateDisplay()

    def updateDisplay(self):
        value = self.field.get('convertedValue', self.field.get('rawValue', "N/A"))
        self.valueLabel.setText(str(value))
        conversion = self.field.get("conversion")
        conversion_function = (
            conversion.get("conversionFuncion", "None")
            if isinstance(conversion, dict)
            else "None"
        )
        toolTipRows = [
            ("Raw Value:", self.field.get("rawValue", "N/A")),
            ("Converted Value:", self.field.get("convertedValue", "None")),
            (
                "Previous Value:",
                self.prevField.get(
                    "convertedValue",
                    self.prevField.get("rawValue", "N/A"),
                ),
            ),
            ("Conversion Function:", conversion_function),
            ("Packet Last Received:", self.lastUpdate),
        ]
        tooltipRowsHtml = "".join(
            "<tr>"
            f"<td align='left'>{escape(str(label))}</td>"
            f"<td>{'&nbsp;' * 4}</td>"
            f"<td align='right'>{escape(str(rowValue))}</td>"
            "</tr>"
            for label, rowValue in toolTipRows
        )
        toolTipString = (
            f"{escape(str(self.field['fieldName']))}<br>"
            "<table cellspacing='0' cellpadding='0'>"
            f"{tooltipRowsHtml}"
            "</table><br>"
            "Double-click to graph."
        )

        self.setToolTip(toolTipString)
        lastPacketSec = (datetime.datetime.now(datetime.UTC) - self.lastUpdateDateTime).seconds
        self.stale = lastPacketSec > GLOBAL_CONFIG['staleDataSeconds']
        self.setStale()

    def setStale(self):
        if self.stale:
            self.nameLabel.setStyleSheet(f"color:rgb{STALE}")
            self.valueLabel.setStyleSheet(f"color:rgb{STALE}")
        else:
            self.valueLabel.setStyleSheet("color:black")
            self.nameLabel.setStyleSheet("color:black")
    
    def mouseDoubleClickEvent(self,event):
        #graph
        pass
