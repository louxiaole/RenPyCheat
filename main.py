# -*- coding: utf-8 -*-
"""小乐 · 游戏实时修改器 —— 程序入口"""

import os
import sys
import traceback

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.game import resource_path
from gui.main_window import MainWindow


def handle_exception(exc_type, exc_value, exc_traceback):
    print("[CRITICAL] %s: %s" % (exc_type.__name__, exc_value))
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("程序错误")
    box.setText("%s: %s" % (exc_type.__name__, exc_value))
    box.exec()


def main():
    sys.excepthook = handle_exception
    app = QApplication(sys.argv)
    app.setApplicationName("小乐 游戏实时修改器")
    app.setStyle("Fusion")

    icon_path = resource_path("小乐工具.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
    app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
