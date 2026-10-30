# -*- coding: utf-8 -*-
"""统一界面样式"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)


APP_QSS = """
QWidget {
    background-color: #131a21;
    color: #e6eef7;
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #131a21; }
QFrame#card {
    background-color: #1b252e;
    border: 1px solid #273743;
    border-radius: 10px;
}
QLabel#title { font-size: 20px; font-weight: 600; letter-spacing: 1px; }
QLabel#subtitle { color: #8fa4b7; font-size: 12px; }
QLabel#section { color: #a8bccd; font-size: 12px; font-weight: 600; }
QLabel#muted { color: #8fa4b7; font-size: 12px; }
QLabel#info { color: #b9cad9; font-size: 12px; }
QLabel#error { color: #ff8080; font-size: 12px; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #18222b;
    border: 1px solid #2b3b48;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #1f6fb2;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #35a3ff; }
QComboBox QAbstractItemView {
    background-color: #18222b;
    border: 1px solid #2b3b48;
    selection-background-color: #1f6fb2;
}
QPushButton {
    background-color: #22303b;
    border: 1px solid #2f4351;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #2a3a47; }
QPushButton:pressed { background-color: #1c2a34; }
QPushButton:disabled { color: #5f7284; background-color: #1a232b; border-color: #24313c; }
QPushButton#primary {
    background-color: #1f7ae0;
    border: 1px solid #1f7ae0;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #2b8bf2; }
QPushButton#primary:disabled { background-color: #24425f; border-color: #24425f; color: #7f95aa; }
QPushButton#danger:hover { background-color: #5a2326; border-color: #8b3a3f; }
QTableWidget {
    background-color: #17212a;
    alternate-background-color: #1b2630;
    border: 1px solid #273743;
    border-radius: 6px;
    gridline-color: #22303b;
}
QTableWidget::item { padding: 2px 4px; }
QTableWidget::item:selected { background-color: #20527d; color: #ffffff; }
QHeaderView::section {
    background-color: #1e2b35;
    color: #a8bccd;
    border: none;
    border-right: 1px solid #273743;
    padding: 6px;
}
QTabWidget::pane {
    border: 1px solid #273743;
    border-radius: 8px;
    background-color: #17212a;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8fa4b7;
    padding: 7px 16px;
    margin-right: 4px;
    border-radius: 6px;
}
QTabBar::tab:selected { background-color: #22303b; color: #e6eef7; }
QTabBar::tab:hover { color: #e6eef7; }
QCheckBox { spacing: 6px; color: #b9cad9; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #3a4d5d; border-radius: 3px;
    background-color: #18222b;
}
QCheckBox::indicator:checked { background-color: #1f7ae0; border-color: #1f7ae0; }
QStatusBar { background-color: #10171d; color: #8fa4b7; }
QStatusBar::item { border: none; }
QScrollBar:vertical { background: #17212a; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2f4351; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #3c5566; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #17212a; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #2f4351; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QMenu { background-color: #1b252e; border: 1px solid #2b3b48; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background-color: #20527d; }
QToolTip {
    background-color: #1b252e;
    color: #e6eef7;
    border: 1px solid #2f4351;
    padding: 4px 6px;
}
"""


class StatusChip(QLabel):
    """右上角连接状态胶囊"""

    def __init__(self, text="未连接"):
        super().__init__(text)
        self.setObjectName("chip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_connected(False, text)

    def set_connected(self, connected: bool, text: str = ""):
        color = "#43d17c" if connected else "#f0b44c"
        background = "rgba(67, 209, 124, 0.14)" if connected else "rgba(240, 180, 76, 0.14)"
        self.setText(text or ("已连接" if connected else "未连接"))
        self.setStyleSheet(
            "QLabel#chip {"
            f" background-color: {background}; color: {color};"
            f" border: 1px solid {color}; border-radius: 11px;"
            " padding: 3px 14px; font-size: 12px; font-weight: 600;"
            "}"
        )


class NoteTable(QTableWidget):
    """最左侧固定一列「备注」，可双击编辑，自动存到游戏目录

    页面仍然按「逻辑列号」使用表格（0 = 原来的第一列），
    内部统一加 1 偏移到真实的物理列，这样各页代码不用改。
    """

    NOTE_WIDTH = 140
    NOTE_TIP = "备注：写清楚这个数值是什么，下次打开这个游戏会自动带出来"

    def __init__(self, headers, ctrl=None):
        super().__init__(0, len(headers) + 1)
        self._ctrl = ctrl
        self.setHorizontalHeaderLabels(["备注"] + list(headers))
        QTableWidget.setColumnWidth(self, 0, self.NOTE_WIDTH)
        self.itemChanged.connect(self._on_note_changed)

    # ---- 列号偏移：页面看到的是逻辑列，真实列 +1 ----
    def item(self, row, col):
        return QTableWidget.item(self, row, col + 1)

    def setItem(self, row, col, item):
        QTableWidget.setItem(self, row, col + 1, item)
        path = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if path:
            self._apply_note(row, str(path))

    def takeItem(self, row, col):
        return QTableWidget.takeItem(self, row, col + 1)

    def columnCount(self):
        return max(QTableWidget.columnCount(self) - 1, 0)

    def setColumnWidth(self, col, width):
        QTableWidget.setColumnWidth(self, col + 1, width)

    def columnWidth(self, col):
        return QTableWidget.columnWidth(self, col + 1)

    def setRowCount(self, count):
        QTableWidget.setRowCount(self, count)
        for row in range(count):
            if QTableWidget.item(self, row, 0) is None:
                cell = QTableWidgetItem("")
                cell.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEditable
                )
                cell.setToolTip(self.NOTE_TIP)
                QTableWidget.setItem(self, row, 0, cell)

    # ---- 备注读写 ----
    def _row_key(self, row):
        """取该行绑定的变量路径；没有路径时退回第一列文本"""
        for col in range(1, QTableWidget.columnCount(self)):
            cell = QTableWidget.item(self, row, col)
            if cell is None:
                continue
            data = cell.data(Qt.ItemDataRole.UserRole)
            if data:
                return str(data)
        cell = QTableWidget.item(self, row, 1)
        return cell.text() if cell is not None else ""

    def _notes(self):
        return getattr(self._ctrl, "notes", None)

    def _apply_note(self, row, key):
        store = self._notes()
        text = store.get(key) if store is not None else ""
        cell = QTableWidget.item(self, row, 0)
        if cell is None or cell.text() == text:
            return
        self.blockSignals(True)
        cell.setText(text)
        cell.setToolTip(key + ("\n" + text if text else ""))
        self.blockSignals(False)

    def _on_note_changed(self, item):
        if item.column() != 0:
            return
        key = self._row_key(item.row())
        if not key:
            return
        store = self._notes()
        if store is not None:
            store.set(key, item.text())
            item.setToolTip(key + ("\n" + item.text() if item.text() else ""))


def make_table(headers, stretch_last=True, ctrl=None):
    if ctrl is not None:
        table = NoteTable(headers, ctrl)
    else:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    if isinstance(table, NoteTable):
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
    else:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    if stretch_last:
        header.setStretchLastSection(True)
    return table
