"""TopicBrowser — sidebar tree view of available topics and fields."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from jig.core.data_store import DataStore
from jig.core.types import TopicInfo

SIGNAL_MIME_TYPE = "application/x-jig-signal-path"


class _DragTree(QTreeWidget):
    """QTreeWidget that puts the signal path into drag mime data."""

    def mimeTypes(self) -> list[str]:
        return [SIGNAL_MIME_TYPE]

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        mime = QMimeData()
        paths = []
        for item in items:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)
        if paths:
            mime.setData(SIGNAL_MIME_TYPE, "\n".join(paths).encode("utf-8"))
        return mime


class TopicBrowser(QWidget):
    """Tree view showing topics and their scalar fields from a DataStore."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = _DragTree()
        self._tree.setHeaderLabels(["Signal", "Type / Count"])
        self._tree.setColumnWidth(0, 220)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)
        layout.addWidget(self._tree)

        self._data_store: DataStore | None = None

    def set_data_store(self, data_store: DataStore) -> None:
        self._data_store = data_store
        data_store.topic_added.connect(self._on_topic_added)
        data_store.data_changed.connect(self._rebuild)

    def _on_topic_added(self, info: TopicInfo) -> None:
        self._add_topic_item(info)

    def _rebuild(self) -> None:
        self._tree.clear()
        if self._data_store is None:
            return
        for info in self._data_store.topics.values():
            self._add_topic_item(info)

    def _add_topic_item(self, info: TopicInfo) -> None:
        # Short type name for display (e.g. "sensor_msgs/msg/JointState" → "JointState")
        short_type = info.message_type.rsplit("/", 1)[-1] if info.message_type else ""
        detail = f"{short_type}  ({info.message_count})" if short_type else str(info.message_count)

        topic_item = QTreeWidgetItem([info.name, detail])
        topic_item.setToolTip(0, info.message_type)
        topic_item.setFlags(topic_item.flags() | Qt.ItemFlag.ItemIsSelectable)
        for field_name in info.fields:
            child = QTreeWidgetItem([field_name, ""])
            child.setData(0, Qt.ItemDataRole.UserRole, f"{info.name}/{field_name}")
            topic_item.addChild(child)
        self._tree.addTopLevelItem(topic_item)
        topic_item.setExpanded(True)
