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
