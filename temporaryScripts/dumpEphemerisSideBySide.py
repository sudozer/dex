from orbitProp import OrbitProp
import csv
import datetime
import pdb
import math
from pathlib import Path

dateFormatString = "%Y-%m-%dT%H:%M:%S.%f"
def calculate_ephemeris_differences(predict_row, asflown_row):
    """Calculate time, position, and velocity differences between predicted and as-flown ephemeris."""
    # Calculate time difference
    asflown_dt = datetime.datetime.strptime(asflown_row['timestamp'].strftime(dateFormatString), dateFormatString)
    predict_dt = datetime.datetime.strptime(predict_row['timestamp'].strftime(dateFormatString), dateFormatString)
    time_diff = (asflown_dt - predict_dt).total_seconds()
    
    # Position differences
    dx = asflown_row['x'] - predict_row['x']
    dy = asflown_row['y'] - predict_row['y']
    dz = asflown_row['z'] - predict_row['z']
    abs_pos_diff = math.sqrt(dx**2 + dy**2 + dz**2)
    
    # Velocity differences
    dvx = asflown_row['vx'] - predict_row['vx']
    dvy = asflown_row['vy'] - predict_row['vy']
    dvz = asflown_row['vz'] - predict_row['vz']
    abs_vel_diff = math.sqrt(dvx**2 + dvy**2 + dvz**2)
    
    # Radial and tangential components (using predict state as reference direction)
    r_mag = math.sqrt(predict_row['x']**2 + predict_row['y']**2 + predict_row['z']**2)
    v_mag = math.sqrt(predict_row['vx']**2 + predict_row['vy']**2 + predict_row['vz']**2)
    
    if r_mag > 0:
        radial_pos_diff = (dx * predict_row['x'] + dy * predict_row['y'] + dz * predict_row['z']) / r_mag
        tangential_pos_diff = math.sqrt(abs_pos_diff**2 - radial_pos_diff**2)
    else:
        radial_pos_diff = 0
        tangential_pos_diff = abs_pos_diff
        
    if v_mag > 0:
        radial_vel_diff = (dvx * predict_row['vx'] + dvy * predict_row['vy'] + dvz * predict_row['vz']) / v_mag
        tangential_vel_diff = math.sqrt(abs_vel_diff**2 - radial_vel_diff**2)
    else:
        radial_vel_diff = 0
        tangential_vel_diff = abs_vel_diff
    #pdb.set_trace()
    return [time_diff, abs_pos_diff, abs_vel_diff, radial_pos_diff, tangential_pos_diff, radial_vel_diff, tangential_vel_diff]

ascPath = Path('../ascFiles')
productPath = Path('../dataProducts/ephemerisComparison.csv')
asFlownData = OrbitProp()
asFlownData.readASC("../ascFiles/art2_asFlown.oem")
files = [f for f in ascPath.iterdir() if f.is_file() and f.suffix == '.asc']

# Store ephemeris with source filenames
ephemerisWithSource = []
for file in files:
    if 'asFlown' not in str(file):
        tempData = OrbitProp()
        tempData.readASC(str(file))
        for row in tempData.ephemeris:
            row_with_source = row.copy()
            row_with_source['_source_file'] = file.name
            ephemerisWithSource.append(row_with_source)

# Sort by timestamp
ephemerisWithSource.sort(key=lambda x: x['timestamp'])

with open(productPath,'w',newline='') as outFile:
    writer = csv.writer(outFile)
    writer.writerow(['source_file','prediction_creation_datestamp','predict_timestamp','predict_ICRF_X','predict_ICRF_Y','predict_ICRF_Z','predict_ICRF_VX','predict_ICRF_VY','predict_ICRF_VZ','asFlown_Timestamp','asFlown_ICRF_X','asFlown_ICRF_Y','asFlown_ICRF_Z','asFlown_ICRF_VX','asFlown_ICRF_VY','asFlown_ICRF_VZ','time_diff_sec','abs_pos_diff_km','abs_vel_diff_km_s','radial_pos_diff_km','tangential_pos_diff_km','radial_vel_diff_km_s','tangential_vel_diff_km_s'])
    
    firstPredictTimestamp = ephemerisWithSource[0]['timestamp']
    asFlowni = 0
    while asFlowni < len(asFlownData.ephemeris) and asFlownData.ephemeris[asFlowni]['timestamp'] < firstPredictTimestamp:
        asFlowni += 1

    for row in ephemerisWithSource:
        source_file = row['_source_file']
        rowlist = [source_file,row['creationDate'], row['timestamp'],row['x'],row['y'],row['z'],row['vx'],row['vy'],row['vz']]
        asFlown = None

        while asFlowni < len(asFlownData.ephemeris) and asFlownData.ephemeris[asFlowni]['timestamp'] < row['timestamp']:
            asFlown = asFlownData.ephemeris[asFlowni]
            asFlowni += 1

        if asFlown is not None:
            asFlownList = [asFlown['timestamp'],asFlown['x'],asFlown['y'],asFlown['z'],asFlown['vx'],asFlown['vy'],asFlown['vz']]
            diff_list = calculate_ephemeris_differences(row, asFlown)
            writer.writerow(rowlist + asFlownList + diff_list)
        else:
            writer.writerow(rowlist + [''] * 8 + [''] * 7)