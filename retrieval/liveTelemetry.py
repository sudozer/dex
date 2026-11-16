from copy import deepcopy
import logging
import sqlite3
from PySide6.QtCore import QObject, QThreadPool, QRunnable, Slot
from threading import Lock, Thread
from typing import Any, Callable

from dataStructures import PACKET_STRUCTURE_COMPONENTS
from loadConfig import GLOBAL_CONFIG


class PacketCallback(QRunnable):
    def __init__(self, func_, packet=None, passPacket=False):
        super().__init__()
        self.func_ = func_
        self.packet = packet
        self.passPacket = passPacket

    @Slot()
    def run(self):
        if self.passPacket:
            self.func_(self.packet)
        else:
            self.func_()

class LiveTelemetry(QObject):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.registry = {}
        self.mostRecentPacket = {}
        self.threadPool = QThreadPool()
        self.msgFunctions = []
        self._queues = []
        self._queueListeners = {}
        self._lock = Lock()
        self._packetLock = Lock()
        self._telemetryDatatagCallbacks = []

    def pushPacket(self, packet, *, broadcast=True):
        """
        Accept a freshly decoded and converted packet to be 
        pushed to live displays.
        """
        with self._packetLock:
            packet_type = packet['metadata_']['packetType']
            with self._lock:
                self.mostRecentPacket[packet_type] = packet
                callbacks = tuple(self.registry.get(packet_type, ()))
                if broadcast and self._queues:
                    packet_snapshot = deepcopy(packet)
                    for packet_queue in self._queues:
                        packet_queue.put(packet_snapshot)

            for callback in callbacks:
                isCallbackConfig = isinstance(callback, dict)
                callback_function = (
                    callback["func_"] if isCallbackConfig else callback
                )
                passPacket = isCallbackConfig and callback.get("passPacket", False)
                if isCallbackConfig and callback.get("synchronous", False):
                    try:
                        callback_function(packet)
                    except sqlite3.Error:
                        message = (
                            f"Failed to write telemetry datatag for packet "
                            f"{packet_type}."
                        )
                        self.logger.exception(message)
                        self.msgFunction(message, "ERROR")
                    continue
                callbackWorker = PacketCallback(
                    callback_function,
                    deepcopy(packet) if passPacket else None,
                    passPacket,
                )
                self.threadPool.start(callbackWorker)

    def registerQueue(self, packet_queue: Any) -> None:
        """Forward packet snapshots to a consumer in another process."""
        with self._lock:
            if packet_queue not in self._queues:
                self._queues.append(packet_queue)

    def removeQueue(self, packet_queue: Any) -> None:
        with self._lock:
            if packet_queue in self._queues:
                self._queues.remove(packet_queue)

    def listenToQueue(self, packet_queue: Any) -> Thread:
        """Apply packets received over IPC to this process's local telemetry."""
        listener = Thread(
            target=self._consumeQueue,
            args=(packet_queue,),
            daemon=True,
        )
        with self._lock:
            self._queueListeners.setdefault(packet_queue, []).append(listener)
        listener.start()
        return listener

    def _consumeQueue(self, packet_queue: Any) -> None:
        while True:
            packet = packet_queue.get()
            if (
                isinstance(packet, dict)
                and len(packet) == 1
                and packet.get("__liveTelemetryStop__") is True
            ):
                return
            self.pushPacket(packet, broadcast=False)

    def stopListeningToQueue(self, packet_queue: Any) -> None:
        with self._lock:
            listeners = self._queueListeners.pop(packet_queue, [])
        for listener in listeners:
            packet_queue.put({"__liveTelemetryStop__": True})
        for listener in listeners:
            listener.join()

    def registerCallback(
        self,
        packetType,
        callback: Callable[..., None] | dict[str, Any],
    ):
        """
        Register a field to be tracked in live telemetry
        component.
        """
        with self._lock:
            self.registry.setdefault(packetType, []).append(callback)

    def removeCallback(self,packetType,callback):
        """
        remove a previously registered callback
        """
        with self._lock:
            callbacks = self.registry.get(packetType)
            if callbacks and callback in callbacks:
                callbacks.remove(callback)

    def registerTelemetryDatatags(self, storage):
        """Register transition-aware callbacks for configured telemetry tags."""
        with self._packetLock:
            for packetType, callback in self._telemetryDatatagCallbacks:
                self.removeCallback(packetType, callback)
            self._telemetryDatatagCallbacks.clear()

            conditions = GLOBAL_CONFIG["storage"]["dataTags"].get("telemetry", [])
            if not isinstance(conditions, list):
                self._reportError(
                    "Telemetry datatag configuration must be a list.",
                )
                return

            for condition in conditions:
                try:
                    packetType, callback = self._createTelemetryDatatagCallback(
                        condition, storage
                    )
                except (KeyError, TypeError, ValueError) as error:
                    self._reportError(
                        f"Unable to register telemetry datatag {condition!r}: {error}",
                    )
                    continue

                self.registerCallback(packetType, callback)
                self._telemetryDatatagCallbacks.append((packetType, callback))

    def _createTelemetryDatatagCallback(self, condition, storage):
        structure = condition["structure"]
        packetType = condition["packet"]
        fieldPath = condition["field"]
        componentName, fieldName = fieldPath.split(".", 1)
        components = PACKET_STRUCTURE_COMPONENTS[structure][packetType]
        fieldDefinition = next(
            (
                field
                for component in components
                if component["component"] == componentName
                for field in component["fields"]
                if field["fieldName"] == fieldName
            ),
            None,
        )
        if fieldDefinition is None:
            raise ValueError(f"field {fieldPath!r} is not defined")
        fieldKey = (
            f'{fieldDefinition["definitionSource"]}__'
            f'{fieldDefinition["fieldName"]}'
        )
        fieldType = fieldDefinition.get("conversion", {}).get(
            "convertedType", fieldDefinition["type"]
        )
        comparator = condition["comparator"]
        triggerValue = self._convertTelemetryDatatagValue(
            condition["value"], fieldType
        )
        if comparator not in ("=", ">=", "<="):
            raise ValueError(f"unsupported comparator {comparator!r}")

        datatagDescription = (
            f"{structure}.{packetType}.{fieldPath} "
            f"{comparator} {condition['value']}"
        )
        triggered = False

        def checkCondition(packet):
            nonlocal triggered
            fieldData = packet.get(fieldKey)
            fieldValue = (
                fieldData.get("convertedValue", fieldData.get("rawValue"))
                if isinstance(fieldData, dict)
                else None
            )
            try:
                conditionMet = (
                    fieldValue is not None
                    and self._compareTelemetryDatatagValue(
                        fieldValue, comparator, triggerValue
                    )
                )
            except TypeError as error:
                self._reportError(
                    f"Cannot compare telemetry field {fieldPath}: {error}",
                )
                conditionMet = False

            if conditionMet and not triggered:
                storage.writeDataTag("TLM", datatagDescription)
            triggered = conditionMet

        return packetType, {
            "func_": checkCondition,
            "passPacket": True,
            "synchronous": True,
        }

    @staticmethod
    def _convertTelemetryDatatagValue(value, fieldType):
        if fieldType in ("char", "str", "string"):
            return str(value)
        if fieldType in ("float", "double"):
            return float(value)
        if fieldType in ("int", "uint") or fieldType.endswith("_t"):
            return int(value)
        raise ValueError(f"unsupported telemetry field type {fieldType!r}")

    @staticmethod
    def _compareTelemetryDatatagValue(fieldValue, comparator, triggerValue):
        if comparator == ">=":
            return fieldValue >= triggerValue
        if comparator == "<=":
            return fieldValue <= triggerValue
        return fieldValue == triggerValue

    def _reportError(self, message):
        self.logger.error(message)
        self.msgFunction(message, "ERROR")

    def registerMessageFunction(self,msgFunction):
        """
        register a message function for printing errors or debugging info
        since LIVETLM is a shared object
        """
        self.msgFunctions.append(msgFunction)

    def removeMessageFunction(self,msgFunction):
        if msgFunction in self.msgFunctions:
            self.msgFunctions.remove(msgFunction)

    def msgFunction(self,msg,level="INFO"):
        for f in self.msgFunctions:
            f(msg,level)

LIVETLM = LiveTelemetry()