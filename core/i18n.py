# -*- coding: utf-8 -*-
"""离线提取 Ren'Py 游戏的中文翻译对照表。

Ren'Py 启动时只会加载「当前语言」的 tl 翻译脚本；玩家没在游戏里选语言时
翻译表是空的，游戏数据表里的原文（韩文/英文）就原样显示。这里直接从游戏的
archive.rpa / 散装 rpyc、rpy 里把中文 tl 的 old→new 全部读出来，写成 JSON
给注入模块兜底使用，跟游戏当前语言无关，换任意 Ren'Py 游戏都能自动提取。
"""
from __future__ import annotations

import ast
import io
import json
import os
import pickle
import re
import struct
import zlib

RPA_HEADER = b"RENPY RPC2"

I18N_FILENAME = "xl_cheat_i18n.json"

# 中文语言包目录名关键词（tl/<language>）。不同游戏/汉化组的命名五花八门。
LANGUAGE_KEYWORDS = (
    "chinese", "schinese", "tchinese", "simplified", "traditional",
    "zh", "cn", "chs", "cht", "简体", "繁体", "中文",
)
SIMPLIFIED_KEYWORDS = ("simplified", "schinese", "chs", "简体", "zh_cn", "zh-cn", "cn")
TRADITIONAL_KEYWORDS = ("traditional", "tchinese", "cht", "繁体", "zh_tw", "zh-tw")


def _language_score(name: str) -> int:
    """0 = 不是中文语言包；3 = 简体优先；2 = 通用中文；1 = 繁体"""
    low = name.lower()
    if not any(keyword in low for keyword in LANGUAGE_KEYWORDS):
        return 0
    if any(keyword in low for keyword in TRADITIONAL_KEYWORDS):
        return 1
    if any(keyword in low for keyword in SIMPLIFIED_KEYWORDS):
        return 3
    return 2


# ----------------------------------------------------------------------
# 反序列化用 stub：游戏脚本里的 Ren'Py 类在工具进程里不存在，
# 统一替换成能承载 state 的空壳，只为了把对象图走一遍取出 old/new。
# ----------------------------------------------------------------------
class _Stub(object):
    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        obj._args = args
        return obj

    def __init__(self, *args, **kwargs):
        self._args = args

    def __setstate__(self, state):
        if isinstance(state, dict):
            for key, value in state.items():
                setattr(self, key, value)
        elif isinstance(state, tuple) and len(state) == 2 and isinstance(state[0], dict):
            for key, value in state[0].items():
                setattr(self, key, value)
            self._slots = state[1]
        else:
            self._state = state


class _StubList(list):
    pass


class _StubDict(dict):
    pass


class _StubSet(set):
    pass


def _stub_class(module, name):
    if "List" in name:
        base = _StubList
    elif "Dict" in name:
        base = _StubDict
    elif "Set" in name:
        base = _StubSet
    else:
        base = _Stub
    return type(name, (base,), {})


_CLASS_CACHE = {}


class _StubUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        key = (module, name)
        cached = _CLASS_CACHE.get(key)
        if cached is not None:
            return cached
        if module.startswith("renpy"):
            cls = _stub_class(module, name)
        elif module in ("collections", "copyreg", "builtins"):
            try:
                builtin_mod = __import__(module)
                cls = getattr(builtin_mod, name, _Stub)
            except Exception:
                cls = _Stub
        else:
            try:
                imported = __import__(module, fromlist=["*"])
                cls = getattr(imported, name)
            except Exception:
                cls = _stub_class(module, name)
        _CLASS_CACHE[key] = cls
        return cls


def _walk_pairs(obj, pairs, depth=0, seen=None):
    if depth > 60:
        return
    if seen is None:
        seen = set()
    if isinstance(obj, (str, bytes, int, float, bool, type(None))):
        return
    marker = id(obj)
    if marker in seen:
        return
    seen.add(marker)

    if isinstance(obj, dict):
        _add_pair(pairs, obj.get("old"), obj.get("new"))
        for value in obj.values():
            _walk_pairs(value, pairs, depth + 1, seen)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            _walk_pairs(value, pairs, depth + 1, seen)
    else:
        state = getattr(obj, "__dict__", None) or {}
        _add_pair(pairs, state.get("old"), state.get("new"))
        for value in state.values():
            _walk_pairs(value, pairs, depth + 1, seen)


def _as_text(value):
    """Ren'Py 7（Python 2）的脚本里字符串是字节串，反序列化出来是 bytes"""
    if isinstance(value, bytes):
        for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", "replace")
    return value


def _add_pair(pairs, old, new):
    old = _as_text(old)
    new = _as_text(new)
    if isinstance(old, str) and isinstance(new, str) and old.strip() and old != new:
        pairs.setdefault(old, new)


# ----------------------------------------------------------------------
# RPA 归档（兼容 RPA-1.0 / 2.0 / 3.0）
# ----------------------------------------------------------------------
def _read_rpa_index(handle):
    """返回 (index, version, key)；不是 RPA 归档返回 (None, 0, 0)"""
    first = handle.readline()
    try:
        header = first.decode("ascii", "ignore").strip()
    except Exception:
        return None, 0, 0
    parts = header.split()
    if not parts or not parts[0].startswith("RPA-"):
        return None, 0, 0
    try:
        if parts[0] == "RPA-3.0":
            offset, version, key = int(parts[1], 16), 3, int(parts[2], 16)
        elif parts[0] == "RPA-2.0":
            offset, version, key = int(parts[1], 16), 2, 0
        elif parts[0] == "RPA-1.0":
            offset, version, key = int(parts[1], 16), 1, 0
        else:
            return None, 0, 0
        handle.seek(offset)
        index = pickle.loads(zlib.decompress(handle.read()))
    except Exception:
        return None, 0, 0
    if not isinstance(index, dict):
        return None, 0, 0
    return index, version, key


def _entry_chunks(stored, version, key):
    items = stored if isinstance(stored, list) else [stored]
    chunks = []
    for entry in items:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        offset, length = entry[0], entry[1]
        prefix = entry[2] if len(entry) > 2 else b""
        if version == 3:
            offset ^= key
            length ^= key
        chunks.append((offset, length, prefix))
    return chunks


def _read_rpa_entry(handle, chunks):
    parts = []
    for offset, length, prefix in chunks:
        handle.seek(offset)
        parts.append(prefix + handle.read(length))
    return _read_slot(b"".join(parts))


def _read_slot(blob):
    if not blob.startswith(RPA_HEADER):
        return zlib.decompress(blob)

    position = len(RPA_HEADER)
    while position + 12 <= len(blob):
        slot, start, length = struct.unpack("III", blob[position:position + 12])
        if slot == 1:
            return zlib.decompress(blob[start:start + length])
        if slot == 0:
            return None
        position += 12
    return None


def _pairs_from_blob(blob):
    pairs = {}
    try:
        data = _StubUnpickler(io.BytesIO(blob)).load()
    except Exception:
        return pairs
    _walk_pairs(data, pairs)
    return pairs


# ----------------------------------------------------------------------
# 文本 rpy 翻译脚本：translate <language> strings: / old "" / new ""
# ----------------------------------------------------------------------
_QUOTED_RE = re.compile(
    r"""^[uUbBrR]{0,2}("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")


def _string_literal(text):
    match = _QUOTED_RE.match(text.strip())
    if not match:
        return None
    try:
        value = ast.literal_eval(match.group(1))
    except Exception:
        return None
    return _as_text(value)


def _pairs_from_script(text):
    pairs = {}
    in_strings = False
    old = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_strings = stripped.startswith("translate ") and stripped.endswith("strings:")
            old = None
            continue
        if not in_strings:
            continue
        if stripped.startswith("old "):
            old = _string_literal(stripped[4:]) or ""
        elif stripped.startswith("new "):
            new = _string_literal(stripped[4:])
            if old and new and old != new:
                pairs.setdefault(old, new)
            old = None
    return pairs


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
def _merge_pairs(target, source):
    for old, new in source.items():
        target.setdefault(old, new)


def _archives(game_dir):
    found = []
    try:
        for folder, _dirs, files in os.walk(game_dir):
            for name in files:
                if name.lower().endswith(".rpa"):
                    found.append(os.path.join(folder, name))
    except OSError:
        pass
    return sorted(found)


def _discover_languages(game_dir, indexes):
    """从 game/tl 目录与归档索引里找出所有中文语言包，简体优先"""
    names = set()
    tl_root = os.path.join(game_dir, "tl")
    try:
        for name in os.listdir(tl_root):
            if os.path.isdir(os.path.join(tl_root, name)):
                names.add(name)
    except OSError:
        pass
    for _path, index, _version, _key in indexes:
        for name in index:
            parts = name.split("/")
            if len(parts) >= 3 and parts[0] == "tl":
                names.add(parts[1])

    scored = [(_language_score(name), name) for name in names]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _score, name in scored]


def extract_translations(game_dir: str) -> dict:
    """扫描 game 目录（.rpa 归档 + 散装 rpyc/rpy），返回 old→中文 对照表"""
    result = {}
    if not game_dir or not os.path.isdir(game_dir):
        return result

    indexes = []
    for path in _archives(game_dir):
        try:
            with open(path, "rb") as handle:
                index, version, key = _read_rpa_index(handle)
        except OSError:
            continue
        if index:
            indexes.append((path, index, version, key))

    for language in _discover_languages(game_dir, indexes):
        # 1) 散装脚本：game/tl/<language>/**/*.rpyc / *.rpy
        loose_root = os.path.join(game_dir, "tl", language)
        for folder, _dirs, files in os.walk(loose_root):
            for name in files:
                low = name.lower()
                if not low.endswith((".rpyc", ".rpy")):
                    continue
                path = os.path.join(folder, name)
                try:
                    if low.endswith(".rpyc"):
                        with open(path, "rb") as handle:
                            raw = _read_slot(handle.read())
                        if raw:
                            _merge_pairs(result, _pairs_from_blob(raw))
                    else:
                        with open(path, "r", encoding="utf-8", errors="replace") as handle:
                            _merge_pairs(result, _pairs_from_script(handle.read()))
                except Exception:
                    continue

        # 2) 归档：tl/<language>/ 下的脚本
        prefix = "tl/%s/" % language
        for path, index, version, key in indexes:
            try:
                with open(path, "rb") as handle:
                    for name in index:
                        low = name.lower()
                        if not low.startswith(prefix.lower()):
                            continue
                        if not low.endswith((".rpyc", ".rpy")):
                            continue
                        stored = index[name]
                        chunks = _entry_chunks(stored, version, key)
                        if not chunks:
                            continue
                        try:
                            raw = _read_rpa_entry(handle, chunks)
                        except Exception:
                            continue
                        if not raw:
                            continue
                        if low.endswith(".rpyc"):
                            _merge_pairs(result, _pairs_from_blob(raw))
                        else:
                            _merge_pairs(result, _pairs_from_script(
                                raw.decode("utf-8", "replace")))
            except OSError:
                continue

    return result


def write_translations(game_dir: str, table: dict) -> str:
    """把对照表写进 game 目录，返回文件路径；表为空时返回空串"""
    if not table:
        return ""
    target = os.path.join(game_dir, I18N_FILENAME)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(table, handle, ensure_ascii=False)
    return target


def table_path(game_dir: str) -> str:
    return os.path.join(game_dir, I18N_FILENAME)


def table_count(game_dir: str) -> int:
    """已写入的对照表条数；没有则 0"""
    path = table_path(game_dir)
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return len(data) if isinstance(data, dict) else 0
    except Exception:
        return 0


def ensure_translations(game_dir: str, force: bool = False) -> int:
    """确保游戏目录里有中文对照表，返回条数（0 表示该游戏没有中文 tl）"""
    if not force:
        count = table_count(game_dir)
        if count:
            return count
    try:
        table = extract_translations(game_dir)
    except Exception:
        return 0
    if not table:
        return 0
    try:
        write_translations(game_dir, table)
    except OSError:
        return 0
    return len(table)
