# -*- coding: utf-8 -*-
"""Ren'Py 游戏识别、注入模块的安装/卸载与启动"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime

from core import i18n


MOD_FILENAME = "zz_xl_cheat.rpy"
MOD_RPYC = "zz_xl_cheat.rpyc"
CONFIG_FILENAME = "xl_cheat_config.json"
MOD_MARKER = "xl_renpy_cheat"

# ---- 存档保护（renpy/savetoken.py 的存档签名校验）----
SAVE_GUARD_FILE = os.path.join("renpy", "savetoken.py")
SAVE_GUARD_MARKER = "xl_cheat_save_guard"
SAVE_GUARD_BACKUP_SUFFIX = ".xl_cheat_bak"

SAVE_GUARD_ON = "on"                # 存档保护开启（原始状态）
SAVE_GUARD_OFF_TOOL = "off_tool"    # 由本工具关闭，可恢复
SAVE_GUARD_OFF_EXTERNAL = "off_external"  # 游戏自带或他人手动关闭
SAVE_GUARD_MISSING = "missing"      # 引擎里没有 savetoken.py，无需处理

# 追加到 savetoken.py 末尾的关闭代码。用 *args 兼容不同 Ren'Py 版本的签名。
# 注意：这段代码会被追加到 Ren'Py 引擎自己的 savetoken.py 末尾。
# Ren'Py 7 用的是 Python 2，源码默认按 ASCII 解析且该文件没有 coding 声明，
# 所以这里只能写纯英文注释，夹带中文会让引擎直接 SyntaxError 起不来。
SAVE_GUARD_BLOCK = (
    "\n"
    "# === %s START ===\n"
    "# Added by RenPyCheat: disable save signature check (skip savefile verification).\n"
    "# To restore, use the \"Restore save protection\" button or delete this block.\n"
    "def check_load(*args, **kwargs):\n"
    "    return True\n"
    "\n"
    "\n"
    "def check_persistent(*args, **kwargs):\n"
    "    return True\n"
    "\n"
    "\n"
    "def upgrade_all_savefiles(*args, **kwargs):\n"
    "    return\n"
    "# === %s END ===\n"
) % (SAVE_GUARD_MARKER, SAVE_GUARD_MARKER)

# 旧式/自带补丁的写法：在函数开头插入 `if True:` + `return`
_NEUTRALIZED_GUARD = re.compile(r"if True:\s*\n\s*return", re.M)
_GUARD_BLOCK_RE = re.compile(
    r"\n*# === %s START ===.*?# === %s END ===\n*" % (SAVE_GUARD_MARKER, SAVE_GUARD_MARKER),
    re.S,
)

TH32CS_SNAPPROCESS = 0x00000002


class GameError(Exception):
    """游戏检测/安装相关错误，message 直接展示给用户"""


@dataclass
class RenpyGame:
    root: str
    game_dir: str
    exe: str = ""
    version: str = ""
    title: str = ""
    writable: bool = False
    installed: bool = False
    running_pids: list = field(default_factory=list)
    config_port: int = 0

    @property
    def exe_name(self):
        return os.path.basename(self.exe) if self.exe else ""


def resource_path(relative: str) -> str:
    """打包后从 _MEIPASS 取资源，源码运行时从工具根目录取"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def tool_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_HELPER_EXES = ("python.exe", "pythonw.exe", "zsync.exe", "zsyncmake.exe")


def _process_path(pid: int) -> str:
    """取进程的完整路径；权限不够时返回空串"""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(4096)
        buf = ctypes.create_unicode_buffer(4096)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(handle)
    return ""


def running_pids_for(exe_name: str, root: str = ""):
    """枚举进程，返回游戏进程的 PID 列表（Windows 原生，无需 psutil）

    二次启动的游戏（启动器 → 真正的 exe，名字可能完全不同）按 exe 名匹配会
    漏掉内层进程，所以传入 root 时再按「进程路径在游戏目录内」兜底匹配。
    """
    if not exe_name and not root:
        return []
    root_prefix = (os.path.abspath(root).rstrip("\\/") + os.sep).lower() if root else ""
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return []
    entry = _PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
    pids = []
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            name = str(entry.szExeFile)
            pid = int(entry.th32ProcessID)
            matched = bool(exe_name) and name.lower() == exe_name.lower()
            if root_prefix and not matched and name.lower() not in _HELPER_EXES:
                path = _process_path(pid)
                matched = bool(path) and path.lower().startswith(root_prefix)
            if matched:
                pids.append(pid)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


def list_renpy_processes():
    """枚举当前正在运行的 Ren'Py 游戏进程（用于「手动附加进程」）

    二次启动的游戏（启动器先跑、再拉起真正的 exe）没法靠「记住启动的 PID」
    匹配，这里直接按进程路径反推游戏根目录，再判断它是不是 Ren'Py 游戏。
    返回 [{pid, exe, name, root, title, installed}]，按 exe 名排序。
    """
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return []
    entry = _PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
    self_root = os.path.abspath(tool_root()).rstrip("\\/").lower()
    found = []
    seen_roots = set()
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            name = str(entry.szExeFile)
            pid = int(entry.th32ProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            if pid <= 4 or name.lower() in _HELPER_EXES:
                continue
            path = _process_path(pid)
            if not path or not path.lower().endswith(".exe"):
                continue
            root = os.path.dirname(path)
            if root.lower() == self_root:
                continue
            # Ren'Py 游戏目录特征：同级的 renpy 与 game 目录
            if not (os.path.isdir(os.path.join(root, "renpy"))
                    and os.path.isdir(os.path.join(root, "game"))):
                continue
            if root.lower() in seen_roots:
                continue
            seen_roots.add(root.lower())
            game = inspect_game(root)
            found.append({
                "pid": pid,
                "exe": path,
                "name": name,
                "root": root,
                "title": game.title or name,
                "installed": game.installed,
                "port": _read_config_port(game.game_dir),
            })
    finally:
        kernel32.CloseHandle(snapshot)
    found.sort(key=lambda item: (item["title"].lower(), item["pid"]))
    return found


def _is_writable(folder: str) -> bool:
    probe = os.path.join(folder, ".xl_write_test.tmp")
    try:
        with open(probe, "wb") as handle:
            handle.write(b"ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _detect_version(root: str) -> str:
    init_file = os.path.join(root, "renpy", "__init__.py")
    try:
        with open(init_file, "r", encoding="utf-8", errors="ignore") as handle:
            text = handle.read(200000)
        # 新版引擎：version = "8.5.2.26010301"
        match = re.search(r"^version\s*=\s*[\"']([0-9][0-9.]*)[\"']", text, re.M)
        if match:
            return match.group(1)
        # 旧版引擎：version_tuple = (8, 2, 3)
        match = re.search(r"version_tuple\s*=\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
        if match:
            return "%s.%s.%s" % match.groups()
    except OSError:
        pass

    # 有些汉化版把版本写进 renpy/version.json，或只在版本模块里动态生成
    for name, pattern in (
        ("version.json", r"\"version\"\s*:\s*\"([0-9][0-9.]*)\""),
        ("versions.json", r"\"version\"\s*:\s*\"([0-9][0-9.]*)\""),
    ):
        path = os.path.join(root, "renpy", name)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                match = re.search(pattern, handle.read(20000))
            if match:
                return match.group(1)
        except OSError:
            pass

    # 兜底：引擎每次启动都会在根目录写 log.txt，首行区就是它自己的版本号
    try:
        with open(os.path.join(root, "log.txt"), "r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(4000)
        match = re.search(r"Ren'Py\s+([0-9]+(?:\.[0-9]+)+)", head)
        if match:
            return match.group(1)
    except OSError:
        pass
    return ""


def _find_exe(root: str) -> str:
    skip_words = ("unins", "updater", "crash", "report", "unitycrash", "python")
    # 二次启动的壳程序：真正的游戏 exe 在它后面，优先选后者
    launcher_words = ("launcher", "启动器", "开始游戏", "start game")
    best = ""
    best_size = -1
    fallback = ""               # 启动器候选，只有找不到别的 exe 时才用
    fallback_size = -1
    try:
        names = os.listdir(root)
    except OSError:
        return ""
    for name in names:
        if not name.lower().endswith(".exe"):
            continue
        low = name.lower()
        if any(word in low for word in skip_words):
            continue
        full = os.path.join(root, name)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        if any(word in low for word in launcher_words):
            if size > fallback_size:
                fallback_size = size
                fallback = full
            continue
        if size > best_size:
            best_size = size
            best = full
    return best or fallback


def _read_config_port(game_dir: str) -> int:
    path = os.path.join(game_dir, CONFIG_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return int(json.load(handle).get("port", 0))
    except (OSError, ValueError, TypeError):
        return 0


def inspect_game(path: str) -> RenpyGame:
    """接受游戏根目录、game 目录，或直接拖进来的启动文件（.exe 等）"""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if not os.path.isdir(path):
        raise GameError("目录不存在：%s" % path)

    root = path
    if os.path.basename(path).lower() == "game" and os.path.isdir(os.path.join(os.path.dirname(path), "game")):
        root = os.path.dirname(path)

    game_dir = os.path.join(root, "game")
    if not os.path.isdir(game_dir):
        raise GameError("所选目录下没有 game 文件夹，不像是 Ren'Py 游戏根目录")

    has_engine_dir = os.path.isdir(os.path.join(root, "renpy"))
    has_lib_dir = os.path.isdir(os.path.join(root, "lib"))
    has_game_assets = False
    try:
        for name in os.listdir(game_dir):
            lower = name.lower()
            if lower.endswith(".rpyc") or lower.endswith(".rpa"):
                has_game_assets = True
                break
    except OSError:
        pass

    if not (has_engine_dir or has_lib_dir or has_game_assets):
        raise GameError("未检测到 Ren'Py 引擎特征（缺少 renpy 目录 / lib 目录 / .rpyc / .rpa）")

    exe = _find_exe(root)
    installed = os.path.exists(os.path.join(game_dir, MOD_FILENAME)) or os.path.exists(
        os.path.join(game_dir, MOD_RPYC)
    )
    game = RenpyGame(
        root=root,
        game_dir=game_dir,
        exe=exe,
        version=_detect_version(root),
        title=os.path.basename(root.rstrip("\\/")),
        writable=_is_writable(game_dir),
        installed=installed,
        config_port=_read_config_port(game_dir),
    )
    game.running_pids = running_pids_for(game.exe_name, root)
    return game


def _read_mod_template() -> str:
    path = resource_path(os.path.join("mod", "xl_renpy_cheat.rpy"))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise GameError("注入模块文件缺失（mod/xl_renpy_cheat.rpy）：%s" % exc)
    if MOD_MARKER not in text:
        raise GameError("注入模块文件内容异常，请重新下载工具")
    return text


def install_mod(path: str, port: int = 47321) -> RenpyGame:
    game = inspect_game(path)
    if not game.writable:
        raise GameError("game 目录不可写（可能位于 Program Files 或被只读保护），无法安装注入模块")

    target = os.path.join(game.game_dir, MOD_FILENAME)
    template = _read_mod_template()

    # 若同名文件不是本工具生成的，先备份，卸载时还原
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8", errors="ignore") as handle:
                existing = handle.read(4000)
        except OSError:
            existing = ""
        if MOD_MARKER not in existing and "Ren'Py 实时修改器" not in existing:
            backup = target + ".bak_" + datetime.now().strftime("%Y%m%d%H%M%S")
            os.replace(target, backup)

    try:
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(template)
    except OSError as exc:
        raise GameError("写入注入模块失败：%s" % exc)

    config_path = os.path.join(game.game_dir, CONFIG_FILENAME)
    try:
        with open(config_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"port": int(port)}, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise GameError("写入端口配置失败：%s" % exc)

    # 中文对照表：游戏没选语言时中文 tl 不会被加载，靠这份表把物品/角色名
    # 显示成中文。提取失败不影响注入，游戏里选中文照样正常。
    try:
        i18n.ensure_translations(game.game_dir, force=True)
    except Exception:
        pass

    # 删掉本模块的旧字节码，确保下次启动重新编译（不动引擎全局缓存，避免全量重编译）
    cache_path = os.path.join(game.game_dir, MOD_RPYC)
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except OSError:
            pass

    return inspect_game(game.root)


def uninstall_mod(path: str) -> RenpyGame:
    game = inspect_game(path)
    for name in (MOD_FILENAME, MOD_RPYC, CONFIG_FILENAME, i18n.I18N_FILENAME):
        target = os.path.join(game.game_dir, name)
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError as exc:
                raise GameError("删除 %s 失败（游戏可能正在运行）：%s" % (name, exc))

    # 引擎编译缓存里可能还留着注入模块的字节码，一并清掉
    # Ren'Py 7.x 的文件名是 bytecode-27.rpyb，旧版本是 bytecode.rpyb
    cache_dir = os.path.join(game.game_dir, "cache")
    try:
        cache_files = os.listdir(cache_dir)
    except OSError:
        cache_files = []
    for name in cache_files:
        if name.startswith("bytecode") and name.endswith(".rpyb"):
            try:
                os.remove(os.path.join(cache_dir, name))
            except OSError:
                pass

    # 还原之前备份的同名脚本
    try:
        names = os.listdir(game.game_dir)
    except OSError:
        names = []
    backups = sorted(
        [n for n in names if n.startswith(MOD_FILENAME + ".bak_")],
        reverse=True,
    )
    if backups:
        try:
            os.replace(os.path.join(game.game_dir, backups[0]), os.path.join(game.game_dir, MOD_FILENAME))
        except OSError:
            pass

    return inspect_game(game.root)


def launch_exe(exe: str, root: str):
    """启动游戏的启动程序"""
    if not exe or not os.path.isfile(exe):
        raise GameError("未找到游戏启动程序（.exe），请手动启动游戏")
    try:
        subprocess.Popen([exe], cwd=root, close_fds=True)
    except OSError as exc:
        raise GameError("启动游戏失败：%s" % exc)


def launch_game(path: str):
    game = inspect_game(path)
    launch_exe(game.exe, game.root)
    return game


# ----------------------------------------------------------------------
# 游戏自动识别：Ren'Py / 未知
# ----------------------------------------------------------------------
ENGINE_RENPY = "renpy"
ENGINE_UNKNOWN = "unknown"


def _normalize_root(path: str) -> str:
    path = os.path.abspath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    # 拖进来的是 game 子目录时，自动回到根目录
    if os.path.basename(path).lower() == "game":
        parent = os.path.dirname(path)
        if os.path.isdir(os.path.join(parent, "game")):
            return parent
    return path


def detect_engine(path: str) -> dict:
    """自动识别游戏

    返回 {"engine": renpy|unknown, "root": 实际根目录,
          "renpy": RenpyGame|None, "error": str}
    """
    root = _normalize_root(path)
    result = {"engine": ENGINE_UNKNOWN, "root": root, "renpy": None, "error": ""}
    if not os.path.isdir(root):
        result["error"] = "目录不存在：%s" % root
        return result

    try:
        result["renpy"] = inspect_game(root)
        result["engine"] = ENGINE_RENPY
        return result
    except GameError as error:
        result["error"] = str(error)
    return result


# ----------------------------------------------------------------------
# 存档保护：改过的存档会被 savetoken 签名校验拒绝，这里直接关掉该校验
# ----------------------------------------------------------------------
def _savetoken_path(root: str) -> str:
    return os.path.join(root, SAVE_GUARD_FILE)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _clear_savetoken_cache(root: str):
    """删除 savetoken 的旧字节码，确保下次启动用修改后的源码

    Ren'Py 7（Python 2）编译出的是 .pyo/.pyc，且优化模式会优先加载 .pyo，
    两种后缀都要清掉，否则改了 .py 也不会生效。
    """
    engine = os.path.join(root, "renpy")
    for folder in (engine, os.path.join(engine, "__pycache__")):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            low = name.lower()
            if low.startswith("savetoken.") and low.endswith((".pyc", ".pyo")):
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass


def save_protection_state(root: str) -> str:
    """返回存档保护状态，供界面展示"""
    path = _savetoken_path(root)
    if not os.path.isfile(path):
        return SAVE_GUARD_MISSING
    try:
        text = _read_text(path)
    except OSError:
        return SAVE_GUARD_MISSING
    if SAVE_GUARD_MARKER in text:
        return SAVE_GUARD_OFF_TOOL
    if _NEUTRALIZED_GUARD.search(text):
        return SAVE_GUARD_OFF_EXTERNAL
    return SAVE_GUARD_ON


def disable_save_protection(root: str) -> str:
    """关闭存档保护，返回操作后的状态"""
    path = _savetoken_path(root)
    if not os.path.isfile(path):
        raise GameError("这个游戏没有 renpy/savetoken.py，没有需要关闭的存档保护")
    if not _is_writable(os.path.dirname(path)):
        raise GameError("renpy 目录不可写（可能位于 Program Files 或只读目录），无法修改存档保护")

    try:
        text = _read_text(path)
    except OSError as exc:
        raise GameError("读取 savetoken.py 失败：%s" % exc)

    if SAVE_GUARD_MARKER in text:
        return SAVE_GUARD_OFF_TOOL
    if _NEUTRALIZED_GUARD.search(text):
        # 游戏自带或此前手动改过，保持原样
        return SAVE_GUARD_OFF_EXTERNAL

    backup = path + SAVE_GUARD_BACKUP_SUFFIX
    if not os.path.exists(backup):
        try:
            shutil.copy2(path, backup)
        except OSError as exc:
            raise GameError("备份 savetoken.py 失败：%s" % exc)

    if not text.endswith("\n"):
        text += "\n"
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text + SAVE_GUARD_BLOCK)
    except OSError as exc:
        raise GameError("写入 savetoken.py 失败：%s" % exc)

    _clear_savetoken_cache(root)
    return SAVE_GUARD_OFF_TOOL


def enable_save_protection(root: str) -> str:
    """恢复本工具关闭的存档保护，返回操作后的状态"""
    path = _savetoken_path(root)
    if not os.path.isfile(path):
        raise GameError("renpy/savetoken.py 不存在，无法恢复")
    try:
        text = _read_text(path)
    except OSError as exc:
        raise GameError("读取 savetoken.py 失败：%s" % exc)
    if SAVE_GUARD_MARKER not in text:
        raise GameError("存档保护不是由本工具关闭的，不能自动恢复")

    backup = path + SAVE_GUARD_BACKUP_SUFFIX
    try:
        if os.path.exists(backup):
            # 按字节还原，避免编码转换把原文件改坏
            shutil.copy2(backup, path)
        else:
            text = _GUARD_BLOCK_RE.sub("\n", text)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    except OSError as exc:
        raise GameError("恢复 savetoken.py 失败：%s" % exc)

    try:
        os.remove(backup)
    except OSError:
        pass

    _clear_savetoken_cache(root)
    return SAVE_GUARD_ON
