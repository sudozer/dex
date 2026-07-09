import psycopg
from psycopg import sql
import json
from pathlib import Path
import pdb
from datetime import datetime
from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

class PGConnection():
    def __init__(self):
        self.pgInfo = CONFIG()['storage']['postgres']
        self.storageLevel = CONFIG()['storage']['storageLevel']
        self.datetimeFormat = CONFIG()['datetimeFormat']
        self.connectionString = f"host={self.pgInfo['host']} dbname={self.pgInfo['dbName']} user={self.pgInfo['user']} password={self.pgInfo['password']}"
        self.loadDefinitions()

    def openConnection(self):
        #some of the functions in this library are made with a different connection string
        #the default connection string used here connects for writing records
        self.conn = psycopg.connect(self.connectionString)

    def createDexUser(self):
        #must be run as postgres
        pdb.set_trace()
        conn = psycopg.connect(
        dbname="postgres",
        user="postgres", 
        host="localhost",
        autocommit=True  # Bypasses open transaction blocks
        )

        new_username = self.pgInfo['user']
        new_password = self.pgInfo['password']

        try:
            with conn.cursor() as cur:
                # 2. Use sql.Identifier and sql.Placeholder to prevent injection
                query = sql.SQL(f"CREATE USER {self.pgInfo['user']} WITH PASSWORD \'{self.pgInfo['password']}\'")
                
                # 3. Execute the statement
                cur.execute(query, (new_password,))
                print(f"User '{new_username}' created successfully.")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            conn.close()

    def createDatabase(self):
        dbCreationString = f"host={self.pgInfo['host']} dbname=postgres user={self.pgInfo['user']} password={self.pgInfo['password']}"
        with psycopg.connect(dbCreationString, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {self.pgInfo['dbName']};")
                cur.execute(f"ALTER DATABASE {self.pgInfo['dbName']} SET timezone TO \'UTC\';")
    
    def initPacketTable(self):
        with psycopg.connect(self.connectionString) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS packets (
                packetUUID UUID PRIMARY KEY,
                rawPacket BYTEA NOT NULL
                );
                """)
        
                cur.execute("""
                CREATE TABLE IF NOT EXISTS packetMetadata (
                packetUUID UUID PRIMARY KEY,
                primaryTimestamp TIMESTAMPTZ NOT NULL,
                telemetryStructure TEXT NOT NULL,
                components TEXT NOT NULL
                );
                """)

    def initDatatagTable(self):
        with psycopg.connect(self.connectionString) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS datatags (
                tagID INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                primaryTimestamp TIMESTAMPTZ NOT NULL,
                description TEXT NOT NULL
                );
                """)

    def loadDefinitions(self):

        tdefPath = Path(CONFIG()['telemetryDefinitionsBasepath'])
        files = [f for f in tdefPath.rglob('*') if f.is_file() and f.suffix in ('.hd')]
        self.telemetryDefinitions = {}

        for telemetryDefinitionFile in files:
            self.telemetryDefinitions[telemetryDefinitionFile.name] = json.load(open(telemetryDefinitionFile,'r'))       
            
        files = [f for f in tdefPath.rglob('*') if f.is_file() and f.suffix in ('.pd')]
        for telemetryDefinitionFile in files:
            self.telemetryDefinitions[telemetryDefinitionFile.name] = json.load(open(telemetryDefinitionFile,'r'))

    def addPacket(self,packet,rawPacket):
       
        metadata = packet['metadata']
        # Insert into packets table
        packets_query = "INSERT INTO packets (packetUUID, rawPacket) VALUES (%s, %s);"
        packets_values = [metadata['packetUUID'], rawPacket]
        
        # Insert into packetMetadata table
        metadata_query = "INSERT INTO packetMetadata (packetUUID, primaryTimestamp, telemetryStructure, components) VALUES (%s, %s, %s, %s);"
        metadata_values = [
            metadata['packetUUID'],
            datetime.strptime(metadata['primaryTimestamp'], self.datetimeFormat),
            metadata['telemetryStructure'],
            json.dumps(metadata['components']) if isinstance(metadata['components'], list) else metadata['components']
        ]
        with self.conn.cursor() as cur:
            cur.execute(metadata_query, metadata_values)
            cur.execute(packets_query, packets_values)
        
        self.conn.commit()
            
        