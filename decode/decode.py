#! /usr/bin/env python

"""
This class receives packets and interprets them,
"""
import json
import sys
import time
import bitstruct
import logging
import pdb
from copy import deepcopy, copy
from pathlib import Path
from loadConfig import cfgLoader, GLOBAL_CONFIG
from dataStructures import PACKET_STRUCTURE_COMPONENTS

#from fieldwiseConversions import FieldConverter
#load configs
import dynamicLengthFields

class Decoder():
    def __init__(self, structureName, msgFunction):
        self.packet_counter = 0
        self.msgFunction = msgFunction
        if structureName not in PACKET_STRUCTURE_COMPONENTS:
            self.msgFunction(f"Structure {structureName} not found in configured packet Structures.\nAvailable structures: \n{list(PACKET_STRUCTURE_COMPONENTS.keys())}","Error")
            return
        else:
            self.structureName = structureName
        self.structureDict = PACKET_STRUCTURE_COMPONENTS[self.structureName]
        self.multiPacket = len(self.structureDict) > 1
        if self.multiPacket:
            self.pktIdInfo = GLOBAL_CONFIG['telemetryStructures'][self.structureName]['packetIdField']
        
        self.numHeaders = len(GLOBAL_CONFIG['telemetryStructures'][self.structureName]['headers'])
        
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
        self.msgFunction(f'Received packet:\n\n{hexPacket}\n\nDecoding with structure: {structureName}',"Debug")
        try:
            try:
                packetTemplate, packetType = self.createPacketTemplate(hexPacket)
            except Exception as E:
                self.msgFunction(f"Decoder unable to build a packet template for decoding.\n{E}", "ERROR")
                return False
            try:
                packet, order = self.readFromTemplate(hexPacket, packetTemplate)
            except Exception as E:
                self.msgFunction(f"Decoder unable to interpret packet.\n{E}","ERROR")
                return False
            return packet, order, packetTemplate, packetType
        except Exception as E:
            self.msgFunction(f"Decoding error: {E}","ERROR")
            return False

    def assembleHeaderTemplate(self):
        #assemble a packet template for just the static header fields that identify the packet type, based on the packetIdentifier settings in globalConfig.
        for pktName,pkt in self.structureDict.items():
            #all packets in a structure have the same headers
            break
        headerTemplate = []
        for i in range(self.numHeaders):
            component = pkt[i]
            if i == self.pktIdInfo['componentIndex']:
                pktIdFieldIndex = len(headerTemplate) + self.pktIdInfo['fieldIndex']
            headerTemplate.extend(component['fields'])
        #assembledHeaderTemplate
        return headerTemplate, pktIdFieldIndex

    def createPacketTemplate(self, hexPacket):
        #based on the structure, return a packet template that defines which bits of the raw binary
        #packet correspond to which fields in the structure.
        #structure components are either a string filepath containing static components of the packet
        #or a dict containing the field name, type, and bit length of a dynamic component of the packet.
        if self.multiPacket:
            #header must be read to determine packet id
            headerTemplate, idFieldIndex = self.assembleHeaderTemplate()
            header,headerOrder = self.readFromTemplate(hexPacket,headerTemplate,False)
            pktId = str(header[headerOrder[idFieldIndex]]['rawValue'])
            if pktId in self.structureDict:
                packetTemplate = []
                #add headers to packetTemplate
                for component in self.structureDict[pktId]:
                    packetTemplate.extend(component['fields'])
                packetType = pktId
            else:
                #error
                self.msgFunction(f"Decoding Error: packetId: {pktId} not found in structure: {self.structureName}. \nAvailable packet IDs: {[i for i in self.structureDict]}")
                return False

        else:
            packetTemplate = []
            for component in self.structureDict[self.structureName]:
                packetTemplate.extend(component['fields'])
            packetType = self.structureName
        return packetTemplate,packetType

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
            self.msgFunction(f"Too many bytes supplied by packet.  Expected {expectedBitNum} and recieved {len(packetBytes)}","WARNING")
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
                self.msgFunction(f"Failed to parse field {fieldName}:\n{E}","ERROR")
        return interpretedFields, order

    def convertBinary(self, packet):
        if type(packet) == bytes:
            bits_ = ''.join(f'{byte:08b}' for byte in packet)
            if len(bits_) < len(packet) * 8:
                bits_ = '0' * (len(packet) * 8 - len(bits_)) + bits_
            return bits_