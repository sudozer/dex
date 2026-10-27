from PySide6.QtCore import QFile,QRunnable, QThread, QObject, Qt, QDateTime, QTimeZone,Signal,Slot,QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QWidget,
    QHBoxLayout
)
from liveTelemetry import LIVETLM
from loadConfig import GLOBAL_CONFIG

class ValueFetch(QObject):
    valueUpdate = Signal(dict,str)
    def __init__(self,telemetryField,refreshDelay):
        self.telemetryField = telemetryField
        self.packet = self.telemetryField.packet
        self.field = self.telemetryField.field
        if refreshDelay > 0:
            #self-manage an updating thread
            self.updateTimer = QTimer()
            self.updateTimer.timeout.connect(self.updateValue)
            self.updateTimer.start(refreshDelay * 1000)
        else:
            LIVETLM.registerCallback(self.packet,self.updateValue)

    @Slot()
    def updateValue(self):
        newField = LIVETLM.mostRecentPacket[self.packet][self.field]
        updateTime = LIVETLM.mostRecentPacket[self.packet]['metadata_']['groundTimestampUTC']
        self.valueUpdate.emit(newField,updateTime)

class TelemetryField(QObject):
    def __init__(self,packet,field,timerOverride = None):
        super().__init__()
        self.running = True
        self.packet = packet
        self.field = field
        self.prevField = field
        self.timerOverride = timerOverride
        self.nameLabel = QLabel(field['fieldName'])
        self.valueLabel = QLabel("N/A")
        self.lastUpdate = "N/A"
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4,4,4,4)
        self.layout.setSpacing(4)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.value)
        self.stale = True
        self.previousValue = None
        self.currentValue = None

        self.setRetrievalThread()

    def setRetrievalThread(self):
        if self.timerOverride == None:
            if GLOBAL_CONFIG['fieldDisplayUpdateDelay'] < 1:
                #just register fetcher to LIVETLM callback registry
                self.fetcher = ValueFetch(self.packet,self.field,0)
                self.fetcher.valueUpdate.connect(self.updateValue)
                LIVETLM.registerCallback(self.packet,self.fetcher.run)
            else:
                self.updateTimer = QTimer(self)
                self.updateTimer.timeout.connect(self.fetcher.run)
        else:
            pass
            #override global timer with something else


    @Slot()
    def updateValue(self,valueField,dateTime):
        self.prevField = self.field
        self.field = LIVETLM.mostRecentPacket[self.packet][self.field['fieldName']]
        self.lastUpdate = LIVETLM.mostRecentPacket[self.packet]['metadata_']['groundTimestampUTC']
        #calculate if data is stale
        self.updateDisplay()

    def updateDisplay(self):
        self.valueLabel.setText(self.field.get('convertedValue',self.field['rawvalue']))
        toolTipString = f"""
        Raw Value:\t\t{self.field['rawValue']}\n
        Converted Value:\t\t{self.field.get('convertedValue',"None")}\n
        Conversion Function:\t\t{self.field.get("conversion","None").get("conversionFuncion","None")}\n
        Packet Last Received:\t\t{self.lastUpdate}\n
        Double-click to graph.
        """
        
    def registerLiveTlm(self):
        pass




        
