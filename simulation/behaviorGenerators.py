from math import exp
from copy import deepcopy
import sqlite3
from contextlib import closing

from PySide6.QtCore import QDateTime, QTimeZone

from convert import Converter
from decode import Decoder
from loadConfig import cfgLoader, GLOBAL_CONFIG

import pdb


def behaviorStaticValue(value):
    while True:
        yield value

def behaviorRampValue(rampParams, startVal, cadence):
    step = 0
    steps = cadence * float(rampParams['rampSeconds'])
    if rampParams['rampType'] == 'Linear':
        increment = (float(rampParams['value']) - startVal)/steps
        rampFunction = lambda step:(increment * step)
    elif rampParams['rampType'] == 'Exponential':
        rampFunction = lambda step: float(rampParams['value']) + (startVal - float(rampParams['value']))* exp(rampParams['coefficient'] * (-1/cadence * step))
    elif rampParams['rampType'] == 'Step':
        rampFunction = lambda step: startVal

    while step < steps:
        yield rampFunction(step)
        step +=1

    while True:
        yield rampParams['value']

def behaviorPlayBackTelemetry(
    fieldInfo,
    database,
    startTime,
    structure,
    packetType,
    simulationMessageFunction=None,
):
    databasePath = cfgLoader.getPath("databases") / database
    tableName = f"{structure}_{packetType}"
    quotedTableName = '"' + tableName.replace('"', '""') + '"'
    fieldKey = f"{fieldInfo['definitionSource']}__{fieldInfo['fieldName']}"

    startDateTime = QDateTime.fromString(
        startTime, GLOBAL_CONFIG["qtDateFormat"]
    )
    if not startDateTime.isValid():
        raise ValueError(f"Invalid playback start time {startTime!r}.")
    startTimeSeconds = QDateTime(
        startDateTime.date(), startDateTime.time(), QTimeZone.utc()
    ).toSecsSinceEpoch()

    def report(message, level="INFO"):
        if simulationMessageFunction is None:
            return
        if hasattr(simulationMessageFunction, "emit"):
            simulationMessageFunction.emit(message, level)
        else:
            simulationMessageFunction(message, level)

    def reportPlaybackIssue(message, level="INFO"):
        if level.lower() in ("warning", "error"):
            report(message, level)

    decoder = Decoder(structure, reportPlaybackIssue)
    decoder.structureDict = deepcopy(decoder.structureDict)
    converter = Converter(report)
    query = (
        f"SELECT archivedPacket.data FROM {quotedTableName} AS archivedPacket "
        "JOIN packets ON packets.packetID = archivedPacket.packetID "
        "WHERE archivedPacket.time >= ? "
        "ORDER BY archivedPacket.time, archivedPacket.packetID"
    )
    lastValue = None
    foundValue = False

    with closing(sqlite3.connect(databasePath)) as connection:
        cursor = connection.execute(query, (startTimeSeconds,))
        for (rawPacket,) in cursor:
            decoded = decoder.readPacket(rawPacket)
            if not decoded:
                report(
                    f"Skipping an undecodable packet in {databasePath.name} "
                    f"for {structure}.{packetType}.",
                    "WARNING",
                )
                continue

            decodedFields, _, packetTemplate, decodedPacketType = decoded
            if str(decodedPacketType) != str(packetType):
                continue
            decodedFields, _ = converter.convertPacket(
                decodedFields, packetTemplate
            )
            fieldData = decodedFields.get(fieldKey)
            if fieldData is None:
                continue

            value = fieldData.get("rawValue", fieldData.get("convertedValue"))
            if value is None:
                continue
            lastValue = value
            foundValue = True
            yield value

    if not foundValue:
        raise ValueError(
            f"No {fieldInfo['fieldName']} telemetry was found in "
            f"{database!r} for {structure}.{packetType} at or after {startTime}."
        )

    report(
        f"Playback data exhausted for {structure}.{packetType} "
        f"{fieldInfo['fieldName']}; holding the last value.",
        "INFO",
    )
    while True:
        yield lastValue