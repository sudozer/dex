import sqlite3
import threading
from datetime import datetime, timezone
import pdb
from loadConfig import cfgLoader, GLOBAL_CONFIG

class Storage():
    def __init__(self, msgFunction):
        self.msgFunction = msgFunction
        self._lock = threading.Lock()
        self.connection = None

    def initDatabase(self,dbName):
        try:
            dbPath = cfgLoader.getPath('databases') / dbName
            with sqlite3.connect(dbPath) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON;")
                #create dataTag table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS datatags (
                time INTEGER NOT NULL,
                tagType TEXT NOT NULL,
                tagDescription TEXT NOT NULL
                )
                """)

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS packets (
                packetID INTEGER PRIMARY KEY AUTOINCREMENT,
                groundTime INTEGER NOT NULL,
                packetType TEXT NOT NULL
                )
                """)

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                commandType TEXT NOT NULL,
                groundTime INTEGER NOT NULL,
                command BLOB NOT NULL
                )
                """)

            self.msgFunction(f"Database {dbName} initialized successfully.", "INFO")
        except Exception as e:
            self.msgFunction(f"Database {dbName} failed to initialize.\n{e}", "ERROR")

    def initPacketTypeTable(self, structure, packetType):
        try:
            cursor = self.connection.cursor()
            # Build the SQL query for creating the packet table based on the structure
            tableName = f"{structure}_{packetType}"
            quotedTableName = '"' + tableName.replace('"', '""') + '"'
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {quotedTableName} (
            packetID INTEGER PRIMARY KEY,
            time INTEGER NOT NULL,
            data BLOB NOT NULL,
            FOREIGN KEY (packetID) REFERENCES packets(packetID))
            """)
            self.msgFunction(f"Packet table for {structure}_{packetType} initialized successfully in database: {self.activeDatabase}", "INFO")
            self.buildTableList()  # Update the table list after creating the new table
        except Exception as e:
            self.msgFunction(f"Failed to initialize packet table for {structure}_{packetType}.\n{e}", "ERROR")

    def setActiveDatabase(self):
        try:
            self.activeDatabase = GLOBAL_CONFIG['storage']['activeDatabase']
            dbPath = cfgLoader.getPath('databases') / self.activeDatabase
            try:
                self.connection.close()
            except Exception as e:
                self.msgFunction(f"Failed to close connection when initiating new database connection.\n{e}","DEBUG")
                pass
            self.connection = sqlite3.connect(dbPath, check_same_thread=False)
            cursor = self.connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            self.buildTableList()
            self.msgFunction(f"Database {self.activeDatabase} connected successfully.", "INFO")
        except Exception as e:
            self.msgFunction(f"Database {self.activeDatabase} failed to connect.\n{e}", "ERROR")

    def buildTableList(self):
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        self.tableList = [row[0] for row in cursor.fetchall()]

    def storePacket(self,packet,rawPacket):
        metadata = packet['metadata_']
        groundTime = int(
            datetime.strptime(
                metadata['groundTimestampUTC'], GLOBAL_CONFIG['datetimeFormat']
            )
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        structure = metadata['telemetryStructure']
        packetType = metadata['packetType']
        tableName = f"{structure}_{packetType}"
        quotedTableName = '"' + tableName.replace('"', '""') + '"'

        with self._lock:
            if tableName not in self.tableList:
                self.initPacketTypeTable(structure, packetType)

            with self.connection:
                cursor = self.connection.cursor()
                cursor.execute(
                    "INSERT INTO packets (groundTime, packetType) VALUES (?, ?)",
                    (groundTime, packetType),
                )
                packetID = cursor.lastrowid
                cursor.execute(
                    f"INSERT INTO {quotedTableName} (packetID, time, data) "
                    "VALUES (?, ?, ?)",
                    (packetID, groundTime, sqlite3.Binary(rawPacket)),
                )

    def storeCommand(self,command, structure, commandType, serialCommand):
        with self._lock:
            dataTag = self.checkDatatag(command,structure,commandType)
            timestamp = int(datetime.now(timezone.utc).timestamp())
            with self.connection:
                cursor = self.connection.cursor()
                commandInsertQuery = "INSERT INTO commands (commandType,groundTime,command) VALUES (?,?,?)"
                self.msgFunction("Storing command to database.","DEBUG")
                cursor.execute(
                    commandInsertQuery,
                    (commandType,timestamp,serialCommand)
                )
                if dataTag:
                    datatagText = f"{structure}.{commandType}.ARGUMENTS:"
                    for field in command:
                        if 'argument' in field:
                            datatagText = datatagText + f" {field['fieldName']} :: {field['value']}"
                    self._insertDataTag(cursor, 'CMD', datatagText, timestamp)

    def checkDatatag(self,command,structure,commandType):
        tagCommands = GLOBAL_CONFIG['storage']['dataTags']['commands']
        commandMatch = False
        if structure in tagCommands:
            if commandType in tagCommands[structure]:
                for triggerCommand in tagCommands[structure][commandType]:
                    commandMatch = True
                    for field in triggerCommand:
                        match = next((item for item in command if item["fieldName"] == field['fieldName'] and item['component'] == field['component'] and item['value'] == field['value']), False)
                        if not match:
                            commandMatch = False
                            break
                    if commandMatch:
                        break

        if commandMatch:
            self.msgFunction("Command matched datatag command table.","DEBUG")
            return not GLOBAL_CONFIG['storage']['dataTags']['tagAllCommands']
        else:
            #command not matched
            return GLOBAL_CONFIG['storage']['dataTags']['tagAllCommands']

    def writeCommand(self,command):
        if self.connection == None:
            self.setActiveDatabase()

    def writeDataTag(self,dataTagType,text):
        if self.connection == None:
            self.setActiveDatabase()
        if not dataTagType in ['MAN','CMD','SYS']:
            self.msgFunction("Supplied dataTag Type not recognized.","warning")
        timestamp = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            with self.connection:
                cursor = self.connection.cursor()
                self._insertDataTag(cursor, dataTagType, text, timestamp)

    def _insertDataTag(self, cursor, dataTagType, text, timestamp):
        self.msgFunction("Writing datatag.","DEBUG")
        cursor.execute(
            "INSERT INTO datatags (time, tagType, tagDescription) VALUES (?, ?, ?)",
            (timestamp, dataTagType, text),
        )