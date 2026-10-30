# -*- coding: utf-8 -*-
"""GitHub Releases 自动更新：检测 → 下载 → 生成 updater.bat 覆盖 → 重启

发版流程（与 Rust Solo Tools 一致）：
  1. 在 GitHub 创建 Release（tag = v1.0.1），上传打包好的 zip（解压后根目录是 RenPyCheat.exe）
  2. 用户启动工具时后台检测到新版本 → 弹窗展示更新日志
  3. 点「立即更新」→ 下载 zip → 生成 updater.bat → 工具退出 → bat 解压覆盖 → 重新启动
"""

import html as _html
import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Optional

EXE_NAME = "RenPyCheat.exe"

GITHUB_OWNER = "louxiaole"
GITHUB_REPO = "RenPyCheat"
GITHUB_API_URL = ("https://api.github.com/repos/%s/%s/releases/latest"
                  % (GITHUB_OWNER, GITHUB_REPO))
RELEASES_PAGE = "https://github.com/%s/%s/releases" % (GITHUB_OWNER, GITHUB_REPO)

CHECK_TIMEOUT = 8
DOWNLOAD_TIMEOUT = 30


@dataclass
class UpdateInfo:
    version: str = ""
    version_name: str = ""
    release_date: str = ""
    download_url: str = ""
    file_size: int = 0
    changelog_html: str = ""
    force: bool = False


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _debug_log(message: str):
    try:
        path = os.path.join(_get_app_dir(), "updater_debug.log")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def current_version() -> str:
    try:
        from core.version import APP_VERSION
        return APP_VERSION
    except Exception:
        return "0.0.0"


def _parse_version(text: str) -> tuple:
    try:
        parts = str(text).strip().lstrip("vV").split()[0].split(".")
        numbers = []
        for part in parts[:4]:
            digits = "".join(ch for ch in part if ch.isdigit())
            numbers.append(int(digits) if digits else 0)
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers)
    except Exception:
        return (0, 0, 0)


# ----------------------------------------------------------------------
# 检测
# ----------------------------------------------------------------------
def _fetch_latest_release() -> Optional[dict]:
    import requests
    resp = requests.get(
        GITHUB_API_URL,
        timeout=CHECK_TIMEOUT,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "RenPyCheat-Updater",
        },
    )
    if resp.status_code != 200:
        _debug_log("GitHub API 状态码：%s" % resp.status_code)
        return None
    return resp.json()


def check_for_updates(version: str = None) -> Optional[UpdateInfo]:
    """有新版本返回 UpdateInfo；已是最新 / 网络异常返回 None"""
    try:
        import requests  # noqa: F401
    except Exception as error:
        _debug_log("import requests 失败：%s" % error)
        return None

    if version is None:
        version = current_version()
    current = _parse_version(version)
    _debug_log("检查更新，当前版本 %s" % version)

    try:
        release = _fetch_latest_release()
    except Exception as error:
        _debug_log("GitHub API 请求失败：%s" % error)
        return None
    if not release:
        return None

    tag = str(release.get("tag_name") or "").lstrip("vV")
    if not tag:
        return None
    if _parse_version(tag) <= current:
        _debug_log("已是最新版本（远端 %s）" % tag)
        return None

    download_url = ""
    file_size = 0
    for asset in release.get("assets") or []:
        if str(asset.get("name", "")).lower().endswith(".zip"):
            download_url = asset.get("browser_download_url", "")
            file_size = int(asset.get("size") or 0)
            break
    if not download_url:
        _debug_log("Release %s 没有 zip 附件，跳过自动更新" % tag)
        return None

    published = str(release.get("published_at") or "")
    info = UpdateInfo(
        version=tag,
        version_name=str(release.get("name") or tag),
        release_date=published[:10],
        download_url=download_url,
        file_size=file_size,
        changelog_html=str(release.get("body") or ""),
    )
    _debug_log("发现新版本：%s" % info.version_name)
    return info


# ----------------------------------------------------------------------
# 更新器脚本
# ----------------------------------------------------------------------
def _generate_updater_bat(zip_path: str, app_dir: str) -> str:
    """bat 放在工具目录内，内部全用相对路径，避免中文路径乱码"""
    bat_path = os.path.join(app_dir, "_updater_temp.bat")
    bat_content = """@echo off
cd /d "%~dp0"
title 小乐 游戏实时修改器 正在更新...

echo ========================================
echo   小乐 游戏实时修改器 正在更新...
echo ========================================
echo.

echo [1/4] 等待主程序退出...
set /a wait_count=0
:wait_loop
tasklist /fi "imagename eq %EXE%" 2>nul | find /i "%EXE%" >nul
if %errorlevel%==0 (
    set /a wait_count+=1
    if %wait_count% geq 30 (
        echo [警告] 等待超时，强制结束进程...
        taskkill /im "%EXE%" /f >nul 2>&1
        timeout /t 2 /nobreak >nul
        goto do_extract
    )
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
echo 主程序已退出。

:do_extract
echo [2/4] 备份用户配置...
if exist "config\\settings.json" (
    copy /y "config\\settings.json" "config\\settings_backup.json" >nul 2>&1
)

echo [3/4] 正在解压更新包...
powershell -ExecutionPolicy Bypass -Command "Expand-Archive -Force -Path 'update_temp.zip' -DestinationPath '.'"
if %errorlevel% neq 0 (
    echo [错误] 解压失败！
    echo 请手动解压 update_temp.zip 到当前目录。
    pause
    exit /b 1
)

echo [4/4] 验证新程序文件...
if not exist "%EXE%" (
    echo [错误] 解压后未找到 %EXE%！
    pause
    exit /b 1
)
for %%A in ("%EXE%") do set exe_size=%%~zA
if %exe_size% lss 1048576 (
    echo [错误] 新程序文件过小（%exe_size% 字节），可能不完整！
    pause
    exit /b 1
)
echo 新程序验证通过（%exe_size% 字节）。

if exist "config\\settings_backup.json" (
    move /y "config\\settings_backup.json" "config\\settings.json" >nul 2>&1
)

del "update_temp.zip" >nul 2>&1
echo.
echo ========================================
echo   更新完成！正在自动启动程序...
echo ========================================
echo.
start "" "%EXE%"
timeout /t 3 /nobreak >nul
del "%~f0"
exit
""".replace("%EXE%", EXE_NAME)
    with open(bat_path, "w", encoding="mbcs") as handle:
        handle.write(bat_content)
    _debug_log("已生成更新脚本：%s（zip=%s）" % (bat_path, zip_path))
    return bat_path


# ----------------------------------------------------------------------
# 界面：更新弹窗 / 下载进度
# ----------------------------------------------------------------------
_DIALOG_QSS = """
QDialog { background-color: #131a21; }
QLabel { color: #e6eef7; font-family: "Microsoft YaHei UI"; font-size: 13px; }
QPushButton {
    background-color: #22303b; border: 1px solid #2f4351;
    border-radius: 6px; padding: 7px 18px; color: #e6eef7;
}
QPushButton:hover { background-color: #2a3a47; }
QPushButton:disabled { color: #5f7284; background-color: #1a232b; border-color: #24313c; }
QPushButton#primary { background-color: #1f7ae0; border: 1px solid #1f7ae0; font-weight: 600; }
QPushButton#primary:hover { background-color: #2b8bf2; }
QProgressBar {
    border: 1px solid #2b3b48; border-radius: 6px;
    background: #18222b; height: 20px; text-align: center; color: #b9cad9;
}
QProgressBar::chunk { background-color: #1f7ae0; border-radius: 5px; }
QTextBrowser { background-color: #17212a; border: 1px solid #273743; border-radius: 6px; }
"""


def _changelog_text(info: UpdateInfo) -> str:
    body = (info.changelog_html or "").strip()
    if not body:
        return "（该版本没有填写更新说明）"
    if body.startswith("<"):
        return body
    return _html.escape(body).replace("\n", "<br>")


def show_update_dialog(info: UpdateInfo, parent=None) -> bool:
    """展示「发现新版本」弹窗；用户点立即更新返回 True"""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
    )
    import webbrowser

    dialog = QDialog(parent)
    dialog.setWindowTitle("发现新版本 v%s" % info.version)
    dialog.resize(620, 540)
    dialog.setStyleSheet(_DIALOG_QSS)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 16)
    layout.setSpacing(10)

    title = QLabel("发现新版本 v%s" % info.version)
    title.setStyleSheet("font-size:18px; font-weight:600; color:#43d17c;")
    layout.addWidget(title)

    detail = "当前版本 v%s　→　最新版本 v%s" % (current_version(), info.version)
    if info.release_date:
        detail += "　（%s 发布）" % info.release_date
    if info.file_size:
        detail += "　安装包 %.1f MB" % (info.file_size / (1024 * 1024))
    sub = QLabel(detail)
    sub.setStyleSheet("font-size:12px; color:#8fa4b7;")
    layout.addWidget(sub)

    body = QTextBrowser()
    body.setOpenExternalLinks(True)
    body.setHtml(
        "<body style='background:#17212a; color:#b9cad9; font-family:\"Microsoft YaHei UI\"; "
        "font-size:13px;'>%s</body>" % _changelog_text(info)
    )
    layout.addWidget(body, 1)

    tip = QLabel("点「立即更新」将自动下载安装包，工具退出后自动解压替换并重新启动（配置会保留）。")
    tip.setStyleSheet("font-size:12px; color:#8fa4b7;")
    tip.setWordWrap(True)
    layout.addWidget(tip)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    skip_btn = QPushButton("下次再说")
    manual_btn = QPushButton("打开下载页")
    update_btn = QPushButton("立即更新")
    update_btn.setObjectName("primary")
    buttons.addWidget(skip_btn)
    buttons.addWidget(manual_btn)
    buttons.addWidget(update_btn)
    layout.addLayout(buttons)

    result = {"update": False}

    def do_update():
        result["update"] = True
        dialog.accept()

    update_btn.clicked.connect(do_update)
    manual_btn.clicked.connect(lambda: webbrowser.open(RELEASES_PAGE))
    skip_btn.clicked.connect(dialog.reject)

    dialog.exec()
    return result["update"]


def download_and_install(info: UpdateInfo, parent=None) -> bool:
    """下载 zip 并生成 updater.bat；返回 True 表示可以退出程序交给 bat"""
    from PyQt6.QtCore import QObject, Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QLabel, QPushButton,
        QProgressBar, QMessageBox, QVBoxLayout,
    )
    import requests

    app_dir = _get_app_dir()
    zip_path = os.path.join(app_dir, "update_temp.zip")

    dialog = QDialog(parent)
    dialog.setWindowTitle("正在下载更新")
    dialog.setMinimumWidth(520)
    dialog.setStyleSheet(_DIALOG_QSS)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 16)
    layout.setSpacing(10)

    title = QLabel("正在下载 v%s" % info.version)
    title.setStyleSheet("font-size:15px; font-weight:600; color:#e6eef7;")
    layout.addWidget(title)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    layout.addWidget(bar)

    status = QLabel("准备中…")
    status.setStyleSheet("font-size:12px; color:#8fa4b7;")
    layout.addWidget(status)

    meta = QLabel("速度：--　剩余：--")
    meta.setStyleSheet("font-size:12px; color:#8fa4b7;")
    layout.addWidget(meta)

    row = QHBoxLayout()
    row.addStretch(1)
    cancel_btn = QPushButton("取消下载")
    row.addWidget(cancel_btn)
    layout.addLayout(row)

    state = {
        "cancelled": False,
        "downloaded": 0,
        "total": int(info.file_size or 0),
        "start": 0.0,
        "error": "",
        "launch": False,
    }

    class _Signals(QObject):
        progress = pyqtSignal()
        completed = pyqtSignal()
        cancelled = pyqtSignal()
        failed = pyqtSignal()

    sig = _Signals()

    def on_cancel():
        state["cancelled"] = True
        cancel_btn.setText("正在取消…")
        cancel_btn.setEnabled(False)

    cancel_btn.clicked.connect(on_cancel)

    def do_download():
        try:
            state["start"] = time.time()
            resp = requests.get(info.download_url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            if state["total"] <= 0:
                state["total"] = int(resp.headers.get("Content-Length") or 0)
            with open(zip_path, "wb") as handle:
                last = 0.0
                for chunk in resp.iter_content(chunk_size=65536):
                    if state["cancelled"]:
                        break
                    if not chunk:
                        continue
                    handle.write(chunk)
                    state["downloaded"] += len(chunk)
                    now = time.time()
                    if now - last >= 0.3:
                        last = now
                        sig.progress.emit()
            if state["cancelled"]:
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
                sig.cancelled.emit()
                return
            sig.completed.emit()
        except Exception as error:
            state["error"] = str(error)
            _debug_log("下载失败：%s\n%s" % (error, traceback.format_exc()))
            sig.failed.emit()

    def update_ui():
        downloaded = state["downloaded"]
        total = state["total"]
        elapsed = time.time() - state["start"]
        if total > 0:
            percent = int(downloaded * 100 / total)
            bar.setValue(min(percent, 100))
            status.setText("已下载 %.1f MB / %.1f MB（%d%%）"
                           % (downloaded / 1048576, total / 1048576, percent))
        else:
            status.setText("已下载 %.1f MB" % (downloaded / 1048576))
        if elapsed > 0.5 and downloaded > 0:
            speed = downloaded / elapsed
            remaining = max(total - downloaded, 0)
            if speed >= 1048576:
                speed_text = "%.1f MB/s" % (speed / 1048576)
            else:
                speed_text = "%.0f KB/s" % (speed / 1024)
            eta_text = "%d 秒" % int(remaining / speed) if speed > 0 and total > 0 else "--"
            meta.setText("速度：%s　剩余：%s" % (speed_text, eta_text))
        QApplication.processEvents()

    def on_complete():
        bar.setValue(100)
        status.setText("下载完成，正在准备安装…")
        cancel_btn.setText("正在安装…")
        cancel_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            bat_path = _generate_updater_bat(zip_path, app_dir)
            os.startfile(bat_path)
            state["launch"] = True
            dialog.accept()
        except Exception as error:
            _debug_log("启动更新脚本失败：%s" % error)
            QMessageBox.critical(dialog, "更新失败", "启动更新脚本失败：\n%s" % error)
            dialog.reject()

    def on_failed():
        QMessageBox.critical(dialog, "下载失败", "下载更新包失败：\n%s" % state["error"])
        dialog.reject()

    sig.progress.connect(update_ui)
    sig.completed.connect(on_complete)
    sig.cancelled.connect(dialog.reject)
    sig.failed.connect(on_failed)

    threading.Thread(target=do_download, daemon=True).start()
    dialog.exec()
    return state["launch"]


def _run_check_in_background(on_result):
    """后台线程检查更新，结果通过回调回到主线程"""

    def worker():
        try:
            info = check_for_updates()
        except Exception:
            _debug_log("检查更新线程异常：\n%s" % traceback.format_exc())
            info = None
        on_result(info)

    threading.Thread(target=worker, daemon=True).start()


def check_and_show_update(parent=None):
    """启动时调用：静默检测，有新版本才弹窗；用户确认后自动下载替换"""
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication

    class _Emitter(QObject):
        found = pyqtSignal(object)

    emitter = _Emitter()
    emitter.setParent(parent)

    def handle(info):
        if info is None:
            return
        if show_update_dialog(info, parent):
            if download_and_install(info, parent):
                QApplication.quit()

    emitter.found.connect(handle)
    _run_check_in_background(lambda info: emitter.found.emit(info))


def check_manually(parent=None):
    """「检查更新」按钮：手动检测，无更新也会给出提示"""
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QMessageBox

    class _Emitter(QObject):
        done = pyqtSignal(object)

    emitter = _Emitter()
    emitter.setParent(parent)

    def handle(info):
        if info is None:
            QMessageBox.information(
                parent, "检查更新",
                "未发现新版本（当前 v%s）。\n如网络异常或无 Release，请稍后再试。"
                % current_version())
            return
        if show_update_dialog(info, parent):
            if download_and_install(info, parent):
                QApplication.quit()

    emitter.done.connect(handle)
    _run_check_in_background(lambda info: emitter.done.emit(info))
