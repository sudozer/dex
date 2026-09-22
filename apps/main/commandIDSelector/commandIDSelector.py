from pathlib import Path
import pdb
import json
import os
import copy
import csv
import logging

from PySide6.QtGui import QColor #for colors
from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, 
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QHeaderView,
    QDialog,
    QWidget,
    QVBoxLayout,
    QFileDialog,
    QTreeWidget,
    QListWidgetItem,
    QTreeWidgetItem,
    QTableWidget,
    QLineEdit,
    QTableWidgetItem,
    QPushButton,
    QAbstractSpinBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QDateTimeEdit
)
from qt_material import apply_stylesheet

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from packetDefinitionLib import PacketDefinitionUtility
from decode import Decoder
from dataStructures import PACKET_TEMPLATES, COMMAND_COMPONENTS

class CommandIDSelector(QDialog):
    def __init__(self,componentList):
        super().__init__()
        loader = QUiLoader()
        self.guiPath = cfgLoader.getPath('apps/main/ui/CommandID.ui')
        ui_file = QFile(self.guiPath)
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file, self)
        ui_file.close()
        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)
        self.setModal(True)

        self.componentList = componentList
        self.populateComponentList()
        self.populateFieldList()
        self.ui.componentBox.currentIndexChanged.connect(self.populateFieldList)
        self.ui.okButton.clicked.connect(self.buildIdDict)
        self.show()

    def populateComponentList(self):
        for component in self.componentList:
            self.ui.componentBox.addItem(component.componentName)

    def populateFieldList(self):
        self.ui.fieldBox.clear()
        selectedComponent = self.componentList[self.ui.componentBox.currentIndex()]
        for field in selectedComponent.componentDict:
            self.ui.fieldBox.addItem(field['fieldName'])

    def buildIdDict(self):
        self.commandIdField = {
            "componentIndex":self.ui.componentBox.currentIndex(),
            "fieldIndex":self.ui.fieldBox.currentIndex()
        }
        self.accept()



