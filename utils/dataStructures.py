import polars as pl
import json
import pdb
import logging
import datetime
from time import perf_counter
from pathlib import Path

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

class PolarsStructures():
    def __init__(self,logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logLevel)
        self.loadPolarsSchema()
        self.datetimeFormat = CONFIG()['datetimeFormat']

    def loadPolarsSchema(self):
        schemaPath = Path(cfgLoader.getPath(CONFIG()['storage']['polarsSchemaPath']))
        if not schemaPath.is_absolute():
            schemaPath = (Path(__file__).resolve().parent.parent / schemaPath).resolve()
        self.logger.info(f"Loading polars storage schema from {schemaPath}...")
        start = perf_counter()
        if not schemaPath.exists():
            self.logger.warning(f"Polars schema file not found at {schemaPath}; continuing without schema initialization")
            self.schemaDict = {}
            self.liveDataDict = {}
            self.liveDataVariableFields = {}
            return self.liveDataDict, self.liveDataDict
        with open(schemaPath,'r') as f:
            self.schemaDict = json.load(f)
        for fieldID in self.schemaDict:
            try:
                self.loadPolarsSchemaField(self.schemaDict[fieldID])
            except Exception as E:
                print(E)
                pdb.set_trace()
        self.liveDataDict = {}
        self.liveDataVariableFields = {}
        for key in self.schemaDict:
            if not 'variableLength' in self.schemaDict[key]:
                self.liveDataDict[key]=pl.DataFrame(schema=self.schemaDict[key])
            else:
                self.liveDataVariableFields[key] = []
        end = perf_counter()
        self.logger.info(f"Polars schem successfully loaded in {end-start} seconds")
        return self.liveDataDict, self.liveDataDict

    def loadPolarsSchemaField(self,field):

        if 'variableLength' in field:
            return field
        for f in field:
            field[f] = eval(field[f])
        return field
            
    def packetDict2Dataframe(self,packetDict):
        dataframeDict = {}
        for field in packetDict:
            if field == 'metadata':
                continue
            fieldDict = packetDict[field]
            dataframeDict[field] = self.field2Dataframe(field,fieldDict,packetDict['metadata'])
        return dataframeDict
    
    def field2Dataframe(self,fieldName,fieldDict,metadata):
        dfDict = {
            "packetUUID":metadata['packetUUID'],
            "primaryTimestamp":datetime.datetime.strptime(metadata['primaryTimestamp'],self.datetimeFormat),
            "rawBits":self.bitstringToBoolean(fieldDict['rawBits']),         
                }
        #polars wants a list of lists for storing an array
        if 'arrayLength' in fieldDict:
            dfDict["rawValue"] = [fieldDict['rawValue']]
        else:
            dfDict["rawValue"] = fieldDict['rawValue']  

        #if no converted value is present, return decoded value
        if 'convertedValue' in fieldDict:
            if isinstance(fieldDict['convertedValue'], list):
                dfDict['convertedValue'] = [fieldDict['convertedValue']]
            else:
                dfDict['convertedValue'] = fieldDict['convertedValue']
        else:
            dfDict['convertedValue'] = dfDict['rawValue']
        try:
            fieldDf = pl.from_dict(dfDict,schema=self.schemaDict[fieldName])
            return fieldDf
        except Exception as E:
            pdb.set_trace()
    def bitstringToBoolean(self,bitstring):
        #polars wants this encapsulated in a list
        #in case multiple lists are simultaneously added
        return [[1 == '1' for bit in bitstring]]

class DataDictionaries():
    #helper class to load packets, etc. without having to read the json files everywhere
    def __init__(self):
        self.loadAllDicts()

    def loadAllDicts(self):
        self.loadStructures()
        self.loadPacketTemplates()

    def loadStructures(self):
        self.structures = CONFIG()['telemetryStructures']

    def loadPacketTemplates(self):
        #read all structures and create a packet dictionary for each
        self.packetTemplates = {}
        #TODO support packet definitions instead of just header definitions
        ##TODO support dynamic sized fields
        for structureName, structure in self.structures.items():
            if not 'packetIdentifier' in structure:
                self.packetTemplates[structureName] = []
                for file in structure['format']:
                    with open(cfgLoader.getPath(file),'r') as file_:
                        packetDict = json.load(file_)
                        self.packetTemplates[structureName].extend(packetDict['fields'])
            else:
                packetFilePath = cfgLoader.getPath(structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']])
                with open(packetFilePath,'r') as packetDefFile:
                    packetDefDict = json.load(packetDefFile)
                for packetId, packetDef in packetDefDict.items():
                    self.packetTemplates[f"{structureName}_{packetId}"] = []
                    i = 0
                    for file in structure['format']:
                        with open(cfgLoader.getPath(file),'r') as file_:
                            packetDict = json.load(file_)
                        if i == structure['packetIdentifier']['packetDefinitionsIndex']:
                            self.packetTemplates[f"{structureName}_{packetId}"].extend(packetDef['fields'])
                        self.packetTemplates[f"{structureName}_{packetId}"].extend(packetDict['fields'])




