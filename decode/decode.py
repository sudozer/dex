#! /usr/bin/env python

"""
This class receives packets and interprets them,
"""
import json
import sys
import bitstruct
import logging
import pdb
from copy import deepcopy, copy
from pathlib import Path
from loadConfig import cfgLoader, GLOBAL_CONFIG

#from fieldwiseConversions import FieldConverter
#load configs
import dynamicLengthFields

class Decoder():
    def __init__(self, structureName, msgFunction):
        self.packet_counter = 0
        self.msgFunction = msgFunction
        self.packetStructures = GLOBAL_CONFIG['telemetryStructures']
        if structureName not in self.packetStructures:
            self.msgFunction(f"Structure {structureName} not found in configured packet Structures.\nAvailable structures: \n{list(self.packetStructures.keys())}","Error")
            return
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

    def readPacket(self, hexPacket):
        structureName = self.structureName
        self.msgFunction(f'Received packet:\n\n{hexPacket}\n\nDecoding with structure:\n\n{structureName}',"Debug")
        structure = deepcopy(self.packetStructures[structureName])
        packetTemplate = []
        components = []
        try:
            packetTemplate, components = self.createPacketTemplate(structure, hexPacket)
            if not packetTemplate:
                self.msgSignal("Unable to build a packet template for the malformed packet", "ERROR")
            packet, order = self.readFromTemplate(hexPacket, packetTemplate)
            if not packet:
                self.msgFunction("The packet decoder produced no interpretable fields", "ERROR")
            return packet, components, order, packetTemplate
        except Exception as E:
            self.msgFunction(f"Decoding error: {E}","ERROR")

    def findPacketType(self, hexPacket, structure):
        #if packetIdField is present in packet structure, a static header field must identify the packet type. Use this to determine how to interpret the rest of the packet.
        #This is for cases where multiple packet types are sent over the same channel and need to be differentiated.
        packetComponents = copy(structure['format'])
        try:
            packetTemplate = self.assembleHeaderTemplate(structure)
            partialPacket, partialPacketOrder = self.readFromTemplate(hexPacket, packetTemplate, False)
            idFile = structure['format'][structure['packetIdField']['componentIndex']]
            idField = structure['packetIdField']['field']
            pktID = partialPacket[f"{idFile}__{idField}"]['rawValue']
            packetFile = structure['format'][structure['packetIdField']['packetDefinitionsIndex']]
            with open(cfgLoader.getPath(packetFile)) as f:
                pktDef = json.load(f)
                try:
                    dynamicStructureComponent = pktDef[str(pktID)]
                    dynamicStructureComponent['fileSource'] = cfgLoader.getPath(packetFile)
                    components = []
                    for component in packetComponents:
                        if component == packetFile:
                            components.append(Path(component).stem + f"__{pktID}")
                        else:
                            components.append(Path(component).stem)
                except KeyError as exc:
                    self.msgFunction(f"Packet ID {pktID} not found in packet definition file {packetFile}", "ERROR")

            structure['format'][structure['packetIdField']['packetDefinitionsIndex']] = dynamicStructureComponent
            return structure, components
        except Exception as E:
            self.msgFunction(f"Error determining packet type: {E}", "ERROR")

    def assembleHeaderTemplate(self, structure):
        #assemble a packet template for just the static header fields that identify the packet type, based on the packetIdentifier settings in globalConfig.
        idFileIndex = structure['packetIdField']['componentIndex']
        idField = structure['packetIdField']['field']
        pktDefFile = structure['format'][structure['packetIdField']['packetDefinitionsIndex']]
        try:
            with open(cfgLoader.getPath(pktDefFile), 'r') as f:
                pktDef = json.load(f)
        except Exception as E:
            self.msgFunction(f"Unable to read packet definition file {pktDefFile}:]n{E}","ERROR")
        packetTemplate = []
        pktIDFound = False
        i = 0
        while i <= idFileIndex:
            pktdef = structure['format'][i]
            with open(cfgLoader.getPath(pktdef)) as f:
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
                        self.msgFunction(f"Packet identifier field {idField} not found in packet definition file {pktDefFile}", "ERROR")
            i += 1
        return packetTemplate

    def createPacketTemplate(self, structure, hexPacket = b"\x00"):
        #based on the structure, return a packet template that defines which bits of the raw binary
        #packet correspond to which fields in the structure.
        #structure components are either a string filepath containing static components of the packet
        #or a dict containing the field name, type, and bit length of a dynamic component of the packet.

        if 'packetIdField' in structure:
            structure, components = self.findPacketType(hexPacket, structure)
            if not structure:
                self.msgFunction(f'Unable to interpret packet: Unable to resolve packet structure','ERROR')
        else:
            components = [Path(component).stem for component in structure['format']]
        packetTemplate = []

        packetFormat = structure['format']
        for pktdef in packetFormat:
            if type(pktdef) == str:
                with open(cfgLoader.getPath(pktdef)) as f:
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
            self.msgFunction("Packet is too short to deserialize with the provided template","ERROR")

        elif expectedBitNum / 8 < len(packetBytes) and verifyLength:
            self.msgFunction("Too many bytes supplied by packet.  Expected {expectedBitNum} and recieved {len(packetBytes)}","WARNING")
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
            except Exception as E:
                self.msgFunction(f"Failed to parse field {fieldName}: {E}","ERROR")
        return interpretedFields, order

    def convertBinary(self, packet):
        if type(packet) == bytes:
            bits_ = ''.join(f'{byte:08b}' for byte in packet)
            if len(bits_) < len(packet) * 8:
                bits_ = '0' * (len(packet) * 8 - len(bits_)) + bits_
            return bits_