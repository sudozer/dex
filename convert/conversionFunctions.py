"""
This file holds all of the conversions that a mission will need.
It comes with a few default supported functions such as polynomial and lookup table
Additional mission-specific conversions must be added to this file as functions
All conversion functions must be written to accept 2 values: the decoded value of the field and a list of arguments
which are defined in the packet definition file.  

Arrays of decoded values are passed all at once as a list in case the 
conversion depends on all values of the array such as a timestamp"""

import json
import datetime
import sys
import math
import pdb

sys.path.append('../utils')
from loadConfig import Configs
cfgLoader = Configs()
CONFIG = cfgLoader.loadGlobalConfig


def list_func(val,args,func):
    """
    basic prototype to handle a list of values
    when the args are the same for all elements of the array
    """
    returnList = []
    for v in val:
        returnList.append(eval(f"{func}({v},{args})"))
    return returnList


def polynomial(val,args):
    """
    simple scaling function
    args are the coefficients of val^argListPosition
    if val = x and args = [3,4,-5]
    return 3*x^0 + 4x^1 - 5x^2
    """
    if not isinstance(val,list):
        r = 0
        i = 0
        for c in args:
            r += c * (val ** i)
            i += 1
        return r
    else:
        return list_func(val,args,"polynomial")

def lookupTable(val,args):
    """
    match the integer value of the lookup table supplied
    in the args list
    """
    if not isinstance(val,list):
        table = args[0]
        return table[str(val)]
    else:
        return list_func(val,args,"lookupTable")

def displayValueAsHex(val,args):
    """
    convert an int to a string of hex bytes
    arg should be 2x byte size
    """
    if not isinstance(val,list):
        retStr = format(val,'x')
        while not len(retStr) == args[0]:
            retStr = '0' + retStr
        return retStr
    else:
        return list_func(val,args,displayValueAsHex)
    
def fileIdLookup(val,args):
    """
    extract a packet definition from a given packet definition file and return the supplied field
    argument = ["/full/path/to/packet/definition","fieldToBeReturned"]
    in the example of a command packet definition such as below:
    the path to the file should be the first argument,
    the value should be the top-level packet id, in this case 4096
    the second argument should be the field you want returned from this packet definition,
    in this case "packetName" will return the name of the command, "ce_noop"
    {
        "4096": {
            "packetName": "ce_noOp",
            "description": "A null command destined for the controller electronics (CE).",
            "apid": 484,
            "packetId": 4096,
            "fields": [
                {
                    "fieldName": "padding",
                    "type": "uint8_t",
                    "arrayLength": 28,
                    "defaultSetting": [
                        222,
                        173,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        190,
                        239
                    ],
                    "bitLength": 224
                }
            ]
        },
        ...(other packetIDs)
    }
    """

    if not isinstance(val,list):
        with open(args[0],'r') as f:
            pktDef = json.load(f) 
        obj = pktDef[str(val)]
        return(obj[args[1]])
    else:
        return list_func(val,args,"fileIdLookup")
    
def ISSTime(val,args):
    #converts a 5 byte iss timestamp to readable time

    issTsFormat = "%Y-%m-%d_%H:%M:%S_%Z"
    issEpochStr = "1980-01-06_00:00:00_UTC"

    issEpoch = datetime.datetime.strptime(issEpochStr,issTsFormat)
    #4 bytes of seconds since epoch
    #1 byte of x/255 subseconds
    bytes_ = b''
    for i in range(0,4):
        bytes_ = bytes_ + val[i].to_bytes(1,byteorder='big')
    secSinceEpoch = int.from_bytes(bytes_,byteorder='big',signed=False)
    subsec = float(val[4])/255
    timestamp = issEpoch + datetime.timedelta(seconds=(secSinceEpoch + subsec))
    return timestamp.strftime(CONFIG()['datetimeFormat'])

"""
###################################
additional conversion functions for mission-specific cases can be written here
###################################
"""

