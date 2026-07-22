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

REPO_ROOT = Path(__file__).resolve().parents[1]
UTILS_DIR = REPO_ROOT / 'utils'
for candidate in [REPO_ROOT, UTILS_DIR]:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import conversionFunctions
from loadConfig import Configs

try:
    from malformedPackets.malformedPacketHandler import PacketProcessingError
except ImportError:
    from malformedPacketHandler import PacketProcessingError

cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig


class Converter():
    def __init__(self, logLevel=logging.WARNING):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=cfgLoader.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)

    def convertField(self, field):
        try:
            conversionFunc = field['conversion']['conversionFunction']
            conversionArgs = field['conversion']['conversionArgs']
            conversionVal = field['rawValue']
            if hasattr(conversionFunctions, conversionFunc):
                callString = f"conversionFunctions.{conversionFunc}({conversionVal},{conversionArgs})"
                field['convertedValue'] = eval(callString)
                return field
            raise PacketProcessingError("convert", f"Conversion function {conversionFunc} not present in conversionFunctions.py", field_names=[field.get('fieldName')], packet_template=[field])
        except PacketProcessingError:
            raise
        except Exception as exc:
            raise PacketProcessingError("convert", f"Error converting field {field.get('fieldName')}: {exc}", field_names=[field.get('fieldName')], packet_template=[field]) from exc

    def convertPacket(self, decodedPacket, packetTemplate=None):
        self.brokenPacket = False
        for fld in decodedPacket:
            field = decodedPacket[fld]
            if 'conversion' in field:
                try:
                    decodedPacket[fld] = self.convertField(field)
                except PacketProcessingError as exc:
                    exc.packet_template = packetTemplate or list(decodedPacket.values())
                    exc.field_names = exc.field_names or [field.get('fieldName')]
                    raise
        return decodedPacket