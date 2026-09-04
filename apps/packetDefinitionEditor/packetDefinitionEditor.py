from pathlib import Path
import pdb
import json
import os
import copy
import csv

"""
TODO
write csv methods
add methods to handle new definitions and remove them
add methods to build and edit telemetry structures
add methods to add and remove fields to telemetry definitions
add methods to define and edit conversions and limits
add methods to link dynamic length fields and link packet telemetry structures"""
from PySide6.QtGui import QColor #for colors
from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, 
    QMainWindow,
    QMessageBox,
    QHeaderView,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QListWidget,
    QListWidgetItem
)
from qt_material import apply_stylesheet

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

from packetDefinitionLib import PacketDefinitionUtility

STRUCTUREBASECOLOR = (70,125,255)
ERRORCOLOR = QColor.fromHsv(0,255,255)
WHITE = QColor.fromHsv(0,0,255)
typeOptions = {
            "uint":{"label":"manually-sized uint","size":0},
            "uint8_t":{"label":"8-bit unsigned int","size":8},
            "uint16_t":{"label":"16-bit unsigned int","size":16},
            "uint32_t":{"label":"32-bit unsigned int","size":32},
            "uint64_t":{"label":"64-bit unsigned int","size":64},
            "uint128_t":{"label":"128-bit unsigned int","size":128},
            "int":{"label":"manually-sized int","size":0},
            "int8_t":{"label":"8-bit signed int","size":8},
            "int16_t":{"label":"16-bit signed int","size":16},
            "int32_t":{"label":"32-bit signed int","size":32},
            "int64_t":{"label":"64-bit signed int","size":64},
            "int128_t":{"label":"128-bit signed int","size":128},
            "float":{"label":"float","size":32},
            "double":{"label":"double","size":64},
            "char":{"label":"char","size":8}
        }

def colorGen(baseColor, hueStep=55):
    while True:
        yield QColor.fromHsv(*baseColor)
        baseColor = ((baseColor[0] + hueStep) % 360, baseColor[1], baseColor[2])

class ParentItem(QTreeWidgetItem):
    def __init__(self,treeWidget,text):
        super().__init__(treeWidget,[text])
        self.children = []
        self.currentlyValid = True
    
    def validate(self):
        self.currentlyValid = True
        for child in self.children:
            if not child.currentlyValid:
                self.setBackground(0,ERRORCOLOR)
                self.currentlyValid = False
                break

        if self.currentlyValid:
            self.setBackground(0,WHITE)

class FieldItem(QTreeWidgetItem):
    def __init__(self,ui,treeWidget,sourceFile,fieldDict,parentItems,color):
        super().__init__(treeWidget,[fieldDict['fieldName']])
        self.fieldDict = fieldDict
        self.color = color
        self.ui = ui
        self.sourceFile = sourceFile
        self.validator = PacketDefinitionUtility()
        self.parentItems = parentItems

        self.parentItemId = None
        if isinstance(self.parent(),ParentItem):
            self.parentItemId = self.parent().text(0).split(' - ')[0]

        self.currentlyValid = True
        self.addToParents()
        self.validate()
        if 'conversion' in fieldDict:
            self.conversion = fieldDict['conversion']
        else:
            self.conversion = None
        if 'limits' in fieldDict:
            self.limits = fieldDict['limits']
        else:
            self.limits = None

    def validate(self):
        validField,msgs = self.validator.validateField(self.fieldDict)
        if validField:
            self.ui.validFieldLabel.setText(f"Valid Field")
            self.ui.validFieldLabel.setStyleSheet("color:green")
            self.ui.fieldMessages.setText("Field fully validated")
            self.setBackground(0,self.color)

        elif not validField:
            self.setBackground(0,ERRORCOLOR)
            self.ui.validFieldLabel.setText(f"Invalid Field")
            self.ui.validFieldLabel.setStyleSheet("color:red")
            self.ui.fieldMessages.setText("\n".join(msgs))

        if not validField == self.currentlyValid:
            self.currentlyValid = validField
            for parent in self.parentItems:
                parent.validate()
    
        return validField
        
    def changeAllParentsColor(self,color):
        for item in self.parentItems:
            item.setBackground(0,color)

    def addToParents(self):
        for parent in self.parentItems:
            parent.children.append(self)

class PacketDefinitionEditor():

    def __init__(self):
        
        self.mainGuiPath = cfgLoader.getPath('apps/packetDefinitionEditor/ui/packetDefinitionBuilder.ui') 
        self.limitsGuiPath = cfgLoader.getPath('apps/packetDefinitionEditor/ui/limitSetter.ui') 
        self.conversionsGuiPath = cfgLoader.getPath('apps/packetDefinitionEditor/ui/conversions.ui') 

        self.pktDefUtil = PacketDefinitionUtility()
        ui_file = QFile(self.mainGuiPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        ui_file.close()
        
        #apply_stylesheet(self.window, theme=CONFIG()['guiTheme'])
        self.ui.show()
        self.initGUI()
    
    def initGUI(self):
        self.fieldChanged = False
        self.ui.telemetryDefinitionsTree.setHeaderHidden(True)
        self.ui.telemetryDefinitionsTree.setColumnCount(1)
        self.ui.structureTree.setHeaderHidden(True)
        self.ui.structureTree.setColumnCount(1)
        self.ui.fieldsTree.setHeaderHidden(True)
        self.ui.fieldsTree.setColumnCount(1)
        self.loadDefsStructs()
        self.ui.structureTree.itemSelectionChanged.connect(self.structureSelected)
        self.ui.telemetryDefinitionsTree.itemSelectionChanged.connect(self.telemetryDefinitionSelected)
        self.ui.fieldsTree.itemSelectionChanged.connect(self.fieldSelected)
        self.previouslySelected = None
        #fields signals
        self.ui.dataTypeComboBox.currentTextChanged.connect(self.dataTypeSelected)

        self.ui.variableLengthCheckbox.stateChanged.connect(self.variableLengthChanged)
        self.ui.arrayLengthSpinBox.valueChanged.connect(self.arrayLengthChanged)
        self.ui.dynamicLengthFieldButton.setEnabled(False)
        self.ui.dynamicLengthFieldLineEdit.setEnabled(False)
        self.ui.lengthFieldOffsetSpinBox.setEnabled(False)
        self.ui.lengthInBitsComboBox.setEnabled(False)
        self.ui.saveFieldButton.clicked.connect(lambda: self.writeDefDict(self.ui.fieldsTree.currentItem()))

        self.fieldControls = [
            self.ui.fieldNameLineEdit,
            self.ui.descriptionTextEdit,
            self.ui.variableLengthCheckbox,
            self.ui.dynamicLengthFieldButton,
            self.ui.dynamicLengthFieldLineEdit, 
            self.ui.lengthFieldOffsetSpinBox, 
            self.ui.lengthInBitsComboBox, 
            self.ui.arrayLengthSpinBox, 
            self.ui.bitLengthSpinBox, 
            self.ui.configureConversionButton,
            self.ui.configureLimitsButton,
            self.ui.saveFieldButton
        ]
        self.ui.fieldNameLineEdit.editingFinished.connect(self.fieldParameterChanged)
        self.ui.descriptionTextEdit.textChanged.connect(self.fieldParameterChanged)
        self.ui.variableLengthCheckbox.checkStateChanged.connect(self.fieldParameterChanged)
        self.ui.dynamicLengthFieldLineEdit.editingFinished.connect(self.fieldParameterChanged)
        self.ui.lengthFieldOffsetSpinBox.valueChanged.connect(self.fieldParameterChanged)
        self.ui.lengthFieldOffsetSpinBox.valueChanged.connect(self.fieldParameterChanged)
        self.ui.lengthInBitsComboBox.currentTextChanged.connect(self.fieldParameterChanged)
        self.ui.arrayLengthSpinBox.valueChanged.connect(self.fieldParameterChanged)
        self.ui.bitLengthSpinBox.valueChanged.connect(self.fieldParameterChanged)

        self.ui.addTelemetryDefinitionButton.clicked.connect(self.addNewDefinition)
        self.ui.importFromCsvButton.clicked.connect(self.addCSVDef)
        self.ui.exportToCsvButton.clicked.connect(self.exportToCsv)
        self.ui.exportCsvTemplate.clicked.connect(self.exportCSVTemplate)
        self.ui.saveDefinitionButton.clicked.connect(self.saveTelemetryDefinitionUI)
        self.ui.newPacketButton.clicked.connect(self.addNewPacket)
        self.ui.removeDefinitionButton.clicked.connect(self.removeDefinition)
        self.ui.newStructureButton.clicked.connect(self.addNewStructure)
        self.ui.addTelemetrySelectionButton.clicked.connect(self.addTelemetryDefinitionToStructure)


    def loadDefsStructs(self):
        self.populateTelemetryDefinitions()
        self.validateAllTelemetryDefinitions()
        self.populateTelemetryStructures()

    def populateTelemetryDefinitions(self):
        self.ui.telemetryDefinitionsTree.clear()
        tdefPath = Path(cfgLoader.getPath(CONFIG()['telemetryDefinitionsBasepath']))

        files = [f for f in tdefPath.rglob('*') if f.is_file() and f.suffix in ('.hd')]
        self.telemetryDefinitions = {}

        for telemetryDefinitionFile in files:
            self.telemetryDefinitions[telemetryDefinitionFile.name] = json.load(open(telemetryDefinitionFile,'r'))
            item = ParentItem(self.ui.telemetryDefinitionsTree,telemetryDefinitionFile.name)            
            
        files = [f for f in tdefPath.rglob('*') if f.is_file() and f.suffix in ('.pd')]
        for telemetryDefinitionFile in files:
            self.telemetryDefinitions[telemetryDefinitionFile.name] = json.load(open(telemetryDefinitionFile,'r'))
            packetDefinition = self.telemetryDefinitions[telemetryDefinitionFile.name]
            item = ParentItem(self.ui.telemetryDefinitionsTree,telemetryDefinitionFile.name)
            for k in packetDefinition.keys():
                packetName = packetDefinition[k]['packetName']
                packetItem = ParentItem(item,f"{k} - {packetName}")

    def populateTelemetryStructures(self):
        self.ui.structureTree.clear()
        colorGenerator = colorGen(STRUCTUREBASECOLOR)
        for structureName, structure in CONFIG()['telemetryStructures'].items():
            item = QTreeWidgetItem([structureName])
            self.ui.structureTree.addTopLevelItem(item)
            for path in structure['format']:
                fname = Path(path).name
                component = QTreeWidgetItem([fname])
                item.addChild(component)
                component.setBackground(0,next(colorGenerator))

    def validateAllTelemetryDefinitions(self):
        for i in range(self.ui.telemetryDefinitionsTree.topLevelItemCount()):
            validDefinition = True
            telemetryDefItem = self.ui.telemetryDefinitionsTree.topLevelItem(i)
            telemetryDefName = telemetryDefItem.text(0)
            telemetryDefDict = self.telemetryDefinitions[telemetryDefName]
            if 'fields' in telemetryDefDict:
                for field in telemetryDefDict['fields']:
                    validField, msgs = self.pktDefUtil.validateField(field)
                    if not validField:
                        validDefinition = False
                        telemetryDefItem.setBackground(0,ERRORCOLOR)
            else:
                for id,packet in telemetryDefDict.items():
                    if 'fields'in packet:
                        for field in packet['fields']:
                            validField, msgs = self.pktDefUtil.validateField(field,telemetryDefName)
                            if not validField:
                                validDefinition = False
                                telemetryDefItem.setBackground(0,ERRORCOLOR)
                        
    def structureSelected(self):
        self.ui.fieldsTree.clear()
        selectedItems = self.ui.structureTree.selectedItems()
        if selectedItems:
            selectedItem = selectedItems[0]
            parentItem = selectedItem.parent()
            if parentItem:
                structureItem = parentItem
            else:
                structureItem = selectedItem
            
            childCount = structureItem.childCount()
            for i in range(childCount):
                childItem = structureItem.child(i)
                childText = childItem.text(0)
                childColor = childItem.background(0).color()
                defDict = self.telemetryDefinitions[childText]
                if 'fields' in defDict:
                    fieldsList = defDict['fields']
                    self.populateFields(fieldsList,childText,self.ui.fieldsTree,childColor)
                else:
                    #packet definition
                    for pktId,pktDef in defDict.items():
                        packetItem = ParentItem(self.ui.fieldsTree,f"{pktId} - {pktDef['packetName']}")
                        packetItem.setBackground(0,childColor)
                        self.populateFields(pktDef['fields'],childText,packetItem,childColor)
    
    def telemetryDefinitionSelected(self):
        self.ui.fieldsTree.clear()
        selectedItems = self.ui.telemetryDefinitionsTree.selectedItems()
        if selectedItems:
            selectedItem = selectedItems[0]
            parentItem = selectedItem.parent()
            if parentItem:
                #packet in telemetry definition selected, show fields for that packet
                telemetryDefinitionName = parentItem.text(0)
                selectedKeyString = selectedItem.text(0).split(' - ')[0]
                defDict = self.telemetryDefinitions[telemetryDefinitionName][selectedKeyString]
                self.populateFields(defDict['fields'],telemetryDefinitionName,self.ui.fieldsTree)
            else:
                defDict = self.telemetryDefinitions[selectedItem.text(0)]
                telemetryDefinitionName = selectedItem.text(0)
                if not 'fields' in defDict:
                    #packet definition selected, display all packets
                    for pktId,pktDef in defDict.items():
                        packetItem = ParentItem(self.ui.fieldsTree,f"{pktId} - {pktDef['packetName']}")
                        self.populateFields(pktDef['fields'],telemetryDefinitionName,packetItem)
                else:
                    #header definition selected, simply show all fields
                    defDict = self.telemetryDefinitions[telemetryDefinitionName]
                    self.populateFields(defDict['fields'],telemetryDefinitionName,self.ui.fieldsTree)
    
    def fieldSelected(self):
        continueChanging = True
        if self.previouslySelected and self.fieldChanged:
            continueChanging = self.askToSave(self.previoiuslySelected)
        
        if continueChanging:
            selectedItems = self.ui.fieldsTree.selectedItems()
            if selectedItems:
                selectedItem = selectedItems[0]

            if len(selectedItems) > 0 and isinstance(selectedItem,FieldItem):
                fieldDict = selectedItem.fieldDict
                self.populateFieldParameters(selectedItem)
            self.previouslySelected = self.ui.fieldsTree.currentItem()

    def askToSave(self,item):
        pass

    def variableLengthChanged(self,state):
        if state == 2:
            self.ui.dynamicLengthFieldButton.setEnabled(True)
            self.ui.dynamicLengthFieldLineEdit.setEnabled(True)
            self.ui.lengthFieldOffsetSpinBox.setEnabled(True)
            self.ui.lengthInBitsComboBox.setEnabled(True)
            self.ui.arrayLengthSpinBox.setEnabled(False)
            self.ui.bitLengthSpinBox.setEnabled(False)
        else:
            self.ui.dynamicLengthFieldButton.setEnabled(False)
            self.ui.dynamicLengthFieldLineEdit.setEnabled(False)
            self.ui.lengthFieldOffsetSpinBox.setEnabled(False)
            self.ui.lengthInBitsComboBox.setEnabled(False)
            self.ui.arrayLengthSpinBox.setEnabled(True)
            self.ui.bitLengthSpinBox.setEnabled(True)

    def dataTypeSelected(self,text):
        if text == "manually-sized uint" or text == "manually-sized int":
            self.ui.bitLengthSpinBox.setEnabled(True)
        else:
            self.setBitLength()

    def arrayLengthChanged(self):
        self.setBitLength()

    def setBitLength(self):
        typeText = self.ui.dataTypeComboBox.currentText()
        for typeName, typeDict in typeOptions.items():
            if typeText == typeDict['label']:
                arrayLength = self.ui.arrayLengthSpinBox.value()
                bitLength = typeDict['size'] * arrayLength
                self.ui.bitLengthSpinBox.setValue(bitLength)
                break
        self.ui.bitLengthSpinBox.setEnabled(False)

    def populateFields(self,fieldsList,sourceFile,parent,color=WHITE):
        for fieldDict in fieldsList:
            parentItems = self.findAllParentItems(sourceFile,parent)
            FieldItem(self.ui,parent,sourceFile,fieldDict,parentItems,color)

    def findAllParentItems(self,sourceFile,parent):

        matches = self.ui.telemetryDefinitionsTree.findItems(sourceFile,Qt.MatchContains)
        parentList = matches
        if sourceFile[-3:] == '.pd':
            #find the parent text and match it in telemetry definitions
            try:
                parentText = parent.text(0)
                parentItem = parentList[0]
                for i in range(parentItem.childCount()):
                    if parentText in parentItem.child(i).text(0):
                        parentList.append(parentItem.child(i))
                        break
                parentList.append(parent)
            except:
                parentList.append(self.ui.telemetryDefinitionsTree.currentItem())
        return parentList
    
    def populateFieldParameters(self,item):
        self.autoPopulating = True
        fieldDict = item.fieldDict
        self.fieldChanged = False
        validField = item.validate()

        self.ui.fieldNameLineEdit.setText(fieldDict['fieldName'])
        
        typeOptions = {
            "uint":{"label":"manually-sized uint","size":0},
            "uint8_t":{"label":"8-bit unsigned int","size":8},
            "uint16_t":{"label":"16-bit unsigned int","size":16},
            "uint32_t":{"label":"32-bit unsigned int","size":32},
            "uint64_t":{"label":"64-bit unsigned int","size":64},
            "uint128_t":{"label":"128-bit unsigned int","size":128},
            "int":{"label":"manually-sized int","size":0},
            "int8_t":{"label":"8-bit signed int","size":8},
            "int16_t":{"label":"16-bit signed int","size":16},
            "int32_t":{"label":"32-bit signed int","size":32},
            "int64_t":{"label":"64-bit signed int","size":64},
            "int128_t":{"label":"128-bit signed int","size":128},
            "float":{"label":"float","size":32},
            "double":{"label":"double","size":64},
            "char":{"label":"char","size":8}
        }
        #encapsulating in try excepts so other parameters still get populated if one of them fails
        try:
            #set dataType combobox
            parameterDict = typeOptions[fieldDict['type']] 
            self.ui.dataTypeComboBox.setCurrentText(parameterDict['label'])
        except Exception as E:
            print(E)
        
        try:
            #set description
            if 'description' in fieldDict:
                self.ui.descriptionTextEdit.setPlainText(fieldDict['description'])
        except Exception as E:
            print(E)

        try:
            if 'arrayLength' in fieldDict:
                self.ui.arrayLengthSpinBox.setValue(fieldDict['arrayLength'])
            else:
                self.ui.arrayLengthSpinBox.setValue(1)
        except Exception as E:
            print(E)

        try:
            if 'variableLength' in fieldDict:
                self.ui.variableLengthCheckbox.setChecked(True)
                self.ui.dynamicLengthFieldLineEdit.setText(fieldDict['variableLength']['lengthField'])
                self.ui.lengthFieldOffsetSpinBox.setValue(fieldDict['variableLength']['lengthFieldOffset'])
                if fieldDict['variableLength']['lengthInBits']:
                    self.ui.lengthInBitsComboBox.setCurrentText("Bits")
                else:                
                    self.ui.lengthInBitsComboBox.setCurrentText("Bytes")
        except Exception as E:
            print(E)

        try:
            if self.ui.dataTypeComboBox.currentText() != "manually-sized uint" and self.ui.dataTypeComboBox.currentText() != "manually-sized int":
                self.ui.bitLengthSpinBox.setValue(parameterDict['size'] * self.ui.arrayLengthSpinBox.value())
            else:
                if 'bitLength' in fieldDict:
                    self.ui.bitLengthSpinBox.setValue(fieldDict['bitLength'])
                else:
                    self.ui.bitLengthSpinBox.setValue(0)
        except Exception as E:
            print(E)
        self.autoPopulating = False

        if not validField:
            for control in self.fieldControls:
                control.setEnabled(True)
        #self.ui.saveFieldButton.setEnabled(False)

    def fieldParameterChanged(self):
        if self.autoPopulating:
            return
        
        self.fieldChanged = True
        currentField = self.ui.fieldsTree.currentItem()
        self.writeDefDict(currentField)
        if currentField.validate():
            self.ui.saveFieldButton.setEnabled(True)

    def writeDefDict(self,item):
        
        fieldDict ={}
        fieldIndex = item.parent().indexOfChild(item)

        fieldDict['fieldName'] = self.ui.fieldNameLineEdit.text()
        fieldDict['bitLength'] = self.ui.bitLengthSpinBox.value()
        for typeName, typeDict in typeOptions.items():
            if self.ui.dataTypeComboBox.currentText() == typeDict['label']:
                fieldDict['type'] = typeName
                break

        if len(self.ui.descriptionTextEdit.toPlainText()) > 0:
            fieldDict['description'] = self.ui.descriptionTextEdit.toPlainText()
        
        if self.ui.arrayLengthSpinBox.value() > 1:
            fieldDict['arrayLength'] = self.ui.arrayLengthSpinBox.value()

        if self.ui.variableLengthCheckbox.isChecked():
            fieldDict['variableLength'] = {
                'lengthField': self.ui.dynamicLengthFieldLineEdit.text(),
                'lengthFieldOffset': self.ui.lengthFieldOffsetSpinBox.value(),
                'lengthInBits': self.ui.lengthInBitsComboBox.currentText() == "Bits"
            }
        else:
            fieldDict['bitstructType'] = self.pktDefUtil.createBitstructString(fieldDict)
        if item.conversion:
            fieldDict['conversion'] = item.conversion
        if item.limits:
            fieldDict['limits'] = item.limits

        item.fieldDict = fieldDict
        if item.parentItemId:
            self.telemetryDefinitions[item.sourceFile][item.parentItemId]['fields'][fieldIndex] = fieldDict
        else:
            self.telemetryDefinitions[item.sourceFile]['fields'][fieldIndex] = fieldDict

    def saveTelemetryDefinition(self, sourceFile):
        defDict = self.telemetryDefinitions[sourceFile]
        savePath = cfgLoader.getPath(CONFIG()['telemetryDefinitionsBasepath']) / sourceFile
        with open(savePath,'w') as f:
            json.dump(defDict,f,indent=4)

    def addCSVDef(self):
        tlmDef = self.ui.telemetryDefinitionsTree.selectedItems()[0]
        if not tlmDef:
            QMessageBox.warning(None,"No telemetry definition selected","Plese select a telemetry definition from the definitions list or add a new one and select it.")
            return
        csvPath, _ = QFileDialog.getOpenFileName(
            parent=None,
            caption="Open CSV File",
            filter="CSV Files (*.csv)"
            )
        
        parentDef = tlmDef.parent()
        if parentDef:
            #packet Definition
            telemetryDefinitionName = parentDef.text(0)
            selectedKeyString = tlmDef.text(0).split(' - ')[0]
            defDict = self.telemetryDefinitions[telemetryDefinitionName][selectedKeyString]
        else:
            telemetryDefinitionName = tlmDef.text(0)
            defDict = self.telemetryDefinitions[telemetryDefinitionName]
        fieldList = self.convertCSV(csvPath)
        if fieldList:
            defDict['fields'] = fieldList
            self.saveTelemetryDefinition(telemetryDefinitionName)
            self.telemetryDefinitionSelected()

    def convertCSV(self,csvPath):
        with open(csvPath,'r') as f:
            reader = csv.reader(f)
            fieldList = []
            rownum = 0
            next(reader,None)
            for row in reader:
                fieldDict = {
                    "fieldName": row[0],
                    "bitLength": int(row[1]),
                    "type": row[2],
                    "description": row[3],
                    "units":row[4],
                }

                if len(row[5]) > 0 and int(row[5]) > 1:
                    fieldDict['arrayLength'] = int(row[5])

                fieldDict['bitstructType'] = self.pktDefUtil.createBitstructString(fieldDict)
                if len(row[6]) > 0:
                    fieldDict['conversion']={
                        "conversionFunction": row[6],
                        "conversionArgs": self.unpackConversionArgs(row[7])
                    }
                    #TODO for now just set enumeration outputs to string but maybe someday change so that it can handle other data types
                    fieldDict['conversion']['convertedType'] = "char"

                valid, errors = self.pktDefUtil.validateField(fieldDict)
                if valid:
                    fieldList.append(fieldDict)
                else:
                    self.csvConversionError(rownum,errors)
                    return False

                rownum += 1
            return fieldList
    
    def unpackConversionArgs(self,argString):
        argString = argString.replace(" ","")
        keyValPairs = argString.split(';')
        argDict = {}
        for pair in keyValPairs:
            if len(pair) > 0:
                key, val = pair.split(':')
                argDict[key] = val
        return argDict
    
    def csvConversionError(self,row,errors):
        emessage = ""
        for e in errors:
            emessage = emessage + e + '\n'
        QMessageBox.warning(None, "CSV conversion error", emessage)

    def exportToCsv(self):
        #TODO support exporting back to a csv
        pass

    def exportCSVTemplate(self):
        #TODO implement CSV template export
        pass

    def saveTelemetryDefinitionUI(self):
        #TODO save a definition from ui (might just remove the button)
        pass

    def addNewPacket(self):
        #TODO support adding new packets to a packet definition
        pass
    
    def removeDefinition(self):
        #TODO remove definition
        pass

    def addNewStructure(self):
        dialogPath = cfgLoader.getPath('apps/packetDefinitionEditor/ui/newStructure.ui')
        ui_file = QFile(dialogPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        dialog = loader.load(ui_file)
        ui_file.close()

        if dialog.exec() == QDialog.Accepted:
            newStructureName = dialog.structureName.text()
            #TODO check for database safe naming
            with open(cfgLoader.global_config_path,'r') as globalConfigFile:
                globalConfigDict = json.load(globalConfigFile)
            globalConfigDict['telemetryStructures'][newStructureName] = {'format':[]}
            with open(cfgLoader.global_config_path,'w') as globalConfigFile:
                json.dump(globalConfigDict, globalConfigFile, indent=4)
            self.populateTelemetryStructures()

    def addTelemetryDefinitionToStructure(self):
        selectedDef = self.ui.telemetryDefinitionsTree.selectedItems()[0]
        selectedStructure = self.ui.structureTree.selectedItems()[0]
        if selectedDef == None or selectedStructure == None:
            QMessageBox.warning(None,"Invalid Selection", "Please select both a telemetry definition and a structure to add it to.")
            return

        structureName = selectedStructure.text(0)
        defName = selectedDef.text(0)

        with open(cfgLoader.global_config_path,'r') as globalConfigFile:
            globalConfigDict = json.load(globalConfigFile)
        globalConfigDict['telemetryStructures'][structureName]['format'].append(f"telemetryDefinitions/{defName}")
        #TODO link packet definitions properly
        with open(cfgLoader.global_config_path,'w') as globalConfigFile:
            json.dump(globalConfigDict, globalConfigFile, indent=4)
        self.populateTelemetryStructures()

    def removeStructureOrComponent(self):
        #TODO depending on what is selected, remove either a component from a structure or an entire structure
        pass

    def addNewDefinition(self):
        dialogPath = cfgLoader.getPath('apps/packetDefinitionEditor/ui/newDefinition.ui')
        ui_file = QFile(dialogPath)
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        dialog = loader.load(ui_file)
        ui_file.close()

        if dialog.exec() == QDialog.Accepted:
            newTlmDefName = dialog.telemetryDefinitionName.text()
            newTlmDefType = '.pd' if dialog.telemetryDefinitionType.currentText() == "Packets" else '.hd'
            self.telemetryDefinitions[newTlmDefName + newTlmDefType]= {}
            self.saveTelemetryDefinition(newTlmDefName + newTlmDefType)
            self.populateTelemetryDefinitions()

if __name__ == '__main__':
    os.environ.pop("SESSION_MANAGER", None)
    app = QApplication([])
    editor = PacketDefinitionEditor()
    app.exec()