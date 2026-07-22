import bitstruct
import logging
import pdb
import sys
sys.path.append('../utils')
from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig
logger = logging.getLogger(__name__)
logLevel = logging.ERROR

logging.basicConfig(filename=CFGLOADER.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)

#hell

def findFieldLength(packet,template,field):
    lengthField = field['variableLength']['lengthField']
    lengthFieldOffset = field['variableLength']['lengthFieldOffset']
    fieldName = lengthField.split('__')[-1]
    lengthFieldIndex = -1
    i=0
    for field in template:
        if field['fieldName'] == fieldName:
            lengthFieldIndex = i
        else:
            i += 1
    if lengthFieldIndex == -1:
        errStr = f"Unable to find specified length field {fieldName} in packet template:\n{template}"
        logging.error(errStr)
        raise Exception()
    templateToLengthField = template[0:lengthFieldIndex+1]
    i = 0
    bitstructString = ""

    for f in templateToLengthField:
        bitstructString += f['bitstructType']
        i += 1

    numBits = bitstruct.calcsize(bitstructString)
    if numBits % 8 > 0:
        numBytes = int(numBits/8) + 1
    else:
        numBytes = int(numBits/8)

    bytes_ = packet[0:numBytes]
    packetValues = bitstruct.unpack(bitstructString,bytes_)
    
    #unpack previous fields
    i=0

    for fld in templateToLengthField:
        
        if 'arrayLength' in fld:
            fld['rawValue'] = []
            j = fld['arrayLength']
            while j > 0:
                fld['rawValue'].append(packetValues[i])
                i+=1
                j-=1
        else:
            fld['rawValue'] = packetValues[i]
            i+=1
    if field['variableLength']['lengthInBits']:
        field['bitLength'] = lengthFieldOffset + templateToLengthField[lengthFieldIndex]['rawValue']
    else:
        lengthBytes = lengthFieldOffset + templateToLengthField[lengthFieldIndex]['rawValue']
        field['bitLength'] = int(lengthBytes*8)
    #back-calculate arrayLength

    baseSize = int(field['bitstructType'][1:])
    if field['bitLength'] % baseSize:
        errStr = f"Incorrect data basetype or bit length:\nBasesize (derived from bitstructType): {baseSize}\nCalculated bitLength: {field['bitLength']}"
        logging.error(errStr)
        raise Exception()
    field['arrayLength'] = int(field['bitLength'] / baseSize)
    field['bitstructType'] = field['bitstructType'] * field['arrayLength']
    return field
