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
sys.path.append('../utils')
sys.path.append('../conversions')

#from fieldwiseConversions import FieldConverter
#load configs
import dynamicLengthFields
from loadConfig import Configs
CFGLOADER = Configs()
CONFIG = CFGLOADER.loadGlobalConfig

class Decoder():
    def __init__(self,structureName,logLevel=logging.WARNING):
        self.packet_counter = 0
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=CONFIG()['logBasepath'], encoding='utf-8', level=logLevel)
        self.packetStructures = CONFIG()['telemetryStructures']
        if structureName not in self.packetStructures:
            self.logger.error(f"Structure {structureName} not found in globalConfig ({CFGLOADER.global_config_path}) packetStructures.")
            self.logger.error(f"Available structures: {list(self.packetStructures.keys())}")
            self.logger.error(f"Unable to initialize RXPacketReader. Without a valid packet structure.")
        else:
            self.structureName = structureName

    def readPacket(self,hexPacket):
        structureName = self.structureName
        self.logger.debug(f'received packet:\n\n{hexPacket}\n\ndecoding with structure:\n\n{structureName}')
        structure = deepcopy(self.packetStructures[structureName])
        pktTemplate, components = self.createPacketTemplate(structure,hexPacket)
        packet, order = self.readFromTemplate(hexPacket,pktTemplate)
        #packet = self.fieldConverter.convertFields(packet)
        return packet, components, order
    
    def findPacketType(self,hexPacket,structure):
        #if packetIdentifier is present in packet structure, a static header field must identify the packet type. Use this to determine how to interpret the rest of the packet.
        #This is for cases where multiple packet types are sent over the same channel and need to be differentiated.
        packetComponents = copy(structure['format'])
        packetTemplate = self.assembleHeaderTemplate(structure)
        partialPacket,partialPacketOrder = self.readFromTemplate(hexPacket,packetTemplate,False)
        idFile = structure['format'][structure['packetIdentifier']['identifierSourceIndex']]
        idField = structure['packetIdentifier']['field']
        #pktID = self.fieldInterpreter.convertFromBits(partialPacket[idFile + "__" +idField])
        pktID = partialPacket[f"{idFile}__{idField}"]['rawValue']
        #packet identifier retrieved, assemble packet structure
        packetFile = structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']]
        with open(packetFile) as f:
            pktDef = json.load(f)
            try:
                dynamicStructureComponent = pktDef[str(pktID)]
                dynamicStructureComponent['fileSource'] = packetFile
                components = []
                for component in packetComponents:
                    if component == packetFile:
                        components.append(Path(component).stem + f"__{pktID}")
                    else:
                        components.append(Path(component).stem)
            except KeyError:
                self.logger.error(f"Packet ID {pktID} not found in packet definition file {packetFile}.")
                self.logger.error(f"Available packet IDs in {packetFile}: {list(pktDef.keys())}")
                return False

        #build dynamic packet template

        structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']] = dynamicStructureComponent
        return structure, components
        
    def assembleHeaderTemplate(self,structure):
        #assemble a packet template for just the static header fields that identify the packet type, based on the packetIdentifier settings in globalConfig.
        idFileIndex = structure['packetIdentifier']['identifierSourceIndex']
        idField = structure['packetIdentifier']['field']
        pktDefFile = structure['format'][structure['packetIdentifier']['packetDefinitionsIndex']]
        try:
            with open(pktDefFile,'r') as f:
                pktDef = json.load(f)
        except:
            pdb.set_trace()
        packetTemplate = []
        pktIDFound = False
        i = 0
        while i <= idFileIndex:
            
            #static component of packet, read in from file
            pktdef = structure['format'][i]
            with open(pktdef) as f:
                staticComponent = json.load(f)
                for field in staticComponent['fields']:
                    field['definitionSource'] = pktdef
                    packetTemplate.append(field)
                
                if i == idFileIndex:
                    #if the packet definition just added to the template contains the packet identifier field,
                    #verify field is present and begin reading packet to determine packet type
                    for fld in packetTemplate:
                        if fld['fieldName'] == idField and fld['definitionSource'] == pktdef:
                            pktIDFound = True  
                            break
                    
                    if pktIDFound:
                        break
                    else:
                        self.logger.error(f"Packet identifier field {idField} not found in packet definition file {pktDef}. Check globalConfig packetStructures. \n\n{structure} \n\npacketIdentifier settings and packet definition files.")
                        return False
            i += 1
        return packetTemplate

    def createPacketTemplate(self,structure,hexPacket):
        #based on the structure, return a packet template that defines which bits of the raw binary
        #packet correspond to which fields in the structure.
        #structure components are either a string filepath containing static components of the packet
        #or a dict containing the field name, type, and bit length of a dynamic component of the packet.

        #determine whether packet is static or dynamically defined.

        if 'packetIdentifier' in structure:
            #dynamic packet structure, need to determine packet type based on static header field before creating packet template
            structure, components = self.findPacketType(hexPacket,structure)
            if not structure:
                self.logger.error('Unable to interpret packet: Unable to resolve packet structure')
                return False
        else:
            components = [Path(component).stem for component in structure['format']]    
        packetTemplate = []

        packetFormat = structure['format']
        for pktdef in packetFormat:
            if type(pktdef) == str:

                #static component of packet, read in from file
                with open(pktdef) as f:
                    staticComponent = json.load(f)
                    for field in staticComponent['fields']:
                        field['definitionSource'] = Path(pktdef).stem
                        packetTemplate.append(field)
            
            elif type(pktdef) == dict:

                #dynamic component of packet, defined by field name, type, and bit length
                for field in pktdef['fields']:
                    field['definitionSource'] = f"{Path(pktdef['fileSource']).stem}__{pktdef['packetId']}"
                    packetTemplate.append(field)
        return packetTemplate, components
    
    def readFromTemplate(self,hexPacket,packetTemplate, verifyLength=True):
        #given a binary packet and a packet template, read the fields from the binary packet according to the template and return a dict containing the field names and values.
        #this is where the actual interpretation of the binary packet happens, using the packet template to determine which bits correspond to which fields.

        expectedBitNum = 0
        interpretedFields = {}
        order = []
        bitstructString = ''
        binaryPacket = self.convertBinary(hexPacket)
        for field in packetTemplate:

            if 'variableLength' in field:
                dynamicLengthFields.findFieldLength(hexPacket,packetTemplate,field)

            bitstructString += field['bitstructType']
            expectedBitNum += field['bitLength']
        
        if expectedBitNum/8 > len(hexPacket):
            self.logger.error(f"Packet is too short to deserialize with provided template:\nPacket:\n\n{hexPacket}\n\nTemplate:\n\n{packetTemplate}")
            return False
        
        elif expectedBitNum/8 < len(hexPacket) and verifyLength:
            self.logger.warning(f"Too many bytes supplied by packet.  Expected {expectedBitNum} and recieved {len(hexPacket)}")
            self.logger.warning(f"Truncating packet to interpret with provided template.")
            packetValues = bitstruct.unpack(bitstructString,hexPacket[0:expectedBitNum/8])
        else:
            packetValues = bitstruct.unpack(bitstructString,hexPacket)
        i = 0
        bitPosition = 0
        for field in packetTemplate:
            if 'arrayLength' in field and field['arrayLength'] == 0:
                #it is possible that a dynamic length field can be 0 bytes
                #i hate it though
                continue
            fieldName = field['fieldName']
            defSource = field['definitionSource']
            if field['bitLength'] > 1:
                field['rawBits'] = binaryPacket[bitPosition:bitPosition + field['bitLength']]
            else:
                field['rawBits'] = binaryPacket[bitPosition]

            #if not len(field['rawBits']) == field['bitLength']:
            try:
                bitPosition += field['bitLength']
                #if field is an array
                if 'arrayLength' in field:
                    field['rawValue'] = []
                    j = field['arrayLength']
                    while j > 0:
                        field['rawValue'].append(packetValues[i])
                        i+=1
                        j-=1
                else:
                    #if field is not an array
                    field['rawValue'] = packetValues[i]
                    i+=1
                fieldKey = f"{defSource}__{fieldName}"
                interpretedFields[fieldKey] = field
                order.append(fieldKey)
            except:
                pdb.set_trace()
        return interpretedFields, order
    
    def convertBinary(self,packet):
        if type(packet) == bytes:
            bits_ = ''.join(f'{byte:08b}' for byte in packet)
            if len(bits_) < len(packet)*8:
                #add leading 0s if necessary
                bits_ = '0' * (len(packet)*8 - len(bits_)) + bits_
            return bits_