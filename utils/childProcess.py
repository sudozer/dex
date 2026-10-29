from __future__ import annotations

import importlib
from multiprocessing import Process, get_context
from multiprocessing.queues import Queue
from threading import Thread
from typing import Any

from liveTelemetry import LIVETLM


def _run_gui_widget(
    module_name: str,
    class_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    telemetry_queue: Queue | None,
) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget_class = importlib.import_module(module_name)
    for name in class_name.split("."):
        widget_class = getattr(widget_class, name)

    if telemetry_queue is not None:
        kwargs["telemetry_queue"] = telemetry_queue

    widget = widget_class(*args, **kwargs)
    widget.show()
    app.exec()


def _release_telemetry_queue(process: Process, telemetry_queue: Queue) -> None:
    process.join()
    LIVETLM.removeQueue(telemetry_queue)
    telemetry_queue.cancel_join_thread()
    telemetry_queue.close()


def launch_gui_process(
    widget_class: type,
    *args: Any,
    share_telemetry: bool = False,
    **kwargs: Any,
) -> Process:
    """Start an importable Qt widget in a spawned process."""
    module_name = widget_class.__module__
    class_name = widget_class.__qualname__
    if module_name == "__main__" or "<locals>" in class_name:
        raise ValueError(
            "The widget class must be defined at module scope in an importable module."
        )

    if share_telemetry and "telemetry_queue" in kwargs:
        raise ValueError(
            "The telemetry_queue argument is managed by launch_gui_process."
        )

    telemetry_queue = get_context("spawn").Queue() if share_telemetry else None
    if telemetry_queue is not None:
        LIVETLM.registerQueue(telemetry_queue)

    process = get_context("spawn").Process(
        target=_run_gui_widget,
        args=(module_name, class_name, args, kwargs, telemetry_queue),
    )

    try:
        process.start()
    except Exception:
        if telemetry_queue is not None:
            LIVETLM.removeQueue(telemetry_queue)
            telemetry_queue.cancel_join_thread()
            telemetry_queue.close()
        raise
    if telemetry_queue is not None:
        Thread(
            target=_release_telemetry_queue,
            args=(process, telemetry_queue),
            daemon=True,
        ).start()
    return process


class ChildProcessManager:
    def __init__(self) -> None:
        self.childProcesses: list[Process] = []

    def launch_gui_process(
        self,
        widget_class: type,
        *args: Any,
        **kwargs: Any,
    ) -> Process:
        process = launch_gui_process(widget_class, *args, **kwargs)
        self.childProcesses.append(process)
        return process
