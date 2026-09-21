#automatically populate commands built in the command builder based on these functions
import datetime
import pdb

def issTime():
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

def primaryLengthField():
    pass
def primarySequenceCount():
    pass