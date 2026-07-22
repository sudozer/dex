import satkit
from pathlib import Path
import csv
import pdb
import numpy as np

class OrbitProp:
    def __init__(self):
        self.ephemeris = []
        self.latestState = None

    def updateEph(self,eph):
        self.latestState, self.latestTimestamp = self.packArray(eph)

    def packArray(self,eph):
        array = np.array([eph['x'],eph['y'],eph['z'],eph['vx'],eph['vy'],eph['vz']])
        time_ = eph['timestamp']
        return array,time_
    
    def readASC(self,fname):
        print(fname)
        self.dateFormatString = "%Y-%m-%dT%H:%M:%S.%f"
        with open(fname,'r') as f:
            reader = csv.reader(f, delimiter=' ')
            for row in reader:
                try:
                    if 'CREATION_DATE' in row[0]:
                        creationDate = row[2]
                        continue
                    #if the first element is a timestamp, than this is a data row
                    dataDict = {}
                    dataDict["source"] = fname
                    dataDict['creationDate'] = creationDate
                    dataDict["timestamp"] = satkit.time.strptime(row[0], self.dateFormatString)
                    dataDict["x"] = float(row[1]) * 1000
                    dataDict["y"] = float(row[2]) * 1000
                    dataDict["z"] = float(row[3]) * 1000
                    dataDict["vx"] = float(row[4]) * 1000
                    dataDict["vy"] = float(row[5]) * 1000
                    dataDict["vz"] = float(row[6]) * 1000
                    self.ephemeris.append(dataDict)
                except:
                    continue
        self.ephemeris.sort(key=lambda x:x["timestamp"])
        self.updateEph(self.ephemeris[-1])

    def closestEph(self, targetTime):
        # find the closest ephemeris state to the provided targetTime
        if not self.ephemeris:
            raise ValueError("No ephemeris data available to find the closest state.")

        return min(
            self.ephemeris,
            key=lambda record: abs((record["timestamp"] - targetTime).seconds),
        )

    def propagateTo(self, targetTime):
        #find nearest ephemeris point to targetTime
        minSecondDifference = 1
        settings = satkit.propsettings()
        #settings.precompute_terms=None

        state,stateTime = self.packArray(self.closestEph(targetTime))
        try:
            propagatedState = satkit.propagate(state,stateTime,end=targetTime,propsettings=settings)
            return propagatedState.state
        except Exception as E:
            print(E)
            return state
            
    
    

    