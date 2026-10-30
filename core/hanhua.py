# -*- coding: utf-8 -*-
"""Ren'Py 文本提取与汉化落盘

只做三件事：
1. 从 game 目录（散装 rpy / rpyc / rpa）提取原文；
2. 把译文写成 game/tl/<language>/ 下的 strings 翻译块（含字体样式、默认语言）；
3. 所有产物统一 zz_xl_ 前缀，支持一键卸载。

不修改原游戏脚本、不改 rpyc，失败可直接删目录回滚。
"""

import ast
import io
import json
import os
import pickle
import re
import struct
import shutil
import urllib.error
import urllib.request
import zlib

from core import i18n

LANGUAGE = "chinese"
PREFIX = "zz_xl_"
TL_PREFIX = PREFIX
STYLE_FILE = PREFIX + "style.rpy"
DEFAULT_FILE = PREFIX + "default_lang.rpy"
FONT_DIRNAME = "fonts"

RPYC2_HEADER = b"RENPY RPC2"

# say 语句里不能当作角色名的关键字
_NOT_WHO = {
    "define", "default", "image", "images", "show", "scene", "hide", "play",
    "queue", "stop", "voice", "window", "pause", "with", "jump", "call",
    "return", "menu", "label", "init", "python", "transform", "style",
    "screen", "translate", "if", "elif", "else", "while", "for", "pass",
    "renpy", "layeredimage", "camera", "audio", "movie", "text",
    "add", "use", "key", "on", "at", "behind", "as", "expression",
}

# 这些关键字开头的块里没有玩家可见的对话：init/python/style/screen/transform/
# image 块里的 `属性 "值"` 形式会被误判成 say 语句（例如 style 里的
# `size_group "mm"`、screen 里的 `layout "subtitle"`），必须整块跳过。
_SKIP_BLOCK_WORDS = {
    "translate", "init", "python", "style", "screen", "transform",
    "layeredimage", "image", "camera",
}

_QUOTED_RE = re.compile(r"""^(?:[uUbBrR]{0,2})("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")
_DEFINE_STR_RE = re.compile(r"""_\(\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\s*\)""")

# screen 块里会渲染成文字、且走 renpy.translate_string() 的语句。
# 依据引擎源码：text 走 renpy.text.text.Text（substitute 默认 True），
# textbutton / label 走 renpy.ui._textbutton / _label（substitute=True），
# 三者都会在显示时查 translate strings 表，所以注册进 tl 就能翻译。
_SCREEN_TEXT_RE = re.compile(
    r"""^(?:textbutton|text|label|tooltip)\s+
        (?P<q>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""",
    re.VERBOSE,
)
# screen 语法树里，这些节点的 positional[0] 就是显示文字
_SCREEN_TEXT_NAMES = {"text", "textbutton", "label"}
# 旧版 rpyc 的 SLDisplayable 只保留 displayable 类名，用类名反推是哪种文字控件
_DISPLAYABLE_TEXT_NAMES = {
    "Text": "text",
    "TextButton": "textbutton",
    "Label": "label",
    "_textbutton": "textbutton",
    "_label": "label",
}

# 文本标签 {color=...} 与变量插值 [var]
_TEXT_TAG_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")
_HAS_WORD_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_OLD_LINE_RE = re.compile(r"""^\s*old\s+("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")


def _is_translatable_text(text):
    """去掉标签与插值后还剩真实文字才算可翻译

    `[_pc_title]`、`{size=16}{/size}` 这类注册进 strings 表也没有意义，
    真正的文字要等运行时变量求值后才出现。
    """
    if not isinstance(text, str) or not text.strip():
        return False
    return bool(_HAS_WORD_RE.search(_TEXT_TAG_RE.sub("", text)))


_SAY_RE = re.compile(
    r"""^(?P<indent>[ \t]*)(?:(?P<who>[A-Za-z_][\w.]*)\s+)?
        (?P<q>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
        (?P<tail>\s*(?:(?:with|id|interact|nointeract|arguments|at)\b.*)?)$""",
    re.VERBOSE,
)


class HanhuaError(Exception):
    pass


# ----------------------------------------------------------------------
# rpyc 反序列化（不依赖 renpy 运行时）
# ----------------------------------------------------------------------
class _Stub(object):
    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        # 旧版 rpyc（Ren'Py 6/7）用 NEWOBJ 构造节点，参数不会经过 __init__，
        # 必须在这里接住，否则 PyExpr 的源码表达式就丢了
        object.__setattr__(obj, "_dict", {})
        object.__setattr__(obj, "_slots", {})
        object.__setattr__(obj, "_args", args)
        return obj

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, "_dict", {})
        object.__setattr__(self, "_slots", {})
        # PyExpr 用 __reduce__ 返回 (类, (源码字符串,))，反序列化时走构造参数，
        # 不存下来就取不到 screen 里的显示文字
        object.__setattr__(self, "_args", args)

    def __setstate__(self, state):
        if isinstance(state, dict):
            object.__setattr__(self, "_dict", state)
        elif isinstance(state, tuple) and len(state) == 2:
            d, s = state
            if isinstance(d, dict):
                object.__setattr__(self, "_dict", d)
            if isinstance(s, dict):
                object.__setattr__(self, "_slots", s)
        else:
            # PyExpr 之类的类用 __reduce__ 直接返回字符串（源码表达式），
            # 不是 dict，必须原样保留，否则 screen 里的显示文字就丢了
            object.__setattr__(self, "_state", state)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            d = object.__getattribute__(self, "_dict")
            s = object.__getattribute__(self, "_slots")
        except AttributeError:
            raise AttributeError(name)
        if name in d:
            return d[name]
        if name in s:
            return s[name]
        raise AttributeError(name)


_class_cache = {}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module == "datetime":
            import datetime
            return getattr(datetime, name)
        if module in ("_ast", "ast"):
            return getattr(ast, name, _Stub)
        if name in ("RevertableDict", "RevertableList", "RevertableSet",
                    "RevertableObject", "defaultdict"):
            key = (module, name)
            if key not in _class_cache:
                if "Dict" in name or "defaultdict" in name:
                    cls = type(name, (dict,), {"__init__": lambda self, *a, **k: dict.__init__(self)})
                elif "List" in name:
                    cls = type(name, (list,), {})
                elif "Set" in name:
                    cls = type(name, (set,), {})
                else:
                    cls = type(name, (_Stub,), {})
                _class_cache[key] = cls
            return _class_cache[key]
        if module == "collections":
            import collections
            return getattr(collections, name)
        key = (module, name)
        if key not in _class_cache:
            _class_cache[key] = type(name, (_Stub,), {})
        return _class_cache[key]


def _load_pickle(blob):
    return _Unpickler(io.BytesIO(blob), fix_imports=True,
                      encoding="utf-8", errors="surrogateescape").load()


def _unpickle_rpyc(blob, already_decompressed=False):
    """把 rpyc / rpymc 还原成可遍历的对象树

    already_decompressed=True 表示传入的已经是解压后的 pickle 字节
    （RPA 条目经 i18n._read_rpa_entry 处理后就是这种形态）。
    """
    if not already_decompressed:
        if blob[:len(RPYC2_HEADER)] == RPYC2_HEADER:
            pos = len(RPYC2_HEADER)
            while pos + 12 <= len(blob):
                slot, start, length = struct.unpack("III", blob[pos:pos + 12])
                if slot == 1:
                    blob = zlib.decompress(blob[start:start + length])
                    break
                pos += 12
            else:
                raise ValueError("rpyc 中没有脚本槽位")
        else:
            blob = zlib.decompress(blob)

    return _load_pickle(blob)


def _walk_text(node, out, depth=0, seen=None):
    if node is None or depth > 40:
        return
    if seen is None:
        seen = set()
    if id(node) in seen:
        return
    seen.add(id(node))

    if isinstance(node, str):
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk_text(item, out, depth + 1, seen)
        return
    if isinstance(node, dict):
        for value in node.values():
            _walk_text(value, out, depth + 1, seen)
        return

    kind = type(node).__name__
    attrs = {}
    d = getattr(node, "_dict", None)
    s = getattr(node, "_slots", None)
    if isinstance(d, dict):
        attrs.update(d)
    if isinstance(s, dict):
        attrs.update(s)

    if kind == "Say":
        what = attrs.get("what")
        if isinstance(what, str) and what.strip():
            out.append(("dialogue", _as_str(attrs.get("who")), what))
    elif kind == "Menu":
        for item in attrs.get("items") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label = item[0]
                if isinstance(label, str) and label.strip():
                    out.append(("menu", "", label))
    elif kind == "SLDisplayable":
        # rpa 里只有 rpyc 时，screen 的界面文字只存在于这个语法节点里。
        # positional[0] 是 text / textbutton / label 的显示文本。
        name = attrs.get("name")
        if not isinstance(name, str):
            # 旧版 rpyc（Ren'Py 6/7）不存 name，只能靠 displayable 类名判断
            name = _DISPLAYABLE_TEXT_NAMES.get(_class_name(attrs.get("displayable")), "")
        if name in _SCREEN_TEXT_NAMES:
            positional = attrs.get("positional") or []
            if positional:
                value = _pyexpr_literal(positional[0])
                if _is_translatable_text(value):
                    out.append(("string", "", value))
    elif kind == "TranslateString":
        # 游戏自带 tl 里的 strings 条目，old 已经在引擎里注册过
        old = attrs.get("old")
        if isinstance(old, str) and old:
            out.append(("tstring", _as_str(attrs.get("language")), old))

    for value in attrs.values():
        if isinstance(value, (str, int, float, bool, bytes, type(None))):
            continue
        _walk_text(value, out, depth + 1, seen)


def _class_name(value):
    if isinstance(value, str):
        return value
    return getattr(value, "__name__", "")


def _as_str(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return ""


def _clean_who(who):
    text = (who or "").strip()
    if text.endswith(".Say"):
        return text[:-4]
    return text


# ----------------------------------------------------------------------
# rpy 源码解析
# ----------------------------------------------------------------------
def _literal(text):
    text = text.strip()
    match = _QUOTED_RE.match(text)
    if not match:
        return None
    try:
        value = ast.literal_eval(re.sub(r"^[uUbBrR]{1,2}", "", match.group(1)))
    except Exception:
        return None
    return value if isinstance(value, str) else None


def _pyexpr_literal(value):
    """从 screen 语法树节点里取出纯字面量文本

    只认 `"..."` 和 `_("...")` 两种形式：其余是变量、表达式或格式化字符串，
    运行时才能确定内容，注册进 strings 表反而会出错。
    """
    if value is None or isinstance(value, (str, bytes)):
        return None
    source = getattr(value, "s", None)
    if not isinstance(source, str):
        # PyExpr 的源码表达式可能在三种位置，按引擎实际序列化方式逐个取
        state = getattr(value, "_state", None)
        if isinstance(state, str):
            source = state
        else:
            args = getattr(value, "_args", None)
            if args and isinstance(args[0], str):
                source = args[0]
    source = _as_str(source).strip()
    if not source:
        return None

    wrapped = _DEFINE_STR_RE.match(source)
    if wrapped and wrapped.end() == len(source):
        result = _literal(wrapped.group(1))
        return result if result and result.strip() else None

    if source[0] in "\"'":
        match = _QUOTED_RE.match(source)
        if match and match.end() == len(source):
            result = _literal(match.group(1))
            return result if result and result.strip() else None
    return None


def _parse_rpy(text, rel_path):
    entries = []
    lines = text.splitlines()
    total = len(lines)
    i = 0
    menu_indent = None
    skip_indent = None
    skip_kind = None

    while i < total:
        raw = lines[i]
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip(" \t"))

        # 块级跳过（python / translate / screen / style 等）
        if skip_indent is not None:
            if stripped and indent <= skip_indent:
                skip_indent = None
                skip_kind = None
            else:
                # screen 块整块跳过，但里面的 text / textbutton / label 要收进
                # 字符串表，否则界面上的文字不会被翻译
                if skip_kind == "screen":
                    match = _SCREEN_TEXT_RE.match(stripped)
                    if match:
                        value = _literal(match.group("q"))
                        if _is_translatable_text(value):
                            entries.append(("string", "", value, rel_path, i + 1))
                    for found in _DEFINE_STR_RE.finditer(raw):
                        value = _literal(found.group(1))
                        if _is_translatable_text(value):
                            entries.append(("string", "", value, rel_path, i + 1))
                i += 1
                continue

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if menu_indent is not None and stripped and indent <= menu_indent:
            menu_indent = None

        head = re.split(r"[\s(]", stripped, 1)[0].rstrip(":")
        if head in _SKIP_BLOCK_WORDS:
            if stripped.endswith(":"):
                skip_indent = indent
                skip_kind = head
            i += 1
            continue

        if stripped.startswith("$") or stripped.startswith("python:"):
            if stripped.endswith(":") and not stripped.startswith("$"):
                skip_indent = indent
                skip_kind = "python"
            i += 1
            continue

        if stripped.startswith("menu"):
            menu_indent = indent
            i += 1
            continue

        # 菜单选项
        if menu_indent is not None and indent > menu_indent:
            if stripped.startswith(('"', "'")):
                value = _literal(stripped)
                if value and value.strip():
                    entries.append(("menu", "", value, rel_path, i + 1))
                i += 1
                continue

        # say 语句
        match = _SAY_RE.match(raw)
        if match:
            who = (match.group("who") or "").strip()
            if who == "extend":
                who = ""
            elif who and who in _NOT_WHO:
                i += 1
                continue
            value = _literal(match.group("q"))
            if value and value.strip():
                entries.append(("dialogue", who, value, rel_path, i + 1))
            i += 1
            continue

        # _("...") 标记的字符串
        for found in _DEFINE_STR_RE.finditer(raw):
            value = _literal(found.group(1))
            if value and value.strip():
                entries.append(("string", "", value, rel_path, i + 1))

        i += 1

    return entries


# ----------------------------------------------------------------------
# 扫描
# ----------------------------------------------------------------------
def _rpa_files(game_dir):
    found = []
    for folder, _dirs, names in os.walk(game_dir):
        if os.path.basename(folder).lower() == "tl":
            continue
        for name in names:
            if name.lower().endswith(".rpa"):
                found.append(os.path.join(folder, name))
    return sorted(found)


def _scan_loose(game_dir, progress):
    entries = []
    for folder, dirs, names in os.walk(game_dir):
        dirs[:] = [d for d in dirs if d.lower() != "tl"]
        # 有同名源码时优先读 rpy，跳过 rpyc，避免同一条被统计两次
        rpy_names = {name.lower() for name in names if name.lower().endswith(".rpy")}
        for name in names:
            low = name.lower()
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, game_dir).replace("\\", "/")
            try:
                if low.endswith(".rpy"):
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                    for kind, who, original, rp, line in _parse_rpy(text, rel):
                        entries.append(_entry(kind, _clean_who(who), original, rp, line))
                elif low.endswith((".rpyc", ".rpymc")):
                    if low.endswith(".rpyc") and low[:-1] in rpy_names:
                        continue
                    with open(path, "rb") as handle:
                        raw = handle.read()
                    for kind, who, original in _collect_from_blob(raw):
                        entries.append(_entry(kind, _clean_who(who), original, rel, 0))
            except Exception:
                continue
            if progress:
                progress("散装脚本：" + rel)
    return entries


def _collect_from_blob(blob, already_decompressed=False):
    found = []
    try:
        data = _unpickle_rpyc(blob, already_decompressed)
    except Exception:
        return found
    try:
        _walk_text(data, found)
    except Exception:
        return found
    return found


def _entry(kind, who, original, file, line):
    return {
        "file": file,
        "line": line,
        "kind": kind,
        "character": who,
        "original": original,
        "translation": "",
        "status": "",
    }


def _registered_old_strings(game_dir, language=LANGUAGE):
    """收集目标语言里已经注册过的 old（含 old==new 的占位条目）

    引擎只要看到同一语言里同一个 old 注册第二次就抛异常，所以判重必须比
    i18n 的 old→new 对照表更宽：不管译文是什么，注册过就得跳过。
    我们自己生成的 zz_xl_ 文件不算，否则改完译文再生成会被全部跳过。
    """
    wanted = "tl/%s/" % language
    olds = set()

    def absorb(blob, already_decompressed):
        try:
            for kind, _who, text in _collect_from_blob(blob, already_decompressed):
                if kind == "tstring":
                    olds.add(text)
        except Exception:
            pass

    for path in _rpa_files(game_dir):
        try:
            with open(path, "rb") as handle:
                index, version, key = i18n._read_rpa_index(handle)
                if not index:
                    continue
                targets = [n for n in index
                           if n.startswith(wanted)
                           and n.lower().endswith((".rpyc", ".rpymc"))]
                for n in targets:
                    if os.path.basename(n).startswith(TL_PREFIX):
                        continue
                    try:
                        raw = i18n._read_rpa_entry(handle, i18n._entry_chunks(index[n], version, key))
                    except Exception:
                        continue
                    if raw:
                        absorb(raw, True)
        except OSError:
            continue

    tl_dir = os.path.join(game_dir, "tl", language)
    if os.path.isdir(tl_dir):
        for folder, _dirs, names in os.walk(tl_dir):
            for name in names:
                if name.startswith(TL_PREFIX):
                    continue
                path = os.path.join(folder, name)
                try:
                    if name.lower().endswith(".rpy"):
                        with open(path, "r", encoding="utf-8", errors="replace") as handle:
                            text = handle.read()
                        for line in text.splitlines():
                            match = _OLD_LINE_RE.match(line)
                            if match:
                                value = _literal(match.group(1))
                                if value:
                                    olds.add(value)
                    elif name.lower().endswith((".rpyc", ".rpymc")):
                        with open(path, "rb") as handle:
                            absorb(handle.read(), False)
                except OSError:
                    continue
    return olds


def scan(game_dir, progress=None, skip_rpa=False):
    """扫描 game 目录，返回 (entries, stats)"""
    if not game_dir or not os.path.isdir(game_dir):
        raise HanhuaError("game 目录不存在")

    entries = []
    stats = []
    if not skip_rpa:
        for path in _rpa_files(game_dir):
            name = os.path.basename(path)
            count = 0
            try:
                with open(path, "rb") as handle:
                    index, version, key = i18n._read_rpa_index(handle)
                    if not index:
                        stats.append((name, 0, "无法解析归档索引"))
                        continue
                    targets = [n for n in index
                               if n.lower().endswith((".rpyc", ".rpymc"))
                               and not n.lower().startswith("tl/")]
                    for n in targets:
                        try:
                            chunks = i18n._entry_chunks(index[n], version, key)
                            raw = i18n._read_rpa_entry(handle, chunks)
                        except Exception:
                            continue
                        if not raw:
                            continue
                        for kind, who, original in _collect_from_blob(raw, True):
                            entries.append(_entry(kind, _clean_who(who), original, n, 0))
                            count += 1
                        if progress:
                            progress("%s / %s" % (name, n))
            except OSError as exc:
                stats.append((name, 0, "读取失败：%s" % exc))
                continue
            stats.append((name, count, "RPA 归档"))

    loose = _scan_loose(game_dir, progress)
    entries.extend(loose)
    stats.append(("散装 rpy / rpyc", len(loose), "目录扫描"))

    # 去重：同文件同原文只留一条
    seen = set()
    unique = []
    for item in entries:
        key = (item["file"], item["original"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique, stats


def fill_existing(entries, game_dir):
    """把游戏里已有的中文 tl 译文填进条目（只读，用于对比/补译）"""
    try:
        table = i18n.extract_translations(game_dir)
    except Exception:
        return 0
    count = 0
    for item in entries:
        new = table.get(item["original"])
        if new and new != item["original"]:
            item["translation"] = new
            item["status"] = "已有"
            count += 1
    return count


# ----------------------------------------------------------------------
# 写入
# ----------------------------------------------------------------------
def escape_rpy(value):
    text = (value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t"))
    try:
        ast.literal_eval('"' + text + '"')
    except (SyntaxError, ValueError) as exc:
        raise HanhuaError("无法生成合法的 Ren'Py 字符串：%s" % exc)
    return text


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def generate(entries, game_dir, language=LANGUAGE, font_path="", force_default=True,
             progress=None, chunk_size=4000, stats=None):
    """把条目里的译文写成 tl 目录，返回写入的文件列表

    stats 传入 dict 时会填 safe / fixed / rejected 三个计数，供界面提示。
    """
    try:
        registered = _registered_old_strings(game_dir, language)
    except Exception:
        registered = set()

    pairs = []
    seen = set()
    skipped = 0
    fixed = 0
    rejected = 0
    for item in entries:
        original = item.get("original", "")
        translation = (item.get("translation") or "").strip()
        if not original or not translation or original == translation:
            continue
        # 插值变量与文本标签必须先过安全检查，否则会让游戏渲染报错
        translation, state = sanitize_translation(original, translation)
        if state == "reject":
            rejected += 1
            item["status"] = "占位符不一致"
            continue
        if state == "fixed":
            fixed += 1
            item["translation"] = translation
        if original in seen:
            continue
        # Ren'Py 对同一语言重复注册同一个 old 会直接抛异常：
        # Exception: A translation for "..." already exists at game/tl/chinese/xxx.rpy
        # 所以只要游戏自带的 tl 里已有该原文，就必须跳过，不能覆盖。
        if original in registered:
            skipped += 1
            continue
        seen.add(original)
        pairs.append((escape_rpy(original), escape_rpy(translation)))

    if stats is not None:
        stats["fixed"] = fixed
        stats["rejected"] = rejected
        stats["written"] = len(pairs)
        stats["skipped"] = skipped

    if not pairs:
        if rejected:
            raise HanhuaError("%d 条译文的占位符/标签与原文不一致，已全部拦下，请修正后再生成" % rejected)
        if skipped:
            raise HanhuaError("所有译文已存在于游戏的中文 tl 中，无需重复写入")
        raise HanhuaError("没有可写入的译文（请先翻译或导入）")

    tl_dir = os.path.join(game_dir, "tl", language)
    os.makedirs(tl_dir, exist_ok=True)

    written = []
    groups = list(_chunks(pairs, chunk_size))
    for index, group in enumerate(groups, 1):
        path = os.path.join(tl_dir, "%sstrings_%d.rpy" % (TL_PREFIX, index))
        lines = ["# 由 小乐修改器 生成，可整目录删除", "translate %s strings:" % language, ""]
        for old, new in group:
            lines.append('    old "%s"' % old)
            lines.append('    new "%s"' % new)
            lines.append("")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))
        written.append(path)
        if progress:
            progress("写入 %s（%d 条）" % (os.path.basename(path), len(group)))

    written.append(_write_style(game_dir, tl_dir, language, font_path))
    if force_default:
        written.append(_write_default(game_dir, language))
    return written


def _write_style(game_dir, tl_dir, language, font_path):
    font_name = ""
    if font_path and os.path.isfile(font_path):
        target_dir = os.path.join(game_dir, FONT_DIRNAME)
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(font_path)[1].lower()
        font_name = "%sfont%s" % (PREFIX, ext)
        target = os.path.join(target_dir, font_name)
        try:
            if os.path.abspath(font_path) != os.path.abspath(target):
                shutil.copyfile(font_path, target)
        except OSError as exc:
            raise HanhuaError("字体复制失败：%s" % exc)
        # .ttc 默认加载第 0 个 face，写路径即可；"索引@路径" 会让 lint 判定文件不可加载
        font_name = "%s/%s" % (FONT_DIRNAME, font_name)

    lines = ["# 由 小乐修改器 生成：中文字体与排版", ""]
    if font_name:
        # 老版本 Ren'Py 可能没有 gui 模块，整块 try 住，失败也不影响启动
        lines.extend([
            "translate %s python:" % language,
            "    try:",
            '        gui.text_font = "%s"' % font_name,
            '        gui.name_text_font = "%s"' % font_name,
            '        gui.interface_text_font = "%s"' % font_name,
            '        gui.button_text_font = "%s"' % font_name,
            '        gui.choice_button_text_font = "%s"' % font_name,
            '        gui.system_font = "%s"' % font_name,
            "    except Exception:",
            "        pass",
            "",
        ])
        # 没有 gui 的老游戏靠样式兜底
        lines.extend([
            "translate %s style say_dialogue:" % language,
            '    font "%s"' % font_name,
            "",
            "translate %s style choice_button_text:" % language,
            '    font "%s"' % font_name,
            "",
        ])
    lines.extend([
        "translate %s style default:" % language,
        '    language "eastasian"',
        "",
    ])
    path = os.path.join(tl_dir, STYLE_FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    return path


def _write_default(game_dir, language):
    path = os.path.join(game_dir, DEFAULT_FILE)
    content = "\n".join([
        "# 由 小乐修改器 生成：首次启动切到中文，之后尊重玩家选择",
        "init 999 python:",
        "    try:",
        "        if not getattr(persistent, 'xl_lang_inited', False):",
        "            persistent.xl_lang_inited = True",
        "",
        "            def _xl_force_language():",
        "                try:",
        '                    renpy.change_language("%s")' % language,
        "                except Exception:",
        "                    pass",
        "",
        "            config.start_callbacks.append(_xl_force_language)",
        "    except Exception:",
        "        pass",
        "",
    ])
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return path


def remove(game_dir, language=LANGUAGE):
    """删除本工具生成的产物，返回删除的文件数"""
    removed = 0
    tl_dir = os.path.join(game_dir, "tl", language)
    if os.path.isdir(tl_dir):
        for name in os.listdir(tl_dir):
            if name.startswith(TL_PREFIX):
                try:
                    os.remove(os.path.join(tl_dir, name))
                    removed += 1
                except OSError:
                    pass
        try:
            if not os.listdir(tl_dir):
                os.rmdir(tl_dir)
        except OSError:
            pass
    for name in (DEFAULT_FILE,):
        path = os.path.join(game_dir, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    font_dir = os.path.join(game_dir, FONT_DIRNAME)
    if os.path.isdir(font_dir):
        for name in os.listdir(font_dir):
            if name.startswith(PREFIX + "font"):
                try:
                    os.remove(os.path.join(font_dir, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def generated_files(game_dir, language=LANGUAGE):
    result = []
    tl_dir = os.path.join(game_dir, "tl", language)
    if os.path.isdir(tl_dir):
        for name in sorted(os.listdir(tl_dir)):
            if name.startswith(TL_PREFIX):
                result.append(os.path.join(tl_dir, name))
    default = os.path.join(game_dir, DEFAULT_FILE)
    if os.path.isfile(default):
        result.append(default)
    return result


# ----------------------------------------------------------------------
# CSV / TSV
# ----------------------------------------------------------------------
CSV_HEADER = ["file", "line", "kind", "character", "original", "translation", "status"]


def export_table(path, entries):
    import csv
    delimiter = "\t" if path.lower().endswith(".tsv") else ","
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(CSV_HEADER)
        for item in entries:
            writer.writerow([item.get("file", ""), item.get("line", 0), item.get("kind", ""),
                             item.get("character", ""), item.get("original", ""),
                             item.get("translation", ""), item.get("status", "")])
    return len(entries)


def import_table(path, entries):
    """按 original 匹配回填，返回匹配条数"""
    import csv
    delimiter = "\t" if path.lower().endswith(".tsv") else ","
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        rows = list(reader)
    by_original = {}
    for row in rows:
        original = (row.get("original") or "").strip()
        translation = (row.get("translation") or "").strip()
        if original and translation:
            by_original.setdefault(original, (translation, (row.get("status") or "").strip()))

    count = 0
    for item in entries:
        found = by_original.get(item["original"])
        if found:
            item["translation"], item["status"] = found
            count += 1
    return count


# ----------------------------------------------------------------------
# 占位符保护
# ----------------------------------------------------------------------
_TAG_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]|\\[ntr\"\\]|%%")


def protect(text):
    slots = []
    def repl(match):
        slots.append(match.group(0))
        return "\u27e6%d\u27e7" % (len(slots) - 1)
    return _TAG_RE.sub(repl, text), slots


def restore(text, slots):
    def repl(match):
        index = int(match.group(1))
        return slots[index] if 0 <= index < len(slots) else match.group(0)
    return re.sub(r"\u27e6(\d+)\u27e7", repl, text)


def check_placeholders(source, translated):
    return sorted(_TAG_RE.findall(source)) == sorted(_TAG_RE.findall(translated))


# % 格式化占位符：少一个会在运行期 TypeError，多一个会 ValueError
_PERCENT_RE = re.compile(r"%\([^)]+\)[sdifr]|%[sdifr%]")


def _scan_tokens(text):
    """按 Ren'Py 语法扫出 [插值] 与 {文本标签}，跳过 [[ 和 {{ 转义"""
    tokens = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "{" and not text.startswith("{{", index):
            end = text.find("}", index + 1)
            if end != -1:
                tokens.append(text[index:end + 1])
                index = end + 1
                continue
        elif char == "[" and not text.startswith("[[", index):
            end = text.find("]", index + 1)
            if end != -1:
                tokens.append(text[index:end + 1])
                index = end + 1
                continue
        index += 1
    return tokens


def _strip_tags(text):
    """删掉所有 {文本标签}，保留 {{ 转义"""
    parts = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "{" and not text.startswith("{{", index):
            end = text.find("}", index + 1)
            if end != -1:
                index = end + 1
                continue
        parts.append(char)
        index += 1
    return "".join(parts)


def _count_tokens(tokens):
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _tag_pairs(tokens):
    """把标签序列配成 (开标签, 闭标签) 对，未闭合的开标签闭标签留空"""
    pairs = []
    stack = []
    for token in tokens:
        if not token.startswith("{"):
            continue
        if token.startswith("{/"):
            name = token[2:-1]
            for position in range(len(stack) - 1, -1, -1):
                if stack[position][0] == name:
                    pairs.append((stack[position][1], token))
                    del stack[position:]
                    break
        else:
            name = token[1:-1].split("=")[0]
            stack.append((name, token))
    for _name, token in stack:
        pairs.append((token, ""))
    return pairs


def _edge_tags(text):
    """原文开头 / 结尾连续的标签（HUD 这类 {vspace}{font}…文本…{/font} 结构）"""
    prefix = []
    index = 0
    while index < len(text):
        if text[index] == "{" and not text.startswith("{{", index):
            end = text.find("}", index + 1)
            if end != -1:
                prefix.append(text[index:end + 1])
                index = end + 1
                continue
        break
    suffix = []
    index = len(text)
    while index > 0:
        start = text.rfind("{", 0, index)
        if start == -1 or text.startswith("{{", start):
            break
        end = text.find("}", start + 1)
        if end != index - 1:
            break
        suffix.insert(0, text[start:end + 1])
        index = start
    return prefix, suffix


def sanitize_translation(original, translated):
    """把译文修成 Ren'Py 能安全渲染的样子，返回 (译文, 状态)

    状态：ok（原样可用）/ fixed（已修复）/ reject（不安全，回退原文）

    修的三件事：
    1. 译文里出现原文没有的 [变量] → 删掉。游戏渲染时会拿它查变量，
       查不到直接抛异常卡住对话。
    2. 译文丢掉原文的 [变量] → 按原文顺序补回，避免文本缺数据。
    3. {标签} 只允许原文出现过的，避免引用不存在的字体/样式文件；
       原文是「前缀标签 + 正文 + 后缀标签」结构时按骨架重建，保证配对。
    """
    if not translated or translated == original:
        return translated, "ok"

    # %s / %(name)s 数量对不上会在格式化阶段直接报错，修补不了，只能回退
    if sorted(_PERCENT_RE.findall(original)) != sorted(_PERCENT_RE.findall(translated)):
        return original, "reject"

    if _scan_tokens(original) == _scan_tokens(translated):
        return translated, "ok"

    original_tokens = _scan_tokens(original)
    original_interps = [t for t in original_tokens if t.startswith("[")]
    allowed_tags = {t for t in original_tokens if t.startswith("{")}

    # 第一步：白名单过滤译文里的标签和插值 —— 原文没有的一律删掉
    kept = []
    index = 0
    while index < len(translated):
        char = translated[index]
        if char == "{" and not translated.startswith("{{", index):
            end = translated.find("}", index + 1)
            if end != -1:
                token = translated[index:end + 1]
                if token in allowed_tags:
                    kept.append(token)
                index = end + 1
                continue
        elif char == "[" and not translated.startswith("[[", index):
            end = translated.find("]", index + 1)
            if end != -1:
                token = translated[index:end + 1]
                if token in original_interps:
                    kept.append(token)
                index = end + 1
                continue
        kept.append(char)
        index += 1
    filtered = "".join(kept)

    # 第二步：补回被译文丢掉的插值（按原文顺序追加，缺数据但不报错）
    have = _count_tokens([t for t in _scan_tokens(filtered) if t.startswith("[")])
    missing = []
    for token in original_interps:
        count = have.get(token, 0)
        if count < 1:
            missing.append(token)
        else:
            have[token] = count - 1

    prefix, suffix = _edge_tags(original)
    if prefix or suffix:
        # 骨架可靠：只用原文的标签顺序，正文换成译文，杜绝错误嵌套；
        # 夹在正文中间的标签（{size=28}…{/size}、{i}…{/i}）成对包回正文，
        # 宁可整句套样式，也不能把标签弄丢
        body = _strip_tags(filtered).strip()
        stop = len(original_tokens) - len(suffix) if suffix else len(original_tokens)
        middle = original_tokens[len(prefix):stop]
        pairs = _tag_pairs(middle)
        opens = "".join(pair[0] for pair in pairs)
        closes = "".join(pair[1] for pair in reversed(pairs))
        return "".join(prefix) + opens + body + "".join(missing) + closes + "".join(suffix), "fixed"

    # 结构未知：把原文里的成对标签还原成“包住整句”，保证标签一个不丢
    body = _strip_tags(filtered).strip()
    if missing:
        body = (body + " " + "".join(missing)).strip()
    pairs = _tag_pairs(original_tokens)
    if not pairs:
        return body, "fixed"
    opens = "".join(pair[0] for pair in pairs)
    closes = "".join(pair[1] for pair in reversed(pairs))
    return opens + body + closes, "fixed"


# ----------------------------------------------------------------------
# 在线翻译（OpenAI 兼容接口）
# ----------------------------------------------------------------------
def translate_entries(entries, api, progress=None, should_stop=None, batch_size=16):
    """用 OpenAI 兼容接口批量翻译，返回成功条数

    api: {base_url, api_key, model, target}
    """
    base = (api.get("base_url") or "").rstrip("/")
    if not base:
        raise HanhuaError("未配置接口地址")
    if not base.endswith("/chat/completions"):
        base += "/chat/completions"

    model = api.get("model") or "deepseek-ai/DeepSeek-V3"
    target = api.get("target") or "简体中文"
    key = api.get("api_key") or ""

    pending = [item for item in entries
               if item.get("original") and not (item.get("translation") or "").strip()]
    if not pending:
        return 0

    ok = 0
    total = len(pending)
    for start in range(0, total, batch_size):
        if should_stop and should_stop():
            break
        batch = pending[start:start + batch_size]
        protected = []
        slots_map = []
        for item in batch:
            text, slots = protect(item["original"])
            protected.append(text)
            slots_map.append(slots)

        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system",
                 "content": ("你是视觉小说本地化译者。把用户给出的每一行英文译成%s。"
                             "严格输出 JSON 字符串数组，长度与输入一致；"
                             "保留 \\u27e6数字\\u27e7 这样的占位符，不要翻译或删除；"
                             "不要输出解释。") % target},
                {"role": "user", "content": json.dumps(protected, ensure_ascii=False)},
            ],
        }
        try:
            answer = _post_json(base, key, payload)
            results = _parse_translation_payload(answer, len(batch))
        except Exception as exc:
            if progress:
                progress("批次失败：%s" % exc)
            continue

        for item, slots, text in zip(batch, slots_map, results):
            if not text:
                continue
            restored = restore(text, slots)
            if not check_placeholders(item["original"], restored):
                item["status"] = "占位符不一致"
                continue
            item["translation"] = restored
            item["status"] = "机翻"
            ok += 1
        if progress:
            progress("已翻译 %d / %d" % (min(start + batch_size, total), total))
    return ok


def _post_json(url, key, payload, timeout=60):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise HanhuaError("HTTP %s：%s" % (exc.code, detail))
    except urllib.error.URLError as exc:
        raise HanhuaError("网络不可用：%s" % exc.reason)


def _parse_translation_payload(raw, expected):
    data = json.loads(raw)
    content = ""
    if isinstance(data, dict):
        choices = data.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
    if not content:
        raise HanhuaError("接口返回中没有译文")

    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", content, re.S)
    if fence:
        content = fence.group(1).strip()
    try:
        items = json.loads(content)
        if isinstance(items, list):
            return [str(x) for x in items][:expected] + [""] * max(0, expected - len(items))
    except ValueError:
        pass
    lines = [line.strip().strip('",') for line in content.splitlines() if line.strip()]
    return (lines + [""] * expected)[:expected]


# ----------------------------------------------------------------------
# 字体探测
# ----------------------------------------------------------------------
def find_font():
    """在常见位置找一个含中文的字体"""
    candidates = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyhbd.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simhei.ttf"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simkai.ttf"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""
