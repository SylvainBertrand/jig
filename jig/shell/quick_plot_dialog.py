"""QuickPlotDialog — Ctrl+P command-palette-style signal picker."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from jig.core.data_store import DataStore


class QuickPlotDialog(QDialog):
    """Modal dialog for quickly finding and selecting signals to plot.

    Activated by Ctrl+P or right-click "Add Signal..." on a chart.
    Supports multi-select (Ctrl+click or Shift+click).
    """

    def __init__(
        self, data_store: DataStore, parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick Plot — Search Signals")
        self.setMinimumSize(500, 400)
        self.resize(550, 450)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        self._data_store = data_store
        self._paths = sorted(data_store.series_names)
        self._selected: list[str] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Search box
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to search signals...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        # Hint label
        hint = QLabel("Enter to confirm  |  Ctrl+Click to multi-select  |  Esc to cancel")
        hint.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(hint)

        # Results list
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list, stretch=1)

        # Populate
        self._filter("")
        self._search.setFocus()

    def _filter(self, text: str) -> None:
        tokens = text.lower().split()
        self._list.clear()
        for path in self._paths:
            lower = path.lower()
            if all(tok in lower for tok in tokens):
                item = QListWidgetItem(path)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self._list.addItem(item)

        # Auto-select first item
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept_selection()
        else:
            super().keyPressEvent(event)

    def _accept_selection(self, _item=None) -> None:
        self._selected = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._list.selectedItems()
        ]
        if not self._selected and self._list.currentItem():
            self._selected = [self._list.currentItem().data(Qt.ItemDataRole.UserRole)]
        self.accept()

    def selected_paths(self) -> list[str]:
        return self._selected
