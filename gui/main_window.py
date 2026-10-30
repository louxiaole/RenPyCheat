# -*- coding: utf-8 -*-
"""主窗口"""

import os
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTabWidget, QComboBox, QFileDialog, QMessageBox,
    QSpinBox, QStatusBar, QApplication, QScrollArea,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
)

from core import i18n
from core.client import APP_MARKER
from core.game import (
    GameError, detect_engine, install_mod, uninstall_mod, launch_game,
    ENGINE_RENPY, ENGINE_UNKNOWN,
    MOD_FILENAME, running_pids_for, list_renpy_processes,
    SAVE_GUARD_ON, SAVE_GUARD_OFF_TOOL, SAVE_GUARD_OFF_EXTERNAL, SAVE_GUARD_MISSING,
    save_protection_state, disable_save_protection, enable_save_protection,
)
from core.settings import Settings
from core.notes import Notes
from core.favorites import Favorites
from gui.pages import (
    FavoritesPage, VariablesPage, SearchPage, CharacterPage, AffectionPage, ItemsPage,
    CollectPage, SponsorPage, RecordsPage, FreezePage, PersistentPage, LogPage,
)
from gui.hanhua_page import HanhuaPage
from gui.about_page import AboutPage, ChangelogPage
from gui.theme import APP_QSS, StatusChip
from gui.worker import AsyncBridge
from core import updater
from core.version import APP_VERSION


SAVE_GUARD_LABELS = {
    SAVE_GUARD_ON: "开启（改过的存档会被拒绝读取）",
    SAVE_GUARD_OFF_TOOL: "已关闭（本工具，可恢复）",
    SAVE_GUARD_OFF_EXTERNAL: "已关闭（游戏自带或手动修改）",
    SAVE_GUARD_MISSING: "该版本没有存档签名校验",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.notes = Notes()
        self.favorites = Favorites()
        self.bridge = AsyncBridge(self)
        self.game = None
        self.connected = False
        self._skipping = False
        self._rollback_unlocked = False
        self.bridge_port = int(self.settings.data.get("port", 47321))
        self._probe_ports_list = []
        self._connect_cycles = 0
        self._connect_reason = ""

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._on_poll)

        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(1500)
        self._probe_timer.timeout.connect(self._probe_tick)

        self._probe_busy = False
        self._pending_report = 0
        self._pending_pid = None
        self._last_pids = None
        self._i18n_checked = {}

        self.setAcceptDrops(True)
        self._build_ui()
        self._restore_session()
        self._poll_timer.start()
        self._probe_timer.start()
        # 启动几秒后静默检查 GitHub 新版本（没有新版本不打扰）
        QTimer.singleShot(3000, self._check_update_on_startup)

    def _check_update_on_startup(self):
        try:
            updater.check_and_show_update(self)
        except Exception as error:
            self.log("[提示] 检查更新失败：" + str(error))

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.setWindowTitle("小乐 · 游戏实时修改器 v%s" % APP_VERSION)
        self.resize(1220, 780)
        self.setMinimumSize(1050, 680)
        self.setStyleSheet(APP_QSS)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 8)
        root.setSpacing(12)

        # 顶部标题
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("小乐 · 游戏实时修改器")
        title.setObjectName("title")
        subtitle = QLabel("Ren'Py 注入式修改 · 数值搜索与锁定")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.port_hint = QLabel("通道端口：--")
        self.port_hint.setObjectName("muted")
        self.chip = StatusChip()
        header.addWidget(self.port_hint)
        header.addSpacing(10)
        header.addWidget(self.chip)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_side_panel())

        self.tabs = QTabWidget()
        self.favorites_page = FavoritesPage(self)
        self.variables_page = VariablesPage(self)
        self.search_page = SearchPage(self)
        self.character_page = CharacterPage(self)
        self.affection_page = AffectionPage(self)
        self.items_page = ItemsPage(self)
        self.collect_page = CollectPage(self)
        self.sponsor_page = SponsorPage(self)
        self.records_page = RecordsPage(self)
        self.freeze_page = FreezePage(self)
        self.persistent_page = PersistentPage(self)
        self.hanhua_page = HanhuaPage(self)
        self.log_page = LogPage(self)
        self.about_page = AboutPage(self)
        self.changelog_page = ChangelogPage(self)
        self.tabs.addTab(self.favorites_page, "收藏修改")
        self.tabs.addTab(self.variables_page, "变量列表")
        self.tabs.addTab(self.search_page, "数值搜索")
        self.tabs.addTab(self.character_page, "角色属性")
        self.tabs.addTab(self.affection_page, "属性识别")
        self.tabs.addTab(self.items_page, "物品")
        self.tabs.addTab(self.collect_page, "画廊 · 解锁")
        self.tabs.addTab(self.sponsor_page, "赞助 · 礼包码")
        self.tabs.addTab(self.records_page, "修改记录")
        self.tabs.addTab(self.freeze_page, "数值锁定")
        self.tabs.addTab(self.persistent_page, "持久化数据")
        self.tabs.addTab(self.hanhua_page, "汉化 · 文本")
        self.tabs.addTab(self.log_page, "日志")
        self.tabs.addTab(self.changelog_page, "更新日志")
        self.tabs.addTab(self.about_page, "关于 · 赞助")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        body.addWidget(self.tabs, 1)
        root.addLayout(body, 1)
        self._install_find_shortcuts()

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("muted")
        status.addWidget(self.status_label)

    def _build_side_panel(self):
        # 内容比窗口高时自动出现竖向滚动条，避免底部按钮 / 说明被裁掉看不到
        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFixedWidth(316)

        panel = QFrame()
        panel.setObjectName("card")
        panel.setMinimumWidth(300)
        scroll.setWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        section = QLabel("游戏设置")
        section.setObjectName("section")
        layout.addWidget(section)

        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText("拖入游戏 exe，或选择根目录")
        self.game_edit.setAcceptDrops(False)  # 交给主窗口统一处理拖拽
        self.game_edit.returnPressed.connect(
            lambda: self._load_game(self.game_edit.text().strip())
        )
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_game)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.game_edit, 1)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        # 拖拽区：把游戏的 exe / 根目录直接拖进来即可识别
        self.drop_hint = QLabel("把游戏启动文件（.exe）或游戏根目录\n拖到这里")
        self.drop_hint.setObjectName("muted")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setMinimumHeight(48)
        self.drop_hint.setStyleSheet(
            "border: 1px dashed #3a5262; border-radius: 6px; color: #7d94a5; padding: 4px;")
        layout.addWidget(self.drop_hint)

        self.recent_box = QComboBox()
        self.recent_box.addItem("最近打开的游戏…")
        self.recent_box.currentIndexChanged.connect(self._on_recent_selected)
        layout.addWidget(self.recent_box)

        self.info_label = QLabel("尚未选择游戏")
        self.info_label.setObjectName("info")
        self.info_label.setWordWrap(True)
        self.info_label.setMinimumHeight(96)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.info_label)

        self.install_btn = QPushButton("安装注入模块")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._install_mod)
        self.uninstall_btn = QPushButton("卸载注入模块")
        self.uninstall_btn.clicked.connect(self._uninstall_mod)
        self.launch_btn = QPushButton("启动游戏")
        self.launch_btn.clicked.connect(self._launch_game)
        self.attach_btn = QPushButton("附加进程")
        self.attach_btn.setToolTip(
            "游戏已经开着了（尤其是二次启动、先加载器后进游戏的）？\n"
            "点这里列出正在运行的 Ren'Py 游戏进程，选一个直接附加，\n"
            "不用重新启动，也不用等自动连接。"
        )
        self.attach_btn.clicked.connect(self._attach_process)
        layout.addWidget(self.install_btn)
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(self.uninstall_btn)
        row2.addWidget(self.launch_btn)
        row2.addWidget(self.attach_btn)
        layout.addLayout(row2)

        self.save_guard_btn = QPushButton("关闭存档保护")
        self.save_guard_btn.clicked.connect(self._toggle_save_guard)
        self.save_guard_btn.setToolTip(
            "关闭 Ren'Py 的存档签名校验（renpy/savetoken.py），"
            "让外部修改过的存档能正常读取。\n"
            "只修改本机游戏文件，会先备份，可随时恢复。"
        )
        layout.addWidget(self.save_guard_btn)

        self.save_guard_hint = QLabel("存档保护：--")
        self.save_guard_hint.setObjectName("muted")
        self.save_guard_hint.setWordWrap(True)
        layout.addWidget(self.save_guard_hint)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("color: #273743;")
        layout.addWidget(line2)

        section_dialog = QLabel("对话功能解锁")
        section_dialog.setObjectName("section")
        layout.addWidget(section_dialog)

        self.skip_unlock_btn = QPushButton("开启跳过未读文本")
        self.skip_unlock_btn.setCheckable(True)
        self.skip_unlock_btn.setToolTip(
            "打开游戏自带「未读的文本也跳过」这个选项。\n"
            "有些游戏设置里没有这一项，这里直接改引擎偏好来激活；\n"
            "激活后在游戏里照常按跳过（Ctrl / 跳过按钮）即可跳过未读文本。\n"
            "状态会保存，重启游戏后自动生效。"
        )
        self.skip_unlock_btn.clicked.connect(self._toggle_unlock_skip)

        self.rollback_unlock_btn = QPushButton("开启回退功能")
        self.rollback_unlock_btn.setCheckable(True)
        self.rollback_unlock_btn.setToolTip(
            "强制打开引擎的回退能力，适合这几种游戏：\n"
            "· 滚轮向上没反应 —— 自动补上「滚轮上=回退上一句」键位；\n"
            "· 回退后无法前进 —— 自动补上「滚轮下=恢复到当前对话」键位；\n"
            "· 只能退一两句 —— 解除游戏用 block_rollback 设下的回退封锁，\n"
            "  并把回退历史上限从默认的 128 提到 512。\n"
            "状态会保存，重启游戏后自动生效；关闭则还原游戏原本的设置。"
        )
        self.rollback_unlock_btn.clicked.connect(self._toggle_unlock_rollback)

        layout.addWidget(self.skip_unlock_btn)
        layout.addWidget(self.rollback_unlock_btn)

        self.dialog_hint = QLabel("跳过未读：--　回退：--")
        self.dialog_hint.setObjectName("muted")
        self.dialog_hint.setWordWrap(True)
        layout.addWidget(self.dialog_hint)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #273743;")
        layout.addWidget(line)

        section2 = QLabel("调试通道")
        section2.setObjectName("section")
        layout.addWidget(section2)

        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.bridge_port)
        self.port_spin.setFixedWidth(96)
        connect_btn = QPushButton("连接")
        connect_btn.clicked.connect(lambda: self._begin_connect("manual"))
        port_row.addWidget(self.port_spin)
        port_row.addWidget(connect_btn)
        port_row.addStretch(1)
        layout.addLayout(port_row)

        layout.addStretch(1)

        tip = QLabel(
            "Ren'Py 游戏：\n"
            "1. 把游戏 exe 拖进来，或选择游戏根目录（含 game 文件夹）\n"
            "2. 安装注入模块\n"
            "3. 启动游戏，等待自动连接\n"
            "4. 在右侧实时读取 / 修改变量\n\n"
            "仅监听本机 127.0.0.1，不会联网上传数据。"
        )
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        return scroll

    # ------------------------------------------------------------------
    # 会话恢复
    # ------------------------------------------------------------------
    def _restore_session(self):
        self._rebuild_recent()
        last = self.settings.data.get("last_game", "")
        if last and os.path.isdir(last):
            self.game_edit.setText(last)
            self._load_game(last, silent=True)

    def _rebuild_recent(self):
        self.recent_box.blockSignals(True)
        self.recent_box.clear()
        self.recent_box.addItem("最近打开的游戏…")
        for path in self.settings.data.get("recent", []):
            if os.path.isdir(path):
                self.recent_box.addItem(self._short_path(path), path)
        self.recent_box.setCurrentIndex(0)
        self.recent_box.blockSignals(False)

    @staticmethod
    def _short_path(path: str) -> str:
        if len(path) <= 46:
            return path
        return "…" + path[-44:]

    def _on_recent_selected(self, index):
        if index <= 0:
            return
        path = self.recent_box.itemData(index)
        if path:
            self.game_edit.setText(path)
            self._load_game(path)

    # ------------------------------------------------------------------
    # 游戏检测 / 模块安装
    # ------------------------------------------------------------------
    def _browse_game(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择游戏根目录（Ren'Py）", self.game_edit.text() or "")
        if folder:
            self.game_edit.setText(folder)
            self._load_game(folder)

    # ---- 拖拽游戏启动文件 / 根目录 ----
    @staticmethod
    def _dropped_paths(event):
        paths = []
        try:
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
        except Exception:
            return paths
        return paths

    def dragEnterEvent(self, event):
        if self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._dropped_paths(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        # 一次拖多个时，依次尝试，谁像 Ren'Py 游戏就用谁
        last_error = ""
        for path in paths:
            detected = detect_engine(path)
            if detected["engine"] != ENGINE_UNKNOWN:
                self._load_game(path)
                return
            last_error = detected.get("error") or ""
        self._show_load_error(last_error or "拖入的不是游戏目录")

    def _show_load_error(self, message, silent=False):
        self.game = None
        self.notes.load("")
        self.favorites.load("")
        self.favorites_page.reload()
        self._last_pids = None
        self.install_btn.setEnabled(True)
        self.info_label.setObjectName("error")
        self.info_label.setStyleSheet("color: #ff8080;")
        self.info_label.setText(message)
        self.log("[错误] " + message)
        if not silent:
            QMessageBox.warning(self, "检测失败", message)

    def _load_game(self, path, silent=False):
        """选择 / 拖入游戏后自动识别，并载入 Ren'Py 修改功能"""
        detected = detect_engine((path or "").strip().strip('"'))
        engine = detected["engine"]
        if engine == ENGINE_RENPY:
            return self._load_renpy_game(detected, silent)
        error = detected.get("error") or ""
        if not error:
            error = ("未识别到 Ren'Py 游戏：所选目录下没有 game 文件夹。\n"
                     "请选择游戏根目录，或直接把游戏启动程序（.exe）拖进来。")
        self._show_load_error(error, silent)
        return False

    def _load_renpy_game(self, detected, silent=False):
        self.game = detected.get("renpy")
        if self.game is None:
            self._show_load_error(detected.get("error") or "Ren'Py 游戏识别失败", silent)
            return False
        game = self.game
        self._last_pids = None
        self.notes.load(game.game_dir)
        self.favorites.load(game.game_dir)
        self.favorites_page.reload()
        self.info_label.setStyleSheet("")
        self.info_label.setObjectName("info")
        self.game_edit.setText(game.root)
        if game.config_port:
            self.port_spin.setValue(game.config_port)
            self.bridge_port = int(game.config_port)
        self._update_info()
        self.records_page.refresh()
        self.hanhua_page.on_game_loaded()
        self.settings.data["port"] = self.port_spin.value()
        self.settings.add_recent(game.root)
        self._rebuild_recent()
        self.port_hint.setText("通道端口：%d" % self.port_spin.value())
        self.tabs.setCurrentWidget(self.variables_page)
        if not silent:
            self.log(
                "已识别游戏：%s（Ren'Py %s，MOD %s）"
                % (game.title, game.version or "版本未知", "已安装" if game.installed else "未安装")
            )
        if game.installed:
            self._begin_connect("startup")
        return True

    def _update_info(self):
        game = self.game
        if game is None:
            self.info_label.setText("尚未选择游戏")
            self._refresh_save_guard()
            return
        running = "运行中" if game.running_pids else "未运行"
        lines = [
            "引擎：Ren'Py %s" % (game.version or "（连接后读取）"),
            "启动程序：%s" % (game.exe_name or "未找到 .exe"),
            "注入模块：%s" % ("已安装" if game.installed else "未安装"),
            "游戏状态：%s" % running,
        ]
        if not game.writable:
            lines.append("目录不可写，无法安装模块")
        self.info_label.setText("\n".join(lines))
        self.install_btn.setEnabled(game.writable)
        self._refresh_save_guard()

    def _refresh_save_guard(self):
        """按当前游戏同步存档保护按钮与状态文字"""
        if self.game is None:
            self.save_guard_hint.setText("存档保护：--")
            self.save_guard_btn.setText("关闭存档保护")
            self.save_guard_btn.setEnabled(False)
            return
        state = save_protection_state(self.game.root)
        self.save_guard_hint.setText("存档保护：" + SAVE_GUARD_LABELS.get(state, "未知"))
        if state == SAVE_GUARD_ON:
            self.save_guard_btn.setText("关闭存档保护")
            self.save_guard_btn.setEnabled(self.game.writable)
        elif state == SAVE_GUARD_OFF_TOOL:
            self.save_guard_btn.setText("恢复存档保护")
            self.save_guard_btn.setEnabled(self.game.writable)
        elif state == SAVE_GUARD_OFF_EXTERNAL:
            self.save_guard_btn.setText("存档保护已关闭")
            self.save_guard_btn.setEnabled(False)
        else:
            self.save_guard_btn.setText("无需关闭存档保护")
            self.save_guard_btn.setEnabled(False)

    def _toggle_save_guard(self):
        if not self.game:
            QMessageBox.information(self, "提示", "请先选择游戏根目录。")
            return
        state = save_protection_state(self.game.root)
        try:
            if state == SAVE_GUARD_ON:
                if disable_save_protection(self.game.root) == SAVE_GUARD_OFF_EXTERNAL:
                    message = "存档保护本就已关闭（游戏自带或手动修改）"
                else:
                    message = "已关闭存档保护"
            elif state == SAVE_GUARD_OFF_TOOL:
                enable_save_protection(self.game.root)
                message = "已恢复存档保护"
            else:
                return
        except GameError as error:
            QMessageBox.warning(self, "操作失败", str(error))
            self.log("[错误] 存档保护：" + str(error))
            return

        self.log("存档保护：" + message)
        self._update_info()
        if self.game.running_pids:
            QMessageBox.information(
                self, "需要重启游戏",
                message + "。\n游戏正在运行，引擎文件在启动时加载，请重启游戏后生效。",
            )
        else:
            self.toast(message)

    def _install_mod(self):
        if not self.game:
            QMessageBox.information(self, "提示", "请先选择游戏根目录。")
            return
        port = self.port_spin.value()
        try:
            game = install_mod(self.game.root, port)
        except GameError as error:
            QMessageBox.warning(self, "安装失败", str(error))
            self.log("[错误] 安装失败：" + str(error))
            return
        self.game = game
        self.bridge_port = int(port)
        self.settings.data["port"] = int(port)
        self.settings.save()
        self.port_hint.setText("通道端口：%d" % port)
        self._update_info()
        self.log("已安装注入模块（端口 %d）：%s" % (port, os.path.join(game.game_dir, MOD_FILENAME)))
        if game.running_pids:
            QMessageBox.information(self, "安装完成", "注入模块已更新，请重启游戏后生效。")
        else:
            self.toast("注入模块安装完成，启动游戏即可连接")

    def _uninstall_mod(self):
        if not self.game:
            QMessageBox.information(self, "提示", "请先选择游戏根目录。")
            return
        confirm = QMessageBox.question(
            self, "确认卸载", "确定移除游戏中的注入模块吗？\n（不会影响游戏存档）"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            game = uninstall_mod(self.game.root)
        except GameError as error:
            QMessageBox.warning(self, "卸载失败", str(error))
            self.log("[错误] 卸载失败：" + str(error))
            return
        self.game = game
        self._update_info()
        self._set_connected(False)
        self.log("已卸载注入模块")
        self.toast("注入模块已卸载")

    def _launch_game(self):
        if not self.game:
            QMessageBox.information(self, "提示", "请先选择游戏根目录。")
            return
        # 换游戏后首次启动：先把注入模块和中文对照表补上，再启动
        self._ensure_ready()
        try:
            launch_game(self.game.root)
        except GameError as error:
            QMessageBox.warning(self, "启动失败", str(error))
            return
        self.log("已启动游戏：%s" % self.game.exe_name)
        self.toast("游戏启动中，等待调试通道…")
        self._begin_connect("launch")

    def _attach_process(self):
        """手动附加到已在运行的游戏进程（应对二次启动 / 自动连接失败）"""
        try:
            procs = list_renpy_processes()
        except Exception as error:
            QMessageBox.warning(self, "附加失败", "枚举进程出错：%s" % error)
            return
        if not procs:
            QMessageBox.information(
                self, "没有可附加的游戏",
                "没有找到正在运行的 Ren'Py 游戏。\n\n"
                "如果游戏刚启动还在加载界面，稍等几秒再点一次；\n"
                "另外要确认注入模块已经安装（未安装的进程无法读取数据）。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("附加到运行中的游戏")
        dialog.resize(560, 320)
        box = QVBoxLayout(dialog)
        box.addWidget(QLabel("选择要附加的游戏进程："))
        listing = QListWidget()
        for item in procs:
            text = "%s   PID %d\n%s\n%s" % (
                item["title"], item["pid"], item["exe"],
                "已安装注入模块" if item["installed"] else "未安装注入模块（需重启游戏后才可读）")
            row = QListWidgetItem(text)
            row.setData(Qt.ItemDataRole.UserRole, item)
            listing.addItem(row)
        listing.setCurrentRow(0)
        box.addWidget(listing, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("附加")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current = listing.currentItem()
        if current is None:
            return
        item = current.data(Qt.ItemDataRole.UserRole)
        self._attach_to(item)

    def _attach_to(self, item):
        root = item.get("root") or os.path.dirname(item.get("exe", ""))
        self.log("手动附加进程：PID %s  %s" % (item.get("pid"), item.get("exe")))
        self._load_game(root, silent=True)
        if self.game is None:
            QMessageBox.warning(self, "附加失败", "无法识别该进程对应的游戏目录。")
            return
        if not self.game.installed:
            QMessageBox.information(
                self, "需要先安装注入模块",
                "这个游戏目录里没有注入模块，当前运行的进程读不到数据。\n\n"
                "请先点「安装注入模块」，然后重启游戏（或让启动器重新拉起游戏），"
                "再回来点「附加进程」。")
            return
        if self.connected:
            self._set_connected(False)
        self._pending_pid = item.get("pid")
        self._begin_connect("manual")
        self.toast("正在附加 PID %s…" % item.get("pid"))

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def _candidate_ports(self):
        base = self.port_spin.value()
        return [base + offset for offset in range(5)]

    def _ensure_ready(self):
        """换游戏后自动补装注入模块与中文对照表，免去手动点安装"""
        game = self.game
        if game is None or not game.writable:
            return
        if not game.installed:
            try:
                self.game = install_mod(game.root, self.port_spin.value())
            except GameError as error:
                self.log("[错误] 自动安装注入模块失败：" + str(error))
                return
            self._update_info()
            self.log("已自动安装注入模块：%s" % self.game.title)
            if self.game.running_pids:
                self.log("游戏正在运行，注入模块需重启游戏后生效")

        game = self.game
        if game.root in self._i18n_checked:
            return
        if not i18n.table_count(game.game_dir):
            # 首次提取可能要几秒（翻译脚本多的大作更久），给个可见提示
            self.status_label.setText("正在提取中文对照表…")
            QApplication.processEvents()
        try:
            count = i18n.ensure_translations(game.game_dir)
        except Exception as error:  # 提取失败不影响注入
            count = 0
            self.log("[错误] 提取中文对照表失败：%s" % error)
        self._i18n_checked[game.root] = count
        if count:
            self.log("中文对照表：%d 条（物品 / 角色名显示中文）" % count)
        else:
            self.log("该游戏没有中文 tl 翻译脚本，名称显示数据表原文")

    def _begin_connect(self, reason: str):
        if self.connected:
            return
        if self.game is None:
            path = self.game_edit.text().strip()
            if not path:
                QMessageBox.information(self, "提示", "请先选择游戏根目录。")
                return
            self._load_game(path)
            if self.game is None:
                return
        self._ensure_ready()
        # 手动连接只提示一次失败；启动游戏时连续提示
        self._pending_report = 1 if reason == "manual" else 15
        self.status_label.setText("正在连接游戏调试通道…")
        self._probe_tick()

    def _probe_tick(self):
        """常驻探测：游戏后启动也能自动连上"""
        if self.connected or self._probe_busy or self.game is None:
            return
        self._refresh_running_state()
        self._probe_busy = True
        self._probe_walk(self._candidate_ports(), 0)

    def _probe_walk(self, ports, index):
        if self.connected or index >= len(ports):
            self._probe_busy = False
            self._on_probe_pass_done()
            return
        port = ports[index]

        def ok(data):
            if data.get("app") == APP_MARKER:
                self._probe_busy = False
                self._on_probe_ok(port, data)
            else:
                self._probe_walk(ports, index + 1)

        def err(_message, _remote):
            self._probe_walk(ports, index + 1)

        self.bridge.call(port, "ping", {}, ok, err, timeout=0.8)

    def _on_probe_pass_done(self):
        if self.connected or self._pending_report <= 0:
            return
        self._pending_report -= 1
        if self._pending_report == 0:
            self.status_label.setText(
                "未检测到游戏调试通道：请确认已安装注入模块，并在安装后重启游戏"
            )

    def _on_probe_ok(self, port, data):
        if data.get("app") != APP_MARKER:
            return
        actual = int(data.get("port") or port)
        self.bridge_port = actual
        self.port_spin.setValue(actual)
        self._pending_report = 0
        self._set_connected(True, data)
        self.status_label.setText(
            "已连接 · %s · %s" % (data.get("title") or "游戏", data.get("renpy") or "Ren'Py")
        )
        self.log(
            "已连接调试通道 127.0.0.1:%d（PID %s，%s，模块 v%s）"
            % (actual, data.get("pid"), data.get("renpy"), data.get("version"))
        )
        pending = self._pending_pid
        self._pending_pid = None
        if pending is not None and str(data.get("pid")) != str(pending):
            self.log("[提示] 附加目标 PID %s，但通道属于 PID %s（可能开着一个游戏）"
                     % (pending, data.get("pid")))
            self.toast("通道实际来自 PID %s，与所选进程不同" % data.get("pid"))

    def _refresh_running_state(self):
        """同步游戏进程状态，避免信息面板停在旧数据"""
        game = self.game
        if game is None:
            return
        pids = running_pids_for(game.exe_name, game.root)
        if pids == self._last_pids:
            return
        self._last_pids = pids
        game.running_pids = pids
        self._update_info()

    def _set_connected(self, connected: bool, info=None):
        self.connected = connected
        if connected:
            self.chip.set_connected(True, "已连接 · %d" % self.bridge_port)
            self.port_hint.setText("通道端口：%d" % self.bridge_port)
            self._poll_timer.start()
            self.refresh_current()
        else:
            self.chip.set_connected(False)
            self.port_hint.setText("通道端口：%d" % self.port_spin.value())
        for page in (self.variables_page, self.search_page, self.character_page,
                     self.affection_page, self.items_page, self.collect_page,
                     self.sponsor_page, self.records_page, self.freeze_page,
                     self.persistent_page, self.log_page):
            page.on_connection_changed(connected)
        self.skip_unlock_btn.setEnabled(connected)
        self.rollback_unlock_btn.setEnabled(connected)
        if not connected:
            self._skipping = False
            self._rollback_unlocked = False
            self.skip_unlock_btn.setChecked(False)
            self.skip_unlock_btn.setText("开启跳过未读文本")
            self.rollback_unlock_btn.setChecked(False)
            self.rollback_unlock_btn.setText("开启回退功能")
            self.dialog_hint.setText("跳过未读：--　回退：--（未连接）")
        if connected:
            self.items_page.refresh()
            self.refresh_dialog_unlock()

    # ------------------------------------------------------------------
    # 对话功能解锁：跳过未读文本 / 回退
    # ------------------------------------------------------------------
    def refresh_dialog_unlock(self):
        if not self.connected:
            return
        self.call("unlock_status", {}, self._on_unlock_status,
                  lambda message: self.dialog_hint.setText("读取解锁状态失败：" + message))

    def _on_unlock_status(self, data):
        data = data or {}
        skip_on = bool(data.get("skip_unseen"))
        rollback_on = bool(data.get("rollback_enabled"))
        skip_flag = bool(data.get("unlocked_skip"))
        rollback_flag = bool(data.get("unlocked_rollback"))
        self._skipping = skip_flag
        self._rollback_unlocked = rollback_flag
        self.skip_unlock_btn.blockSignals(True)
        self.skip_unlock_btn.setChecked(skip_flag)
        self.skip_unlock_btn.setText("关闭跳过未读文本" if skip_flag else "开启跳过未读文本")
        self.skip_unlock_btn.blockSignals(False)
        self.rollback_unlock_btn.blockSignals(True)
        self.rollback_unlock_btn.setChecked(rollback_flag)
        self.rollback_unlock_btn.setText("关闭回退功能" if rollback_flag else "开启回退功能")
        self.rollback_unlock_btn.blockSignals(False)
        hint = "跳过未读：%s　回退：%s" % ("已开启" if skip_on else "未开启",
                                    "已开启" if rollback_on else "未开启")
        if rollback_flag:
            key_ok = bool(data.get("rollback_key_ok"))
            forward_ok = bool(data.get("rollforward_key_ok"))
            patched = bool(data.get("rollback_block_patched"))
            depth = int(data.get("rollback_log_len") or 0)
            hint += "（滚轮上=回退%s　滚轮下=前进%s　可回退 %d 句%s）" % (
                "✓" if key_ok else "✗",
                "✓" if forward_ok else "✗",
                depth,
                "　已解除封锁" if patched else "")
        self.dialog_hint.setText(hint)

    def _toggle_unlock_skip(self):
        self._set_dialog_unlock("unlock_skip", self.skip_unlock_btn.isChecked())

    def _toggle_unlock_rollback(self):
        self._set_dialog_unlock("unlock_rollback", self.rollback_unlock_btn.isChecked())

    def _set_dialog_unlock(self, op, on):
        self.call(op, {"on": on}, self._on_unlock_changed, self._on_unlock_failed)

    def _on_unlock_changed(self, data):
        data = data or {}
        self._on_unlock_status(data)
        skip_on = bool(data.get("skip_unseen"))
        rollback_on = bool(data.get("rollback_enabled"))
        self.log("对话解锁状态：跳过未读=%s，回退=%s" % (skip_on, rollback_on))
        self.toast("已更新对话功能，游戏里马上生效")

    def _on_unlock_failed(self, message):
        self.toast("设置失败：" + message)
        self.refresh_dialog_unlock()

    def _handle_bridge_error(self, message):
        if not self.connected:
            return
        self._set_connected(False)
        self.status_label.setText("与游戏的连接已断开")
        self.log("[断开] " + message)

    # ------------------------------------------------------------------
    # 供页面调用
    # ------------------------------------------------------------------
    def call(self, op, payload=None, on_ok=None, on_err=None, timeout=8.0):
        if not self.connected:
            if on_err is not None:
                on_err("尚未连接游戏，请先点击「连接」")
            return

        def _ok(data):
            if on_ok is not None:
                on_ok(data)

        def _err(message, is_remote):
            if is_remote:
                self.log("[失败] " + message)
            else:
                self._handle_bridge_error(message)
            if on_err is not None:
                on_err(message)

        return self.bridge.call(self.bridge_port, op, payload or {}, _ok, _err, timeout=timeout)

    def refresh_current(self):
        page = self.tabs.currentWidget()
        if isinstance(page, (VariablesPage, FreezePage, PersistentPage, RecordsPage)):
            page.refresh()

    # ------------------------------------------------------------------
    # 快速查找：Ctrl+F 聚焦搜索框 / F3 下一个结果（Esc 清除在搜索框内处理）
    # ------------------------------------------------------------------
    def _install_find_shortcuts(self):
        self._find_shortcuts = []
        bindings = (
            (QKeySequence(QKeySequence.StandardKey.Find), self.focus_find),
            (QKeySequence("F3"), lambda: self.find_step(1)),
            (QKeySequence("Shift+F3"), lambda: self.find_step(-1)),
        )
        for sequence, handler in bindings:
            shortcut = QShortcut(sequence, self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(handler)
            self._find_shortcuts.append(shortcut)

    def focus_find(self):
        page = self.tabs.currentWidget()
        box = page.search_box() if hasattr(page, "search_box") else None
        if box is None:
            # 本页没有搜索框时，回到变量列表统一查找
            self.tabs.setCurrentWidget(self.variables_page)
            box = self.variables_page.search_box()
            if box is not None:
                self.toast("本页没有搜索框，已切到「变量列表」查找")
        if box is None:
            return
        box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        box.selectAll()

    def find_step(self, step):
        page = self.tabs.currentWidget()
        table = page.result_table() if hasattr(page, "result_table") else None
        if table is None or table.rowCount() == 0:
            return
        row = table.currentRow()
        if row < 0:
            row = 0 if step > 0 else table.rowCount() - 1
        else:
            row = (row + step) % table.rowCount()
        table.selectRow(row)
        item = table.item(row, 0)
        if item is not None:
            table.scrollToItem(item)

    def toast(self, message: str):
        self.status_label.setText(message)
        self.statusBar().showMessage(message, 4000)

    def log(self, message: str):
        self.log_page.text.appendPlainText(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        )

    def copy_text(self, text: str):
        QApplication.clipboard().setText(text)
        self.toast("已复制：" + text)

    # ---- 收藏修改（按游戏目录保存，下次打开自动带出）----
    def is_favorite(self, path):
        return self.favorites.has(path)

    def favorite_add(self, path, cn="", type_name=""):
        if self.favorites.add(path, cn, type_name):
            self.favorites_page.reload()
            return True
        return False

    def favorite_remove(self, path):
        if self.favorites.remove(path):
            self.favorites_page.reload()
            return True
        return False

    # ---- 修改记录（按游戏根目录保存，重启工具后仍在）----
    MAX_RECORDS = 200

    def _record_store(self, create=False):
        if self.game is None:
            return None
        data = self.settings.data
        store = data.get("records")
        if not isinstance(store, dict):
            store = {}
            data["records"] = store
        records = store.get(self.game.root)
        if not isinstance(records, list):
            if not create:
                return None
            records = []
            store[self.game.root] = records
        return records

    def records(self):
        return list(self._record_store() or [])

    def has_record(self, path):
        return any(item.get("path") == path for item in self.records())

    def record_change(self, path, before, after, value_type="", note="", frozen=False):
        records = self._record_store(create=True)
        if records is None:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in records:
            if item.get("path") == path:
                # 原值只记录第一次，之后一直保留，方便对比
                if not item.get("before") or item.get("before") == "—":
                    item["before"] = str(before)
                item["after"] = str(after)
                if value_type:
                    item["type"] = value_type
                if note:
                    item["note"] = note
                if frozen:
                    item["frozen"] = True
                item["updated"] = now
                break
        else:
            records.insert(0, {
                "path": path,
                "note": note,
                "type": value_type,
                "before": str(before),
                "after": str(after),
                "frozen": bool(frozen),
                "updated": now,
            })
            del records[self.MAX_RECORDS:]
        self.settings.save()
        self.records_page.refresh()

    def update_record(self, path, **changes):
        records = self._record_store()
        if not records:
            return
        for item in records:
            if item.get("path") == path:
                item.update(changes)
                item["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        self.settings.save()
        self.records_page.refresh()

    def remove_records(self, paths):
        records = self._record_store()
        if not records:
            return
        records[:] = [item for item in records if item.get("path") not in paths]
        self.settings.save()
        self.records_page.refresh()

    def clear_records(self):
        records = self._record_store()
        if records is not None:
            del records[:]
        self.settings.save()
        self.records_page.refresh()

    def _on_poll(self):
        if not self.connected:
            return
        page = self.tabs.currentWidget()
        if hasattr(page, "poll_if_needed"):
            page.poll_if_needed()

    def _on_tab_changed(self, index):
        page = self.tabs.widget(index)
        if isinstance(page, FavoritesPage):
            page.reload()
        elif isinstance(page, (FreezePage, PersistentPage)):
            page.refresh()
        elif isinstance(page, RecordsPage):
            page.refresh()
        elif isinstance(page, (AffectionPage, ItemsPage, CollectPage, SponsorPage)) and self.connected:
            page.refresh()
        elif isinstance(page, VariablesPage) and not page.auto_box.isChecked():
            page.refresh()

    def closeEvent(self, event):
        super().closeEvent(event)
