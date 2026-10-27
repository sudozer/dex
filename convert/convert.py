"""
This file contains the final conversions for data being decoded from packets.
At this point a packet is received, the bits have been split into their appropriate fields,
and data the data has been interpreted to a primitive data type.

This set of functions performs any further necessary manipulation of the data in those fields.
"""
import logging
import sys
import pdb
import json
from pathlib import Path

import conversionFunctions
from loadConfig import Configs

try:
    from malformedPackets.malformedPacketHandler import PacketProcessingError
except ImportError:
    from malformedPacketHandler import PacketProcessingError

cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig


class Converter():
    def __init__(self, msgFunction):
        self.msgFunction = msgFunction
        pass
    
    def convertField(self, field):
        try:
            conversionFunc = field['conversion']['conversionFunction']
            conversionArgs = field['conversion']['conversionArgs']
            conversionVal = field['rawValue']
            if hasattr(conversionFunctions, conversionFunc):
                callString = f"conversionFunctions.{conversionFunc}({conversionVal},{conversionArgs})"
                field['convertedValue'] = eval(callString)
                return field
            else:
                self.msgFunction(f"Conversion function {conversionFunc} not present in conversionFunctions.py", "WARNING")
        except Exception as exc:
            raise self.msgFunction(f"Error converting field {field.get('fieldName')}: {exc}","WARNING")

    def convertPacket(self, decodedPacket, packetTemplate=None):
        self.brokenPacket = False
        for fld in decodedPacket:
            field = decodedPacket[fld]
            if 'conversion' in field:
                try:
                    decodedPacket[fld] = self.convertField(field)
                except:
                    self.brokenPacket = True
                    pass #error handeled in convert field, allow porcessing to continue when 
        return decodedPacket, self.brokenPacket