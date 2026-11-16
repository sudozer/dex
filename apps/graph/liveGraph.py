import json
import logging
import math
import re
from html import escape as html_escape
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from dataStructures import PACKET_STRUCTURE_COMPONENTS
from liveTelemetry import LIVETLM
from loadConfig import GLOBAL_CONFIG, cfgLoader
from telemetryRetrieval import retrieveAllDatatags
from telemetrySelector import TelemetryFieldSelector

LOGGER = logging.getLogger(__name__)
_OPEN_GRAPHS = []
TAG_COLORS = {
    "CMD": "#50f2cc",
    "SYS": "#f7e8a3",
    "MAN": "#f57da5",
    "TLM": "#6db9f7",
}


class UtcAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            try:
                labels.append(
                    datetime.fromtimestamp(value, timezone.utc).strftime(
                        "%Y-%m-%d\n%H:%M:%S"
                    )
                )
            except (OverflowError, OSError, ValueError):
                labels.append("")
        return labels


def _resolve_field(field_config):
    structure = field_config.get("structure")
    packet = field_config.get("packet")
    field_name = field_config.get("field")
    if structure not in PACKET_STRUCTURE_COMPONENTS:
        raise ValueError(f"Unknown telemetry structure: {structure!r}")
    if packet not in PACKET_STRUCTURE_COMPONENTS[structure]:
        raise ValueError(f"Unknown packet {packet!r} in structure {structure!r}")
    matches = []
    for component in PACKET_STRUCTURE_COMPONENTS[structure][packet]:
        for field in component["fields"]:
            if field_name in (
                field["fieldName"],
                f'{component["component"]}.{field["fieldName"]}',
            ):
                matches.append((component, field))
    if len(matches) == 1:
        component, field = matches[0]
        return {
            "structure": structure,
            "packet": packet,
            "field": field["fieldName"],
            "fieldKey": f'{field["definitionSource"]}__{field["fieldName"]}',
            "fieldName": field["fieldName"],
        }
    if len(matches) > 1:
        raise ValueError(
            f"Telemetry field {field_name!r} is ambiguous in "
            f"{structure!r}/{packet!r}; use component.field notation."
        )
    raise ValueError(
        f"Telemetry field {field_name!r} was not found in "
        f"{structure!r}/{packet!r}"
    )


def launchGraph(config=None):
    graph = LiveGraph(config)
    graph.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    _OPEN_GRAPHS.append(graph)

    def remove_graph():
        if graph in _OPEN_GRAPHS:
            _OPEN_GRAPHS.remove(graph)

    graph.destroyed.connect(remove_graph)
    graph.show()
    return graph


class LiveGraph(QMainWindow):
    packetReceived = Signal(dict)

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Telemetry Graph")
        self.resize(1100, 720)
        self.packetReceived.connect(
            self._receive_packet, Qt.ConnectionType.QueuedConnection
        )
        self.config = config or {}
        self.series = []
        self.axes = []
        self._callbacks = {}
        self._color_index = 0
        self._loading_config = True
        self._setting_range = False
        self._user_zoomed = False
        self._tag_rows = []
        self._tag_items = []
        self._tag_error_reported = False

        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)

        top_controls = QHBoxLayout()
        top_controls.addWidget(QLabel("Graph Name"))
        self.graph_name = QLineEdit(self.config.get("name", ""))
        self.graph_name.setPlaceholderText("Graph Name")
        top_controls.addWidget(self.graph_name, 1)
        top_controls.addWidget(QLabel("Points per field"))
        self.point_count = QSpinBox()
        self.point_count.setRange(1, 1000000)
        self.point_count.setValue(
            max(
                1,
                int(
                    self.config.get(
                        "dataPoints", GLOBAL_CONFIG.get("graphingDataPoints", 200)
                    )
                ),
            )
        )
        top_controls.addWidget(self.point_count)
        self.point_count.valueChanged.connect(self._trim_series)
        self.store_button = QPushButton("Store graph")
        self.store_button.clicked.connect(self.store_graph)
        top_controls.addWidget(self.store_button)
        self.open_button = QPushButton("Open stored graph")
        self.open_button.clicked.connect(self.open_stored_graph)
        top_controls.addWidget(self.open_button)
        root_layout.addLayout(top_controls)

        plot_controls = QHBoxLayout()
        self.zoom_box = QCheckBox("Drag to zoom")
        self.zoom_box.setChecked(True)
        self.zoom_box.toggled.connect(self._set_zoom_mode)
        plot_controls.addWidget(self.zoom_box)
        plot_controls.addWidget(QLabel("X"))
        self._add_zoom_button(plot_controls, "+", lambda: self._zoom_x(0.8))
        self._add_zoom_button(plot_controls, "-", lambda: self._zoom_x(1.25))
        plot_controls.addWidget(QLabel("Y"))
        self._add_zoom_button(plot_controls, "+", lambda: self._zoom_y(0.8))
        self._add_zoom_button(plot_controls, "-", lambda: self._zoom_y(1.25))
        reset_button = QPushButton("Reset zoom")
        reset_button.clicked.connect(self.reset_zoom)
        plot_controls.addWidget(reset_button)
        plot_controls.addStretch(1)
        root_layout.addLayout(plot_controls)

        self.plot_widget = pg.PlotWidget(
            axisItems={"bottom": UtcAxisItem(orientation="bottom")}
        )
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.getAxis("bottom").enableAutoSIPrefix(False)
        self.plot_item.setLabel("bottom", "Ground timestamp (UTC)")
        self.plot_item.showGrid(x=True, y=True, alpha=0.25)
        self.plot_item.addLegend()
        self.base_view = self.plot_item.getViewBox()
        self.base_view.setMouseMode(pg.ViewBox.RectMode)
        self.base_view.sigResized.connect(self._sync_view_geometry)
        self.base_view.sigRangeChanged.connect(self._range_changed)
        root_layout.addWidget(self.plot_widget, 1)

        lower = QHBoxLayout()
        axes_scroll = QScrollArea()
        axes_scroll.setWidgetResizable(True)
        axes_scroll.setMaximumHeight(150)
        self.axes_container = QWidget()
        self.axes_layout = QHBoxLayout(self.axes_container)
        self.axes_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        axes_scroll.setWidget(self.axes_container)
        tags_group = QVBoxLayout()
        tags_group.addWidget(QLabel("Display datatags"))
        tag_options = self.config.get("datatags", {})
        self.tag_checkboxes = {}
        for tag_type, label in (
            ("CMD", "Command"),
            ("SYS", "System"),
            ("MAN", "Manual"),
            ("TLM", "Telemetry"),
        ):
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(tag_options.get(tag_type, True)))
            checkbox.toggled.connect(self._refresh_datatags)
            self.tag_checkboxes[tag_type] = checkbox
            tags_group.addWidget(checkbox)
        lower.addLayout(tags_group)
        axis_controls = QVBoxLayout()
        add_axis_button = QPushButton("Add Y axis scale")
        add_axis_button.clicked.connect(self._add_axis)
        axis_controls.addWidget(add_axis_button)
        axis_controls.addWidget(axes_scroll, 1)
        lower.addLayout(axis_controls, 1)
        root_layout.addLayout(lower)

        axes_config = self.config.get("axes", [])
        if not isinstance(axes_config, list):
            raise ValueError("Graph config 'axes' must be a list.")
        if axes_config:
            for axis_config in axes_config:
                axis = self._add_axis()
                for field_config in axis_config.get("fields", []):
                    self._add_field(axis, field_config)
        else:
            self._add_axis()

        self._loading_config = False
        self._maybe_auto_range()
        self._set_zoom_mode(self.zoom_box.isChecked())
        self._refresh_datatags()
        self._datatag_timer = QTimer(self)
        self._datatag_timer.timeout.connect(self._refresh_datatags)
        self._datatag_timer.start(5000)
        self._mouse_proxy = pg.SignalProxy(
            self.plot_item.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._mouse_moved,
        )

    @staticmethod
    def _add_zoom_button(layout, text, callback):
        button = QPushButton(text)
        button.setFixedWidth(34)
        button.clicked.connect(callback)
        layout.addWidget(button)

    def _add_axis(self):
        axis_index = len(self.axes)
        view = self.base_view
        axis_item = None
        if axis_index:
            if axis_index == 1:
                self.plot_item.showAxis("right")
                axis_item = self.plot_item.getAxis("right")
            else:
                axis_item = pg.AxisItem("right")
                self.plot_item.layout.addItem(axis_item, 2, axis_index + 1)
            axis_item.setLabel("")
            view = pg.ViewBox()
            view.setXLink(self.base_view)
            view.setMouseMode(pg.ViewBox.RectMode)
            view.setZValue(-10000)
            view.sigRangeChanged.connect(self._range_changed)
            self.plot_item.scene().addItem(view)
            axis_item.linkToView(view)
        view.setMouseEnabled(x=axis_index == 0, y=True)
        group = {
            "view": view,
            "axisItem": axis_item,
            "fields": [],
            "control": QWidget(),
        }
        control_layout = QVBoxLayout(group["control"])
        control_layout.setContentsMargins(5, 2, 5, 2)
        header = QHBoxLayout()
        header.addWidget(QLabel(f"Y scale {axis_index + 1}"))
        add_button = QPushButton("Add telemetry field")
        add_button.clicked.connect(lambda checked=False, item=group: self._choose_field(item))
        header.addWidget(add_button)
        if axis_index:
            remove_button = QPushButton("Remove scale")
            remove_button.clicked.connect(
                lambda checked=False, item=group: self._remove_axis(item)
            )
            header.addWidget(remove_button)
        control_layout.addLayout(header)
        field_layout = QHBoxLayout()
        group["fieldLayout"] = field_layout
        control_layout.addLayout(field_layout)
        self.axes_layout.addWidget(group["control"])
        self.axes.append(group)
        if axis_index:
            self._sync_view_geometry()
        return group

    def _choose_field(self, axis):
        selector = TelemetryFieldSelector(self)
        if selector.exec() == QDialog.DialogCode.Accepted:
            try:
                self._add_field(axis, selector.returnDict)
            except (KeyError, ValueError) as error:
                QMessageBox.warning(self, "Cannot add telemetry field", str(error))

    def _add_field(self, axis, field_config):
        field = _resolve_field(field_config)
        if any(existing["id"] == field for existing in axis["fields"]):
            return
        series = {
            "id": field,
            "axis": axis,
            "x": [],
            "y": [],
            "values": [],
            "curve": pg.PlotDataItem(
                pen=pg.intColor(self._color_index, hues=12, values=1),
                name=field["fieldName"],
                connect="finite",
            ),
        }
        self._color_index += 1
        axis["view"].addItem(series["curve"])
        self.plot_item.legend.addItem(series["curve"], field["fieldName"])
        axis["fields"].append(series)
        self.series.append(series)

        field_widget = QWidget()
        field_row = QHBoxLayout(field_widget)
        field_row.setContentsMargins(0, 0, 0, 0)
        field_row.addWidget(QLabel(field["fieldName"]))
        remove_button = QPushButton("×")
        remove_button.setFixedWidth(26)
        remove_button.setToolTip("Remove telemetry field")
        remove_button.clicked.connect(
            lambda checked=False, item=series: self._remove_field(item)
        )
        field_row.addWidget(remove_button)
        axis["fieldLayout"].addWidget(field_widget)
        series["control"] = field_widget

        packet_type = field["packet"]
        if packet_type not in self._callbacks:
            callback = {"func_": self._packet_callback, "passPacket": True}
            self._callbacks[packet_type] = callback
            LIVETLM.registerCallback(packet_type, callback)
        existing_packet = LIVETLM.mostRecentPacket.get(packet_type)
        if existing_packet is not None:
            self._append_packet(existing_packet, [series])
            if series["x"] and not self._loading_config:
                self.reset_zoom()

    def _remove_field(self, series):
        series["axis"]["fields"].remove(series)
        self.series.remove(series)
        series["axis"]["view"].removeItem(series["curve"])
        self.plot_item.legend.removeItem(series["curve"])
        series["control"].deleteLater()
        packet_type = series["id"]["packet"]
        if not any(item["id"]["packet"] == packet_type for item in self.series):
            callback = self._callbacks.pop(packet_type, None)
            if callback is not None:
                LIVETLM.removeCallback(packet_type, callback)
        self._refresh_tag_positions()
        self._maybe_auto_range()

    def _remove_axis(self, axis):
        if axis not in self.axes or len(self.axes) == 1:
            return
        if axis is not self.axes[-1]:
            QMessageBox.information(
                self,
                "Remove Y scale",
                "Remove Y scales in reverse order, starting with the last scale.",
            )
            return
        for series in tuple(axis["fields"]):
            self._remove_field(series)
        self.axes.remove(axis)
        if axis["axisItem"] is not None:
            self.plot_item.scene().removeItem(axis["view"])
            if axis["axisItem"] is not self.plot_item.getAxis("right"):
                axis["axisItem"].setVisible(False)
                self.plot_item.layout.removeItem(axis["axisItem"])
                self.plot_item.scene().removeItem(axis["axisItem"])
            elif not any(item["axisItem"] is axis["axisItem"] for item in self.axes):
                self.plot_item.hideAxis("right")
                axis["axisItem"].setVisible(False)
        axis["control"].deleteLater()

    def _packet_callback(self, packet):
        self.packetReceived.emit(packet)

    @Slot(dict)
    def _receive_packet(self, packet):
        packet_type = packet.get("metadata_", {}).get("packetType")
        matching = [
            item for item in self.series if item["id"]["packet"] == packet_type
        ]
        if matching:
            self._append_packet(packet, matching)

    def _append_packet(self, packet, series_items):
        metadata = packet.get("metadata_", {})
        timestamp = metadata.get("groundTimestampUTC")
        if not timestamp:
            return
        try:
            moment = datetime.strptime(
                timestamp, GLOBAL_CONFIG["datetimeFormat"]
            ).replace(tzinfo=timezone.utc)
            x_value = moment.timestamp()
        except (KeyError, TypeError, ValueError, OverflowError):
            LOGGER.warning("Skipping telemetry packet with invalid ground timestamp %r", timestamp)
            return
        for series in series_items:
            field = packet.get(series["id"]["fieldKey"])
            if not isinstance(field, dict):
                continue
            value = field.get("convertedValue")
            if value is None:
                value = field.get("rawValue")
            try:
                y_value = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(y_value):
                continue
            if series["x"] and x_value < series["x"][-1]:
                continue
            if series["x"] and x_value == series["x"][-1]:
                series["y"][-1] = y_value
                series["values"][-1] = value
            else:
                series["x"].append(x_value)
                series["y"].append(y_value)
                series["values"].append(value)
            maximum = self.point_count.value()
            del series["x"][:-maximum]
            del series["y"][:-maximum]
            del series["values"][:-maximum]
            series["curve"].setData(series["x"], series["y"])
        self._maybe_auto_range()

    @Slot(int)
    def _trim_series(self, count):
        for series in self.series:
            del series["x"][:-count]
            del series["y"][:-count]
            del series["values"][:-count]
            series["curve"].setData(series["x"], series["y"])
        self._maybe_auto_range()

    def _maybe_auto_range(self):
        if (
            not self._loading_config
            and not self._user_zoomed
            and any(series["x"] for series in self.series)
        ):
            self.reset_zoom()

    def _range_changed(self, *_):
        if not self._setting_range:
            self._user_zoomed = True

    def _set_zoom_mode(self, enabled):
        mode = pg.ViewBox.RectMode if enabled else pg.ViewBox.PanMode
        for axis in self.axes:
            axis["view"].setMouseMode(mode)

    def _zoom_x(self, factor):
        current = self.base_view.viewRange()[0]
        center = sum(current) / 2
        half_range = (current[1] - current[0]) * factor / 2
        self._setting_range = True
        self.base_view.setXRange(center - half_range, center + half_range, padding=0)
        self._setting_range = False
        self._user_zoomed = True
        self._refresh_tag_positions()

    def _zoom_y(self, factor):
        self._setting_range = True
        for axis in self.axes:
            current = axis["view"].viewRange()[1]
            center = sum(current) / 2
            half_range = (current[1] - current[0]) * factor / 2
            axis["view"].setYRange(center - half_range, center + half_range, padding=0)
        self._setting_range = False
        self._user_zoomed = True
        self._refresh_tag_positions()

    def reset_zoom(self):
        all_x = [x for series in self.series for x in series["x"]]
        if not all_x:
            return
        x_min, x_max = min(all_x), max(all_x)
        x_padding = max((x_max - x_min) * 0.02, 0.5)
        self._setting_range = True
        try:
            self.base_view.setXRange(x_min - x_padding, x_max + x_padding, padding=0)
            for axis in self.axes:
                y_values = [y for series in axis["fields"] for y in series["y"]]
                if not y_values:
                    continue
                y_min, y_max = min(y_values), max(y_values)
                y_padding = max((y_max - y_min) * 0.05, abs(y_min) * 0.01, 0.01)
                axis["view"].setYRange(
                    y_min - y_padding, y_max + y_padding, padding=0
                )
        finally:
            self._setting_range = False
        self._user_zoomed = False
        self._refresh_tag_positions()

    def _sync_view_geometry(self):
        for axis in self.axes:
            if axis["view"] is not self.base_view:
                axis["view"].setGeometry(self.base_view.sceneBoundingRect())
                axis["view"].linkedViewChanged(self.base_view, axis["view"].XAxis)

    def _active_database(self):
        return GLOBAL_CONFIG.get("storage", {}).get("activeDatabase")

    def _refresh_datatags(self):
        database = self._active_database()
        if not database or not any(box.isChecked() for box in self.tag_checkboxes.values()):
            rows = []
        else:
            try:
                database_path = cfgLoader.getPath("databases") / database
                if not database_path.is_file():
                    raise FileNotFoundError(
                        f"Active telemetry database does not exist: {database_path}"
                    )
                rows = retrieveAllDatatags(database)
            except (OSError, sqlite3.Error) as error:
                LOGGER.exception("Unable to retrieve graph datatags from %s", database)
                if not self._tag_error_reported:
                    QMessageBox.warning(
                        self,
                        "Unable to load datatags",
                        f"Could not read datatags from {database!r}: {error}",
                    )
                    self._tag_error_reported = True
                return
            self._tag_error_reported = False
        checked_rows = [
            row
            for row in rows
            if len(row) >= 3
            and row[1] in self.tag_checkboxes
            and self.tag_checkboxes[row[1]].isChecked()
        ]
        if checked_rows == self._tag_rows:
            self._refresh_tag_positions()
            return
        for item in self._tag_items:
            self.base_view.removeItem(item["line"])
            self.base_view.removeItem(item["point"])
        self._tag_items.clear()
        self._tag_rows = checked_rows
        for timestamp, tag_type, description in checked_rows:
            try:
                x_value = float(timestamp)
            except (TypeError, ValueError, OverflowError):
                continue
            color = TAG_COLORS[tag_type]
            line = pg.InfiniteLine(
                pos=x_value,
                angle=90,
                movable=False,
                pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine),
            )
            line.setZValue(5)
            self.base_view.addItem(line, ignoreBounds=True)
            point = pg.ScatterPlotItem(
                x=[x_value],
                y=[0],
                symbol="o",
                size=10,
                brush=color,
                pen=pg.mkPen(color, width=1),
            )
            point.setZValue(10)
            self.base_view.addItem(point, ignoreBounds=True)
            self._tag_items.append(
                {
                    "x": x_value,
                    "type": tag_type,
                    "description": description,
                    "line": line,
                    "point": point,
                }
            )
        self._refresh_tag_positions()

    def _refresh_tag_positions(self):
        if not self.axes:
            return
        bottom = self.base_view.viewRange()[1][0]
        for item in self._tag_items:
            item["point"].setData(x=[item["x"]], y=[bottom])

    def _mouse_moved(self, event):
        position = event[0]
        if not self.base_view.sceneBoundingRect().contains(position):
            QToolTip.hideText()
            return
        point = self.base_view.mapSceneToView(position)
        for item in self._tag_items:
            tag_point = self.base_view.mapViewToScene(
                QPointF(item["x"], self.base_view.viewRange()[1][0])
            )
            if (tag_point - position).manhattanLength() <= 14:
                moment = datetime.fromtimestamp(item["x"], timezone.utc)
                QToolTip.showText(
                    QCursor.pos(),
                    f"{moment:%Y-%m-%d %H:%M:%S} UTC<br>"
                    f"{item['type']}: {html_escape(str(item['description']))}",
                    self.plot_widget,
                )
                return

        nearest = []
        for series in self.series:
            if not series["x"]:
                continue
            index = min(
                range(len(series["x"])),
                key=lambda current: abs(series["x"][current] - point.x()),
            )
            nearest.append((series, index))
        moment = datetime.fromtimestamp(point.x(), timezone.utc)
        value_rows = "".join(
            f"<tr><td>{html_escape(item['id']['fieldName'])}</td>"
            f"<td align='right'>{html_escape(str(item['values'][index]))}</td></tr>"
            for item, index in nearest
        )
        if nearest:
            QToolTip.showText(
                QCursor.pos(),
                f"{moment:%Y-%m-%d %H:%M:%S.%f} UTC"
                f"<table cellspacing='2'>{value_rows}</table>",
                self.plot_widget,
            )
        else:
            QToolTip.hideText()

    def _configuration(self):
        return {
            "name": self.graph_name.text().strip(),
            "dataPoints": self.point_count.value(),
            "axes": [
                {
                    "fields": [
                        {
                            "structure": series["id"]["structure"],
                            "packet": series["id"]["packet"],
                            "field": series["id"]["fieldName"],
                        }
                        for series in axis["fields"]
                    ]
                }
                for axis in self.axes
            ],
            "datatags": {
                tag_type: checkbox.isChecked()
                for tag_type, checkbox in self.tag_checkboxes.items()
            },
            "database": self._active_database(),
        }

    def store_graph(self):
        config = self._configuration()
        name = config["name"]
        if not name:
            QMessageBox.warning(self, "Graph name required", "Enter a Graph Name before storing.")
            return
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        if not safe_name:
            QMessageBox.warning(self, "Invalid graph name", "Enter a valid Graph Name.")
            return
        directory = cfgLoader.getPath("apps/graph/storedGraphs")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{safe_name}.json"
            with path.open("w", encoding="utf-8") as file:
                json.dump(config, file, indent=2)
        except OSError as error:
            LOGGER.exception("Unable to store graph configuration at %s", directory)
            QMessageBox.critical(self, "Unable to store graph", str(error))

    def open_stored_graph(self):
        directory = cfgLoader.getPath("apps/graph/storedGraphs")
        directory.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open stored graph", str(directory), "Graph configurations (*.json)"
        )
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8") as file:
                config = json.load(file)
            if not isinstance(config, dict):
                raise ValueError("Graph configuration must be a JSON object.")
            launchGraph(config)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            LOGGER.exception("Unable to open stored graph %s", path)
            QMessageBox.warning(self, "Unable to open graph", str(error))

    def closeEvent(self, event):
        self._datatag_timer.stop()
        for packet_type, callback in self._callbacks.items():
            LIVETLM.removeCallback(packet_type, callback)
        self._callbacks.clear()
        super().closeEvent(event)