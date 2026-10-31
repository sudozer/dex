from math import exp
def behaviorStaticValue(value):
    while True:
        yield value

def behaviorRampValue(rampParams, startVal, cadence):
    step = 0
    steps = cadence * rampParams['rampSeconds']
    if rampParams['rampType'] == 'Linear':
        increment = (rampParams['value'] - startVal)/steps
        rampFunction = lambda step:(increment * step)
    elif rampParams['rampType'] == 'Exponential':
        rampFunction = lambda step: rampParams['value'] + (startVal - rampParams['value'])* exp(rampParams['coefficient'] * (-1/cadence * step))

    while step < steps:
        yield rampFunction(step)
        step +=1

    while True:
        yield rampParams['value']

def behaviorPlayBackTelemetry(fieldInfo,database,startTime):
    while True:
        yield 0