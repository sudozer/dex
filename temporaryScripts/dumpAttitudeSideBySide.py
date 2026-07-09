import csv
from pathlib import Path
from datetime import datetime

# File paths
flightPath = Path('../ascFiles/Art-II_Flight.csv')
predictPath = Path('../ascFiles/Art-II_Predict.csv')
productPath = Path('../dataProducts/attitudeComparison.csv')

def parse_gmt_time(gmt_str):
    """Parse GMT string in format DDD/HH:MM:SS to a comparable value."""
    if not gmt_str or gmt_str.strip() == '':
        return None
    try:
        parts = gmt_str.split('/')
        day = int(parts[0])
        time_parts = parts[1].split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        second = int(time_parts[2])
        return day * 86400 + hour * 3600 + minute * 60 + second
    except:
        return None

# Read flight data
flight_data = []
with open(flightPath, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        flight_data.append(row)

# Read predict data
predict_data = []
with open(predictPath, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        predict_data.append(row)

# Create output CSV
with open(productPath, 'w', newline='') as outFile:
    writer = csv.writer(outFile)
    writer.writerow([
        'predict_gmt_start', 'predict_gmt_end', 
        'predict_icrf_yaw', 'predict_icrf_pitch', 'predict_icrf_roll',
        'flight_gmt_start', 'flight_gmt_end',
        'flight_icrf_yaw', 'flight_icrf_pitch', 'flight_icrf_roll',
        'time_difference_sec'
    ])
    
    flight_idx = 0
    
    for predict_row in predict_data:
        # Parse predict times
        predict_start_time = parse_gmt_time(predict_row['gmt start'])
        predict_end_time = parse_gmt_time(predict_row['gmt end'])
        
        # Build predict row list
        predict_list = [
            predict_row['gmt start'], predict_row['gmt end'],
            predict_row['ICRF Yaw'], predict_row['ICRF Pitch'], predict_row['ICRF Roll']
        ]
        
        # Check if predict end time passes the next flight row start time
        flight_list = []
        time_diff = ''
        
        if flight_idx < len(flight_data):
            flight_start_time = parse_gmt_time(flight_data[flight_idx]['gmt start'])
            
            # If predict end time is >= flight start time, write flight row alongside
            if flight_start_time is not None and predict_end_time is not None:
                if predict_end_time >= flight_start_time:
                    flight_row = flight_data[flight_idx]
                    flight_list = [
                        flight_row['gmt start'], flight_row['gmt end'],
                        flight_row['ICRF Yaw'], flight_row['ICRF Pitch'], flight_row['ICRF Roll']
                    ]
                    # Calculate time difference (flight start - predict start)
                    time_diff = flight_start_time - predict_start_time
                    flight_idx += 1
        
        writer.writerow(predict_list + flight_list + [time_diff])

print(f"Attitude comparison written to {productPath}")
