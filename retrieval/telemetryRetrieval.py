import sqlite3
from loadConfig import cfgLoader, GLOBAL_CONFIG

def retrieveAllDatatags(database):
    dbPath = cfgLoader.getPath('databases') / database
    with sqlite3.connect(dbPath) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT time, tagType, tagDescription FROM datatags")
        return cursor.fetchall()
