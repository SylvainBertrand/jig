"""VariableBrowser — hierarchical sidebar for browsing and searching signals."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QMimeData, QTimer, Qt
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jig.core.data_store import DataStore
from jig.core.types import TopicInfo

SIGNAL_MIME_TYPE = "application/x-jig-signal-ref"


def _make_signal_mime(paths: list[str]) -> QMimeData:
    """Create MIME data from a list of full signal paths."""
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, "\n".join(paths).encode("utf-8"))
    return mime


class _SignalTree(QTreeWidget):
    """Tree widget that supports dragging signal paths."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def mimeTypes(self) -> list[str]:
        return [SIGNAL_MIME_TYPE]

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        paths: list[str] = []
        for item in items:
            self._collect_leaf_paths(item, paths)
        return _make_signal_mime(paths)

    def _collect_leaf_paths(self, item: QTreeWidgetItem, out: list[str]) -> None:
        """Collect signal paths from item and all its descendants."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            out.append(path)
        for i in range(item.childCount()):
            self._collect_leaf_paths(item.child(i), out)


class VariableBrowser(QWidget):
    """Sidebar widget showing a searchable, hierarchical tree of signals.

    Signals are organised by splitting their full path on ``/``.  Leaf nodes
    are plottable scalar series from the DataStore.  Branch nodes (topics,
    namespaces) can be dragged to add all children at once.
    """

    # Signal emitted when user double-clicks a leaf signal path
    signal_double_clicked = None  # set up in __init__ via Qt Signal

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data_stores: list[DataStore] = []
        self._all_paths: list[str] = []  # cache for search
        self._all_metadata: dict[str, dict[str, Any]] = {}  # path → metadata

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Search bar ---
        search_row = QHBoxLayout()
        search_row.setSpacing(2)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search variables...")
        self._search_box.setClearButtonEnabled(True)
        search_row.addWidget(self._search_box)
        layout.addLayout(search_row)

        # Debounce timer for search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._apply_search)
        self._search_box.textChanged.connect(self._on_search_text_changed)

        # --- Signal count label ---
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("font-size: 11px; color: #888; padding: 0 2px;")
        layout.addWidget(self._count_label)

        # --- Tree view ---
        self._tree = _SignalTree()
        self._tree.setHeaderLabels(["Signal", "Info"])
        self._tree.setColumnWidth(0, 220)
        self._tree.setIndentation(16)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree, stretch=1)

        # Track the callback for double-click
        self._double_click_callback = None

    def set_double_click_callback(self, callback) -> None:
        """Set a callback ``fn(full_path: str)`` for when a leaf signal is double-clicked."""
        self._double_click_callback = callback

    def focus_search(self) -> None:
        """Focus the search box and select all text."""
        self._search_box.setFocus()
        self._search_box.selectAll()

    # -- Data binding --------------------------------------------------------

    def set_data_store(self, data_store: DataStore) -> None:
        """Connect to a DataStore and populate the tree."""
        if data_store in self._data_stores:
            return
        self._data_stores.append(data_store)
        data_store.data_changed.connect(self._rebuild)
        data_store.topic_added.connect(lambda _info: self._rebuild())

    def _rebuild(self) -> None:
        """Rebuild the tree from all connected DataStores."""
        self._all_paths.clear()
        self._all_metadata.clear()

        for ds in self._data_stores:
            for topic_name, info in ds.topics.items():
                for field in info.fields:
                    full_path = f"{topic_name}/{field}"
                    self._all_paths.append(full_path)

                    # Metadata for tooltips
                    series = ds.get_series(full_path)
                    meta: dict[str, Any] = {
                        "topic": topic_name,
                        "field": field,
                        "type": info.message_type,
                        "count": len(series) if series else 0,
                    }
                    if series and len(series) > 0:
                        meta["t_min"] = float(series.timestamps[0])
                        meta["t_max"] = float(series.timestamps[-1])
                        meta["v_min"] = float(series.values.min())
                        meta["v_max"] = float(series.values.max())
                        duration = meta["t_max"] - meta["t_min"]
                        if duration > 0:
                            meta["freq_hz"] = meta["count"] / duration
                    self._all_metadata[full_path] = meta

            # Also track message-only topics (images, TF, etc.)
            for topic_name in ds.message_topics():
                if topic_name not in {info.name for info in ds.topics.values()}:
                    # No scalar fields — add as a topic node anyway
                    pass

        self._all_paths.sort()
        self._apply_search()

    # -- Search --------------------------------------------------------------

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _apply_search(self) -> None:
        query = self._search_box.text().strip()
        self._tree.clear()

        if query:
            matched = self._search_paths(query)
            self._populate_flat(matched)
            self._count_label.setText(f"{len(matched)} / {len(self._all_paths)} signals")
        else:
            self._populate_tree(self._all_paths)
            self._count_label.setText(f"{len(self._all_paths)} signals")

    def _search_paths(self, query: str) -> list[str]:
        """Filter paths by query.  Splits query on whitespace and requires
        all tokens to appear (case-insensitive substring match)."""
        tokens = query.lower().split()
        results = []
        for path in self._all_paths:
            lower = path.lower()
            if all(tok in lower for tok in tokens):
                results.append(path)
        return results

    # -- Tree population -----------------------------------------------------

    def _populate_tree(self, paths: list[str]) -> None:
        """Build a hierarchical tree from a sorted list of signal paths."""
        # Intermediate nodes keyed by path prefix
        nodes: dict[str, QTreeWidgetItem] = {}

        for full_path in paths:
            # Split path, e.g. "/joint_states/position[0]"
            # into parts: ["", "joint_states", "position[0]"]
            parts = full_path.split("/")
            # Remove empty leading part from paths starting with "/"
            if parts and parts[0] == "":
                parts = parts[1:]

            parent = None
            prefix = ""
            for i, part in enumerate(parts):
                prefix = f"{prefix}/{part}"
                is_leaf = (i == len(parts) - 1)

                if prefix in nodes:
                    parent = nodes[prefix]
                    continue

                item = QTreeWidgetItem()
                item.setText(0, part)

                if is_leaf:
                    # Leaf: plottable signal
                    item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                    meta = self._all_metadata.get(full_path, {})
                    item.setText(1, f"{meta.get('count', '')}")
                    item.setToolTip(0, self._format_tooltip(full_path))
                else:
                    # Branch: count children
                    child_count = sum(
                        1 for p in paths if p.startswith(prefix + "/")
                    )
                    item.setText(1, f"({child_count})")
                    item.setForeground(1, self._tree.palette().color(
                        self._tree.palette().ColorRole.PlaceholderText
                    ))

                if parent is None:
                    self._tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)

                nodes[prefix] = item
                parent = item

        # Expand first level by default
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            top.setExpanded(True)
            # Expand second level too if there aren't too many
            if top.childCount() <= 10:
                for j in range(top.childCount()):
                    top.child(j).setExpanded(True)

    def _populate_flat(self, paths: list[str]) -> None:
        """Show search results as a flat list."""
        for full_path in paths:
            item = QTreeWidgetItem()
            item.setText(0, full_path)
            item.setData(0, Qt.ItemDataRole.UserRole, full_path)
            meta = self._all_metadata.get(full_path, {})
            item.setText(1, f"{meta.get('count', '')}")
            item.setToolTip(0, self._format_tooltip(full_path))
            self._tree.addTopLevelItem(item)

    def _format_tooltip(self, full_path: str) -> str:
        meta = self._all_metadata.get(full_path, {})
        lines = [full_path]
        if "type" in meta:
            lines.append(f"Type: {meta['type']}")
        if "count" in meta:
            lines.append(f"Samples: {meta['count']}")
        if "t_min" in meta and "t_max" in meta:
            lines.append(f"Time: {meta['t_min']:.3f} – {meta['t_max']:.3f} s")
        if "v_min" in meta and "v_max" in meta:
            lines.append(f"Range: {meta['v_min']:.4f} – {meta['v_max']:.4f}")
        if "freq_hz" in meta:
            lines.append(f"Frequency: {meta['freq_hz']:.1f} Hz")
        return "\n".join(lines)

    # -- Double-click --------------------------------------------------------

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and self._double_click_callback:
            self._double_click_callback(path)
