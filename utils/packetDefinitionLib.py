import sys
import json
import logging
import pdb
import polars as pl
sys.path.append('../utils')
from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig



class PacketDefinitionUtility():

    def __init__(self,logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CFGLOADER.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)

    def addBitstructStrings(self,pktDefPath):
        with open(pktDefPath,'r') as f:
            pktDef = json.load(f)

        if 'fields' in pktDef:
            for field in pktDef['fields']:
                field['bitstructType'] = self.createBitstructString(field)

        if not 'fields' in pktDef:
            for pkt in pktDef:
                singlePkt = pktDef[pkt]
                for field in singlePkt['fields']:
                    field['bitstructType'] = self.createBitstructString(field)
            
        with open(pktDefPath,'w') as f:
            json.dump(pktDef,f, indent=4)

    def createBitstructString(self,field):

        if 'int' in field['type']:
            bs = 's'
            if 'uint' in field['type']:
                bs = 'u'

            for i in ['8','16','32','64']:
                if i in field['type']:
                    bs += str(i)
                    break
            #size not defined in type field    
            if len(bs) < 2:
                if not 'arrayLength' in field:
                    bs += str(field['bitLength'])
                else:
                    bitLen = field['bitLength'] / field['arrayLength']
                    bs += str(bitLen)

            baseBitstructType = bs

        if 'float' == field['type']:
            baseBitstructType = 'f32'

        if 'double' == field['type']:
            baseBitstructType = 'f64'

        if 'char' in field['type']:
            baseBitstructType = 't8'

        if 'bool' in field['type']:
            baseBitstructType = 'b1'

        if 'arrayLength' in field:
            bsString = baseBitstructType * field['arrayLength']
        else:
            bsString = baseBitstructType

        return bsString
    
    def addConvertedTypes(self,definitionPath):
        with open(definitionPath,'r') as f:
            defDict = json.load(f)
        if 'fields' in defDict:
            for field in defDict['fields']:
                if 'conversion' in field:
                    field = self.findConvertedType(field)
        else:
            for pktID in defDict:
                for field in defDict[pktID]['fields']:
                    if 'conversion' in field:
                        try:
                            field = self.findConvertedType(field)
                        except:
                            pdb.set_trace()
        if self.validateDefinitionFile(definitionPath):
            with open(definitionPath,'w') as f:
                json.dump(defDict,f,indent=4)
    
    def findConvertedType(self,field):
        if not 'conversion' in field:
            return field
        #polynomial, just determine whether return is an int or a float
        if field['conversion']['conversionFunction'] == "polynomial":
            
            if field['type'] in ['float','double']:
                #converted value will just be a scaled decimal value
                field['conversion']['convertedType'] = field['type']
                return field
            for num in field['conversion']['conversionArgs']:
                if isinstance(num,float):
                    field['conversion']['convertedType'] = 'float'
                    return field
            field['conversion']['convertedType'] = field['type']
            return field
        
        #lookupTable, determine datatype of first entry
        if field['conversion']['conversionFunction'] == 'lookupTable':
            conversionTable = field['conversion']['conversionArgs'][0]
            for entry in conversionTable:
                if isinstance(conversionTable[entry],str):
                    field['conversion']['convertedType'] = 'char'
                    return field
                if isinstance(conversionTable[entry],int):
                    field['conversion']['convertedType'] = 'int16_t'
                    return field

        if field['conversion']['conversionFunction'] == 'displayValueAsHex':
            field['conversion']['convertedType'] = 'char'
            return field
        
        if field['conversion']['conversionFunction'] == 'fileIdLookup':
            field['conversion']['convertedType'] = 'char'
            return field
        
        if field['conversion']['conversionFunction'] == 'ISSTime':
            field['conversion']['convertedType'] = 'char'
            return field

    def writePolarSchema(self,definitionPath):
        if not self.validateDefinitionFile(definitionPath):
            self.logger.error(f"Unable to write polars schema for file: {definitionPath}\nFile failed validation.")
            return False

        with open(definitionPath,'r') as f:
            defDict = json.load(f)
        
        polarSchema = {}
        if 'fields' in defDict:
            for field in defDict['fields']:
                polarSchema[f"{definitionPath}__{field['fieldName']}"] =  self.writePolarSchemaField(field)
        else:
            for pktDef in defDict:
                fields = defDict[pktDef]['fields']
                for field in fields:
                    polarSchema[f"{definitionPath}__{pktDef}__{field['fieldName']}"] = self.writePolarSchemaField(field)
        return polarSchema

    def writePolarSchemaField(self,field):
        if "variableLength" in field:
            return {"variableLength":1}
        #{uniqueID,timestamp,rawbits,rawValue,convertedValue}
        schemaDict = {"packetUUID":"pl.UInt128()","primaryTimestamp":"pl.Datetime(time_zone=\"UTC\")","rawBits":f"pl.Array(pl.Boolean(),{field['bitLength']})"}
        polarsDT = self.primitive2polars(field['type'])
        if 'arrayLength' in field:
            schemaDict['rawValue'] = f"pl.Array({polarsDT},{field['arrayLength']})"
        else:
            schemaDict['rawValue'] = polarsDT

        if 'conversion' not in field:
            schemaDict['convertedValue'] = schemaDict['rawValue']
        else:
            schemaDict['convertedValue'] = self.primitive2polars(field['conversion']['convertedType'])
        return schemaDict

    def primitive2polars(self,datatype):
        match datatype:
            case "uint8_t":
                return "pl.UInt8()"
            case "uint16_t":
                return "pl.UInt16()"
            case "uint32_t":
                return "pl.UInt32()"
            case "uint64_t":
                return "pl.UInt64()"
            case "int8_t":
                return "pl.Int8()"
            case "int16_t":
                return "pl.Int16()"
            case "int32_t":
                return "pl.Int32()"
            case "int64_t":
                return "pl.Int64()"
            case "char":
                return "pl.String()"
            case "float":
                return "pl.Float32()"
            case "double":
                return "pl.Float64()"
            case "boolean":
                return "pl.Boolean()"
            case "dateTime":
                return "pl.Datetime()"
        return "pl.UInt32()"

    def validateDefinitionFile(self,definitionPath):
        #validate json format
        self.currentProcessingPath = definitionPath
        try:
            with open(definitionPath,'r') as f:
                defDict = json.load(f)
        except Exception as e:
            self.logger.error(e)
            self.logger.error(f"\n\nValidation of definition file: {definitionPath} failed: Unable to load json packet definition.")
        #validate fields in either top level of dict or just one level down
        if 'fields' in defDict:
            validFile = self.validateFields(defDict)
            if validFile:
                defDict['totalBitLength'] = self.sumBitLengths(defDict['fields'])
        else:
            for pktDef in defDict:
                pktDict = defDict[pktDef]
                if 'fields' in pktDict:
                    validFile = self.validateFields(pktDict)
                    if validFile:
                        pktDict['totalBitLength'] = self.sumBitLengths(pktDict['fields'])
                else:
                    self.logger.error(f"Validation error:\n\n\"fields\" key not present in definition file: {definitionPath}")
                    self.logger.error(f"\"fields\" key must be present in either the top level of the json file or in every field one level down.")
        if validFile:
            json.dump(defDict,open(definitionPath,'w'),indent=4)
        return validFile

    def validateFields(self,defDict):
        validFields = True
        for field in defDict['fields']:
            if not self.validateField(field):
                validFields = False
        return validFields

    def validateField(self,field,path_=""):
        #enforce database_safe naming, cant start with a number and only _ is allowed
        validationErrors = []
        requiredKeys = [
            "fieldName",
            "type"
        ]

        knownTypeSizes = {
            "uint":0,
            "int":0,
            "uint8_t":8,
            "uint16_t":16,
            "uint32_t":32,
            "uint64_t":64,
            "uint128_t":128,
            "int8_t":8,
            "int16_t":16,
            "int32_t":32,
            "int64_t":64,
            "int128_t":128,
            "float":32,
            "double":64,
            "char":8
        }

        #validate required keys are present
        for key in requiredKeys:
            if not key in field:
                if key == "fieldName":
                    logMsg = f"Unnamed field present in file."
                    validationErrors.append(logMsg)
                else:
                    logMsg = f"Required key: {key} absent from field {field['fieldName']} in file."
                    validationErrors.append(logMsg)

            else:
                #check required keys are correct type
                if key == "fieldName" and not isinstance(field['fieldName'],str):
                    logMsg = f"\'fieldName\' must be string."
                    validationErrors.append(logMsg)
                if key == "type" and not field['type'] in knownTypeSizes:
                    logMsg = f"\'type\' field must be a known primitive datatype.\nAccepted datatypes are: {list(knownTypeSizes.keys())}"
                    validationErrors.append(logMsg)
        #fieldname and type fully validated at this point

        #field must either be variable length or contain bitLength and bitstructType fields      
        if "variableLength" in field:
            if not "lengthField" in field['variableLength'] or not isinstance(field['variableLength']['lengthField'],str):
                logMsg = f"\'variableLength\' must contain a string \'lengthField\' field."
                validationErrors.append(logMsg)
                
            if not "lengthFieldOffset" in field['variableLength'] or not isinstance(field['variableLength']['lengthFieldOffset'],int):
                logMsg = f"\'variableLength\' must contain a string \'lengthField\' field."
                validationErrors.append(logMsg)
    
        elif "bitLength" in field and "bitstructType" in field:
            if not isinstance(field['bitLength'],int):
                logMsg = f"\'bitLength\' must be int."
                validationErrors.append(logMsg)

            if not isinstance(field['bitstructType'],str):
                logMsg = f"\'bitstructType\' must be string"
                validationErrors.append(logMsg)
        else:
            logMsg = f"Field must contain either \'variableLength\' field for dynamically sized fields or \'bitLength\' and \'bitstructType\' fields for statically determined fields.\n\n{field}"
            validationErrors.append(logMsg)

        # validate key primitive datatypes
        if 'arrayLength' in field:
            if not isinstance(field['arrayLength'],int):
                logMsg = f"\'arrayLength\' must be int."
                validationErrors.append(logMsg)

        #validate bitLength
        if 'bitLength' in field:
            if field['type'] in knownTypeSizes:
                baseFieldLength = knownTypeSizes[field['type']]
                if 'arrayLength' in field:
                    expectedFieldLength = baseFieldLength * field['arrayLength']
                else:
                    expectedFieldLength = baseFieldLength
                if not expectedFieldLength == field['bitLength'] and not baseFieldLength == 0:
                    validationErrors.append(f"bitLength supplied differs from expected.\nExpecting {expectedFieldLength} - Supplied {field['bitLength']}")

        #validate bitstruct string
        if 'bitstructType' in field:
            if field['bitstructType'] != self.createBitstructString(field):
                validationErrors.append(f"Bitstruct string not correct for given type and field length.")

        #validate conversion
        if 'conversion' in field:
            conv = field['conversion']
            if not 'conversionFunction' in conv:
                validationErrors.append(f"No conversion function supplied.")
                
            if not 'conversionArgs' in conv:
                validationErrors.append(f"No conversion arguments supplied.  Supply an empty list if no arguments are necessary for the specified conversion function.")
        
            if not 'convertedType' in conv:
                validationErrors.append(f"No converted datatype supplied.")


        if len(validationErrors) > 0:
            self.logger.error(f"Validation of field: {field['fieldName']} in file: {path_} failed with the following errors:")
            for error in validationErrors:
                self.logger.error(error)
            return False, validationErrors
        return True, validationErrors
    
    def sumBitLengths(self,fields):
        totalBits = 0
        for field in fields:
            if 'variableLength' in field:
                return 'variable'
            totalBits += field['bitLength']
        return totalBits