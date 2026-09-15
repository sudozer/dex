#! /usr/bin/env python

"""
This class receives packets and interprets them,
"""
import json
import sys
import bitstruct
import logging
import pdb
from pathlib import Path
from copy import deepcopy, copy

REPO_ROOT = Path(__file__).resolve().parents[1]
UTILS_DIR = REPO_ROOT / 'utils'
CONVERSIONS_DIR = REPO_ROOT / 'conversions'
for candidate in [REPO_ROOT, UTILS_DIR, CONVERSIONS_DIR]:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

#from fieldwiseConversions import FieldConverter
#load configs
import dynamicLengthFields
from loadConfig import Configs

try:
    from malformedPackets.malformedPacketHandler import PacketProcessingError
except ImportError:
    from malformedPacketHandler import PacketProcessingError

CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig


class Decoder():
    def __init__(self, structureName, logLevel=logging.WARNING):
        self.packet_counter = 0
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CFGLOADER.getPath(CONFIG()['logBasepath']), encoding='utf-8', level=logLevel)
        self.packetStructures = CONFIG()['telemetryStructures']
        if structureName not in self.packetStructures:
            self.logger.error(f"Structure {structureName} not found in globalConfig ({CFGLOADER.global_config_path}) packetStructures.")
            self.logger.error(f"Available structures: {list(self.packetStructures.keys())}")
            self.logger.error(f"Unable to initialize RXPacketReader. Without a valid packet structure.")
        else:
            self.structureName = structureName

    def _packet_to_bytes(self, packet):
        if isinstance(packet, bytes):
            return packet
        if isinstance(packet, bytearray):
            return bytes(packet)
        if isinstance(packet, str):
            try:
                return bytes.fromhex(packet)
            except ValueError:
                return packet.encode("utf-8")
        raise PacketProcessingError("decode", f"Unsupported packet type {type(packet)}", raw_packet=packet)

    def readPacket(self, hexPacket):
        structureName = self.structureName
        self.logger.debug(f'received packet:\n\n{hexPacket}\n\ndecoding with structure:\n\n{structureName}')
        structure = deepcopy(self.packetStructures[structureName])
        packetTemplate = []
        components = []
        try:
            packetTemplate, components = self.createPacketTemplate(structure, hexPacket)
            if not packetTemplate:
                raise PacketProcessingError("decode", "Unable to build a packet template for the malformed packet", raw_packet=hexPacket, packet_template=packetTemplate)
            packet, order = self.readFromTemplate(hexPacket, packetTemplate)
            if not packet:
                raise PacketProcessingError("decode", "The packet decoder produced no interpret-able fields", raw_packet=hexPacket, packet_template=packetTemplate)
            return packet, components, order, packetTemplate
        except PacketProcessingError:
            raise
        except Exception as exc:
            raise PacketProcessingError("decode", f"Failed to decode packet: {exc}", raw_packet=hexPacket, packet_template=packetTemplate) from exc

    def findPacketType(self, hexPacket, structure):
        #if packetIdentifier is present in packet structure, a static header field must identify the packet type. Use this to determine how to interpret the rest of the packet.
        #This is for cases where multiple packet types are sent over the same channel and need to be differentiated.
        packetComponents = copy(structure['format'])
        try:
            packetTemplate = self.assembleHeaderTemplate(structure)
            partialPacket, partialPacketOrder = self.readFromTemplate(hexPacket, packetTemplate, False)
            idFile = structure['format'][structure['packetIdentifier']['identifierSourceIndex']]
            idField = structure['packetIdentifier']['field']
            pktID = partialPacket[f"{idFile}__{idField}"]['rawValue']
            packetFile = structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']]
            with open(CFGLOADER.getPath(packetFile)) as f:
                pktDef = json.load(f)
                try:
                    dynamicStructureComponent = pktDef[str(pktID)]
                    dynamicStructureComponent['fileSource'] = CFGLOADER.getPath(packetFile)
                    components = []
                    for component in packetComponents:
                        if component == packetFile:
                            components.append(Path(component).stem + f"__{pktID}")
                        else:
                            components.append(Path(component).stem)
                except KeyError as exc:
                    raise PacketProcessingError("decode", f"Packet ID {pktID} not found in packet definition file {packetFile}", raw_packet=hexPacket, packet_template=packetTemplate) from exc

            structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']] = dynamicStructureComponent
            return structure, components
        except PacketProcessingError:
            raise
        except Exception as exc:
            raise PacketProcessingError("decode", f"Unable to resolve packet structure: {exc}", raw_packet=hexPacket, packet_template=packetTemplate) from exc

    def assembleHeaderTemplate(self, structure):
        #assemble a packet template for just the static header fields that identify the packet type, based on the packetIdentifier settings in globalConfig.
        idFileIndex = structure['packetIdentifier']['identifierSourceIndex']
        idField = structure['packetIdentifier']['field']
        pktDefFile = structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']]
        try:
            with open(CFGLOADER.getPath(pktDefFile), 'r') as f:
                pktDef = json.load(f)
        except Exception as exc:
            raise PacketProcessingError("decode", f"Unable to read packet definition file {pktDefFile}: {exc}") from exc
        packetTemplate = []
        pktIDFound = False
        i = 0
        while i <= idFileIndex:
            pktdef = structure['format'][i]
            with open(CFGLOADER.getPath(pktdef)) as f:
                staticComponent = json.load(f)
                for field in staticComponent['fields']:
                    field['definitionSource'] = pktdef
                    packetTemplate.append(field)

                if i == idFileIndex:
                    for fld in packetTemplate:
                        if fld['fieldName'] == idField and fld['definitionSource'] == pktdef:
                            pktIDFound = True
                            break

                    if pktIDFound:
                        break
                    else:
                        raise PacketProcessingError("decode", f"Packet identifier field {idField} not found in packet definition file {pktDefFile}", packet_template=packetTemplate)
            i += 1
        return packetTemplate

    def createPacketTemplate(self, structure, hexPacket = b"\x00"):
        #based on the structure, return a packet template that defines which bits of the raw binary
        #packet correspond to which fields in the structure.
        #structure components are either a string filepath containing static components of the packet
        #or a dict containing the field name, type, and bit length of a dynamic component of the packet.

        if 'packetIdentifier' in structure:
            structure, components = self.findPacketType(hexPacket, structure)
            if not structure:
                raise PacketProcessingError("decode", 'Unable to interpret packet: Unable to resolve packet structure', raw_packet=hexPacket)
        else:
            components = [Path(component).stem for component in structure['format']]
        packetTemplate = []

        packetFormat = structure['format']
        for pktdef in packetFormat:
            if type(pktdef) == str:
                with open(CFGLOADER.getPath(pktdef)) as f:
                    staticComponent = json.load(f)
                    for field in staticComponent['fields']:
                        field['definitionSource'] = Path(pktdef).stem
                        packetTemplate.append(field)
            elif type(pktdef) == dict:
                for field in pktdef['fields']:
                    field['definitionSource'] = f"{Path(pktdef['fileSource']).stem}__{pktdef['packetId']}"
                    packetTemplate.append(field)
        return packetTemplate, components

    def readFromTemplate(self, hexPacket, packetTemplate, verifyLength=True):
        #given a binary packet and a packet template, read the fields from the binary packet according to the template and return a dict containing the field names and values.
        #this is where the actual interpretation of the binary packet happens, using the packet template to determine which bits correspond to which fields.

        expectedBitNum = 0
        interpretedFields = {}
        order = []
        bitstructString = ''
        packetBytes = self._packet_to_bytes(hexPacket)
        binaryPacket = self.convertBinary(packetBytes)
        for field in packetTemplate:
            if 'variableLength' in field:
                dynamicLengthFields.findFieldLength(hexPacket, packetTemplate, field)
            bitstructString += field['bitstructType']
            expectedBitNum += field['bitLength']

        if expectedBitNum / 8 > len(packetBytes):
            raise PacketProcessingError("decode", "Packet is too short to deserialize with the provided template", raw_packet=hexPacket, packet_template=packetTemplate)

        elif expectedBitNum / 8 < len(packetBytes) and verifyLength:
            self.logger.warning(f"Too many bytes supplied by packet.  Expected {expectedBitNum} and recieved {len(packetBytes)}")
            self.logger.warning("Truncating packet to interpret with the provided template.")
            packetValues = bitstruct.unpack(bitstructString, packetBytes[0:int(expectedBitNum / 8)])
        else:
            packetValues = bitstruct.unpack(bitstructString, packetBytes)
        i = 0
        bitPosition = 0
        for field in packetTemplate:
            fieldName = field['fieldName']
            defSource = field['definitionSource']
            if field['bitLength'] > 1:
                field['rawBits'] = binaryPacket[bitPosition:bitPosition + field['bitLength']]
            else:
                field['rawBits'] = binaryPacket[bitPosition]

            try:
                bitPosition += field['bitLength']
                field['rawValue'] = packetValues[i]
                i += 1
                field['bitOffset'] = bitPosition - field['bitLength']
                fieldKey = f"{defSource}__{fieldName}"
                interpretedFields[fieldKey] = field
                order.append(fieldKey)
            except Exception as exc:
                raise PacketProcessingError("decode", f"Failed to parse field {fieldName}: {exc}", raw_packet=hexPacket, packet_template=packetTemplate, field_names=[fieldName]) from exc
        return interpretedFields, order

    def convertBinary(self, packet):
        if type(packet) == bytes:
            bits_ = ''.join(f'{byte:08b}' for byte in packet)
            if len(bits_) < len(packet) * 8:
                bits_ = '0' * (len(packet) * 8 - len(bits_)) + bits_
            return bits_