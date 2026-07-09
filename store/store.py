"""The """

import json
import polars
import logging
import sys
from uuid import uuid6
import pdb

sys.path.append('../utils')
from dataStructures import PolarsStructures
from loadConfig import Configs
from postgresAdapter import PGConnection
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

class Storage():
    def __init__(self,logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CONFIG()['logBasepath'],encoding = 'utf-8', level=logLevel)
        cfg = CONFIG()
        self.storageMethod = cfg['storage']['activeStorageMethod']
        self.storageLevel = cfg['storage']['storageLevel']
        self.transientStorageBytes = cfg['storage']['transientWriteSizeBytes']
        self.transientStoragePath = cfg['storage']['transientStoragePath']
        self.dataStructureConversion = PolarsStructures(logLevel)
        if self.storageMethod == "parquet":
            self.logger.info(f"Storage Initiated: writing data to parquet files every {self.transientStorageBytes} bytes.  Files will be written in: {self.storageConfig['parquetBaseDirectory']}")
        
        if 'postgres' in self.storageMethod:
            self.database = PGConnection()
            self.database.openConnection()

    def storePacket(self,packet,rawPacket):
        #generate a unique packet identifier to accompany the fields if the packet needs to be reconstructed
        packet['metadata']['packetUUID'] = uuid6()
        # packet['metadata']['components'] = self.findComponents(packet)
        #convert packet datastructure to polars dataframe
        #fieldDataFrames = self.dataStructureConversion.packetDict2Dataframe(packet)
        #write to transient storage
        #write to permanent storage after transient storage fills
        match self.storageMethod:
            case "postgresDirect":
                self.database.addPacket(packet,rawPacket)

    def initTransientStorage(self):
        self.transientStorage = open(self.transientStoragePath,'w')
    def writeTransientStorage(self,fields):
        pass
    def writePermanentStorage(self,transientFilePath):
        if self.storageMethod == "parquet":
            storageFunction = self.storeParquet

    def storeParquet(self,transientFilePath):
        pass