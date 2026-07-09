from postgresAdapter import PGConnection
import pdb
connection = PGConnection()
try:
    connection.createDatabase()
except Exception as E:
    print(E)
connection.initPacketTable()
connection.initDatatagTable()
