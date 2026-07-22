from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UTILS_DIR = REPO_ROOT / "utils"
for candidate in [REPO_ROOT, UTILS_DIR]:
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    from PySide6.QtCore import QTimer, Qt, QRect
except ImportError as exc:
    raise SystemExit("PySide6 is required to run the malformed packet viewer.") from exc
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from malformedPackets.malformedPacketHandler import Configs
except ImportError:
    from malformedPacketHandler import Configs


class HexDumpWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.packet_hex = ""
        self.fields = []
        self.highlighted_bytes = set()
        self.hovered_byte_index = None
        self.font = QFont("Consolas", 10)
        self.byte_width = 24
        self.byte_height = 18
        self.gap = 6
        self.setMouseTracking(True)

    def set_packet(self, packet_hex, fields, highlighted_bytes=None):
        self.packet_hex = packet_hex
        self.fields = fields
        self.highlighted_bytes = set(highlighted_bytes or [])
        self.hovered_byte_index = None
        self.update()

    def _byte_indices_for_field(self, field):
        bit_length = field.get("bitLength", 0)
        bit_offset = field.get("bitOffset", 0)
        if not bit_length:
            return []
        start_byte = bit_offset // 8
        end_byte = (bit_offset + bit_length - 1) // 8
        return list(range(start_byte, end_byte + 1))

    def _field_for_byte(self, byte_index):
        matching = []
        for field in self.fields:
            byte_indices = self._byte_indices_for_field(field)
            if byte_index in byte_indices:
                matching.append(field)
        return matching

    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        byte_index = int(x // (self.byte_width + self.gap))
        row = int(y // (self.byte_height + self.gap))
        index = row * 16 + byte_index
        self.hovered_byte_index = index if index < len(self._packet_bytes()) else None
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.update()
        super().mouseReleaseEvent(event)

    def _packet_bytes(self):
        if not self.packet_hex:
            return []
        try:
            return bytes.fromhex(self.packet_hex)
        except ValueError:
            return []

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font)
        bytes_data = self._packet_bytes()
        if not bytes_data:
            return

        for row in range((len(bytes_data) + 15) // 16):
            offset = row * 16
            for col in range(16):
                idx = offset + col
                if idx >= len(bytes_data):
                    break
                byte = bytes_data[idx]
                rect = QRect(col * (self.byte_width + self.gap), row * (self.byte_height + self.gap), self.byte_width, self.byte_height)
                if idx in self.highlighted_bytes:
                    painter.setBrush(QColor(255, 90, 90, 80))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(rect)
                elif self.hovered_byte_index == idx:
                    painter.setBrush(QColor(70, 130, 255, 70))
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(rect)
                else:
                    painter.setBrush(Qt.transparent)
                    painter.setPen(Qt.NoPen)
                    painter.drawRect(rect)
                painter.setPen(QPen(QColor(240, 240, 240)))
                painter.drawText(rect, Qt.AlignCenter, f"{byte:02X}")

        painter.setPen(QPen(QColor(180, 180, 180)))
        painter.drawText(10, 20, f"Hover over a byte to inspect the matching field(s).")


class MalformedPacketViewer(QMainWindow):
    def __init__(self, storage_path=None):
        super().__init__()
        self.storage_path = Path(storage_path or "./malformedPackets/malformedPacketStorage").resolve()
        self.setWindowTitle("Malformed Packet Handler")
        self.resize(1400, 900)
        self.entries = []
        self.index_path = self.storage_path / "index.json"
        self._build_ui()
        self._refresh_entries()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_entries)
        self.timer.start(2000)

    def _build_ui(self):
        self.list_widget = QListWidget(self)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

        self.hex_widget = HexDumpWidget(self)
        self.details_browser = QTextBrowser(self)
        self.details_browser.setOpenExternalLinks(False)
        self.errors_browser = QTextBrowser(self)
        self.errors_browser.setOpenExternalLinks(False)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Malformed packets"))
        left_layout.addWidget(self.list_widget)

        center = QWidget(self)
        center_layout = QVBoxLayout(center)
        center_layout.addWidget(QLabel("Hex dump"))
        center_layout.addWidget(self.hex_widget)
        center_layout.addWidget(QLabel("Errors"))
        center_layout.addWidget(self.errors_browser)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Field details"))
        right_layout.addWidget(self.details_browser)

        splitter = QWidget(self)
        splitter_layout = QHBoxLayout(splitter)
        splitter_layout.addWidget(left, 1)
        splitter_layout.addWidget(center, 2)
        splitter_layout.addWidget(right, 2)
        splitter_layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _refresh_entries(self):
        if not self.index_path.exists():
            self.entries = []
            self.list_widget.clear()
            return

        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return

        if index == self.entries:
            return

        self.entries = index
        self.list_widget.clear()
        for entry in self.entries:
            title = entry.get("timestamp", "unknown")
            components = entry.get("components", [])
            if components:
                title = f"{title} :: {'/'.join(components)}"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)

        if self.list_widget.count() and self.list_widget.currentRow() < 0:
            self.list_widget.setCurrentRow(0)

    def _on_selection_changed(self, current, previous):
        if not current:
            return
        entry = current.data(Qt.UserRole)
        self._populate_details(entry)

    def _load_entry(self, entry):
        storage_path = Path(entry.get("storagePath"))
        if not storage_path.exists():
            return None
        try:
            return json.loads(storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _populate_details(self, entry):
        details = self._load_entry(entry)
        if not details:
            self.details_browser.setPlainText("Unable to load malformed packet entry.")
            self.errors_browser.setPlainText("")
            self.hex_widget.set_packet("", [])
            return

        packet_hex = details.get("rawPacketHex", "")
        fields = details.get("packetTemplate", [])
        errors = details.get("errors", [])
        self.errors_browser.setPlainText("\n\n".join([f"[{err.get('stage','unknown')}] {err.get('message','')}" for err in errors]))

        highlight_bytes = set()
        field_names = []
        for error in errors:
            for field_name in error.get("fieldNames", []):
                field_names.append(field_name)
                for field in fields:
                    if field.get("fieldName") == field_name:
                        highlight_bytes.update(self._byte_indices_for_field(field))

        self.hex_widget.set_packet(packet_hex, fields, highlighted_bytes=highlight_bytes)

        detail_lines = []
        for field in fields:
            field_name = field.get("fieldName", "")
            raw_bits = field.get("rawBits", "")
            raw_value = field.get("rawValue", "")
            converted_value = field.get("convertedValue", "")
            detail_lines.append(
                f"{field_name}: bits={raw_bits}, raw={raw_value}, converted={converted_value}"
            )
        self.details_browser.setPlainText("\n".join(detail_lines) if detail_lines else "No field detail available.")

    def _byte_indices_for_field(self, field):
        bit_length = field.get("bitLength", 0)
        bit_offset = field.get("bitOffset", 0)
        if not bit_length:
            return []
        start_byte = bit_offset // 8
        end_byte = (bit_offset + bit_length - 1) // 8
        return list(range(start_byte, end_byte + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-path", default="./malformedPackets/malformedPacketStorage")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    viewer = MalformedPacketViewer(args.storage_path)
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
