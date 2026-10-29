import importlib
from multiprocessing import Process, get_context, Manager
from typing import Any

from loadConfig import GLOBAL_CONFIG
from liveTelemetry import LIVETLM

# SHARED_DICT = Manager().dict()
# SHARED_DICT['GLOBAL_CONFIG'] = GLOBAL_CONFIG
# SHARED_DICT['LIVETLM'] = LIVETLM
# ACTIVE_SUBPROCESSES = []
class ChildProcess(Process):
    def __init__(self):

class ChildProcessManager():
    def __init__(self):
        self.childProcesses = []
        self.manager = Manager()
        self.sharedData = self.manager.dict()

    def _run_gui_widget(
        self,
        module_name: str,
        class_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication([])
        widget_class = importlib.import_module(module_name)
        for name in class_name.split("."):
            widget_class = getattr(widget_class, name)

        widget = widget_class(*args, **kwargs)
        widget.show()
        app.exec()


    def launch_gui_process(self, widget_class: type, *args: Any, **kwargs: Any) -> Process:
        """Start a Qt widget in a spawned process, forwarding args to its constructor.

        The widget class and all positional and keyword arguments must be importable
        and pickleable for multiprocessing's spawn mode.
        """
        module_name = widget_class.__module__
        class_name = widget_class.__qualname__
        if module_name == "__main__" or "<locals>" in class_name:
            raise ValueError(
                "The widget class must be defined at module scope in an importable module."
            )

        process = get_context("spawn").Process(
            target=_run_gui_widget,
            args=(module_name, class_name, args, kwargs),
        )
        process.start()
        return process
