from html import escape

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QComboBox
)

from datetime import datetime, UTC, timedelta
from loadConfig import GLOBAL_CONFIG
UPDATE_CADENCE = 1.0

class UpdateThread(QObject):
    updateTime = Signal(datetime)

    def __init__(self):
        super().__init__()
        self.updateTimer = None

    @Slot()
    def start_(self):
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.emitTime)
        self.updateTimer.start(UPDATE_CADENCE * 1000)

    @Slot()
    def stop_(self):
        if self.updateTimer is not None:
            self.updateTimer.stop()

    def emitTime(self):
        self.updateTime.emit(datetime.now(UTC))

class TimeLabel(QWidget):
    def __init__(self):
        super().__init__()
        self.timeOptions = {
            'UTC':"%Y-%m-%dT%H:%M:%S",
            'DOY UTC':"%Y-%jT%H:%M:%S",
            'Local':"%Y-%m-%dT%H:%M:%S",
            'DOY Local':"%Y-%jT%H:%M:%S",
            'GPS':"%Y-%m-%dT%H:%M:%S",
            'DOY GPS':"%Y-%jT%H:%M:%S"
        }
        self.leapSec = GLOBAL_CONFIG['leapSeconds']
        self.layout = QHBoxLayout()
        self.nameBox = QComboBox()
        self.nameBox.addItems(list(self.timeOptions.keys()))
        self.nameBox.setMaximumWidth(100)
        self.nameBox.currentTextChanged.connect(self.updateLabel)
        self.timeLabel = QLabel()
        self.layout.addWidget(self.nameBox)
        self.layout.addWidget(self.timeLabel)
        self.setLayout(self.layout)
        self.nameBox.currentIndexChanged.connect(lambda _: self.updateLabel())
        self.currentTime = datetime.now(UTC)
        self.updateLabel()

        self.thread = QThread()
        self.updateWorker = UpdateThread()
        self.updateWorker.moveToThread(self.thread)

        self.thread.started.connect(self.updateWorker.start_)
        self.updateWorker.updateTime.connect(self.updateLabel)
        self.thread.start()

    @Slot()
    def updateLabel(self, currentTime=None):
        if isinstance(currentTime,datetime):
            self.currentTime = currentTime
        selectedOption = self.nameBox.currentText()
        self.timeLabel.setText(
            self._time_for_option(selectedOption).strftime(
                self.timeOptions[selectedOption]
            )
        )

        tooltipRows = []
        for option, optionFormat in self.timeOptions.items():
            optionTime = self._time_for_option(option)
            tooltipRows.append(
                "<tr>"
                f"<td align='left'>{escape(option)}</td>"
                f"<td align='right'>{escape(optionTime.strftime(optionFormat))}</td>"
                "</tr>"
            )
        self.timeLabel.setToolTip(
            "<table cellspacing='0' cellpadding='0'>"
            f"{''.join(tooltipRows)}"
            "</table>"
        )

    def _time_for_option(self, option):
        displayTime = self.currentTime
        if "GPS" in option:
            displayTime += timedelta(seconds=self.leapSec)
        if "Local" in option:
            displayTime = displayTime.astimezone()
        return displayTime

    def exit_(self):
        self.updateWorker.stop_()
        self.thread.quit()
        self.thread.wait()