# -*- coding: utf-8 -*-
"""汉化 · 文本页：原文提取、翻译回填、tl 落盘、字体注入"""

import os

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core import hanhua
from gui.pages import BasePage
from gui.theme import make_table

MAX_ROWS = 3000
KIND_LABELS = {"dialogue": "对话", "menu": "选项", "string": "字符串"}
COLUMNS = ["原文", "译文（双击编辑）", "角色", "来源"]


class _Task(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, func, parent=None):
        super().__init__(parent)
        self._func = func
        self._stop = False

    def stop(self):
        self._stop = True

    def stopped(self):
        return self._stop

    def run(self):
        try:
            result = self._func(self.progress.emit, self)
        except Exception as exc:  # noqa: BLE001 - 统一转成界面提示
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


class HanhuaPage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._entries = []
        self._task = None
        self._filling = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.path_label = QLabel("未选择游戏")
        self.path_label.setObjectName("muted")
        layout.addWidget(self.path_label)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.scan_btn = QPushButton("① 扫描原文")
        self.scan_btn.clicked.connect(self.start_scan)
        self.fill_btn = QPushButton("补填已有译文")
        self.fill_btn.clicked.connect(self.fill_existing)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_task)
        self.stat_label = QLabel("尚未扫描")
        self.stat_label.setObjectName("muted")
        bar.addWidget(self.scan_btn)
        bar.addWidget(self.fill_btn)
        bar.addWidget(self.stop_btn)
        bar.addSpacing(6)
        bar.addWidget(self.stat_label, 1)
        layout.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = make_table(COLUMNS, stretch_last=False)
        self.table.setColumnWidth(0, 380)
        self.table.setColumnWidth(1, 380)
        self.table.setColumnWidth(2, 90)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.cellChanged.connect(self._on_cell_changed)
        splitter.addWidget(self.table)

        splitter.addWidget(self._build_bottom())
        splitter.setSizes([420, 260])
        layout.addWidget(splitter, 1)

    def _build_bottom(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        font_row = QHBoxLayout()
        font_row.setSpacing(8)
        font_row.addWidget(QLabel("中文字体"))
        self.font_edit = QLineEdit()
        self.font_edit.setPlaceholderText("留空则不替换字体（仍会写入中文换行规则）")
        font_row.addWidget(self.font_edit, 1)
        pick_btn = QPushButton("选择…")
        pick_btn.clicked.connect(self._pick_font)
        auto_btn = QPushButton("自动查找")
        auto_btn.clicked.connect(self._auto_font)
        font_row.addWidget(pick_btn)
        font_row.addWidget(auto_btn)
        self.default_box = QCheckBox("首次启动自动切到中文")
        self.default_box.setChecked(True)
        font_row.addWidget(self.default_box)
        layout.addLayout(font_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.build_btn = QPushButton("② 生成汉化 tl")
        self.build_btn.clicked.connect(self.build_tl)
        self.remove_btn = QPushButton("卸载汉化")
        self.remove_btn.clicked.connect(self.remove_tl)
        export_btn = QPushButton("导出 CSV")
        export_btn.clicked.connect(self.export_csv)
        import_btn = QPushButton("导入 CSV")
        import_btn.clicked.connect(self.import_csv)
        action_row.addWidget(self.build_btn)
        action_row.addWidget(self.remove_btn)
        action_row.addStretch(1)
        action_row.addWidget(export_btn)
        action_row.addWidget(import_btn)
        layout.addLayout(action_row)

        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        api_row.addWidget(QLabel("翻译接口"))
        self.api_url = QLineEdit()
        self.api_url.setPlaceholderText("https://api.siliconflow.cn/v1")
        self.api_model = QLineEdit()
        self.api_model.setPlaceholderText("deepseek-ai/DeepSeek-V3")
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("API Key（仅保存在本机配置）")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_row.addWidget(self.api_url, 2)
        api_row.addWidget(self.api_model, 2)
        api_row.addWidget(self.api_key, 2)
        self.translate_btn = QPushButton("③ 自动翻译")
        self.translate_btn.clicked.connect(self.auto_translate)
        api_row.addWidget(self.translate_btn)
        layout.addLayout(api_row)

        self.hint = QLabel("流程：扫描原文 → 翻译（自动 / 导入 CSV）→ 生成 tl → 启动游戏验证。"
                           "生成的 tl 只写 game/tl/chinese 与 zz_xl_ 前缀文件，卸载即删除。")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self._load_settings()
        return box

    # ---- 配置 ----
    def _load_settings(self):
        data = (self.ctrl.settings.data.get("hanhua") or {})
        self.api_url.setText(data.get("base_url", ""))
        self.api_model.setText(data.get("model", ""))
        self.api_key.setText(data.get("api_key", ""))
        self.font_edit.setText(data.get("font", ""))
        self.default_box.setChecked(bool(data.get("default_lang", True)))

    def _save_settings(self):
        self.ctrl.settings.data["hanhua"] = {
            "base_url": self.api_url.text().strip(),
            "model": self.api_model.text().strip(),
            "api_key": self.api_key.text().strip(),
            "font": self.font_edit.text().strip(),
            "default_lang": self.default_box.isChecked(),
        }
        self.ctrl.settings.save()

    # ---- 生命周期 ----
    def on_game_loaded(self):
        game = self._game()
        if game is None:
            self.path_label.setText("未选择游戏")
            return
        self.path_label.setText("游戏：%s（%s）" % (game.title, game.game_dir))
        self._entries = []
        self.table.setRowCount(0)
        self.stat_label.setText("尚未扫描")

    def poll_if_needed(self):
        pass

    def _game(self):
        return getattr(self.ctrl, "game", None)

    def _game_dir(self):
        game = self._game()
        if game is None:
            QMessageBox.information(self, "提示", "请先在左侧选择 Ren'Py 游戏。")
            return ""
        return game.game_dir

    # ---- 扫描 ----
    def start_scan(self):
        game_dir = self._game_dir()
        if not game_dir or self._busy():
            return
        self._save_settings()

        def job(progress, task):
            progress("正在读取归档与脚本…")
            entries, stats = hanhua.scan(game_dir, progress=lambda text: progress(text))
            filled = hanhua.fill_existing(entries, game_dir)
            return entries, stats, filled

        self._run(job, self._scan_done, "扫描")

    def _scan_done(self, result):
        entries, stats, filled = result
        self._entries = entries
        self._fill_table()
        total = len(entries)
        missing = sum(1 for item in entries if not item.get("translation"))
        text = "共 %d 条（已译 %d / 缺 %d）" % (total, filled, missing)
        if len(entries) > MAX_ROWS:
            text += " · 表格仅显示前 %d 条，导出 CSV 可看全部" % MAX_ROWS
        self.stat_label.setText(text)
        for name, count, note in stats:
            self.ctrl.log("[汉化] %s：%d 条（%s）" % (name, count, note))

    def fill_existing(self):
        if not self._entries:
            self.start_scan()
            return
        game_dir = self._game_dir()
        if not game_dir:
            return
        count = hanhua.fill_existing(self._entries, game_dir)
        self._fill_table()
        self.stat_label.setText("已补填 %d 条已有译文" % count)

    # ---- 表格 ----
    def _fill_table(self):
        self._filling = True
        rows = self._entries[:MAX_ROWS]
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            original = QTableWidgetItem(item["original"])
            original.setFlags(original.flags() & ~Qt.ItemFlag.ItemIsEditable)
            original.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(row, 0, original)

            translation = QTableWidgetItem(item.get("translation", ""))
            translation.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(row, 1, translation)

            who = QTableWidgetItem(item.get("character", ""))
            who.setFlags(who.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, who)

            source = QTableWidgetItem("%s%s" % (KIND_LABELS.get(item["kind"], item["kind"]),
                                                "  " + item["file"] if item["file"] else ""))
            source.setFlags(source.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, source)
        self._filling = False

    def _on_cell_changed(self, row, column):
        if self._filling or column != 1:
            return
        item = self.table.item(row, 1)
        if item is None or row >= len(self._entries):
            return
        self._entries[row]["translation"] = item.text().strip()

    # ---- 生成 / 卸载 ----
    def build_tl(self):
        game_dir = self._game_dir()
        if not game_dir:
            return
        self._sync_table()
        self._save_settings()
        font = self.font_edit.text().strip()
        if font and not os.path.isfile(font):
            QMessageBox.warning(self, "字体无效", "字体文件不存在：%s" % font)
            return
        stats = {}
        try:
            written = hanhua.generate(self._entries, game_dir, font_path=font,
                                      force_default=self.default_box.isChecked(),
                                      stats=stats)
        except hanhua.HanhuaError as exc:
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self.ctrl.log("[汉化] 生成 %d 个文件" % len(written))
        extra = []
        if stats.get("fixed"):
            extra.append("%d 条译文补回了被改动的变量/标签" % stats["fixed"])
        if stats.get("rejected"):
            extra.append("%d 条译文占位符不一致，已跳过（保留原文）" % stats["rejected"])
        QMessageBox.information(self, "完成",
                                "已写入 %d 个文件到：\n%s\n\n启动游戏验证效果。"
                                % (len(written), os.path.dirname(written[0]))
                                + ("\n\n" + "\n".join(extra) if extra else ""))
        self.stat_label.setText("已生成汉化文件 %d 个" % len(written))

    def remove_tl(self):
        game_dir = self._game_dir()
        if not game_dir:
            return
        answer = QMessageBox.question(self, "卸载汉化",
                                      "将删除本工具生成的 tl 文件与默认语言文件，继续？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = hanhua.remove(game_dir)
        self.ctrl.log("[汉化] 删除 %d 个文件" % removed)
        self.stat_label.setText("已删除 %d 个汉化文件" % removed)

    def _sync_table(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is not None and row < len(self._entries):
                self._entries[row]["translation"] = item.text().strip()

    # ---- 导入导出 ----
    def export_csv(self):
        if not self._entries:
            QMessageBox.information(self, "提示", "请先扫描原文。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出对照表", "xl_text.csv",
                                              "表格 (*.csv *.tsv)")
        if not path:
            return
        self._sync_table()
        count = hanhua.export_table(path, self._entries)
        self.ctrl.log("[汉化] 导出 %d 条到 %s" % (count, path))
        self.stat_label.setText("已导出 %d 条" % count)

    def import_csv(self):
        if not self._entries:
            QMessageBox.information(self, "提示", "请先扫描原文，再导入译文。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入译文", "",
                                              "表格 (*.csv *.tsv)")
        if not path:
            return
        try:
            count = hanhua.import_table(path, self._entries)
        except Exception as exc:  # noqa: BLE001 - 文件格式错误直接提示
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._fill_table()
        self.stat_label.setText("已回填 %d 条" % count)

    # ---- 自动翻译 ----
    def auto_translate(self):
        game_dir = self._game_dir()
        if not game_dir or self._busy():
            return
        if not self._entries:
            QMessageBox.information(self, "提示", "请先扫描原文。")
            return
        if not self.api_url.text().strip():
            QMessageBox.information(self, "提示", "请填写接口地址（OpenAI 兼容）。")
            return
        self._sync_table()
        self._save_settings()
        api = {
            "base_url": self.api_url.text().strip(),
            "model": self.api_model.text().strip(),
            "api_key": self.api_key.text().strip(),
        }

        def job(progress, task):
            count = hanhua.translate_entries(self._entries, api,
                                             progress=lambda text: progress(text),
                                             should_stop=task.stopped)
            return count

        self._run(job, self._translate_done, "翻译")

    def _translate_done(self, count):
        self._fill_table()
        missing = sum(1 for item in self._entries if not item.get("translation"))
        self.stat_label.setText("已翻译 %d 条，仍缺 %d 条" % (count, missing))
        if missing:
            self.ctrl.log("[汉化] 仍有 %d 条未译（可重试或导入 CSV 补）" % missing)

    # ---- 字体 ----
    def _pick_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择中文字体", "",
                                              "字体 (*.ttf *.otf *.ttc)")
        if path:
            self.font_edit.setText(path)

    def _auto_font(self):
        path = hanhua.find_font()
        if path:
            self.font_edit.setText(path)
        else:
            QMessageBox.information(self, "提示", "没有找到系统自带中文字体，请手动选择。")

    # ---- 任务框架 ----
    def _busy(self):
        return self._task is not None and self._task.isRunning()

    def _run(self, func, on_done, name):
        self._set_busy(True, name)
        self._task = _Task(func, self)
        self._task.progress.connect(self._on_progress)
        self._task.done.connect(lambda result: self._finish(on_done, result))
        self._task.failed.connect(lambda message: self._fail(name, message))
        self._task.start()

    def _set_busy(self, busy, name=""):
        self.scan_btn.setEnabled(not busy)
        self.build_btn.setEnabled(not busy)
        self.translate_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        self.progress.setVisible(busy)
        if busy:
            self.stat_label.setText("%s中…" % name)
            self.ctrl.status_label.setText("%s中…" % name)

    def _on_progress(self, text):
        self.stat_label.setText(text)

    def _finish(self, on_done, result):
        self._set_busy(False)
        self.ctrl.status_label.setText("就绪")
        try:
            on_done(result)
        except Exception as exc:  # noqa: BLE001 - 回调异常不吞
            self._fail("完成", str(exc))
        self._task = None

    def _fail(self, name, message):
        self._set_busy(False)
        self.ctrl.status_label.setText("就绪")
        self.ctrl.log("[汉化] %s失败：%s" % (name, message))
        QMessageBox.warning(self, "%s失败" % name, message)
        self._task = None

    def _stop_task(self):
        if self._task is not None:
            self._task.stop()
            self.stat_label.setText("正在停止…（当前批次结束后生效）")
