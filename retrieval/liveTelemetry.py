from copy import copy
from datetime import datetime

class LiveTelemetry():
    def __init__(self):
        self.registry = {}

    def pushPacket(self,packet):
        """
        Accept a freshly decoded and converted packet to be 
        pushed to live displays.
        """
        matches = list(set(packet['metadata']['components']) & set(self.registry.keys()))
        for component in matches:
            for field in self.registry[component]:
                fieldKey = f"{component}__{field}"
                liveTlm = copy(self.registry[component][field]['liveTelemetry'])
                updateDict = {
                'previous_timestamp':liveTlm['timestamp'],
                'previous_rawBinary':liveTlm['rawBinary'],
                'previous_rawHex':liveTlm['rawHex'],
                'previous_rawValue':liveTlm['rawValue'],
                'previous_convertedValue': liveTlm['convertedValue'],

                'timestamp':packet['metadata']['primaryTimestamp'],
                'rawBinary':packet[fieldKey]['rawBits'],
                'rawValue':packet[fieldKey]['rawValue'],
                'convertedValue':packet[fieldKey]['rawValue']
                    }
                if 'convertedValue' in packet[fieldKey]:
                    updateDict['convertedValue'] = packet[fieldKey]['convertedValue']
                if len(packet['rawBits']) % 8 == 0:
                    hex_ = int(packet['rawBits'], 2).to_bytes(len(packet['rawBits'])//8, byteorder='big').hex()
                else:
                    hex_ = None
                updateDict['rawHex'] = hex_
                self.registry[component][field]['liveTelemetry'].update(updateDict)
            
                #current live packet updated, call supplied callbacks
                for callback in self.registry[component][field]['callbacks']:
                    callback(self.registry[component][field]['liveTelemetry'])

    def registerCallback(self,component,field,callback):
        """
        Register a field to be tracked in live telemetry
        component.

        Args:
        component(str) the component which must be present to trigger this callback.
        field(str) the fieldname which will be extracted from the packet
        callback the function which will be called with the liveTelemetry object as its argument
        """

        if not component in self.registry:
            self.registry[component] = {}

        if not field in self.registry[component]:
            self.registry[component][field] = {
                'liveTelemetry':{
                    'timestamp':None,
                    'rawBinary':None,
                    'rawHex':None,
                    'rawValue':None,
                    'convertedValue': None,

                    'previous_timestamp':None,
                    'previous_rawBinary':None,
                    'previous_rawHex':None,
                    'previous_rawValue':None,
                    'previous_convertedValue': None
                },
                'callbacks':[callback]
            }
        else:
            self.registry[component][field]['callbacks'].append(callback)

live_telemetry = LiveTelemetry()