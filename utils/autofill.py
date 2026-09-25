#automatically populate fields built in the command builder based on these functions
import datetime
import pdb
import struct

from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig

class Autofiller():
    def __init__(self):
        pass

    def autofillAllFields(self,fieldList):
        self.fieldList = fieldList
        for field in fieldList:
            field = self.autofillField(field)
        return self.fieldList

    def autofillField(self,field):
        if not 'autofill' in field:
            return field
        field['value'] = eval(f"self.{field['autofill']}()")
        field['bitstring'] = self.bitConvert(field)
        return field

    def bitConvert(self,field):
        #ai code cuz I can't be assed with this again
        conversionType = field['type']
        bitLength = field['bitLength']
        knownTypes = {
            "uint": 0,
            "int": 0,
            "uint8_t": 8,
            "uint16_t": 16,
            "uint32_t": 32,
            "uint64_t": 64,
            "uint128_t": 128,
            "int8_t": 8,
            "int16_t": 16,
            "int32_t": 32,
            "int64_t": 64,
            "int128_t": 128,
            "float": 32,
            "double": 64,
            "char": 8
        }

        if conversionType not in knownTypes:
            raise ValueError(f"Unknown field type: {conversionType}")
        if not isinstance(bitLength, int) or bitLength < 0:
            raise ValueError("field['bitLength'] must be a non-negative integer")

        if conversionType == 'char':
            value = field['value']
            if not isinstance(value, str) or len(value) != 1:
                raise ValueError("char fields must contain exactly one character")
            convertedValue = ord(value)
            return format(convertedValue & ((1 << bitLength) - 1), f'0{bitLength}b')

        if conversionType in ('float', 'double'):
            expectedLength = knownTypes[conversionType]
            if bitLength != expectedLength:
                raise ValueError(
                    f"{conversionType} fields must have a bitLength of {expectedLength}"
                )
            format_ = '>f' if conversionType == 'float' else '>d'
            return ''.join(
                format(byte, '08b')
                for byte in struct.pack(format_, float(field['value']))
            )

        convertedValue = int(field['value'])
        if bitLength:
            return format(convertedValue & ((1 << bitLength) - 1), f'0{bitLength}b')
        return format(convertedValue, 'b')

    ############
    #Unique autofill functions can be added below here
    ############

    def issTime(self):
        #return 5 byte iss time
        #iss time epoch is Jan 6,1980 0:0:0
        issEpoch = datetime.datetime(1980,1,6,0,0,0,tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        epochDiff = now - issEpoch
        epochSec = epochDiff.total_seconds()
        epochSubSec = epochSec % 1.0
        secBytes = int(epochSec).to_bytes(4,byteorder='big')
        subsecBytes = int(epochSubSec/(1.0/255)).to_bytes(1,byteorder='big')
        return int.from_bytes(secBytes + subsecBytes)

    def primaryLengthField(self):
        bitLen = sum(self.fieldList[i]['bitLength'] for i in range(len(self.fieldList)))
        return bitLen // 8

    def primarySequenceCount(self):
        return CONFIG()['commandSequenceNumber']