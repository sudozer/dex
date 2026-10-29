from copy import deepcopy
from PySide6.QtCore import QObject, QThreadPool, QRunnable, Slot
from threading import Lock, Thread
from typing import Any, Callable

class PacketCallback(QRunnable):
    def __init__(self,func_):    
        super().__init__()
        self.func_ = func_

    @Slot()
    def run(self):
        self.func_()

class LiveTelemetry(QObject):
    def __init__(self):
        super().__init__()
        self.registry = {}
        self.mostRecentPacket = {}
        self.threadPool = QThreadPool()
        self.msgFunctions = []
        self._queues = []
        self._lock = Lock()

    def pushPacket(self, packet, *, broadcast=True):
        """
        Accept a freshly decoded and converted packet to be 
        pushed to live displays.
        """
        packet_type = packet['metadata_']['packetType']
        with self._lock:
            self.mostRecentPacket[packet_type] = packet
            callbacks = tuple(self.registry.get(packet_type, ()))
            if broadcast and self._queues:
                packet_snapshot = deepcopy(packet)
                for packet_queue in self._queues:
                    packet_queue.put(packet_snapshot)

        for callback in callbacks:
            callback_function = (
                callback["func_"] if isinstance(callback, dict) else callback
            )
            callbackWorker = PacketCallback(callback_function)
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
        listener.start()
        return listener

    def _consumeQueue(self, packet_queue: Any) -> None:
        while True:
            packet = packet_queue.get()
            self.pushPacket(packet, broadcast=False)

    def registerCallback(
        self,
        packetType,
        callback: Callable[[], None] | dict[str, Callable[[], None]],
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