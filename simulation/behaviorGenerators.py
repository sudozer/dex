def behaviorStaticValue(value):
    while True:
        yield value

def behaviorRampValue(rampParams, startVal, cadence):
    while True:
        yield 0
    pass

def behaviorPlayBackTelemetry(fieldInfo,database,startTime):
    while True:
        yield 0
    pass