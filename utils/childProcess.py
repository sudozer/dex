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
    shutdown_event: Any,
) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    widget_class = importlib.import_module(module_name)
    for name in class_name.split("."):
        widget_class = getattr(widget_class, name)

    if telemetry_queue is not None:
        kwargs["telemetry_queue"] = telemetry_queue

    widget = widget_class(*args, **kwargs)
    shutdown_timer = QTimer(widget)

    def close_on_request() -> None:
        if shutdown_event.is_set():
            shutdown_timer.stop()
            widget.close()
            app.quit()

    try:
        widget.show()
        shutdown_timer.timeout.connect(close_on_request)
        shutdown_timer.start(100)
        app.exec()
    finally:
        shutdown_timer.stop()
        if telemetry_queue is not None:
            LIVETLM.stopListeningToQueue(telemetry_queue)
            LIVETLM.threadPool.waitForDone()
        widget.close()


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

    context = get_context("spawn")
    telemetry_queue = context.Queue() if share_telemetry else None
    shutdown_event = context.Event()
    if telemetry_queue is not None:
        LIVETLM.registerQueue(telemetry_queue)

    process = context.Process(
        target=_run_gui_widget,
        args=(module_name, class_name, args, kwargs, telemetry_queue, shutdown_event),
    )

    try:
        process.start()
    except Exception:
        if telemetry_queue is not None:
            LIVETLM.removeQueue(telemetry_queue)
            telemetry_queue.cancel_join_thread()
            telemetry_queue.close()
        raise
    process.shutdown_event = shutdown_event
    if telemetry_queue is not None:
        cleanup_thread = Thread(
            target=_release_telemetry_queue,
            args=(process, telemetry_queue),
            daemon=True,
        )
        process.telemetry_cleanup_thread = cleanup_thread
        cleanup_thread.start()
    return process


def shutdown_gui_process(process: Process, timeout: float = 5.0) -> None:
    if process.is_alive():
        process.shutdown_event.set()
        process.join(timeout)
    else:
        process.join(timeout=0)
    if process.is_alive():
        process.terminate()
        process.join(timeout)
    if process.is_alive():
        raise TimeoutError(f"GUI process {process.pid} did not exit.")
    cleanup_thread = getattr(process, "telemetry_cleanup_thread", None)
    if cleanup_thread is not None:
        cleanup_thread.join(timeout)
        if cleanup_thread.is_alive():
            raise TimeoutError(f"GUI process {process.pid} cleanup did not finish.")


def shutdown_gui_processes(processes: list[Process]) -> None:
    errors = []
    for process in processes:
        try:
            shutdown_gui_process(process)
        except (OSError, TimeoutError) as error:
            errors.append(f"{process.pid}: {error}")
    processes.clear()
    if errors:
        raise RuntimeError(f"Unable to shut down GUI processes: {'; '.join(errors)}")


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
