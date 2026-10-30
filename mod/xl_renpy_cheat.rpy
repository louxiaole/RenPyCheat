# ============================================================================
# 小乐 · Ren'Py 实时修改器 —— 注入模块
# ----------------------------------------------------------------------------
# 本文件由「游戏修改器」工具安装到游戏的 game 目录，随游戏启动在进程内运行。
# 它在游戏内部启动一个仅监听 127.0.0.1 的调试通道，外部工具通过该通道
# 实时读取 / 修改存档变量、持久化变量，并支持数值搜索与数值锁定（类似 CE）。
#
# 卸载请使用工具：直接删 .rpy 可能残留 .rpyc 缓存。
#
# 两个必须遵守的约束（踩过的坑）：
# 1. Ren'Py store 里的 `renpy` 指向 renpy.exports（公共 API），不是 renpy 包。
#    绝对不能 import renpy，否则会覆盖该名字，导致引擎自身的
#    `renpy.Displayable` 等调用失效、游戏启动即崩溃。
# 2. Ren'Py store 里的 `dict` / `list` / `set` / `tuple` 被替换成了
#    renpy.revertable 的 Revertable* 类型，不是内建类型。因此模块内部
#    一律使用 xl_ 前缀的内建别名，否则 isinstance/dict() 判断会全部失效。
#
# 所有符号统一加 xl_cheat_ 前缀，避免污染游戏全局变量。
# ============================================================================

init -100 python:
    import os as xl_cheat_os
    import io as xl_cheat_io
    import sys as xl_cheat_sys
    import time as xl_cheat_time
    import json as xl_cheat_json
    import types as xl_cheat_types
    import socket as xl_cheat_socket
    import threading as xl_cheat_threading

    # Ren'Py 7 是 Python 2，没有 builtins 模块；且这里的 __builtins__ 可能是 dict。
    try:
        import builtins as xl_cheat_builtins
    except Exception:
        xl_cheat_builtins = None
    if xl_cheat_builtins is None:
        try:
            import __builtin__ as xl_cheat_builtins
        except Exception:
            xl_cheat_builtins = __builtins__

    def xl_cheat_builtin(name, default=None):
        """__builtins__ 在不同环境下可能是 module 也可能是 dict，两种都取"""
        table = xl_cheat_builtins
        if table is None:
            return default
        try:
            return table[name]
        except Exception:
            pass
        try:
            return xl_getattr_raw(table, name)
        except Exception:
            return default

    def xl_getattr_raw(obj, name):
        return object.__getattribute__(obj, name)

    try:
        import ast as xl_cheat_ast
    except Exception:
        xl_cheat_ast = None

    # ---- 内建类型别名（store 里的同名变量已被 Ren'Py 替换，不能用）----
    xl_isinstance = xl_cheat_builtin("isinstance")
    xl_getattr = xl_cheat_builtin("getattr")
    xl_setattr = xl_cheat_builtin("setattr")
    xl_hasattr = xl_cheat_builtin("hasattr")
    xl_callable = xl_cheat_builtin("callable")
    xl_type = xl_cheat_builtin("type")
    xl_len = xl_cheat_builtin("len")
    xl_id = xl_cheat_builtin("id")
    xl_vars = xl_cheat_builtin("vars")
    xl_repr = xl_cheat_builtin("repr")
    xl_sorted = xl_cheat_builtin("sorted")
    xl_dir = xl_cheat_builtin("dir")
    xl_min = xl_cheat_builtin("min")
    xl_abs = xl_cheat_builtin("abs")
    xl_range = xl_cheat_builtin("range")
    xl_int = xl_cheat_builtin("int")
    xl_float = xl_cheat_builtin("float")
    xl_bool = xl_cheat_builtin("bool")
    xl_dict_type = xl_cheat_builtin("dict")
    xl_list_type = xl_cheat_builtin("list")
    xl_tuple_type = xl_cheat_builtin("tuple")
    xl_set_type = xl_cheat_builtin("set")

    # Python 2 下优先用 unicode，保证中文/韩文不乱码
    xl_cheat_str_type = xl_cheat_builtin("unicode", xl_cheat_builtin("str"))
    # Python 2 里普通的 str 是字节串，字典键 / 对象字段名几乎都是它；漏掉它
    # 会让整片名称判断失效。
    #
    # 坑：Ren'Py 7 的 store 里 `str` 已被换成 BaseNewStr（unicode 子类），
    # 连 __builtin__ 里的 str 也被替换过，`type("")` 同样是 BaseNewStr。
    # 真正的字节 str 只能从引擎返回值上取 —— os.sep 在 Py2 永远是字节串。
    xl_cheat_text_types = (xl_cheat_str_type,)
    for xl_cheat_candidate in (xl_cheat_builtin("str"), xl_type(""),
                               xl_type(xl_cheat_os.sep)):
        if xl_cheat_candidate not in xl_cheat_text_types:
            xl_cheat_text_types = xl_cheat_text_types + (xl_cheat_candidate,)

    xl_cheat_long_type = xl_int

    XL_CHEAT_VERSION = 52
    XL_CHEAT_MARKER = "xl_renpy_cheat"

    # 冻结表：变量路径 -> 被锁定的值
    xl_cheat_frozen = {}
    # 主线程任务队列（网络线程投递，主线程执行）
    xl_cheat_queue = []
    # 数值搜索的上一次命中列表
    xl_cheat_scan_hits = []
    # 游戏端日志
    xl_cheat_logs = []
    xl_cheat_last_freeze = 0.0

    def xl_cheat_dbg(msg):
        # 诊断日志：只有 game 目录里存在 xl_cheat_debug 开关文件时才写，
        # 平时不会往游戏目录塞日志。需要排查启动问题时手动建该文件即可。
        try:
            gamedir = xl_cheat_conf("gamedir", "")
            if not gamedir:
                return
            if not xl_cheat_os.path.exists(xl_cheat_os.path.join(gamedir, "xl_cheat_debug")):
                return
            text = xl_cheat_text_safe(msg)
            if text is None:
                text = xl_cheat_str_type(xl_repr(msg))
            handle = xl_cheat_io.open(
                xl_cheat_os.path.join(gamedir, "xl_cheat_debug.log"), "a", encoding="utf-8")
            handle.write(xl_cheat_time.strftime("%H:%M:%S ") + text + "\n")
            handle.close()
        except Exception:
            pass

    def xl_cheat_log(msg):
        try:
            entry = "[%s] %s" % (xl_cheat_time.strftime("%H:%M:%S"), msg)
            xl_cheat_logs.append(entry)
            if xl_len(xl_cheat_logs) > 300:
                del xl_cheat_logs[0:xl_len(xl_cheat_logs) - 300]
        except Exception:
            pass
        xl_cheat_dbg(msg)

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
    def xl_cheat_store_dict():
        """返回 store 命名空间字典（游戏脚本里的全局变量都在这里）"""
        try:
            import renpy.python as xl_cheat_python_module
            return xl_cheat_python_module.store_dicts["store"]
        except Exception:
            pass
        try:
            return renpy.store.__dict__
        except Exception:
            return {}

    def xl_cheat_conf(attr, default=None):
        """安全读取 config 属性（renpy.config 为模块级变量）"""
        try:
            import renpy.config as xl_cheat_config_module
            if xl_hasattr(xl_cheat_config_module, attr):
                return xl_getattr(xl_cheat_config_module, attr)
        except Exception:
            pass
        try:
            if xl_hasattr(renpy, "config") and xl_hasattr(renpy.config, attr):
                return xl_getattr(renpy.config, attr)
        except Exception:
            pass
        try:
            module_config = globals().get("config")
            if module_config is not None and xl_hasattr(module_config, attr):
                return xl_getattr(module_config, attr)
        except Exception:
            pass
        return default

    def xl_cheat_persistent():
        """返回 persistent 对象（跨存档保存的数据）"""
        try:
            import renpy.game as xl_cheat_game_module
            return xl_cheat_game_module.persistent
        except Exception:
            pass
        try:
            return persistent
        except Exception:
            return None

    def xl_cheat_is_number(value):
        if xl_isinstance(value, xl_bool):
            return True
        if xl_isinstance(value, xl_float):
            return True
        return xl_isinstance(value, xl_cheat_long_type)

    def xl_cheat_type_name(value):
        if xl_isinstance(value, xl_bool):
            return "bool"
        if xl_isinstance(value, xl_cheat_text_types):
            return "str"
        if xl_isinstance(value, xl_float):
            return "float"
        if xl_isinstance(value, xl_cheat_long_type):
            return "int"
        if xl_isinstance(value, xl_dict_type):
            return "dict"
        if xl_isinstance(value, xl_list_type):
            return "list"
        if xl_isinstance(value, xl_tuple_type):
            return "tuple"
        if xl_isinstance(value, xl_set_type):
            return "set"
        if value is None:
            return "None"
        if xl_hasattr(value, "__dict__") and not xl_isinstance(value, xl_type):
            return "obj:" + xl_type(value).__name__
        return xl_type(value).__name__

    def xl_cheat_describe(value, limit=200):
        try:
            if xl_isinstance(value, xl_bool):
                return "True" if value else "False"
            if xl_isinstance(value, xl_cheat_text_types):
                if xl_len(value) > limit:
                    return value[:limit] + "..."
                return value
            if xl_cheat_is_number(value):
                return xl_cheat_str_type(value)
            if value is None:
                return "None"
            text = xl_repr(value)
            if xl_len(text) > limit:
                return text[:limit] + "..."
            return text
        except Exception:
            return "<无法显示>"

    def xl_cheat_is_container(value):
        return (xl_isinstance(value, xl_dict_type) or xl_isinstance(value, xl_list_type)
                or xl_isinstance(value, xl_tuple_type) or xl_isinstance(value, xl_set_type))

    def xl_cheat_text_safe(value):
        # 游戏文本可能是非 UTF-8 的 bytes（cp1252 之类）。直接塞进 JSON 会让
        # 整个响应变成非法 UTF-8，客户端连整包都解析不出来，所以统一转成
        # unicode，坏字节用替换字符兜底。
        #
        # 坑：这个游戏的 Python 2.7 里 unicode(bytes, "utf-8") 走 strict 解码，
        # 遇到非法字节时会在 C 层直接把进程带崩（0xc0000005，且不抛异常），
        # 只能改用 decode("utf-8", "replace") 的容错路径。
        if not xl_isinstance(value, xl_cheat_text_types):
            return None
        try:
            if xl_isinstance(value, xl_cheat_str_type):
                return value
        except Exception:
            pass
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            pass
        try:
            return xl_cheat_str_type(xl_repr(value))
        except Exception:
            return xl_cheat_str_type("?")

    def xl_cheat_payload_safe(value, depth=0):
        # 递归清洗即将序列化的返回值，避免个别脏字节毁掉整条响应
        if depth > 12:
            return None
        if value is None or value is True or value is False:
            return value
        if xl_cheat_is_number(value):
            return value
        text = xl_cheat_text_safe(value)
        if text is not None:
            return text
        if xl_isinstance(value, xl_dict_type):
            out = {}
            for key, item in value.items():
                out[xl_cheat_payload_safe(key, depth + 1)] = xl_cheat_payload_safe(item, depth + 1)
            return out
        if xl_isinstance(value, (xl_list_type, xl_tuple_type, xl_set_type)):
            return [xl_cheat_payload_safe(item, depth + 1) for item in value]
        try:
            return xl_cheat_text_safe(xl_repr(value))
        except Exception:
            return None

    def xl_cheat_editable(value):
        if xl_cheat_is_container(value):
            return False
        return xl_isinstance(value, xl_bool) or xl_cheat_is_number(value) or xl_isinstance(
            value, xl_cheat_text_types
        )

    def xl_cheat_engine_object(value):
        """renpy. 模块里的对象一律当引擎噪音

        Partial / Displayable / Transition 这些对象的属性又深又多，
        既不是玩家数据，还会把扫描预算吃光，导致真正的存档变量漏掉。
        """
        try:
            module = xl_cheat_str_type(value.__class__.__module__ or "")
        except Exception:
            return False
        return module.startswith("renpy.") or module.startswith("__")

    def xl_cheat_visible_name(name, value, show_objects=False):
        """过滤掉引擎内部变量、函数、模块、角色对象等噪音"""
        low = name.lower()
        if name.startswith("_") or name.startswith("__"):
            return False
        if low.startswith("xl_cheat") or low.startswith("xl_"):
            return False
        if xl_isinstance(value, xl_cheat_types.ModuleType):
            return False
        if xl_isinstance(value, xl_cheat_types.FunctionType):
            return False
        if xl_isinstance(value, xl_type):
            return False
        # 有些游戏的数据对象实现了 __call__（GameData 这类），
        # 一刀切按 callable 过滤会把整个存档对象表一起丢掉
        if xl_callable(value) and not (show_objects and xl_hasattr(value, "__dict__")):
            return False
        if xl_cheat_is_container(value):
            return True
        if xl_cheat_is_number(value) or xl_isinstance(value, xl_cheat_text_types) or value is None:
            return True
        if xl_cheat_engine_object(value):
            return False
        if show_objects and xl_hasattr(value, "__dict__"):
            return True
        return False

    # ------------------------------------------------------------------
    # 路径解析：支持 a.b.c、列表下标、persistent.xxx
    # ------------------------------------------------------------------
    def xl_cheat_split(path):
        if path.startswith("persistent."):
            return True, path[len("persistent."):].split(".")
        return False, path.split(".")

    def xl_cheat_step(obj, key):
        if xl_isinstance(obj, xl_dict_type):
            try:
                return obj[key]
            except Exception:
                pass
            # 存档里常用整数键（ObjectsList[5] 这类），而路径是字符串
            for xl_cheat_conv in (xl_int, xl_float):
                try:
                    xl_cheat_alt = xl_cheat_conv(key)
                except Exception:
                    continue
                try:
                    if xl_cheat_alt in obj:
                        return obj[xl_cheat_alt]
                except Exception:
                    continue
            raise KeyError(key)
        if xl_isinstance(obj, (xl_list_type, xl_tuple_type)):
            return obj[xl_int(key)]
        # 兜底：支持带 __getitem__ 的映射类
        if xl_hasattr(obj, "__getitem__") and xl_hasattr(obj, "__contains__"):
            try:
                if key in obj:
                    return obj[key]
            except Exception:
                pass
        return xl_getattr(obj, key)

    def xl_cheat_default_dict():
        """default store：脚本里 default 声明的变量。
        主菜单还没进游戏时，游戏变量都在这里，普通 store 只有引擎变量。"""
        try:
            import renpy.python as xl_cheat_python_default
            return xl_cheat_python_default.store_dicts["default"]
        except Exception:
            return {}

    def xl_cheat_parent(path):
        is_persistent, parts = xl_cheat_split(path)
        parts = [part for part in parts if part != ""]
        if not parts:
            raise ValueError("变量路径为空")
        obj = xl_cheat_persistent() if is_persistent else xl_cheat_store_dict()
        if not is_persistent and path.startswith("default."):
            obj = xl_cheat_default_dict()
            parts = parts[1:]
            if not parts:
                raise ValueError("变量路径为空")
        if obj is None:
            raise ValueError("无法访问 persistent 数据")
        for part in parts[:-1]:
            obj = xl_cheat_step(obj, part)
        return obj, parts[-1]

    def xl_cheat_get(path):
        parent, key = xl_cheat_parent(path)
        return xl_cheat_step(parent, key)

    def xl_cheat_set(path, value):
        parent, key = xl_cheat_parent(path)
        # 列表必须先判断：list 同时有 __setitem__/__contains__，走下面那句
        # 会被当成字典用字符串下标，报 "list indices must be integers"。
        if xl_isinstance(parent, xl_list_type):
            parent[xl_int(key)] = value
        elif xl_isinstance(parent, xl_dict_type) or (
            xl_hasattr(parent, "__setitem__") and xl_hasattr(parent, "__contains__")
        ):
            parent[key] = value
        else:
            xl_setattr(parent, key, value)

    def xl_cheat_parse(text, old, forced_type=None):
        """把界面输入的文本转换成与旧值同类型的数据"""
        kind = forced_type or "auto"
        text = text if xl_isinstance(text, xl_cheat_text_types) else xl_cheat_str_type(text)

        if kind == "str":
            return text
        if kind == "bool":
            return text.strip().lower() in ("1", "true", "yes", "on", "是", "开")
        if kind == "int":
            try:
                return xl_int(text)
            except Exception:
                return xl_int(xl_float(text))
        if kind == "float":
            return xl_float(text)
        if kind in ("list", "tuple", "set", "dict"):
            value = xl_cheat_ast.literal_eval(text)
            if kind == "tuple":
                return xl_tuple_type(value)
            if kind == "set":
                return xl_set_type(value)
            if kind == "dict":
                return xl_dict_type(value)
            return xl_list_type(value)

        if xl_isinstance(old, xl_bool):
            return text.strip().lower() in ("1", "true", "yes", "on", "是", "开")
        if xl_isinstance(old, xl_cheat_text_types):
            return text
        if xl_cheat_is_number(old):
            if xl_isinstance(old, xl_float):
                return xl_float(text)
            try:
                return xl_int(text)
            except Exception:
                return xl_int(xl_float(text))
        if old is None:
            stripped = text.strip()
            if stripped in ("", "None", "null"):
                return None
            try:
                return xl_cheat_ast.literal_eval(stripped)
            except Exception:
                return text
        raise ValueError("该变量不是基础类型，请编辑它下面的具体属性路径")

    # ------------------------------------------------------------------
    # 数值搜索（CE 风格：首次扫描 + 再次扫描）
    # ------------------------------------------------------------------
    def xl_cheat_parse_target(text):
        text = text.strip()
        try:
            return ("num", xl_float(xl_int(text)))
        except Exception:
            pass
        try:
            return ("num", xl_float(text))
        except Exception:
            pass
        return ("str", text)

    def xl_cheat_matches(value, target):
        if target[0] == "num":
            if not xl_cheat_is_number(value):
                return False
            try:
                return xl_abs(xl_float(value) - target[1]) < 1e-6
            except Exception:
                return False
        return xl_isinstance(value, xl_cheat_text_types) and value == target[1]

    def xl_cheat_scan(target, mode):
        """首次扫描递归进入字典/列表/对象（深度 3）；再次扫描只过滤上次命中"""
        global xl_cheat_scan_hits

        if mode == "reset":
            xl_cheat_scan_hits = []
            return []

        if mode == "next":
            hits = []
            for path in xl_list_type(xl_cheat_scan_hits):
                try:
                    if xl_cheat_matches(xl_cheat_get(path), target):
                        hits.append(path)
                except Exception:
                    pass
            xl_cheat_scan_hits = hits
            return hits

        skip_names = ("renpy", "store", "config", "persistent", "ui", "gui",
                      "default_store", "renpy_version")
        budget = {"nodes": 0}
        deadline = xl_cheat_time.time() + 6.0
        seen = set()
        hits = []

        def walk(path, value, depth):
            # 属性识别能看到的「看法 / 魅力」在 Relations.data.N.opinion.Value，
            # 这类值要下钻 4 层才能拿到；旧的深度 3 直接把它们挡在外面，
            # 于是出现了「属性页识别得到、数值搜索查不到」。
            if budget["nodes"] > 160000 or xl_len(hits) > 6000:
                return
            budget["nodes"] += 1
            if xl_cheat_time.time() > deadline:
                return

            if xl_isinstance(value, xl_cheat_types.ModuleType):
                return
            if xl_isinstance(value, xl_type):
                return
            if not xl_cheat_is_container(value) and xl_callable(value):
                return

            if xl_cheat_matches(value, target):
                hits.append(path)
                return

            if depth >= 5:
                return

            # 数值壳：DynamicValue / DynamicVar 之类的对象，真正的数在 .Value 上，
            # 而且 Value 可能是 property（不在 vars() 里），必须用 getattr 单独取。
            value_in_vars = False
            if xl_hasattr(value, "__dict__"):
                try:
                    value_in_vars = "Value" in xl_vars(value)
                except Exception:
                    value_in_vars = False
            if not value_in_vars and xl_hasattr(value, "Value"):
                try:
                    inner = xl_getattr(value, "Value")
                except Exception:
                    inner = None
                if inner is not None and xl_cheat_scalar(inner):
                    walk(path + ".Value", inner, depth + 1)

            if xl_isinstance(value, xl_dict_type):
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for key in xl_list_type(value.keys())[:400]:
                    if not xl_isinstance(key, xl_cheat_text_types):
                        continue
                    try:
                        child = value[key]
                    except Exception:
                        continue
                    walk(path + "." + key, child, depth + 1)
            elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for index in xl_range(xl_min(xl_len(value), 400)):
                    try:
                        child = value[index]
                    except Exception:
                        continue
                    walk(path + "." + xl_cheat_str_type(index), child, depth + 1)
            elif xl_hasattr(value, "__dict__") and not xl_isinstance(value, xl_set_type):
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for key, child in xl_list_type(xl_vars(value).items())[:200]:
                    if key.startswith("_"):
                        continue
                    walk(path + "." + xl_cheat_str_type(key), child, depth + 1)

        data = xl_cheat_store_dict()
        for name in xl_list_type(data.keys()):
            if not xl_isinstance(name, xl_cheat_text_types):
                continue
            if name.startswith("_") or name.lower().startswith("xl_cheat"):
                continue
            if name in skip_names:
                continue
            try:
                value = data[name]
            except Exception:
                continue
            try:
                walk(name, value, 0)
            except Exception as error:
                xl_cheat_log("扫描异常 %s：%s: %s" % (name, xl_type(error).__name__, error))

        xl_cheat_scan_hits = hits
        return hits

    # ------------------------------------------------------------------
    # 角色识别：按角色名 / 变量名找到对应的属性集合
    # ------------------------------------------------------------------
    def xl_cheat_scalar(value):
        return (xl_cheat_is_number(value) or xl_isinstance(value, xl_cheat_text_types)
                or value is None)

    def xl_cheat_attrs(base, obj, limit=200):
        """提取对象/字典里可编辑的标量属性，返回属性路径列表"""
        attrs = []
        try:
            if xl_isinstance(obj, xl_dict_type):
                pairs = xl_list_type(obj.items())
            else:
                pairs = xl_list_type(xl_vars(obj).items())
        except Exception:
            return attrs
        for key, value in pairs[:limit]:
            if not xl_isinstance(key, xl_cheat_text_types):
                continue
            if key.startswith("_") or key.lower().startswith("xl_cheat"):
                continue
            key_text = xl_cheat_str_type(key)
            if xl_cheat_scalar(value):
                attrs.append({
                    "name": key_text,
                    "path": base + "." + key_text,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value, 80),
                })
                continue
            if xl_len(attrs) >= limit:
                break
            # 属性包在 DynamicVar 这类子对象里：Charisma.Value / opinion.Value
            if xl_hasattr(value, "Value"):
                try:
                    inner = xl_getattr(value, "Value")
                except Exception:
                    inner = None
                if xl_cheat_scalar(inner) and inner is not None:
                    attrs.append({
                        "name": key_text,
                        "path": "%s.%s.Value" % (base, key_text),
                        "type": xl_cheat_type_name(inner),
                        "value": xl_cheat_describe(inner, 80),
                    })
                    continue
            # 字典里的数值项：Interests = {"Sports": 0.5}
            if xl_isinstance(value, xl_dict_type):
                try:
                    subs = xl_list_type(value.items())[:40]
                except Exception:
                    subs = []
                added = 0
                for sub_key, sub_value in subs:
                    if added >= 20:
                        break
                    if not xl_isinstance(sub_key, xl_cheat_text_types):
                        continue
                    if not xl_cheat_is_number(sub_value):
                        continue
                    attrs.append({
                        # 带上父级名字，避免 TB_Actor.dana.real_age 与
                        # TB_Actor.diana.real_age 在列表里都只叫 real_age
                        "name": "%s.%s" % (key_text, xl_cheat_str_type(sub_key)),
                        "owner": key_text,
                        "path": "%s.%s.%s" % (
                            base, key_text, xl_cheat_str_type(sub_key)),
                        "type": xl_cheat_type_name(sub_value),
                        "value": xl_cheat_describe(sub_value, 80),
                    })
                    added += 1
        return attrs

    def xl_cheat_kind(path, value):
        """按变量前缀给出中文分类，方便区分角色 / 任务 / 地点"""
        seg = path.split(".")[0].lower()
        class_name = xl_type(value).__name__.lower()
        if "actorgrp" in seg:
            return "角色组"
        if "relationslist" in class_name or "relationslist" in seg:
            return "关系表"
        if "relation" in class_name and "list" not in class_name:
            return "关系"
        if "person" in class_name or "actor" in class_name:
            return "角色"
        if "actor" in seg or "char" in seg:
            return "角色"
        if "quest" in seg:
            return "任务"
        if "room" in seg or "map" in seg:
            return "地点"
        if "item" in seg or "inventory" in seg:
            return "物品"
        return "对象"

    def xl_cheat_explore(keyword):
        """按角色名 / 变量名找对象并列出标量属性；关键字为空时列出全部角色"""
        keyword = (keyword or "").strip().lower()
        actors_only = not keyword
        skip_names = ("renpy", "store", "config", "persistent", "ui", "gui",
                      "default_store", "renpy_version")
        budget = {"nodes": 0}
        seen = set()
        strong = []
        weak = []

        def label_of(path, value):
            for key in ("name", "Name", "char_name", "display_name", "title",
                        "label", "pKey", "Alias", "AliasStd", "FullName"):
                try:
                    if xl_isinstance(value, xl_dict_type):
                        if key not in value:
                            continue
                        text_value = value[key]
                    elif xl_hasattr(value, key):
                        text_value = xl_getattr(value, key)
                    else:
                        continue
                    if xl_isinstance(text_value, xl_cheat_text_types) and text_value.strip():
                        return xl_cheat_localize(text_value.strip())
                except Exception:
                    pass
            return path.split(".")[-1]

        def strong_hints(path, value):
            """名称类线索：路径末段、类名、显示名。命中这些才算真正的角色匹配"""
            hints = [path.split(".")[-1].lower(), xl_type(value).__name__.lower(),
                     label_of(path, value).lower()]
            return hints

        def hints_of(path, value):
            hints = [path.split(".")[-1].lower(), xl_type(value).__name__.lower()]
            try:
                if xl_isinstance(value, xl_dict_type):
                    pairs = xl_list_type(value.items())
                else:
                    pairs = xl_list_type(xl_vars(value).items())
                for key, child in pairs[:80]:
                    if xl_isinstance(key, xl_cheat_text_types):
                        hints.append(key.lower())
                    if xl_isinstance(child, xl_cheat_text_types):
                        hints.append(child.lower()[:120])
            except Exception:
                pass
            return hints

        def relation_attrs_for(person_name):
            """把关系表（Relations.data）里和这个人相关的看法 / 魅力取出来"""
            extra = []
            try:
                rels = xl_cheat_store_dict()["Relations"]
            except Exception:
                return extra
            try:
                entries = xl_list_type(xl_getattr(rels, "data"))[:300]
            except Exception:
                return extra
            surname = xl_cheat_str_type(person_name).strip().lower()
            if not surname:
                return extra
            for index in xl_range(xl_len(entries)):
                try:
                    record = entries[index]
                except Exception:
                    continue
                names = []
                for key in ("sub1", "sub2"):
                    try:
                        part = xl_getattr(record, key)
                    except Exception:
                        continue
                    if xl_isinstance(part, xl_cheat_text_types):
                        names.append(xl_cheat_str_type(part).strip().lower())
                if surname not in names:
                    continue
                rec_base = "Relations.data.%d" % index
                for field in ("opinion", "allure", "conflict"):
                    try:
                        cell = xl_getattr(record, field)
                    except Exception:
                        continue
                    value = cell
                    if xl_hasattr(cell, "Value"):
                        try:
                            value = xl_getattr(cell, "Value")
                        except Exception:
                            continue
                        extra.append({
                            "name": field,
                            "path": "%s.%s.Value" % (rec_base, field),
                            "type": xl_cheat_type_name(value),
                            "value": xl_cheat_describe(value, 80),
                        })
            return extra

        def is_record(value):
            """「一条记录」：字典 / 对象，且至少有两个标量字段"""
            if xl_isinstance(value, (xl_list_type, xl_tuple_type, xl_set_type)):
                return False
            if not xl_isinstance(value, xl_dict_type) and not (
                    xl_hasattr(value, "__dict__") and not xl_isinstance(value, xl_type)):
                return False
            try:
                if xl_isinstance(value, xl_dict_type):
                    pairs = xl_list_type(value.items())
                else:
                    pairs = xl_list_type(xl_vars(value).items())
            except Exception:
                return False
            scalars = 0
            for key, child in pairs[:40]:
                if xl_cheat_scalar(child) and child is not None:
                    scalars += 1
                    if scalars >= 2:
                        return True
            return False

        def record_children(value):
            """容器里装的是同构记录（TB_Actor.<角色> = {...}）时返回 [(名字, 记录)]"""
            try:
                if xl_isinstance(value, xl_dict_type):
                    pairs = xl_list_type(value.items())
                elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                    pairs = []
                    for index in xl_range(xl_min(xl_len(value), 80)):
                        try:
                            pairs.append((xl_cheat_str_type(index), value[index]))
                        except Exception:
                            continue
                else:
                    return []
            except Exception:
                return []
            pairs = pairs[:80]
            if xl_len(pairs) < 3:
                return []
            records = []
            for key, child in pairs:
                if not xl_isinstance(key, xl_cheat_text_types):
                    if not xl_cheat_is_number(key):
                        continue
                    key = xl_cheat_str_type(xl_int(key))
                key_text = xl_cheat_str_type(key)
                if not key_text or "." in key_text:
                    continue
                if is_record(child):
                    records.append((key_text, child))
            # 一半以上是记录才算「角色表」，避免把普通对象里的少量字典字段误拆
            if xl_len(records) < 3 or xl_len(records) * 2 < xl_len(pairs):
                return []
            return records

        def record_label(key, child):
            """记录显示名：关系记录用 sub1 ↔ sub2，角色记录优先 name 字段"""
            names = []
            for field in ("sub1", "sub2"):
                try:
                    if xl_isinstance(child, xl_dict_type):
                        part = child.get(field)
                    elif xl_hasattr(child, field):
                        part = xl_getattr(child, field)
                    else:
                        part = None
                except Exception:
                    part = None
                if xl_isinstance(part, xl_cheat_text_types) and part.strip():
                    names.append(xl_cheat_localize(part.strip()))
            if xl_len(names) == 2:
                return "%s ↔ %s" % (names[0], names[1])
            if xl_len(names) == 1:
                return names[0]
            label = label_of(key, child)
            if label and label != key:
                return label
            return key

        def walk(path, value, depth):
            if budget["nodes"] > 80000 or xl_len(strong) >= 120 or xl_len(weak) >= 120:
                return
            budget["nodes"] += 1
            if xl_isinstance(value, xl_cheat_types.ModuleType):
                return
            if xl_isinstance(value, xl_type):
                return
            if not xl_cheat_is_container(value) and xl_callable(value):
                return

            is_object = xl_isinstance(value, xl_dict_type) or (
                xl_hasattr(value, "__dict__") and not xl_isinstance(value, xl_set_type)
            )
            if is_object:
                kind = xl_cheat_kind(path, value)
                seg = path.split(".")[0].lower()
                matched_strong = False
                if actors_only:
                    # 只列出角色表里的单个角色（PersonClass / TB_Actor.xxx），排除库存/角色组
                    matched_strong = (
                        kind == "角色" and path.count(".") <= 3
                        and "inventory" not in seg and "grp" not in seg
                        and "say" not in seg and seg != "g_actor"
                        and "relation" not in seg
                    )
                else:
                    for hint in strong_hints(path, value):
                        if keyword in hint:
                            matched_strong = True
                            break
                matched_weak = False
                if not matched_strong and keyword:
                    for hint in hints_of(path, value):
                        if keyword in hint:
                            matched_weak = True
                            break

                if matched_strong or matched_weak:
                    # TB_Actor / g_characters 这类「表里套角色记录」的容器：
                    # 整体拍平会让 25 个角色的同名字段混成一堆（real_age ×25），
                    # 这里按子记录拆成多个角色条目，属性名自然带上归属。
                    records = record_children(value) if kind in ("角色", "关系") else []
                    if records:
                        for key, child in records:
                            child_path = path + "." + key
                            child_attrs = xl_cheat_attrs(child_path, child)
                            known = set(attr["path"] for attr in child_attrs)
                            for extra in relation_attrs_for(key):
                                if extra["path"] not in known:
                                    child_attrs.append(extra)
                            if not child_attrs:
                                continue
                            entry = {
                                "path": child_path,
                                "label": record_label(key, child),
                                "type": xl_cheat_type_name(child),
                                "kind": kind,
                                "score": 5 if matched_strong else 2,
                                "attrs": child_attrs,
                                "count": xl_len(child_attrs),
                            }
                            if matched_strong:
                                strong.append(entry)
                            elif not actors_only:
                                weak.append(entry)
                        if matched_strong:
                            return
                    else:
                        attrs = xl_cheat_attrs(path, value)
                        if kind in ("角色", "关系"):
                            known = set(attr["path"] for attr in attrs)
                            for extra in relation_attrs_for(path.split(".")[-1]):
                                if extra["path"] not in known:
                                    attrs.append(extra)
                        if attrs:
                            entry = {
                                "path": path,
                                "label": label_of(path, value),
                                "type": xl_cheat_type_name(value),
                                "kind": kind,
                                "score": 5 if matched_strong else 2,
                                "attrs": attrs,
                                "count": xl_len(attrs),
                            }
                            if matched_strong:
                                strong.append(entry)
                            elif not actors_only:
                                # 弱匹配容易命中翻译表、设置表这类大字典，过滤掉
                                if xl_len(attrs) <= 80 and "translat" not in path.lower():
                                    weak.append(entry)
                        if matched_strong and attrs:
                            return

            if depth >= 3:
                return
            if xl_isinstance(value, xl_dict_type):
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for key in xl_list_type(value.keys())[:400]:
                    if not xl_isinstance(key, xl_cheat_text_types):
                        continue
                    try:
                        child = value[key]
                    except Exception:
                        continue
                    walk(path + "." + key, child, depth + 1)
            elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for index in xl_range(xl_min(xl_len(value), 400)):
                    try:
                        child = value[index]
                    except Exception:
                        continue
                    walk(path + "." + xl_cheat_str_type(index), child, depth + 1)
            elif is_object:
                if xl_id(value) in seen:
                    return
                seen.add(xl_id(value))
                for key, child in xl_list_type(xl_vars(value).items())[:200]:
                    if key.startswith("_"):
                        continue
                    walk(path + "." + xl_cheat_str_type(key), child, depth + 1)

        data = xl_cheat_store_dict()
        for name in xl_list_type(data.keys()):
            if not xl_isinstance(name, xl_cheat_text_types):
                continue
            if name.startswith("_") or name.lower().startswith("xl_cheat"):
                continue
            if name in skip_names:
                continue
            try:
                value = data[name]
            except Exception:
                continue
            try:
                walk(name, value, 0)
            except Exception as error:
                xl_cheat_log("角色识别异常 %s：%s: %s" % (name, xl_type(error).__name__, error))

        # 角色优先：搜到角色名时只列角色，避免任务/地点混在里面
        roles = [entry for entry in strong if entry.get("kind") == "角色"]
        prefix_actors = xl_cheat_prefix_actors(keyword) if keyword else []
        if roles:
            found = roles
        elif prefix_actors:
            # <角色>_<属性> 形式的变量最贴近用户想看的角色面板
            found = prefix_actors
        elif strong:
            found = strong
        else:
            found = weak
        found = xl_sorted(found, key=lambda entry: entry["path"])
        # 角色表拆开后条目会变多（TB_Actor 里就可能有几十个角色），别只留 40 条
        return found[:80]

    def xl_cheat_prefix_actors(keyword):
        """把 <角色>_<属性> 形式的变量按前缀聚合成角色条目"""
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return []
        prefix = keyword + "_"
        tables = (("", xl_cheat_store_dict()), ("default.", xl_cheat_default_dict()))
        attrs = []
        seen = set()
        for table_prefix, table in tables:
            for name in xl_list_type(table.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                low = name.lower()
                if not low.startswith(prefix) or name in seen:
                    continue
                try:
                    value = table[name]
                except Exception:
                    continue
                if not xl_cheat_scalar(value):
                    continue
                seen.add(name)
                attrs.append({
                    "name": name[xl_len(prefix):],
                    "path": table_prefix + name,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value, 80),
                })
        if xl_len(attrs) < 2:
            return []
        attrs = xl_sorted(attrs, key=lambda entry: entry["name"].lower())
        return [{
            "path": keyword,
            "label": keyword,
            "type": "前缀变量",
            "kind": "角色",
            "score": 3,
            "attrs": attrs,
            "count": xl_len(attrs),
        }]

    # ------------------------------------------------------------------
    # 属性识别：好感、角色状态、资源货币、等级成长……
    # 各游戏命名五花八门：nora_affection、affection.nora、角色对象 .love、
    # g_affection = {"nora": 10}、g_amelia_heart = [0,0,...]。
    # 这里只按「名字里的关键词」分组识别，不绑定任何具体游戏。
    # ------------------------------------------------------------------
    XL_CHEAT_ATTR_GROUPS = (
        ("好感 · 关系", (
            "affection", "affinity", "fondness", "romance", "relationship",
            "relation", "favor", "favour", "love", "likes", "trust", "heart",
            "hearts", "intimacy", "bond", "charm", "attraction",
            "interest", "interests", "friend", "friendship", "romancepoints",
            "opinion", "opinions", "allure", "appeal", "view", "views",
            "looks", "conflict",
            "好感", "爱意", "感情", "关系", "信任", "爱心", "心动",
            "亲密度", "好感度", "爱慕", "兴趣", "友谊",
            "看法", "魅力", "印象", "观念", "冲突",
        )),
        ("角色状态", (
            "corruption", "lust", "arousal", "desire", "obedience", "submission",
            "mood", "sanity", "stress", "fatigue", "drunk", "pregnancy",
            "horny", "anger", "fear", "shyness", "shame", "willpower",
            "discipline", "training", "addiction", "dependency",
            "grades", "popularity", "influence", "hygiene", "cleanliness",
            "fitness", "beauty", "dominance", "sensitivity", "pleasure",
            "pain", "hunger", "thirst", "tiredness", "suspicion", "jealousy",
            "堕落", "心情", "服从", "欲望", "理智", "压力", "疲劳", "醉酒",
            "成绩", "人气", "影响力", "清洁", "嫉妒", "怀疑",
        )),
        ("资源 · 货币", (
            "money", "cash", "coins", "coin", "gold", "credit", "credits",
            "funds", "currency", "diamond", "diamonds", "gem", "gems",
            "crystal", "ticket", "tickets", "token", "tokens", "energy",
            "stamina", "hp", "health", "ammo", "food", "water",
            "supplies", "goldcoin",
            "金钱", "金币", "钻石", "水晶", "体力", "能量", "钞票", "存款",
        )),
        ("等级 · 成长", (
            "level", "lvl", "exp", "xp", "points", "stats", "stat", "skill",
            "skills", "proficiency", "progress", "rank", "score", "reputation",
            "fame", "karma", "intelligence", "strength", "agility", "charisma",
            "luck", "wisdom", "perk", "perks", "talent", "talentpoint",
            "等级", "经验", "技能", "属性点", "声望", "进度", "天赋",
        )),
    )
    XL_CHEAT_ATTR_GROUP_NAMES = tuple(group for group, _keys in XL_CHEAT_ATTR_GROUPS)
    XL_CHEAT_AFFECTION_SKIP = (
        "item", "inventory", "shop", "price", "cost", "text", "desc",
        "name", "icon", "image", "url", "btn", "translat", "word",
        "quest_desc", "tooltip", "label",
        # protection_love / protect_xxx 这类是防作弊校验值（哈希/道具钥匙），
        # 不是好感数值，改它只会让游戏判定异常，必须排除。
        "protection", "protect",
    )
    XL_CHEAT_AFFECTION_GENERIC = (
        "g", "p", "s", "tb", "var", "global", "cheat", "stat", "stats",
        "value", "val", "lv", "lvl", "level", "point", "points", "pts",
        "max", "min", "cur", "current", "total", "flag", "flags",
        "num", "cnt", "count", "amount", "own", "have", "my", "the", "a",
    )
    # 名字像「角色表」的容器优先扫描（属性常常藏在 TB_Actor 这类表里）
    XL_CHEAT_AFFECTION_TABLE_HINTS = (
        "actor", "char", "girl", "npc", "heroine", "role", "person",
        "people", "unit", "slave", "student", "member", "teacher",
        "wife", "daughter", "sister", "mother", "girls", "waifu",
        "player", "hero", "party", "team", "roster", "inventoryactor",
        "objectslist", "gang", "crew", "cast", "contacts",
    )

    # 这几个键太短、太容易出现在别的单词里（status 里的 stat），只认独立词
    XL_CHEAT_ATTR_EXACT = ("hp", "mp", "xp", "exp", "lvl", "stat",
                           "favor", "favour", "heart", "bond", "charm",
                           "opinion", "allure", "appeal", "view", "views",
                           "looks", "conflict")

    # 引擎自带的命名空间：扫描时会混进 gui.browser_favourite_button_borders
    # 这类界面尺寸，全是噪音，一律跳过
    XL_CHEAT_SCOPE_SKIP = ("renpy", "store", "config", "persistent", "ui",
                           "gui", "default_store", "renpy_version",
                           "word_translations", "translations", "translator",
                           "director", "conststore", "build", "updater",
                           "bubble", "iap", "achievement", "_warper",
                           "_console", "screen", "style")

    def xl_cheat_attr_match(name):
        """返回 (分类名, 命中的关键词)；没命中返回 None"""
        low = xl_cheat_str_type(name or "").lower()
        if not low:
            return None
        for skip in XL_CHEAT_AFFECTION_SKIP:
            if skip in low:
                return None
        tokens = None
        for group, keys in XL_CHEAT_ATTR_GROUPS:
            for key in keys:
                if xl_len(key) <= 3 or key in XL_CHEAT_ATTR_EXACT:
                    if tokens is None:
                        text = low
                        for ch in "._-[]()/\\|,:;+=*&^%$#@!?<>{}'\"~`":
                            text = text.replace(ch, " ")
                        tokens = text.split()
                    if key in tokens:
                        return group, key
                    continue
                if key in low:
                    return group, key
        return None

    def xl_cheat_affection_hit(name):
        match = xl_cheat_attr_match(name)
        return match[1] if match else None

    def xl_cheat_affection_character(name, key):
        """从变量名里去掉关键词和通用前缀，剩下的就是角色名"""
        low = xl_cheat_str_type(name).lower()
        cleaned = low.replace(key, "_")
        for ch in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
                   "-", ".", " ", "[", "]"):
            cleaned = cleaned.replace(ch, "_")
        parts = [part for part in cleaned.split("_")
                 if part and part not in XL_CHEAT_AFFECTION_GENERIC]
        return "_".join(parts)

    def xl_cheat_affection_num(value):
        """好感值允许三种存法：数字、布尔、以及「数字字符串」（如 '0'）。
        特工17 的 protection_love 就是字符串 '0'，不认这种会整片漏掉。"""
        if xl_cheat_is_number(value):
            return True
        if not xl_isinstance(value, xl_cheat_text_types):
            return False
        try:
            text = value.strip()
        except Exception:
            return False
        if not text or xl_len(text) > 12:
            return False
        try:
            xl_float(text)
            return True
        except Exception:
            return False

    def xl_cheat_affection_scan():
        items = []
        seen = set()
        budget = [60000]
        candidates = []

        def add(path, name, character, value, scope, table_path="", group=None):
            if path in seen:
                return
            # 布尔值多半是「开关 / 已解锁标记」，不是数值属性，列出来只会误导
            if xl_isinstance(value, xl_bool):
                return
            seen.add(path)
            if group is None:
                match = xl_cheat_attr_match(name)
                group = match[0] if match else "其他数值"
            items.append({
                "path": path,
                "name": xl_cheat_str_type(name),
                "character": xl_cheat_localize(character) if character else "通用",
                "scope": scope,
                "group": group,
                "type": xl_cheat_type_name(value),
                "value": xl_cheat_describe(value, 60),
                "table": table_path,
            })

        def label_of_mapping(mapping):
            for key in ("name", "char_name", "display_name", "full_name",
                        "nickname", "title", "label", "pKey", "key"):
                try:
                    text = mapping[key]
                except Exception:
                    continue
                if (xl_isinstance(text, xl_cheat_text_types) and text.strip()
                        and text.strip() not in ("?", "？", "-", "...", "…")
                        and not text.strip().startswith("[")):
                    return xl_cheat_str_type(text)
            return None

        def char_label(container, fallback):
            """角色表里的子项通常是 {'name': 'Amelia', ...}，
            运行时角色对象则把资料放在 .data 字典里。"""
            if xl_isinstance(container, xl_dict_type):
                return label_of_mapping(container) or xl_cheat_str_type(fallback)
            if xl_hasattr(container, "__dict__"):
                for key in ("name", "char_name", "display_name", "full_name",
                            "nickname", "title", "label"):
                    try:
                        text = xl_getattr(container, key)
                    except Exception:
                        continue
                    if (xl_isinstance(text, xl_cheat_text_types) and text.strip()
                            and text.strip() not in ("?", "？", "-", "...", "…")
                            and not text.strip().startswith("[")):
                        return xl_cheat_str_type(text)
                for holder in ("data", "info", "actor"):
                    try:
                        inner = xl_getattr(container, holder)
                    except Exception:
                        continue
                    if xl_isinstance(inner, xl_dict_type):
                        text = label_of_mapping(inner)
                        if text:
                            return text
                for key in ("key", "pKey"):
                    try:
                        text = xl_getattr(container, key)
                    except Exception:
                        continue
                    if xl_isinstance(text, xl_cheat_text_types) and text.strip():
                        return xl_cheat_str_type(text)
            return xl_cheat_str_type(fallback)

        def expand_list(base, label, character, value, scope, limit=60, group=None):
            """列表型：g_amelia_heart = [0, 0, ...] → 逐项展开成可改路径"""
            try:
                seq = xl_list_type(value)
            except Exception:
                return
            if not seq:
                return
            count = xl_min(xl_len(seq), limit)
            for index in xl_range(count):
                try:
                    child = seq[index]
                except Exception:
                    continue
                if not xl_cheat_affection_num(child):
                    continue
                add("%s.%d" % (base, index), "%s[%d]" % (label, index),
                    character, child, scope, base, group)

        def fields_of(container):
            """dict / 对象 → [(字段名, 值)]，对象实例字段最多 60 个"""
            pairs = []
            if xl_isinstance(container, xl_dict_type):
                try:
                    keys = xl_list_type(container.keys())[:60]
                except Exception:
                    return pairs
                for key in keys:
                    if not xl_isinstance(key, xl_cheat_text_types):
                        continue
                    try:
                        pairs.append((xl_cheat_str_type(key), container[key]))
                    except Exception:
                        continue
                return pairs
            if xl_hasattr(container, "__dict__"):
                known = set()
                try:
                    entries = xl_list_type(xl_vars(container).items())[:60]
                except Exception:
                    entries = []
                for key, value in entries:
                    if not xl_isinstance(key, xl_cheat_text_types) or key.startswith("_"):
                        continue
                    known.add(key)
                    pairs.append((xl_cheat_str_type(key), value))
                # 类上声明的默认值：例如 ActorData.love = 0。好感没涨过时
                # 实例上根本没有 love 这个属性，只读 vars() 会整片漏掉。
                try:
                    class_items = xl_list_type(
                        xl_getattr(xl_type(container), "__dict__", {}).items())
                except Exception:
                    class_items = []
                added = 0
                for key, value in class_items:
                    if added >= 40:
                        break
                    if not xl_isinstance(key, xl_cheat_text_types) or key.startswith("_"):
                        continue
                    if key in known or xl_callable(value):
                        continue
                    if xl_cheat_is_container(value) or value is None:
                        continue
                    if not (xl_cheat_is_number(value) or xl_isinstance(value, xl_cheat_text_types)):
                        continue
                    pairs.append((xl_cheat_str_type(key), value))
                    added += 1
            return pairs

        def is_record(value):
            if xl_isinstance(value, (xl_cheat_types.ModuleType,
                                     xl_cheat_types.FunctionType, xl_type)):
                return False
            if xl_isinstance(value, xl_dict_type):
                return True
            if xl_isinstance(value, (xl_list_type, xl_tuple_type, xl_cheat_text_types)):
                return False
            return xl_hasattr(value, "__dict__") and not xl_callable(value)

        def record_has_attrs(record, limit=40):
            checked = 0
            try:
                pairs = fields_of(record)
            except Exception:
                return False
            for field, _value in pairs:
                checked += 1
                if checked > limit:
                    break
                if xl_cheat_attr_match(field) is not None:
                    return True
            return False

        def table_has_attrs(table, limit=8):
            """只看前几个子项：表里有「love / mood / money」这类字段，
            才当成角色 / 属性表扫描，避免把无关字典（赞助表等）扫进来。"""
            is_dict = xl_isinstance(table, xl_dict_type)
            try:
                if is_dict:
                    children = xl_list_type(table.values())[:limit]
                else:
                    children = xl_list_type(xl_vars(table).values())[:limit]
            except Exception:
                return False
            for child in children:
                if is_record(child) and record_has_attrs(child):
                    return True
            return False

        def list_has_attrs(entries, limit=8):
            for index in xl_range(xl_min(xl_len(entries), limit)):
                try:
                    child = entries[index]
                except Exception:
                    continue
                if is_record(child) and record_has_attrs(child):
                    return True
            return False

        def scan_keyed_dict(base, mapping, scope):
            """统计表：{'corruption': 3, 'money': 120}，键就是属性名"""
            keyed = 0
            try:
                subs = xl_list_type(mapping.keys())[:300]
            except Exception:
                subs = []
            for sub in subs:
                if not xl_isinstance(sub, xl_cheat_text_types):
                    continue
                sub_match = xl_cheat_attr_match(sub)
                if sub_match is None:
                    continue
                try:
                    inner = mapping[sub]
                except Exception:
                    continue
                sub_text = xl_cheat_str_type(sub)
                if xl_cheat_affection_num(inner):
                    add("%s.%s" % (base, sub_text), sub_text, "", inner,
                        scope, base, sub_match[0])
                    keyed += 1
                elif xl_isinstance(inner, (xl_list_type, xl_tuple_type)):
                    expand_list("%s.%s" % (base, sub_text), sub_text, "",
                                inner, scope, 40, sub_match[0])
                    keyed += 1
            return keyed

        def scan_grouped(base, grouped, character, scope, limit=60):
            """按类型分组的变量表：{'int': {'money': 120}, 'str': {...}}

            TGCharacter 这类框架把角色数值放在私有字段里，例如
            _m1_TGCharacter__variables = {'int': {'relationshipPoints': 0}}，
            组名（int/str/bool）不是属性名，必须往下再走一层。
            """
            if not xl_isinstance(grouped, xl_dict_type):
                return 0
            found = 0
            try:
                groups = xl_list_type(grouped.items())[:16]
            except Exception:
                return 0
            # 只认「组名是类型名」的表。否则 TB_Quest = {任务名: {reward_gold: 100}}
            # 这类普通数据表也会被误判成分组表，白白丢掉后面的 scan_char_table。
            typed = False
            for group_key, inner in groups:
                if not xl_isinstance(inner, xl_dict_type):
                    continue
                if not xl_isinstance(group_key, xl_cheat_text_types):
                    continue
                group_word = xl_cheat_str_type(group_key).lower().strip()
                for word in ("int", "integer", "long", "float", "double", "str",
                             "string", "text", "unicode", "bool", "boolean",
                             "list", "dict", "tuple", "set", "num", "number"):
                    if group_word == word:
                        typed = True
                        break
                if typed:
                    break
            if not typed:
                return 0
            for group_key, inner in groups:
                if not xl_isinstance(inner, xl_dict_type):
                    continue
                group_path = base
                if xl_isinstance(group_key, xl_cheat_text_types):
                    group_text = xl_cheat_str_type(group_key)
                    if group_text:
                        group_path = "%s.%s" % (base, group_text)
                try:
                    pairs = xl_list_type(inner.items())[:limit]
                except Exception:
                    continue
                for field, value in pairs:
                    budget[0] -= 1
                    if budget[0] <= 0:
                        return found
                    if not xl_isinstance(field, xl_cheat_text_types):
                        continue
                    field_text = xl_cheat_str_type(field)
                    match = xl_cheat_attr_match(field_text)
                    if match is None:
                        continue
                    if xl_cheat_affection_num(value):
                        add("%s.%s" % (group_path, field_text), field_text,
                            character, value, scope, group_path, match[0])
                        found += 1
                    elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                        expand_list("%s.%s" % (group_path, field_text), field_text,
                                    character, value, scope, 40, match[0])
                        found += 1
            return found

        def scan_sub_record(base, label, record, character, scope, group):
            """对象里再套一层对象：Player.Charisma.Value / Energy.Max

            困难时期这类游戏把属性包在 DynamicVar 里，
            名字（charisma / fitness）在外层，数值（Value）在内层。
            """
            total = 0
            try:
                pairs = fields_of(record)[:40]
            except Exception:
                return 0
            for field, value in pairs:
                budget[0] -= 1
                if budget[0] <= 0:
                    return total
                if not xl_cheat_affection_num(value):
                    continue
                add("%s.%s" % (base, field), "%s.%s" % (label, field),
                    character, value, scope, base, group)
                total += 1
            return total

        def scan_relation_records(base, entries, scope, limit=300):
            """关系表：Relations.data = [RelationClass(sub1, sub2, opinion, allure)]

            困难时期这类框架把「看法 / 魅力」存在关系对象里，
            数值在 DynamicVar.Value 里，角色名在 sub1 / sub2 里。
            """
            total = 0
            try:
                seq = xl_list_type(entries)[:limit]
            except Exception:
                return 0
            for index in xl_range(xl_len(seq)):
                if budget[0] <= 0:
                    break
                budget[0] -= 1
                try:
                    record = seq[index]
                except Exception:
                    continue
                if not is_record(record):
                    continue
                who = ""
                names = []
                for key in ("sub1", "sub2"):
                    try:
                        part = xl_getattr(record, key)
                    except Exception:
                        continue
                    if not xl_isinstance(part, xl_cheat_text_types):
                        continue
                    text = xl_cheat_str_type(part)
                    names.append(text)
                    if text and text != "Player" and not who:
                        who = text
                if not who and names:
                    who = names[0]
                rec_path = "%s.%d" % (base, index)
                for field, value in fields_of(record):
                    if not xl_isinstance(field, xl_cheat_text_types) or field.startswith("_"):
                        continue
                    match = xl_cheat_attr_match(field)
                    if match is None:
                        continue
                    if xl_cheat_affection_num(value):
                        add("%s.%s" % (rec_path, field), field, who,
                            value, scope, rec_path, match[0])
                        total += 1
                        continue
                    if xl_hasattr(value, "Value"):
                        try:
                            inner = xl_getattr(value, "Value")
                        except Exception:
                            continue
                        if xl_cheat_affection_num(inner):
                            add("%s.%s.Value" % (rec_path, field), field, who,
                                inner, scope, rec_path, match[0])
                            total += 1
            return total

        def scan_object_grouped(container, base, character, scope):
            """对象上的分组变量表（含 _m1_Class__variables 这类私有名字）"""
            try:
                pairs = xl_list_type(xl_vars(container).items())[:100]
            except Exception:
                return
            for attr, child in pairs:
                if not xl_isinstance(attr, xl_cheat_text_types):
                    continue
                attr_text = xl_cheat_str_type(attr)
                if attr_text.startswith("__"):
                    continue
                low = attr_text.lower()
                if not low.startswith("_"):
                    # 公开字段只看名字像「变量表」的，避免扫到角色资料字典
                    hinted = False
                    for hint in ("var", "stat", "attr", "data", "prop", "value"):
                        if hint in low:
                            hinted = True
                            break
                    if not hinted:
                        continue
                if not xl_isinstance(child, xl_dict_type):
                    continue
                scan_grouped("%s.%s" % (base, attr_text), child, character, scope)

        def scan_char_table(base, table, scope):
            """角色表（TB_Actor / gd_InventoryActor 之类）：
            表名本身不带属性关键词，属性藏在每个角色的字段里。"""
            is_dict = xl_isinstance(table, xl_dict_type)
            keys = []
            try:
                if is_dict:
                    keys = xl_list_type(table.keys())[:150]
                else:
                    keys = [key for key in xl_list_type(xl_vars(table).keys())[:150]
                            if xl_isinstance(key, xl_cheat_text_types) and not key.startswith("_")]
            except Exception:
                return
            if not keys:
                return
            for sub in keys:
                if budget[0] <= 0:
                    return
                try:
                    child = table[sub] if is_dict else xl_getattr(table, sub)
                except Exception:
                    continue
                if not is_record(child):
                    continue
                character = char_label(child, sub)
                child_path = "%s.%s" % (base, xl_cheat_str_type(sub))
                for field, value in fields_of(child):
                    budget[0] -= 1
                    match = xl_cheat_attr_match(field)
                    if match is not None:
                        if xl_cheat_affection_num(value):
                            add("%s.%s" % (child_path, field), field, character,
                                value, scope, child_path, match[0])
                            continue
                        if xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                            expand_list("%s.%s" % (child_path, field), field,
                                        character, value, scope, 40, match[0])
                            continue
                    if is_record(value) and match is not None:
                        # 属性包在子对象里：Player.Charisma.Value
                        scan_sub_record("%s.%s" % (child_path, field), field,
                                        value, character, scope, match[0])
                # 角色对象里的私有分组变量表（TGCharacter 等框架）
                scan_object_grouped(child, child_path, character, scope)

        tables = (("", "存档", xl_cheat_store_dict()),
                  ("default.", "默认存档", xl_cheat_default_dict()))
        for prefix, scope, table in tables:
            names = xl_list_type(table.keys())
            for name in names:
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                if name.startswith("_") or xl_cheat_str_type(name).lower().startswith("xl_cheat"):
                    continue
                if xl_cheat_str_type(name).lower() in XL_CHEAT_SCOPE_SKIP:
                    continue
                try:
                    value = table[name]
                except Exception:
                    continue
                base = prefix + xl_cheat_str_type(name)
                match = xl_cheat_attr_match(name)
                if match is not None:
                    group, key = match
                    character = xl_cheat_affection_character(name, key)
                    if xl_cheat_affection_num(value):
                        add(base, xl_cheat_str_type(name), character, value,
                            scope, "", group)
                        continue
                    if xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                        # 列表型：g_amelia_heart = [0, 0, ...]
                        expand_list(base, key, character, value, scope, 60, group)
                        continue
                    if xl_isinstance(value, xl_dict_type):
                        # 角色名 -> 数值；或 角色名 -> 角色字典 / 列表
                        try:
                            subs = xl_list_type(value.keys())[:300]
                        except Exception:
                            subs = []
                        has_record = False
                        for sub in subs:
                            try:
                                child = value[sub]
                            except Exception:
                                continue
                            sub_text = xl_cheat_str_type(sub)
                            if xl_cheat_affection_num(child):
                                add(base + "." + sub_text, sub_text, sub_text,
                                    child, scope, base, group)
                            elif xl_isinstance(child, (xl_list_type, xl_tuple_type)):
                                expand_list(base + "." + sub_text, key, sub_text,
                                            child, scope, 40, group)
                            elif is_record(child):
                                has_record = True
                        if has_record:
                            scan_char_table(base, value, scope)
                        continue
                if xl_isinstance(value, xl_dict_type):
                    # 变量名不带关键词，但表里的「键」是属性名：
                    # stats = {"corruption": 3, "money": 120}
                    if scan_keyed_dict(base, value, scope):
                        continue
                    # 分组表：stats = {"int": {"money": 120}, "str": {...}}
                    if scan_grouped(base, value, "", scope):
                        continue
                if xl_isinstance(value, xl_dict_type) or (
                        xl_hasattr(value, "__dict__")
                        and not xl_isinstance(value, (xl_list_type, xl_tuple_type))):
                    low = xl_cheat_str_type(name).lower()
                    hinted = False
                    for hint in XL_CHEAT_AFFECTION_TABLE_HINTS:
                        if hint in low:
                            hinted = True
                            break
                    if hinted or table_has_attrs(value):
                        candidates.append((0 if hinted else 1, base, scope, value))

        # 角色对象上的属性：nora.love / actor.affection
        store = xl_cheat_store_dict()
        for name in xl_list_type(store.keys()):
            if not xl_isinstance(name, xl_cheat_text_types):
                continue
            if name.startswith("_") or name.lower().startswith("xl_cheat"):
                continue
            try:
                obj = store[name]
            except Exception:
                continue
            if xl_isinstance(obj, xl_list_type):
                # 角色对象列表：g_InventoryActor = [ActorData, ...]
                low_list = xl_cheat_str_type(name).lower()
                hinted = False
                for hint in XL_CHEAT_AFFECTION_TABLE_HINTS:
                    if hint in low_list:
                        hinted = True
                        break
                if not hinted:
                    try:
                        entries = xl_list_type(obj)[:200]
                    except Exception:
                        continue
                    if not list_has_attrs(entries):
                        continue
                else:
                    try:
                        entries = xl_list_type(obj)[:200]
                    except Exception:
                        continue
                for index in xl_range(xl_len(entries)):
                    child = entries[index]
                    if not is_record(child):
                        continue
                    character = char_label(child, index)
                    base = "%s.%d" % (xl_cheat_str_type(name), index)
                    for field, value in fields_of(child):
                        budget[0] -= 1
                        match = xl_cheat_attr_match(field)
                        if match is None:
                            continue
                        if xl_cheat_affection_num(value):
                            add("%s.%s" % (base, field), field, character,
                                value, "对象", base, match[0])
                        elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                            expand_list("%s.%s" % (base, field), field,
                                        character, value, "对象", 40, match[0])
                    scan_object_grouped(child, base, character, "对象")
                continue
            if xl_isinstance(obj, xl_dict_type) or not xl_hasattr(obj, "__dict__"):
                continue
            if xl_isinstance(obj, (xl_cheat_types.ModuleType,
                                   xl_cheat_types.FunctionType, xl_type)) or xl_callable(obj):
                continue
            try:
                pairs = xl_list_type(xl_vars(obj).items())[:200]
            except Exception:
                continue
            for attr, child in pairs:
                if not xl_isinstance(attr, xl_cheat_text_types) or attr.startswith("_"):
                    continue
                attr_text = xl_cheat_str_type(attr)
                match = xl_cheat_attr_match(attr)
                if match is not None and xl_cheat_affection_num(child):
                    add(xl_cheat_str_type(name) + "." + attr_text, attr_text,
                        xl_cheat_str_type(name), child, "对象", "", match[0])
                elif xl_isinstance(child, xl_dict_type):
                    # 对象里的统计表：player.stats = {'corruption': 3}
                    scan_keyed_dict(xl_cheat_str_type(name) + "." + attr_text,
                                    child, "对象")
                elif is_record(child):
                    if match is not None:
                        # 属性包在子对象里：Player.Charisma.Value
                        scan_sub_record(xl_cheat_str_type(name) + "." + attr_text,
                                        attr_text, child, xl_cheat_str_type(name),
                                        "对象", match[0])
                    candidates.append((0, xl_cheat_str_type(name) + "." + attr_text,
                                       "对象", child))

            # 私有分组变量表：以对象名作为角色名
            scan_object_grouped(obj, xl_cheat_str_type(name),
                                xl_cheat_str_type(name), "对象")

            # 关系表：Relations.data = [RelationClass(sub1, sub2, opinion, allure)]
            if is_record(obj):
                try:
                    list_attrs = xl_list_type(xl_vars(obj).items())[:30]
                except Exception:
                    list_attrs = []
                for attr, child in list_attrs:
                    if not xl_isinstance(attr, xl_cheat_text_types):
                        continue
                    attr_low = xl_cheat_str_type(attr).lower()
                    if not xl_isinstance(child, (xl_list_type, xl_tuple_type)):
                        continue
                    if not ("rel" in attr_low
                            or attr_low in ("data", "items", "rels", "list")):
                        continue
                    try:
                        entries = xl_list_type(child)[:60]
                    except Exception:
                        continue
                    if not entries:
                        continue
                    if scan_relation_records(
                            xl_cheat_str_type(name) + "." + attr_low,
                            child, "对象"):
                        break

            # 有些游戏的属性写成 property / 类级默认值，实例 __dict__ 里没有，
            # 用 dir() 只挑命中关键词的名字再取一次值。
            known = set()
            for attr, _child in pairs:
                if xl_isinstance(attr, xl_cheat_text_types):
                    known.add(attr)
            try:
                dir_names = xl_list_type(xl_dir(obj))[:400]
            except Exception:
                dir_names = []
            for attr in dir_names:
                if not xl_isinstance(attr, xl_cheat_text_types):
                    continue
                if attr in known or attr.startswith("_"):
                    continue
                if xl_cheat_attr_match(attr) is None:
                    continue
                try:
                    child = xl_getattr(obj, attr)
                except Exception:
                    continue
                if xl_callable(child) or xl_cheat_is_container(child):
                    continue
                if xl_cheat_affection_num(child):
                    add(xl_cheat_str_type(name) + "." + xl_cheat_str_type(attr),
                        xl_cheat_str_type(attr), xl_cheat_str_type(name),
                        child, "对象")

        candidates = xl_sorted(candidates, key=lambda entry: entry[0])
        for _priority, base, scope, value in candidates:
            if budget[0] <= 0:
                break
            scan_char_table(base, value, scope)

        # persistent：跨存档数据。不少游戏把金钱 / 属性放在这里，
        # 存档变量里反而找不到。
        pers = xl_cheat_persistent()
        if pers is not None:
            try:
                pers_pairs = xl_list_type(xl_vars(pers).items())[:600]
            except Exception:
                pers_pairs = []
            for attr, child in pers_pairs:
                if not xl_isinstance(attr, xl_cheat_text_types) or attr.startswith("_"):
                    continue
                attr_text = xl_cheat_str_type(attr)
                base = "persistent." + attr_text
                match = xl_cheat_attr_match(attr)
                if match is not None and xl_cheat_affection_num(child):
                    add(base, attr_text, "", child, "持久化", "", match[0])
                    continue
                if match is not None and xl_isinstance(child, (xl_list_type, xl_tuple_type)):
                    expand_list(base, attr_text, "", child, "持久化", 60, match[0])
                    continue
                if xl_isinstance(child, xl_dict_type):
                    if not scan_keyed_dict(base, child, "持久化") and table_has_attrs(child):
                        scan_char_table(base, child, "持久化")
                    continue
                if is_record(child):
                    scan_char_table(base, child, "持久化")

        order = {}
        for position in xl_range(xl_len(XL_CHEAT_ATTR_GROUP_NAMES)):
            order[XL_CHEAT_ATTR_GROUP_NAMES[position]] = position
        items = xl_sorted(items, key=lambda item: (
            order.get(item["group"], 99), item["character"], item["path"]))
        return {"items": items[:1800], "total": xl_len(items),
                "groups": [group for group in XL_CHEAT_ATTR_GROUP_NAMES]}

    def xl_cheat_affection_set(paths, text):
        changed = 0
        failed = []
        for path in paths or []:
            path = xl_cheat_str_type(path)
            try:
                old = xl_cheat_get(path)
                value = xl_cheat_parse(xl_cheat_str_type(text), old, None)
                xl_cheat_set(path, value)
                changed += 1
            except Exception as error:
                failed.append([path, "%s: %s" % (xl_type(error).__name__, error)])
        return changed, failed

    # ------------------------------------------------------------------
    # 画廊 / 回忆 / 收集：扫描解锁标记，支持一键解锁与撤销
    # 各游戏命名五花八门，这里只按关键词 + 布尔/字典结构识别，不绑定具体游戏。
    # ------------------------------------------------------------------
    XL_CHEAT_COLLECT_KEYS = (
        ("unlock", "解锁"), ("gallery", "画廊"), ("cg", "CG"), ("scene", "场景"),
        ("recall", "回忆"), ("memories", "回忆"), ("memory", "回忆"),
        ("bonus", "特典"), ("extra", "特典"), ("achievement", "成就"),
        ("illust", "插图"), ("replay", "回放"), ("album", "相册"),
        ("collect", "收集"), ("photo", "照片"), ("event", "事件"),
        ("outfit", "服装"), ("chara", "角色"),
        ("回顾", "回忆"), ("回想", "回忆"), ("画廊", "画廊"),
        ("图鉴", "图鉴"), ("回忆", "回忆"),
    )
    xl_cheat_unlock_backup = []
    # Ren'Py 引擎自带的「已看图片/已听音频」记录，绝大多数画廊都靠它解锁
    XL_CHEAT_INTERNAL_COLLECT = ("_seen_images", "_seen_audio")

    def xl_cheat_collect_match(name):
        """返回 (分类键, 中文分类名)；没匹配到返回 (None, None)"""
        low = (name or "").lower()
        for key, label in XL_CHEAT_COLLECT_KEYS:
            if key in low:
                return key, label
        return None, None

    def xl_cheat_collect_group(name, label):
        """按「分类 + 首个词」分组，避免几百个一组一行的碎分组"""
        parts = (name or "").split("_")
        prefix = parts[0].lower() if parts else (name or "").lower()
        for suffix in ("unlocked", "unlock", "seen", "done", "visible"):
            if prefix == suffix and xl_len(parts) > 1:
                prefix = parts[1].lower()
                break
        return "%s · %s" % (label, prefix) if prefix else label

    def xl_cheat_image_names():
        """收集引擎里注册过的图片名，用于补全 Ren'Py 自带的已看图片表"""
        names = []
        seen = {}
        try:
            import renpy.display.image as xl_cheat_image_module
            tables = [xl_getattr(xl_cheat_image_module, "images", {})]
        except Exception:
            tables = []
        for table in tables:
            try:
                keys = xl_list_type(table.keys())
            except Exception:
                continue
            for key in keys:
                text = ""
                if xl_isinstance(key, xl_cheat_text_types):
                    text = xl_cheat_str_type(key)
                elif xl_isinstance(key, (xl_tuple_type, xl_list_type)) and xl_len(key):
                    first = key[0]
                    if xl_isinstance(first, xl_cheat_text_types):
                        text = xl_cheat_str_type(first)
                if not text or text in seen:
                    continue
                seen[text] = True
                names.append(text)
        return names

    def xl_cheat_seen_stats(name, value):
        """统计 _seen_images / _seen_audio 的解锁情况，空表时按引擎图片名估算总数"""
        total = 0
        unlocked = 0
        try:
            for key in xl_list_type(value.keys()):
                if xl_isinstance(value[key], xl_bool):
                    total += 1
                    if value[key]:
                        unlocked += 1
        except Exception:
            pass
        if name == "_seen_images":
            names = xl_cheat_image_names()
            if xl_len(names) > total:
                total = xl_len(names)
        return total, xl_min(unlocked, total)

    def xl_cheat_collect_entry(path, name, value, include_all=False):
        category, label = xl_cheat_collect_match(name)
        if name in XL_CHEAT_INTERNAL_COLLECT:
            category = "cg"
            label = "CG"
            if path.startswith("persistent._seen_audio"):
                label = "音频"
        matched = category is not None
        if xl_isinstance(value, xl_bool):
            if not matched and not include_all:
                return None
            return {
                "path": path,
                "name": name,
                "group": xl_cheat_collect_group(name, label or "其他"),
                "category": category or "other",
                "type": "bool",
                "value": value,
                "unlocked": bool(value),
            }
        if xl_isinstance(value, xl_dict_type):
            if not matched:
                return None
            total, unlocked = xl_cheat_seen_stats(name, value)
            if total == 0:
                return None
            return {
                "path": path,
                "name": name,
                "group": xl_cheat_collect_group(name, label),
                "category": category,
                "type": "dict",
                "value": "%d/%d" % (unlocked, total),
                "unlocked": unlocked,
                "total": total,
                "container": True,
            }
        return None

    def xl_cheat_collect_scan(include_all=False, keyword=""):
        keyword = (keyword or "").strip().lower()
        entries = []
        seen = set()
        tables = (("", xl_cheat_store_dict()), ("default.", xl_cheat_default_dict()))
        for prefix, table in tables:
            for name in xl_list_type(table.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                if name.startswith("_"):
                    continue
                if keyword and keyword not in name.lower():
                    continue
                path = prefix + name
                if path in seen:
                    continue
                try:
                    value = table[name]
                except Exception:
                    continue
                entry = xl_cheat_collect_entry(path, name, value, include_all)
                if entry:
                    seen.add(path)
                    entries.append(entry)

        target = xl_cheat_persistent()
        if target is not None:
            try:
                names = xl_list_type(xl_vars(target).keys())
            except Exception:
                names = []
            for name in names:
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                if name.startswith("_") and name not in XL_CHEAT_INTERNAL_COLLECT:
                    continue
                if keyword and keyword not in name.lower():
                    continue
                path = "persistent." + name
                if path in seen:
                    continue
                try:
                    value = xl_getattr(target, name)
                except Exception:
                    continue
                entry = xl_cheat_collect_entry(path, name, value, include_all)
                if entry:
                    seen.add(path)
                    entries.append(entry)

        groups = {}
        for entry in entries:
            group = groups.get(entry["group"])
            if group is None:
                group = {"name": entry["group"], "total": 0, "unlocked": 0, "paths": []}
                groups[entry["group"]] = group
            if entry.get("container"):
                group["total"] += entry.get("total") or 0
                group["unlocked"] += entry.get("unlocked") or 0
            else:
                group["total"] += 1
                if entry.get("unlocked"):
                    group["unlocked"] += 1
            group["paths"].append(entry["path"])

        for group in groups.values():
            group["locked"] = group["total"] - group["unlocked"]
            group["count"] = xl_len(group["paths"])
        # 未解锁多的组排前面，方便一眼看到哪块还没收集完
        group_list = xl_sorted(groups.values(),
                               key=lambda item: (-item["locked"], item["name"].lower()))
        unlocked = xl_len([e for e in entries if e.get("unlocked") and not e.get("container")])
        total = xl_len([e for e in entries if not e.get("container")])
        containers = [e for e in entries if e.get("container")]
        return {
            "items": entries,
            "groups": group_list,
            "total": total,
            "unlocked": unlocked,
            "locked": total - unlocked,
            "containers": containers,
            "include_all": include_all,
        }

    def xl_cheat_unlock_paths(paths):
        changed = 0
        failed = []
        for path in paths:
            try:
                value = xl_cheat_get(path)
            except Exception as error:
                failed.append([path, "%s: %s" % (xl_type(error).__name__, error)])
                continue
            if xl_isinstance(value, xl_bool):
                if not value:
                    xl_cheat_unlock_backup.append(["bool", path, None, value])
                    xl_cheat_set(path, True)
                    changed += 1
                continue
            if xl_isinstance(value, xl_dict_type):
                parent, key = xl_cheat_parent(path)
                target = xl_cheat_step(parent, key)
                if path.endswith("persistent._seen_images") and not target:
                    # 空表：用引擎里注册的图片名一次性写满，等效于「画廊全解锁」
                    for image_name in xl_cheat_image_names():
                        xl_cheat_unlock_backup.append(["dict", path, image_name, None])
                        target[image_name] = True
                        changed += 1
                    continue
                for sub_key in xl_list_type(target.keys()):
                    try:
                        sub = target[sub_key]
                    except Exception:
                        continue
                    if xl_isinstance(sub, xl_bool) and not sub:
                        xl_cheat_unlock_backup.append(
                            ["dict", path, xl_cheat_str_type(sub_key), sub])
                        target[sub_key] = True
                        changed += 1
                continue
            if xl_isinstance(value, xl_set_type):
                continue
            failed.append([path, "不支持的类型：" + xl_cheat_type_name(value)])
        return changed, failed

    def xl_cheat_unlock_undo():
        restored = 0
        for kind, path, key, old in reversed(xl_cheat_unlock_backup):
            try:
                if kind == "bool":
                    xl_cheat_set(path, old)
                else:
                    parent, name = xl_cheat_parent(path)
                    target = xl_cheat_step(parent, name)
                    if old is None:
                        try:
                            del target[key]
                        except Exception:
                            pass
                    else:
                        target[key] = old
                restored += 1
            except Exception:
                pass
        del xl_cheat_unlock_backup[:]
        return restored

    # ------------------------------------------------------------------
    # 赞助码 / 会员奖励 / 礼品码奖励：一键解锁
    # 大部分游戏把「输入码后解锁」的结果存成布尔、0/1 或领取状态表，只是名字
    # 五花八门（sponsor / patreon / gift_code / 礼包码 ...）。这里按关键词识别，
    # 不绑定具体游戏；码文本本身不猜，避免写入无效值让游戏报错。
    # ------------------------------------------------------------------
    XL_CHEAT_SPONSOR_KEYS = (
        "sponsor", "patreon", "patron", "backer", "supporter",
        "premium", "donat", "subscrib", "entitlement", "dlc",
        "赞助", "会员", "vip", "付费", "打赏", "完整版", "豪华版",
    )
    # 礼品码 / 礼包码：名字里同时出现这两种词才算开关，
    # 避免把普通的 gift 道具、每日 reward 当成兑换奖励。
    XL_CHEAT_SPONSOR_GIFT_PAIRS = (
        ("gift", "code"), ("gift", "reward"), ("gift", "claim"),
        ("gift", "unlock"), ("gift", "bonus"), ("gift", "received"),
        ("gift", "used"), ("gift", "done"), ("gift", "extra"),
        ("promo", "code"), ("promo", "reward"), ("promo", "claim"),
        ("coupon", "code"), ("coupon", "used"), ("voucher", "code"),
        ("redeem", "reward"), ("redeem", "claim"), ("redeem", "used"),
        ("bonus", "code"), ("bonus", "reward"), ("bonus", "claim"),
        ("reward", "code"), ("reward", "claim"), ("reward", "gift"),
        ("福利", "码"), ("礼品", "码"), ("礼包", "码"), ("兑换", "码"),
        ("礼品", "奖励"), ("礼包", "奖励"), ("礼品", "领取"),
        ("礼包", "领取"), ("福利", "领取"), ("兑换", "奖励"),
    )
    # 名字里带这些组合才算「兑换码变量」，避免误伤普通 code / 颜色代码
    XL_CHEAT_SPONSOR_CODE_KEYS = (
        "sponsor_code", "sponsorcode", "patreon_code", "patreoncode",
        "patron_code", "unlock_code", "unlockcode", "secret_code", "secretcode",
        "cheat_code", "cheatcode", "redeem_code", "redeemcode", "promo_code",
        "promocode", "gift_code", "giftcode", "access_code", "accesscode",
        "赞助码", "兑换码", "激活码", "优惠码", "礼品码", "礼包码",
    )
    # URL / 展示文本类的变量不是开关，直接跳过
    XL_CHEAT_SPONSOR_SKIP = (
        "sponsor_url", "sponsor_link", "sponsor_name", "sponsor_text",
        "sponsor_image", "sponsor_btn", "sponsor_icon", "sponsor_title",
        "patreon_url", "patreon_link", "patreon_name", "patreon_text",
        "patreon_image", "patreon_btn", "patreon_icon",
        "donate_url", "support_url", "support_link",
        "gift_name", "gift_desc", "gift_text", "gift_image", "gift_icon",
        "gift_item", "reward_name", "reward_desc", "reward_text",
        "reward_image", "reward_icon",
    )
    # 顶层变量名里出现这些词时，才继续往容器内部找真正的开关。
    # 不做无差别的全库下钻，否则会钻进角色表 / 物品表，把噪音当奖励。
    XL_CHEAT_SPONSOR_DEEP = (
        "sponsor", "patreon", "patron", "backer", "supporter", "premium",
        "donat", "subscrib", "entitlement", "dlc", "vip",
        "gift", "reward", "bonus", "promo", "redeem",
        "赞助", "会员", "付费", "打赏", "完整版", "豪华版",
        "礼包", "礼品", "福利", "兑换", "码",
    )
    xl_cheat_sponsor_backup = []

    def xl_cheat_sponsor_children(value, limit=200):
        """枚举 dict / list / tuple / 普通对象的直接子项（键名, 值）"""
        try:
            if xl_isinstance(value, xl_dict_type):
                items = xl_list_type(value.items())
            elif xl_isinstance(value, (xl_list_type, xl_tuple_type)):
                items = []
                for index in xl_range(xl_min(xl_len(value), limit)):
                    try:
                        items.append((xl_cheat_str_type(index), value[index]))
                    except Exception:
                        continue
            elif xl_hasattr(value, "__dict__"):
                items = xl_list_type(xl_vars(value).items())
            else:
                return []
        except Exception:
            return []
        pairs = []
        for key, item in items:
            if xl_len(pairs) >= limit:
                break
            if not xl_isinstance(key, xl_cheat_text_types):
                key = xl_cheat_str_type(key)
            key = xl_cheat_str_type(key)
            if key.startswith("_") or key.startswith("xl_"):
                continue
            pairs.append((key, item))
        return pairs

    def xl_cheat_sponsor_kind(name):
        """返回 None / 'code' / 'tier' / 'gift' / 'flag'"""
        low = (name or "").lower()
        for skip in XL_CHEAT_SPONSOR_SKIP:
            if skip in low:
                return None
        # 「已领取 / 已使用」这类状态优先按开关处理，别被 code 关键字吃掉
        for first, second in XL_CHEAT_SPONSOR_GIFT_PAIRS:
            if first in low and second in low:
                if "tier" in low or "level" in low or "rank" in low or "grade" in low:
                    return "tier"
                return "gift"
        for key in XL_CHEAT_SPONSOR_CODE_KEYS:
            if key in low:
                return "code"
        for key in XL_CHEAT_SPONSOR_KEYS:
            if key in low:
                if "tier" in low or "level" in low or "rank" in low or "grade" in low:
                    return "tier"
                return "flag"
        return None

    def xl_cheat_sponsor_dict_pending(value):
        """领取状态表：全部是布尔 / 0-1 时返回未领取条数，否则 -1（只读）"""
        try:
            keys = xl_list_type(value.keys())
        except Exception:
            return -1
        if not keys:
            return -1
        pending = 0
        for key in keys:
            try:
                item = value[key]
            except Exception:
                return -1
            if xl_isinstance(item, xl_bool):
                if not item:
                    pending += 1
                continue
            if xl_isinstance(item, xl_float):
                return -1
            if xl_cheat_is_number(item):
                try:
                    if xl_int(item) < 1:
                        pending += 1
                except Exception:
                    return -1
                continue
            return -1
        return pending


    def xl_cheat_sponsor_name(path):
        name = path
        if name.startswith("persistent."):
            name = name[len("persistent."):]
        elif name.startswith("default."):
            name = name[len("default."):]
        return name

    def xl_cheat_sponsor_target(name, value, kind=None):
        """返回 (解锁后的目标值, 是否需要修改)；不支持的类型返回 (None, False)"""
        kind = kind or xl_cheat_sponsor_kind(name)
        if kind is None:
            return None, False
        if xl_isinstance(value, xl_bool):
            return True, not value
        if xl_isinstance(value, xl_cheat_text_types) or xl_cheat_is_container(value):
            return None, False
        if not xl_cheat_is_number(value):
            return None, False
        if kind == "code":
            return None, False
        if kind == "tier":
            target = 3
        elif low_is_vip(name):
            # vip / 会员 这类词可能是货币，只认布尔开关，数值不动
            return None, False
        else:
            target = 1
        try:
            current = xl_float(value)
        except Exception:
            return None, False
        if current >= target:
            return None, False
        if xl_isinstance(value, xl_float):
            return xl_float(target), True
        return xl_int(target), True

    def low_is_vip(name):
        return "vip" in (name or "").lower()

    def xl_cheat_sponsor_entry(path, name, value, scope, kind=None):
        kind = kind or xl_cheat_sponsor_kind(name)
        if kind is None:
            return None
        entry = {
            "path": path,
            "name": name,
            "scope": scope,
            "kind": kind,
            "type": xl_cheat_type_name(value),
            "value": xl_cheat_describe(value, 60),
            "target": "",
            "unlocked": False,
            "editable": False,
            "note": "",
        }
        target, need = xl_cheat_sponsor_target(name, value, kind)
        label = "礼品码奖励" if kind == "gift" else "赞助奖励"
        if xl_isinstance(value, xl_bool):
            entry["unlocked"] = bool(value)
            entry["editable"] = True
            entry["target"] = "True"
            if not value:
                entry["note"] = label + "开关，可一键打开"
            return entry
        if xl_cheat_is_number(value):
            entry["unlocked"] = not need
            entry["editable"] = target is not None or not need
            if target is not None:
                entry["target"] = xl_cheat_describe(target)
            entry["note"] = ("等级标记" if kind == "tier" else label + "数值标记")
            if low_is_vip(name) and kind != "tier":
                entry["editable"] = False
                entry["note"] = "可能是货币，未自动修改"
            return entry
        if xl_isinstance(value, xl_cheat_text_types):
            entry["note"] = "码文本，需要在游戏里手动输入有效码"
            return entry
        if xl_isinstance(value, xl_dict_type):
            pending = xl_cheat_sponsor_dict_pending(value)
            if pending < 0:
                if kind == "code":
                    # 码表 / 校验表：只给出只读提示，具体码文得在游戏里输
                    entry["note"] = "码表（只读，游戏用它校验码，不能直接改）"
                    return entry
                # 混合结构的数据表（里面有文本/子表）：这里不给出只读条目，
                # 交给扫描继续下钻，去找里面真正的开关。
                return None
            entry["unlocked"] = pending == 0
            entry["editable"] = True
            entry["target"] = "全部领取"
            entry["note"] = "%s领取表，%d 项未领取" % (label, pending)
            return entry
        # 列表 / 元组 / 集合这类容器同样交给扫描下钻
        return None

    def xl_cheat_sponsor_scan():
        entries = []
        seen = {}
        budget = {"nodes": 0}

        def add(path, name, value, scope, depth, kind=None):
            if budget["nodes"] > 4000:
                return
            budget["nodes"] += 1
            entry = xl_cheat_sponsor_entry(path, name, value, scope, kind)
            if entry is not None:
                if entry["path"] not in seen:
                    seen[entry["path"]] = True
                    entries.append(entry)
                return
            if depth <= 0:
                return
            low = (name or "").lower()
            deep = False
            for token in XL_CHEAT_SPONSOR_DEEP:
                if token in low:
                    deep = True
                    break
            if not deep:
                return
            if kind is None:
                kind = xl_cheat_sponsor_kind(name)
            if xl_isinstance(value, (xl_dict_type, xl_list_type, xl_tuple_type)):
                pass
            elif (xl_hasattr(value, "__dict__") and not xl_isinstance(value, xl_type)
                  and not xl_cheat_engine_object(value)):
                pass
            else:
                return
            count = 0
            for child_name, child in xl_cheat_sponsor_children(value):
                count += 1
                if count > 80:
                    break
                add(path + "." + child_name, child_name, child, scope, depth - 1, kind)

        tables = (("", "存档", xl_cheat_store_dict()),
                  ("default.", "默认存档", xl_cheat_default_dict()))
        for prefix, scope, table in tables:
            for name in xl_list_type(table.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                low = xl_cheat_str_type(name).lower()
                if name.startswith("_") or low.startswith("xl_"):
                    continue
                try:
                    value = table[name]
                except Exception:
                    continue
                add(prefix + xl_cheat_str_type(name), xl_cheat_str_type(name), value, scope, 2)

        target = xl_cheat_persistent()
        if target is not None:
            try:
                names = xl_list_type(xl_vars(target).keys())
            except Exception:
                names = []
            for name in names:
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                if name.startswith("_"):
                    continue
                try:
                    value = xl_getattr(target, name)
                except Exception:
                    continue
                add("persistent." + xl_cheat_str_type(name), xl_cheat_str_type(name),
                    value, "持久化", 2)

        # 未解锁且可一键修改的排前面
        pending = [e for e in entries if e["editable"] and not e["unlocked"]]
        others = [e for e in entries if not (e["editable"] and not e["unlocked"])]
        others = xl_sorted(others, key=lambda item: item["path"].lower())
        return {
            "items": pending + others,
            "total": xl_len(entries),
            "locked": xl_len(pending),
            "codes": xl_len([e for e in entries if e["kind"] == "code"]),
        }

    def xl_cheat_sponsor_unlock(paths):
        changed = 0
        failed = []
        if paths is None:
            data = xl_cheat_sponsor_scan()
            paths = [e["path"] for e in data["items"] if e["editable"] and not e["unlocked"]]
        for path in paths:
            path = xl_cheat_str_type(path)
            try:
                value = xl_cheat_get(path)
            except Exception as error:
                failed.append([path, "%s: %s" % (xl_type(error).__name__, error)])
                continue
            # 领取状态表：逐条把 False / 0 改成已领取
            if xl_isinstance(value, xl_dict_type) and xl_cheat_sponsor_dict_pending(value) > 0:
                try:
                    keys = xl_list_type(value.keys())
                except Exception:
                    keys = []
                for key in keys:
                    try:
                        item = value[key]
                    except Exception:
                        continue
                    if xl_isinstance(item, xl_bool):
                        target = True
                    elif xl_cheat_is_number(item) and xl_int(item) < 1:
                        target = xl_int(1)
                    else:
                        continue
                    try:
                        xl_cheat_sponsor_backup.append(["dict", path, key, item])
                        value[key] = target
                        changed += 1
                    except Exception as error:
                        failed.append([path, "%s: %s" % (xl_type(error).__name__, error)])
                continue
            target, need = xl_cheat_sponsor_target(xl_cheat_sponsor_name(path), value)
            if target is None or not need:
                continue
            try:
                xl_cheat_sponsor_backup.append(["set", path, None, value])
                xl_cheat_set(path, target)
                changed += 1
            except Exception as error:
                failed.append([path, "%s: %s" % (xl_type(error).__name__, error)])
        return changed, failed

    def xl_cheat_sponsor_undo():
        restored = 0
        for kind, path, key, old in reversed(xl_cheat_sponsor_backup):
            try:
                if kind == "dict":
                    container = xl_cheat_get(path)
                    container[key] = old
                else:
                    xl_cheat_set(path, old)
                restored += 1
            except Exception:
                pass
        del xl_cheat_sponsor_backup[:]
        return restored

    # ------------------------------------------------------------------
    # 按名称搜索：直接输属性名 / 变量名 / 字典键名，不需要先知道数值
    # ------------------------------------------------------------------
    def xl_cheat_find_names(keyword, limit=300):
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return []
        try:
            limit = xl_int(limit)
        except Exception:
            limit = 300
        if limit <= 0:
            limit = 300

        store = xl_cheat_store_dict()
        found = []
        seen = set()
        budget = {"nodes": 0}
        # 全量名称搜索要下钻到壳里的 .Value（第 4~5 层），节点数会变多；
        # 用节点预算 + 时间上限兜住，保证不会拖到客户端超时。
        deadline = xl_cheat_time.time() + 5.5

        def consider(owner, key, value, path=None):
            low = key.lower()
            if keyword == low:
                rank = 0
            elif low.startswith(keyword):
                rank = 1
            elif keyword in low:
                rank = 2
            else:
                return
            if path is None:
                path = key if not owner else owner + "." + key
            if path in seen:
                return
            seen.add(path)
            found.append((rank, path.count("."), path, {
                "name": key,
                "path": path,
                "owner": owner or "全局",
                "type": xl_cheat_type_name(value),
                "value": xl_cheat_describe(value, 80),
            }))

        def children(obj):
            try:
                if xl_isinstance(obj, xl_dict_type):
                    return xl_list_type(obj.items())
                if xl_isinstance(obj, (xl_list_type, xl_tuple_type)):
                    # 列表/元组要按下标遍历：Relations.data 就是「记录列表」，
                    # 之前只认 dict / 对象，整片列表数据都搜不到。
                    pairs = []
                    for index in xl_range(xl_min(xl_len(obj), 400)):
                        try:
                            pairs.append((xl_cheat_str_type(index), obj[index]))
                        except Exception:
                            continue
                    return pairs
                if xl_hasattr(obj, "__dict__"):
                    entries = xl_list_type(xl_vars(obj).items())
                    pairs = xl_list_type(entries)
                    known = set()
                    for key in xl_list_type(xl_vars(obj).keys()):
                        known.add(key)
                    # 类上声明的默认值（ActorData.love = 0）：好感没涨过时实例里
                    # 根本没有 love 字段，只读 vars() 会整片漏掉，属性识别页却能看到。
                    try:
                        class_items = xl_list_type(
                            xl_getattr(xl_type(obj), "__dict__", {}).items())
                    except Exception:
                        class_items = []
                    added = 0
                    for key, value in class_items:
                        if added >= 40:
                            break
                        if not xl_isinstance(key, xl_cheat_text_types) or key.startswith("_"):
                            continue
                        if key in known or xl_callable(value) or value is None:
                            continue
                        if not xl_cheat_scalar(value):
                            continue
                        pairs.append((key, value))
                        known.add(key)
                        added += 1
                    return pairs
            except Exception:
                pass
            return []

        def walk(owner, obj, depth):
            if budget["nodes"] > 200000 or xl_len(found) >= limit * 3:
                return
            budget["nodes"] += 1
            if xl_cheat_time.time() > deadline:
                return
            for key, value in children(obj)[:800]:
                raw_key = key
                if not xl_isinstance(key, xl_cheat_text_types):
                    # ObjectsList 这类容器用整数键，转成文本才能拼出可回写的路径
                    if xl_cheat_is_number(key):
                        raw_key = xl_cheat_str_type(xl_int(key))
                    else:
                        continue
                if not raw_key:
                    continue
                if "." in raw_key:
                    continue
                # 私有字段名 _GameData__interest → 用 interest 参与匹配，
                # 但路径仍保留原名，才能回写
                match_key = raw_key
                if raw_key.startswith("__"):
                    continue
                if raw_key.startswith("_"):
                    if "__" not in raw_key:
                        continue
                    match_key = raw_key.split("__", 1)[1]
                    if not match_key or match_key.startswith("_"):
                        continue
                if match_key.lower().startswith("xl_cheat"):
                    continue
                path = (owner + "." + raw_key) if owner else raw_key
                if xl_cheat_scalar(value):
                    consider(owner, match_key, value, path)
                    continue
                # 数值常包在 DynamicValue / DynamicVar 这类壳里：
                # 名字（love / friendship / opinion）在壳上，真正的数在 .Value 上。
                # 只比名字就会漏掉这些属性，必须把壳里的 Value 也当成候选。
                wrapped = None
                if xl_hasattr(value, "Value"):
                    try:
                        wrapped = xl_getattr(value, "Value")
                    except Exception:
                        wrapped = None
                if wrapped is not None and xl_cheat_scalar(wrapped):
                    consider(owner, match_key, wrapped, path + ".Value")
                    continue
                if depth >= 5:
                    continue
                if xl_isinstance(value, xl_cheat_types.ModuleType):
                    continue
                if xl_isinstance(value, xl_type):
                    continue
                # 可调用但带 __dict__ 的是游戏数据对象，继续往下走
                if xl_callable(value) and not xl_hasattr(value, "__dict__"):
                    continue
                if xl_cheat_engine_object(value):
                    continue
                walk(owner + "." + raw_key if owner else raw_key, value, depth + 1)

        skip_names = XL_CHEAT_SCOPE_SKIP
        # 普通 store 与 default store 都搜：主菜单时游戏变量只在 default 里
        for prefix, table in (("", store), ("default.", xl_cheat_default_dict())):
            for name, value in xl_list_type(table.items()):
                if not xl_isinstance(name, xl_cheat_text_types) or not name:
                    continue
                if name.startswith("_") or xl_cheat_str_type(name).lower() in skip_names:
                    continue
                if name.lower().startswith("xl_cheat"):
                    continue
                if xl_cheat_scalar(value):
                    consider(prefix.rstrip("."), name, value)
                    continue
                # 顶层的数值壳（极少数游戏会把 love 这种变量本身做成 DynamicValue）
                wrapped = None
                if xl_hasattr(value, "Value"):
                    try:
                        wrapped = xl_getattr(value, "Value")
                    except Exception:
                        wrapped = None
                if wrapped is not None and xl_cheat_scalar(wrapped):
                    consider(prefix.rstrip("."), name, wrapped, prefix + name + ".Value")
                    continue
                if xl_isinstance(value, xl_cheat_types.ModuleType):
                    continue
                if xl_isinstance(value, xl_type):
                    continue
                if xl_callable(value) and not xl_hasattr(value, "__dict__"):
                    continue
                if xl_cheat_engine_object(value):
                    continue
                try:
                    walk(prefix + name, value, 0)
                except Exception as error:
                    xl_cheat_log("名称搜索异常 %s：%s: %s"
                                 % (name, xl_type(error).__name__, error))

        # persistent 里的数据路径以 persistent. 开头，同样支持搜索
        target = xl_cheat_persistent()
        if target is not None:
            try:
                walk("persistent", target, 0)
            except Exception:
                pass

        found = xl_sorted(found, key=lambda entry: (entry[0], entry[1], entry[2]))
        items = [entry[3] for entry in found[:limit]]
        return items

    # ------------------------------------------------------------------
    # 文本本地化：物品/角色名在数据表里是原文（韩文），用引擎翻译表转成当前语言
    # ------------------------------------------------------------------
    xl_cheat_i18n_cache = None
    xl_cheat_i18n_stamp = ""

    def xl_cheat_i18n_table():
        """工具写下的中文对照表（任意游戏都由工具自动提取）。
        游戏没在设置里选中文时，Ren'Py 不会加载中文 tl 脚本，
        引擎自带的 translate_string 查不到译文，只能靠这份离线表。
        每次请求都检查文件是否变了，换游戏/工具重写后无需重启游戏。"""
        global xl_cheat_i18n_cache, xl_cheat_i18n_stamp
        path = ""
        stamp = ""
        try:
            gamedir = xl_cheat_conf("gamedir")
            if gamedir:
                path = xl_cheat_os.path.join(gamedir, "xl_cheat_i18n.json")
                info = xl_cheat_os.stat(path)
                stamp = "%d_%d" % (xl_int(info.st_mtime), xl_int(info.st_size))
        except Exception:
            path = ""
            stamp = ""
        if xl_cheat_i18n_cache is not None and stamp == xl_cheat_i18n_stamp:
            return xl_cheat_i18n_cache
        table = {}
        if path and stamp:
            try:
                with xl_cheat_io.open(path, "r", encoding="utf-8") as handle:
                    loaded = xl_cheat_json.load(handle)
                if xl_isinstance(loaded, xl_dict_type):
                    table = loaded
            except Exception:
                table = {}
        xl_cheat_i18n_cache = table
        xl_cheat_i18n_stamp = stamp
        return table

    def xl_cheat_localize(text):
        """优先查离线中文对照表，再按游戏当前语言翻译"""
        if not xl_isinstance(text, xl_cheat_text_types) or not text:
            return text
        key = text.strip()
        table = xl_cheat_i18n_table()
        if table:
            try:
                translated = table.get(key)
            except Exception:
                translated = None
            if xl_isinstance(translated, xl_cheat_text_types) and translated:
                return translated
        func = xl_getattr(renpy, "translate_string", None)
        if not xl_callable(func):
            return text
        for language in (None, "chinese_simplified", "chinese_traditional", "chinese"):
            try:
                translated = func(text) if language is None else func(text, language)
            except Exception:
                continue
            if (xl_isinstance(translated, xl_cheat_text_types)
                    and translated.strip() and translated != text):
                return translated
        return text

    def xl_cheat_language():
        try:
            import renpy.game as xl_cheat_game_language
            language = xl_cheat_game_language.preferences.language
            return language or "None"
        except Exception:
            return "None"

    # ------------------------------------------------------------------
    # 物品：读取物品表 / 背包，并支持直接添加
    # 各家游戏结构差别很大，这里按「数据结构特征」识别而不是写死变量名
    # ------------------------------------------------------------------
    XL_CHEAT_NAME_FIELDS = ("name", "itemname", "item_name", "displayname",
                            "display_name", "title", "label", "cn_name")
    XL_CHEAT_DESC_FIELDS = ("desc", "description", "info", "intro", "text")
    XL_CHEAT_CATE_FIELDS = ("cate", "category", "type", "kind", "group")
    XL_CHEAT_PRICE_FIELDS = ("price", "cost", "sell", "buy", "value")
    XL_CHEAT_ID_FIELDS = ("pkey", "id", "item_id", "itemid", "key", "item", "code")
    XL_CHEAT_COUNT_FIELDS = ("count", "amount", "num", "qty", "quantity",
                             "number", "stack")
    XL_CHEAT_BAG_HINTS = ("inventory", "inv", "bag", "backpack", "items", "item",
                          "storage", "仓库", "背包", "道具")

    def xl_cheat_field(obj, names, default=None):
        """按字段名取值（不区分大小写），dict 与对象都支持"""
        try:
            if xl_isinstance(obj, xl_dict_type):
                for key in xl_list_type(obj.keys()):
                    if not xl_isinstance(key, xl_cheat_text_types):
                        continue
                    if xl_cheat_str_type(key).lower() in names:
                        return obj[key]
            else:
                attrs = xl_vars(obj)
                for attr in xl_list_type(attrs.keys()):
                    if xl_cheat_str_type(attr).lower() in names:
                        return attrs[attr]
        except Exception:
            pass
        return default

    def xl_cheat_looks_like_item(obj):
        if not (xl_isinstance(obj, xl_dict_type) or xl_hasattr(obj, "__dict__")):
            return False
        return (xl_cheat_field(obj, XL_CHEAT_NAME_FIELDS) is not None
                or xl_cheat_field(obj, XL_CHEAT_ID_FIELDS) is not None)

    def xl_cheat_catalog_row(key, meta):
        name = xl_cheat_field(meta, XL_CHEAT_NAME_FIELDS)
        if name is None:
            name = key
        return {
            "pKey": xl_cheat_str_type(key),
            "name": xl_cheat_localize(xl_cheat_describe(name, 60)),
            "desc": xl_cheat_localize(xl_cheat_describe(
                xl_cheat_field(meta, XL_CHEAT_DESC_FIELDS, ""), 80)),
            "cate": xl_cheat_describe(xl_cheat_field(meta, XL_CHEAT_CATE_FIELDS, ""), 20),
            "price": xl_cheat_describe(xl_cheat_field(meta, XL_CHEAT_PRICE_FIELDS, ""), 20),
            "grade": xl_cheat_describe(
                xl_cheat_field(meta, ("grade", "rarity", "quality"), ""), 10),
        }

    def xl_cheat_build_catalog(table):
        catalog = {}
        if xl_isinstance(table, xl_dict_type):
            for key in xl_list_type(table.keys()):
                try:
                    meta = table[key]
                except Exception:
                    continue
                if not (xl_isinstance(meta, xl_dict_type) or xl_hasattr(meta, "__dict__")):
                    continue
                if xl_isinstance(meta, xl_cheat_text_types):
                    continue
                try:
                    if xl_cheat_field(meta, ("is_active",), 1) in (0, "0", False):
                        continue
                except Exception:
                    pass
                catalog[xl_cheat_str_type(key)] = xl_cheat_catalog_row(key, meta)
        elif xl_isinstance(table, (xl_list_type, xl_tuple_type)):
            for index in xl_range(xl_len(table)):
                meta = table[index]
                if not (xl_isinstance(meta, xl_dict_type) or xl_hasattr(meta, "__dict__")):
                    continue
                key = xl_cheat_field(meta, XL_CHEAT_ID_FIELDS)
                if key is None:
                    key = index
                catalog[xl_cheat_str_type(key)] = xl_cheat_catalog_row(key, meta)
        return catalog

    def xl_cheat_item_catalog(data):
        """自动找物品定义表：先认 TB_Item 这类命名，再按数据结构通用识别"""
        candidates = []
        for name in xl_list_type(data.keys()):
            if not xl_isinstance(name, xl_cheat_text_types) or name.startswith("_"):
                continue
            low = name.lower()
            try:
                value = data[name]
            except Exception:
                continue
            if not (xl_isinstance(value, xl_dict_type)
                    or xl_isinstance(value, (xl_list_type, xl_tuple_type))):
                continue
            sample_len = xl_len(value)
            if sample_len < 3:
                continue
            if xl_isinstance(value, xl_dict_type):
                sample_keys = xl_list_type(value.keys())[:8]
            else:
                sample_keys = xl_range(xl_min(sample_len, 8))
            hits = 0
            for key in sample_keys:
                try:
                    meta = value[key]
                except Exception:
                    continue
                if xl_cheat_looks_like_item(meta):
                    hits += 1
            if hits < 3:
                continue
            named = ("item" in low or "goods" in low
                     or "物品" in low or "道具" in low)
            table_like = (low.startswith("tb_") or low.endswith("_table")
                          or low in ("items", "itemdata", "item_data",
                                     "itemlist", "item_list", "shop"))
            score = hits * 3
            if named:
                score += 8
            if table_like:
                score += 6
            candidates.append((score, name, value))
        if not candidates:
            return xl_cheat_var_catalog(data), ""
        candidates.sort(key=lambda item: (-item[0], item[1]))
        _score, source, table = candidates[0]
        return xl_cheat_build_catalog(table), source

    def xl_cheat_var_catalog(data):
        """兜底：把 item_xxx / itm_xxx / goods_xxx 这类数值计数器当成道具
        有些游戏没有物品定义表，道具只是若干独立变量（如 item_dress_A01_gift）。
        """
        catalog = {}
        for name in xl_list_type(data.keys()):
            if not xl_isinstance(name, xl_cheat_text_types) or name.startswith("_"):
                continue
            low = xl_cheat_str_type(name).lower()
            if not (low.startswith("item_") or low.startswith("itm_")
                    or low.startswith("goods_") or low.startswith("prop_")):
                continue
            try:
                value = data[name]
            except Exception:
                continue
            if not xl_cheat_is_number(value):
                continue
            catalog[xl_cheat_str_type(name)] = {
                "pKey": xl_cheat_str_type(name),
                "name": xl_cheat_localize(xl_cheat_str_type(name)),
                "desc": "变量型道具（直接控制该变量数值）",
                "cate": "变量道具",
                "price": "",
                "grade": "",
                "var": True,
            }
        return catalog

    def xl_cheat_inventory_score(name, value, catalog):
        """判断某个变量是否像背包，返回 (得分, 类型) 或 None"""
        if not xl_isinstance(name, xl_cheat_text_types):
            return None
        low = xl_cheat_str_type(name).lower()
        hint = False
        for word in XL_CHEAT_BAG_HINTS:
            if word in low:
                hint = True
                break
        strong = ("inventoryitem" in low or low.endswith("_items")
                  or low in ("inventory", "bag", "backpack", "items"))
        if xl_isinstance(value, xl_list_type):
            sample = []
            for index in xl_range(xl_min(xl_len(value), 6)):
                try:
                    sample.append(value[index])
                except Exception:
                    pass
            if not sample:
                return (5 + (6 if hint else 0) + (6 if strong else 0), "list") if hint else None
            good = 0
            for entry in sample:
                if not (xl_isinstance(entry, xl_dict_type)
                        or xl_hasattr(entry, "__dict__")):
                    continue
                if xl_cheat_field(entry, XL_CHEAT_COUNT_FIELDS) is not None:
                    good += 1
            if good == xl_len(sample):
                return (10 + (6 if hint else 0) + (6 if strong else 0), "list")
            return None
        if xl_isinstance(value, xl_dict_type):
            if not value:
                return (5 + (6 if hint else 0) + (6 if strong else 0), "countmap") if hint else None
            keys = xl_list_type(value.keys())
            sample = keys[:8]
            numbers = 0
            known = 0
            for key in sample:
                try:
                    sub = value[key]
                except Exception:
                    continue
                if xl_cheat_is_number(sub):
                    numbers += 1
                if xl_isinstance(key, xl_cheat_text_types):
                    if not catalog or xl_cheat_str_type(key) in catalog:
                        known += 1
            if numbers == xl_len(sample):
                return (8 + (6 if hint else 0) + (4 if known else 0), "countmap")
            return None
        return None

    def xl_cheat_pick_inventory(data, catalog):
        best = None
        for name in xl_list_type(data.keys()):
            if not xl_isinstance(name, xl_cheat_text_types) or name.startswith("_"):
                continue
            try:
                value = data[name]
            except Exception:
                continue
            candidate = xl_cheat_inventory_score(name, value, catalog)
            if candidate:
                row = {"score": candidate[0], "name": name, "value": value,
                       "kind": candidate[1], "path": xl_cheat_str_type(name)}
                if best is None or row["score"] > best["score"]:
                    best = row
            # 对象内部再找一层，如 inventory.items
            if xl_isinstance(value, xl_dict_type) or not xl_hasattr(value, "__dict__"):
                continue
            low = xl_cheat_str_type(name).lower()
            if not any(word in low for word in XL_CHEAT_BAG_HINTS):
                continue
            attrs = xl_vars(value)
            for attr in xl_list_type(attrs.keys()):
                low_attr = xl_cheat_str_type(attr).lower()
                if not any(word in low_attr for word in XL_CHEAT_BAG_HINTS):
                    continue
                try:
                    inner = xl_getattr(value, attr)
                except Exception:
                    continue
                candidate = xl_cheat_inventory_score(attr, inner, catalog)
                if candidate:
                    row = {"score": candidate[0] + 3, "name": attr, "value": inner,
                           "kind": candidate[1],
                           "path": xl_cheat_str_type(name) + "." + xl_cheat_str_type(attr),
                           "owner": name}
                    if best is None or row["score"] > best["score"]:
                        best = row
        if best is None:
            return None
        value = best["value"]
        best["id_field"] = "pkey"
        best["count_field"] = "count"
        if best["kind"] == "list" and xl_len(value):
            entry = value[0]
            for field in XL_CHEAT_ID_FIELDS:
                if xl_cheat_field(entry, (field,)) is not None:
                    best["id_field"] = field
                    break
            for field in XL_CHEAT_COUNT_FIELDS:
                if xl_cheat_field(entry, (field,)) is not None:
                    best["count_field"] = field
                    break
        return best

    def xl_cheat_inventory_var(data):
        info = xl_cheat_pick_inventory(data, {})
        if info is None:
            return "", None
        return info["path"], info["value"]

    def xl_cheat_field_key(obj, names):
        """返回实际字段名（保留原始大小写），找不到返回 None"""
        try:
            if xl_isinstance(obj, xl_dict_type):
                for key in xl_list_type(obj.keys()):
                    if not xl_isinstance(key, xl_cheat_text_types):
                        continue
                    if xl_cheat_str_type(key).lower() in names:
                        return xl_cheat_str_type(key)
            else:
                attrs = xl_vars(obj)
                for attr in xl_list_type(attrs.keys()):
                    if xl_cheat_str_type(attr).lower() in names:
                        return xl_cheat_str_type(attr)
        except Exception:
            pass
        return None

    def xl_cheat_item_entry(obj, index, catalog, source, info=None):
        info = info or {}
        id_field = info.get("id_field") or "pkey"
        count_field = info.get("count_field") or "count"
        key = xl_cheat_field(obj, (id_field,))
        if key is None:
            key = xl_cheat_field(obj, XL_CHEAT_ID_FIELDS)
        if key is None:
            key = ""
        count = xl_cheat_field(obj, (count_field,), None)
        if count is None:
            count = xl_cheat_field(obj, XL_CHEAT_COUNT_FIELDS, 0)
        # 指针落到数量字段本身：列表里的物品是 dict / 对象，直接指向条目会
        # 把整个物品替换成一个数字（曾把道具写成 int，需精确到 .count）
        count_key = xl_cheat_field_key(obj, (count_field,) + XL_CHEAT_COUNT_FIELDS)
        key_text = xl_cheat_str_type(key)
        row = catalog.get(key_text) or {}
        if not row:
            name = xl_cheat_field(obj, XL_CHEAT_NAME_FIELDS)
            if name is not None:
                row = {"name": xl_cheat_localize(xl_cheat_describe(name, 60))}
        path = "%s.%d" % (source, index)
        if count_key:
            path = path + "." + count_key
        return {
            "pKey": key_text,
            "name": row.get("name") or key_text,
            "count": xl_cheat_describe(count, 20),
            "cate": row.get("cate", ""),
            "grade": row.get("grade", ""),
            "desc": row.get("desc", ""),
            "path": path,
        }

    def xl_cheat_item_inventory(data, catalog):
        info = xl_cheat_pick_inventory(data, catalog)
        if info is None:
            return [], ""
        inventory = info["value"]
        source = info["path"]
        entries = []
        if info["kind"] == "countmap":
            for key in xl_list_type(inventory.keys()):
                try:
                    count = inventory[key]
                except Exception:
                    continue
                key_text = xl_cheat_str_type(key)
                row = catalog.get(key_text) or {}
                entries.append({
                    "pKey": key_text,
                    "name": row.get("name") or key_text,
                    "count": xl_cheat_describe(count, 20),
                    "cate": row.get("cate", ""),
                    "grade": row.get("grade", ""),
                    "desc": row.get("desc", ""),
                    "path": "%s.%s" % (source, key_text),
                })
            return entries, source
        for index in xl_range(xl_len(inventory)):
            try:
                obj = inventory[index]
            except Exception:
                continue
            try:
                entries.append(xl_cheat_item_entry(obj, index, catalog, source, info))
            except Exception:
                continue
        return entries, source

    def xl_cheat_item_count(data, key):
        func = data.get("GetItemCount")
        if xl_callable(func):
            try:
                return xl_int(func(key))
            except Exception:
                pass
        info = xl_cheat_pick_inventory(data, {})
        if info is None:
            return 0
        inventory = info["value"]
        if info["kind"] == "countmap":
            try:
                return xl_int(inventory.get(key, 0))
            except Exception:
                return 0
        total = 0
        for index in xl_range(xl_len(inventory)):
            try:
                entry = xl_cheat_item_entry(inventory[index], index, {}, info["path"], info)
                if entry["pKey"] == key:
                    total += xl_int(entry["count"])
            except Exception:
                continue
        return total

    def xl_cheat_item_add(data, key, count):
        """优先调用游戏自带的添加函数，其次按背包结构直接写入"""
        # 变量型道具（item_xxx 计数器）：直接加数值
        try:
            direct = data.get(key)
        except Exception:
            direct = None
        if xl_cheat_is_number(direct):
            xl_cheat_set(key, xl_int(direct) + count)
            return "var"
        for fname in ("PutItemNoNotice", "PutItem", "AddItem", "GiveItem"):
            func = data.get(fname)
            if not xl_callable(func):
                continue
            for args in ((key, count), (key, count, 2), (key, count, 0), (key,)):
                try:
                    func(*args)
                    return fname
                except Exception:
                    continue
        info = xl_cheat_pick_inventory(data, xl_cheat_item_catalog(data)[0])
        if info is None:
            raise ValueError("找不到背包变量，无法添加物品")
        inventory = info["value"]
        if info["kind"] == "countmap":
            try:
                current = inventory.get(key)
                inventory[key] = count if current is None else xl_int(current) + count
                return "countmap"
            except Exception as error:
                raise ValueError("写入背包失败：%s" % error)
        id_field = info.get("id_field") or "pkey"
        count_field = info.get("count_field") or "count"
        for index in xl_range(xl_len(inventory)):
            try:
                obj = inventory[index]
                entry = xl_cheat_item_entry(obj, index, {}, info["path"], info)
                if entry["pKey"] != key:
                    continue
                current = xl_cheat_field(obj, (count_field,), 0)
                if xl_isinstance(obj, xl_dict_type):
                    obj[count_field] = xl_int(current) + count
                else:
                    setattr(obj, count_field, xl_int(current) + count)
                return "stack"
            except Exception:
                continue
        # 背包所在对象可能自带添加方法（inventory.items 这类结构）
        owner = info.get("owner")
        if owner is not None:
            try:
                owner_obj = xl_cheat_get(xl_cheat_str_type(owner))
            except Exception:
                owner_obj = None
            if owner_obj is not None:
                for fname in ("AddItem", "Add", "PutItem", "Put", "GiveItem",
                              "AddItemToInventory"):
                    func = xl_getattr(owner_obj, fname, None)
                    if not xl_callable(func):
                        continue
                    for args in ((key, count), (key,), (count, key)):
                        try:
                            func(*args)
                            return "method:" + fname
                        except Exception:
                            continue
        # 用现有元素当模板构造一条新记录
        template = None
        if xl_len(inventory):
            try:
                template = inventory[0]
            except Exception:
                template = None
        if template is not None and xl_isinstance(template, xl_dict_type):
            row = xl_dict_type()
            for field in xl_list_type(template.keys()):
                row[field] = template[field]
            row[id_field] = key
            row[count_field] = count
            inventory.append(row)
            return "append-dict"
        cls = data.get("ItemData")
        if xl_callable(cls):
            obj = cls(key)
            try:
                setattr(obj, count_field, count)
            except Exception:
                pass
            inventory.append(obj)
            return "append"
        if template is not None:
            try:
                obj = xl_type(template).__new__(xl_type(template))
                xl_setattr(obj, id_field, key)
                xl_setattr(obj, count_field, count)
                inventory.append(obj)
                return "append-copy"
            except Exception:
                pass
        row = xl_dict_type()
        row[id_field] = key
        row[count_field] = count
        inventory.append(row)
        return "append-dict"

    # ------------------------------------------------------------------
    # 数值锁定
    # ------------------------------------------------------------------
    def xl_cheat_apply_frozen(force=False):
        global xl_cheat_last_freeze
        if not xl_cheat_frozen:
            return
        now = xl_cheat_time.time()
        if not force and now - xl_cheat_last_freeze < 0.2:
            return
        xl_cheat_last_freeze = now
        changed = False
        for path in xl_list_type(xl_cheat_frozen.keys()):
            value = xl_cheat_frozen[path]
            try:
                current = xl_cheat_get(path)
                try:
                    same = (current == value)
                except Exception:
                    same = False
                if not same:
                    xl_cheat_set(path, value)
                    changed = True
            except Exception as error:
                xl_cheat_log("锁定失败，已移除 %s：%s" % (path, error))
                try:
                    del xl_cheat_frozen[path]
                except Exception:
                    pass
        if changed:
            try:
                renpy.restart_interaction()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 请求分发
    # ------------------------------------------------------------------
    def xl_cheat_list_items(scope, keyword, show_objects):
        items = []
        keyword = (keyword or "").strip().lower()
        if scope == "persistent":
            source = {}
            obj = xl_cheat_persistent()
            try:
                source = xl_dict_type(xl_vars(obj))
            except Exception:
                source = {}
            for name in xl_sorted(source.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                value = source[name]
                if not xl_cheat_visible_name(name, value, show_objects):
                    continue
                if keyword and keyword not in name.lower():
                    continue
                path = "persistent." + name
                items.append({
                    "name": name,
                    "path": path,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value),
                    "editable": xl_cheat_editable(value),
                    "frozen": path in xl_cheat_frozen,
                })
        else:
            data = xl_cheat_store_dict()
            for name in xl_sorted(data.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                try:
                    value = data[name]
                except Exception:
                    continue
                if not xl_cheat_visible_name(name, value, show_objects):
                    continue
                if keyword and keyword not in name.lower():
                    continue
                items.append({
                    "name": name,
                    "path": name,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value),
                    "editable": xl_cheat_editable(value),
                    "frozen": name in xl_cheat_frozen,
                })
        return items

    # ------------------------------------------------------------------
    # 对话功能解锁：跳过未读文本 / 回退
    # 有些游戏设置里根本没有「未读的文本也跳过」「返回」这两个开关，
    # 这里直接把引擎里对应的偏好和 config 打开，让游戏自带的跳过、回退生效。
    #
    # 回退要同时处理四层，少一层就会出现「滚轮没反应」或「只能退一两句」：
    #   1. config.rollback_enabled / hard_rollback_limit / rollback_length；
    #   2. config.keymap 里的 rollback / rollforward 键位（滚轮上下），
    #      改完必须清 keymap 缓存，否则引擎仍用旧的编译结果；
    #   3. store._rollback 与所有 context.rollback —— renpy.rollback() 的前置检查；
    #   4. RollbackLog.block 换成空函数，并把 rollback_limit 顶到历史长度
    #      —— 游戏用 block_rollback() 掐断回退才是「只能退一两句」的真正原因。
    #
    # 设置会写进 persistent，重启游戏后自动恢复。
    # ------------------------------------------------------------------
    xl_cheat_unlock_flags = {"skip": None, "rollback": None}
    xl_cheat_unlock_saved = {
        "loaded": False, "allow_skipping": None, "skip_after": None,
        "rollback_before": None, "hard_limit_before": None,
        "rollback_length_before": None, "keymap_before": None,
        "store_rollback_before": None, "context_rollback_before": None,
        "block_patched": False,
    }

    # 回退 / 前进必须存在的键位：滚轮上下、PageUp/Down、安卓返回键
    xl_cheat_rollback_keys = {
        "rollback": ["mousedown_4", "any_K_PAGEUP", "any_KP_PAGEUP", "K_AC_BACK"],
        "rollforward": ["mousedown_5", "any_K_PAGEDOWN", "any_KP_PAGEDOWN"],
    }
    # 回退历史条数（默认引擎只有 128，部分游戏还会改成个位数）
    XL_CHEAT_ROLLBACK_LIMIT = 512

    # 引擎里的原始 block 方法放在 sys 上，别塞进 store（store 变量会被写进存档）
    def xl_cheat_rollback_state():
        state = xl_getattr(xl_cheat_sys, "_xl_cheat_rollback_state", None)
        if state is None:
            state = {"block_orig": None}
            xl_setattr(xl_cheat_sys, "_xl_cheat_rollback_state", state)
        return state

    def xl_cheat_rollback_log():
        try:
            import renpy.game as xl_cheat_game_log
            return xl_getattr(xl_cheat_game_log, "log", None)
        except Exception:
            return None

    def xl_cheat_rollback_class():
        try:
            import renpy.rollback as xl_cheat_rollback_module
            cls = xl_getattr(xl_cheat_rollback_module, "RollbackLog", None)
            if xl_isinstance(cls, xl_type):
                return cls
        except Exception:
            pass
        log = xl_cheat_rollback_log()
        if log is not None:
            return xl_type(log)
        return None

    def xl_cheat_rollback_block_noop(*args, **kwargs):
        """顶替 RollbackLog.block：游戏调用 block_rollback() 不再掐断回退"""
        return None

    def xl_cheat_keymap_clear_cache():
        try:
            import renpy.display.behavior as xl_cheat_behavior
            clear = xl_getattr(xl_cheat_behavior, "clear_keymap_cache", None)
            if clear is not None:
                clear()
        except Exception:
            pass

    def xl_cheat_rollback_config(on):
        cfg = xl_cheat_config_module()
        if cfg is None:
            xl_cheat_log("取不到 config，回退开关无法设置")
            return False
        saved = xl_cheat_unlock_saved
        if on:
            # 记住游戏原本的回退开关，关闭时还原，别把游戏自带的能力关掉
            if saved.get("rollback_before") is None:
                try:
                    saved["rollback_before"] = bool(xl_getattr(cfg, "rollback_enabled", True))
                except Exception:
                    saved["rollback_before"] = True
            try:
                cfg.rollback_enabled = True
            except Exception as error:
                xl_cheat_log("打开 rollback_enabled 失败：%s" % error)
            # 部分游戏把回退上限设成个位数，甚至 0，打开了也退不回去
            for key, attr in (("hard_limit_before", "hard_rollback_limit"),
                              ("rollback_length_before", "rollback_length")):
                try:
                    current = xl_int(xl_getattr(cfg, attr, 0) or 0)
                except Exception as error:
                    xl_cheat_log("读取 %s 失败：%s" % (attr, error))
                    continue
                if saved.get(key) is None:
                    saved[key] = current
                if current < XL_CHEAT_ROLLBACK_LIMIT:
                    try:
                        xl_setattr(cfg, attr, XL_CHEAT_ROLLBACK_LIMIT)
                    except Exception as error:
                        xl_cheat_log("设置 %s 失败：%s" % (attr, error))
            return True
        before = saved.get("rollback_before")
        if before is None:
            return True
        try:
            cfg.rollback_enabled = bool(before)
            saved["rollback_before"] = None
        except Exception:
            return False
        for key, attr in (("hard_limit_before", "hard_rollback_limit"),
                          ("rollback_length_before", "rollback_length")):
            value = saved.get(key)
            if value is None:
                continue
            try:
                xl_setattr(cfg, attr, xl_int(value))
                saved[key] = None
            except Exception:
                pass
        return True

    def xl_cheat_rollback_keymap(on):
        cfg = xl_cheat_config_module()
        if cfg is None:
            return False
        try:
            keymap = xl_getattr(cfg, "keymap", None)
        except Exception:
            keymap = None
        if not xl_isinstance(keymap, xl_dict_type):
            return False
        saved = xl_cheat_unlock_saved
        changed = False
        if on:
            before = saved.get("keymap_before")
            if before is None:
                before = {}
                for name in xl_cheat_rollback_keys:
                    try:
                        current = keymap.get(name)
                    except Exception:
                        current = None
                    if xl_isinstance(current, (xl_list_type, xl_tuple_type)):
                        before[name] = xl_list_type(current)
                    else:
                        before[name] = None
                saved["keymap_before"] = before
            for name in xl_cheat_rollback_keys:
                try:
                    current = keymap.get(name)
                except Exception:
                    current = None
                if xl_isinstance(current, (xl_list_type, xl_tuple_type)):
                    items = xl_list_type(current)
                    added = False
                else:
                    items = xl_list_type()
                    added = True
                for key in xl_cheat_rollback_keys[name]:
                    if key not in items:
                        items.append(key)
                        added = True
                if added:
                    try:
                        keymap[name] = items
                        changed = True
                    except Exception:
                        pass
        else:
            before = saved.get("keymap_before")
            if before is not None:
                for name in before:
                    original = before.get(name)
                    try:
                        if original is None:
                            keymap.pop(name, None)
                        else:
                            keymap[name] = xl_list_type(original)
                        changed = True
                    except Exception:
                        pass
                saved["keymap_before"] = None
        if changed:
            xl_cheat_keymap_clear_cache()
        return True

    def xl_cheat_rollback_flags(on):
        """store._rollback 与每个 context.rollback 是 renpy.rollback() 的前置检查"""
        saved = xl_cheat_unlock_saved
        store = xl_cheat_store_dict()
        if on:
            try:
                current = bool(store.get("_rollback", True))
            except Exception:
                current = True
            if saved.get("store_rollback_before") is None:
                saved["store_rollback_before"] = current
            if not current:
                try:
                    store["_rollback"] = True
                except Exception:
                    pass
            try:
                import renpy.game as xl_cheat_game_flags
                contexts = xl_getattr(xl_cheat_game_flags, "contexts", None)
            except Exception:
                contexts = None
            if contexts is not None:
                before = saved.get("context_rollback_before")
                if before is None:
                    before = {}
                    saved["context_rollback_before"] = before
                for ctx in contexts:
                    key = xl_id(ctx)
                    try:
                        value = bool(xl_getattr(ctx, "rollback", True))
                    except Exception:
                        value = True
                    if key not in before:
                        before[key] = value
                    if not value:
                        try:
                            ctx.rollback = True
                        except Exception:
                            pass
        else:
            if saved.get("store_rollback_before") is not None:
                try:
                    store["_rollback"] = bool(saved.get("store_rollback_before"))
                    saved["store_rollback_before"] = None
                except Exception:
                    pass
            before = saved.get("context_rollback_before")
            if before is not None:
                try:
                    import renpy.game as xl_cheat_game_flags2
                    for ctx in xl_getattr(xl_cheat_game_flags2, "contexts", []):
                        key = xl_id(ctx)
                        if key in before:
                            try:
                                ctx.rollback = bool(before[key])
                            except Exception:
                                pass
                    saved["context_rollback_before"] = None
                except Exception:
                    pass

    def xl_cheat_rollback_patch(on):
        """把 RollbackLog.block 换成空函数（改类属性，不影响存档序列化）"""
        saved = xl_cheat_unlock_saved
        state = xl_cheat_rollback_state()
        cls = xl_cheat_rollback_class()
        if cls is None:
            return False
        try:
            current = xl_vars(cls).get("block")
        except Exception:
            current = None
        if on:
            if saved.get("block_patched") and current is xl_cheat_rollback_block_noop:
                return True
            if state.get("block_orig") is None:
                if current is None:
                    return False
                state["block_orig"] = current
            try:
                xl_setattr(cls, "block", xl_cheat_rollback_block_noop)
                saved["block_patched"] = True
            except Exception:
                return False
        else:
            if not saved.get("block_patched"):
                return False
            original = state.get("block_orig")
            try:
                if original is not None:
                    xl_setattr(cls, "block", original)
            except Exception:
                pass
            saved["block_patched"] = False
            state["block_orig"] = None
        return saved.get("block_patched") is True

    def xl_cheat_rollback_log_apply():
        """把当前日志的 rollback_limit 顶满，并解除 fix_rollback 的限制"""
        log = xl_cheat_rollback_log()
        if log is None:
            return False
        try:
            history = xl_len(xl_getattr(log, "log", []))
            limit = xl_int(xl_getattr(log, "rollback_limit", 0) or 0)
            if limit < history:
                log.rollback_limit = history
        except Exception:
            pass
        try:
            if bool(xl_getattr(log, "rollback_is_fixed", False)):
                log.rollback_is_fixed = False
        except Exception:
            pass
        return True

    def xl_cheat_rollback_diag():
        cfg = xl_cheat_config_module()
        try:
            keymap = xl_getattr(cfg, "keymap", None) if cfg is not None else None
        except Exception:
            keymap = None

        def key_ok(action, key):
            if not xl_isinstance(keymap, xl_dict_type):
                return False
            try:
                current = keymap.get(action)
            except Exception:
                return False
            if not xl_isinstance(current, (xl_list_type, xl_tuple_type)):
                return False
            return key in current

        log = xl_cheat_rollback_log()
        limit = 0
        history = 0
        fixed = False
        if log is not None:
            try:
                limit = xl_int(xl_getattr(log, "rollback_limit", 0) or 0)
            except Exception:
                limit = 0
            try:
                history = xl_len(xl_getattr(log, "log", []))
            except Exception:
                history = 0
            try:
                fixed = bool(xl_getattr(log, "rollback_is_fixed", False))
            except Exception:
                fixed = False
        cls = xl_cheat_rollback_class()
        patched = False
        if cls is not None:
            try:
                patched = xl_vars(cls).get("block") is xl_cheat_rollback_block_noop
            except Exception:
                patched = False
        store = xl_cheat_store_dict()
        try:
            store_flag = bool(store.get("_rollback", True))
        except Exception:
            store_flag = True
        return {
            "rollback_key_ok": key_ok("rollback", "mousedown_4"),
            "rollforward_key_ok": key_ok("rollforward", "mousedown_5"),
            "rollback_limit": limit,
            "rollback_log_len": history,
            "rollback_block_patched": patched,
            "rollback_is_fixed": fixed,
            "store_rollback": store_flag,
        }

    def xl_cheat_rollback_reapply():
        """周期性把回退状态顶回去，防止游戏在剧情里重新关掉 / 重新 block"""
        if not xl_cheat_unlock_flags.get("rollback"):
            return
        try:
            xl_cheat_rollback_config(True)
        except Exception:
            pass
        try:
            xl_cheat_rollback_keymap(True)
        except Exception:
            pass
        try:
            xl_cheat_rollback_flags(True)
        except Exception:
            pass
        try:
            xl_cheat_rollback_patch(True)
        except Exception:
            pass
        try:
            xl_cheat_rollback_log_apply()
        except Exception:
            pass

    def xl_cheat_prefs():
        try:
            import renpy.game as xl_cheat_game_prefs
            return xl_cheat_game_prefs.preferences
        except Exception:
            pass
        try:
            return xl_cheat_store_dict().get("preferences")
        except Exception:
            return None

    def xl_cheat_config_module():
        try:
            import renpy.config as xl_cheat_config_unlock
            return xl_cheat_config_unlock
        except Exception:
            return None

    def xl_cheat_unlock_load():
        target = xl_cheat_persistent()
        if target is None:
            return
        try:
            data = xl_getattr(target, "_xl_cheat_unlock", None)
        except Exception:
            return
        if not xl_isinstance(data, xl_dict_type):
            return
        for key in ("skip", "rollback"):
            try:
                value = data.get(key)
            except Exception:
                continue
            if value is not None:
                xl_cheat_unlock_flags[key] = bool(value)

    def xl_cheat_unlock_persist():
        target = xl_cheat_persistent()
        if target is None:
            return
        try:
            data = xl_getattr(target, "_xl_cheat_unlock", None)
            if not xl_isinstance(data, xl_dict_type):
                data = xl_dict_type()
                xl_setattr(target, "_xl_cheat_unlock", data)
            for key in ("skip", "rollback"):
                data[key] = xl_cheat_unlock_flags.get(key)
            try:
                renpy.save_persistent()
            except Exception:
                pass
        except Exception:
            pass

    def xl_cheat_apply_skip(on):
        ok = False
        prefs = xl_cheat_prefs()
        if prefs is not None:
            try:
                prefs.skip_unseen = bool(on)
                ok = True
            except Exception:
                pass
            if on:
                # 选项后也继续跳过，和游戏里两个勾一起打开的效果一致
                try:
                    if xl_cheat_unlock_saved.get("skip_after") is None:
                        xl_cheat_unlock_saved["skip_after"] = bool(
                            xl_getattr(prefs, "skip_after_choices", False))
                    prefs.skip_after_choices = True
                except Exception:
                    pass
            else:
                saved_after = xl_cheat_unlock_saved.get("skip_after")
                if saved_after is not None:
                    try:
                        prefs.skip_after_choices = saved_after
                        xl_cheat_unlock_saved["skip_after"] = None
                    except Exception:
                        pass
        cfg = xl_cheat_config_module()
        if cfg is None:
            return ok
        if on:
            if not xl_getattr(cfg, "allow_skipping", True):
                if xl_cheat_unlock_saved.get("allow_skipping") is None:
                    xl_cheat_unlock_saved["allow_skipping"] = False
                try:
                    cfg.allow_skipping = True
                    ok = True
                except Exception:
                    pass
        else:
            saved = xl_cheat_unlock_saved.get("allow_skipping")
            if saved is not None:
                try:
                    cfg.allow_skipping = saved
                    xl_cheat_unlock_saved["allow_skipping"] = None
                except Exception:
                    pass
        return ok

    def xl_cheat_apply_rollback(on):
        on = bool(on)
        ok = xl_cheat_rollback_config(on)
        if on:
            # 四层一起打开，缺一层就会出现「滚轮没反应」或「只能退一两句」
            for step in (xl_cheat_rollback_keymap, xl_cheat_rollback_flags,
                         xl_cheat_rollback_patch):
                try:
                    step(True)
                except Exception as error:
                    xl_cheat_log("回退设置失败(%s)：%s" % (step.__name__, error))
            try:
                xl_cheat_rollback_log_apply()
            except Exception as error:
                xl_cheat_log("回退历史设置失败：%s" % error)
            try:
                xl_cheat_log("回退状态 %s" % xl_cheat_rollback_diag())
            except Exception as error:
                xl_cheat_log("回退状态读取失败：%s" % error)
        else:
            # 关闭顺序反过来：先还原引擎内部，再还原 config
            for step in (xl_cheat_rollback_patch, xl_cheat_rollback_keymap,
                         xl_cheat_rollback_flags):
                try:
                    step(False)
                except Exception:
                    pass
        return ok

    def xl_cheat_unlock_status():
        prefs = xl_cheat_prefs()

        def pref(name):
            try:
                return xl_getattr(prefs, name, None)
            except Exception:
                return None

        data = {
            "skip_unseen": bool(pref("skip_unseen")),
            "skip_after_choices": bool(pref("skip_after_choices")),
            "allow_skipping": bool(xl_cheat_conf("allow_skipping", True)),
            "rollback_enabled": bool(xl_cheat_conf("rollback_enabled", True)),
            "rollback_length": xl_cheat_conf("rollback_length", 0),
            "hard_rollback_limit": xl_cheat_conf("hard_rollback_limit", 0),
            "unlocked_skip": xl_cheat_unlock_flags.get("skip") is True,
            "unlocked_rollback": xl_cheat_unlock_flags.get("rollback") is True,
        }
        try:
            data.update(xl_cheat_rollback_diag())
        except Exception as error:
            xl_cheat_log("回退诊断失败：%s: %s" % (xl_type(error).__name__, error))
        return data

    def xl_cheat_unlock_set(kind, on, silent=False):
        on = bool(on)
        if kind == "skip":
            ok = xl_cheat_apply_skip(on)
            label = "跳过未读文本"
        elif kind == "rollback":
            ok = xl_cheat_apply_rollback(on)
            label = "回退功能"
        else:
            return {"ok": False, "error": "未知的解锁类型"}
        if not ok:
            return {"ok": False, "error": "游戏里找不到对应设置，无法修改"}
        xl_cheat_unlock_flags[kind] = on
        xl_cheat_unlock_persist()
        if not silent:
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log(("已开启" if on else "已关闭") + label)
        return {"ok": True, "data": xl_cheat_unlock_status()}

    def xl_cheat_unlock_tick():
        """首次运行时恢复上次的解锁状态，并看护游戏不要把它重置"""
        if not xl_cheat_unlock_saved.get("loaded"):
            xl_cheat_unlock_saved["loaded"] = True
            xl_cheat_unlock_load()
            for key in ("skip", "rollback"):
                if xl_cheat_unlock_flags.get(key):
                    xl_cheat_unlock_set(key, True, silent=True)
        if xl_cheat_unlock_flags.get("skip"):
            prefs = xl_cheat_prefs()
            try:
                if prefs is not None and not xl_getattr(prefs, "skip_unseen", False):
                    prefs.skip_unseen = True
            except Exception:
                pass
            cfg = xl_cheat_config_module()
            try:
                if cfg is not None and not xl_getattr(cfg, "allow_skipping", True):
                    cfg.allow_skipping = True
            except Exception:
                pass
        if xl_cheat_unlock_flags.get("rollback"):
            try:
                xl_cheat_rollback_reapply()
            except Exception:
                pass


    def xl_cheat_dispatch(req):
        op = req.get("op", "")

        if op == "ping":
            state = xl_cheat_server_state()
            try:
                renpy_version = renpy.version()
            except Exception:
                renpy_version = "未知"
            try:
                title = xl_cheat_conf("name", "")
            except Exception:
                title = ""
            return {"ok": True, "data": {
                "app": XL_CHEAT_MARKER,
                "version": XL_CHEAT_VERSION,
                "port": state.get("port"),
                "pid": xl_cheat_os.getpid(),
                "renpy": renpy_version,
                "python": xl_cheat_sys.version.split()[0],
                "title": title,
                "frozen": xl_len(xl_cheat_frozen),
            }}

        if op == "list":
            items = xl_cheat_list_items(req.get("scope", "store"), req.get("filter", ""), bool(req.get("objects")))
            capped = False
            if xl_len(items) > 3000:
                items = items[:3000]
                capped = True
            return {"ok": True, "data": {
                "count": xl_len(items),
                "capped": capped,
                "scope": req.get("scope", "store"),
                "store_size": xl_len(xl_cheat_store_dict()),
                "items": items,
            }}

        if op == "items":
            data = xl_cheat_store_dict()
            catalog, catalog_source = xl_cheat_item_catalog(data)
            inventory, inventory_source = xl_cheat_item_inventory(data, catalog)
            max_slot = 0
            for name in xl_list_type(data.keys()):
                if not xl_isinstance(name, xl_cheat_text_types):
                    continue
                low = xl_cheat_str_type(name).lower()
                if not (("max" in low and "slot" in low) or "capacity" in low):
                    continue
                try:
                    value = xl_int(data[name] or 0)
                except Exception:
                    continue
                if value > max_slot:
                    max_slot = value
            return {"ok": True, "data": {
                "count": xl_len(inventory),
                "inventory_source": inventory_source,
                "catalog_source": catalog_source,
                "max_slot": max_slot,
                "language": xl_cheat_language(),
                "i18n": xl_len(xl_cheat_i18n_table()),
                "inventory": inventory,
                "catalog": catalog,
            }}

        if op == "add_item":
            key = xl_cheat_str_type(req.get("pKey", "")).strip()
            if not key:
                raise ValueError("缺少物品 ID")
            try:
                count = xl_int(req.get("count", 1))
            except Exception:
                count = 1
            if count <= 0:
                raise ValueError("数量必须大于 0")
            data = xl_cheat_store_dict()
            catalog, _source = xl_cheat_item_catalog(data)
            if catalog and key not in catalog:
                raise ValueError("物品 ID 不存在：%s" % key)
            added = xl_cheat_item_add(data, key, count)
            total = xl_cheat_item_count(data, key)
            xl_cheat_log("添加物品 %s x%d（当前 %d）" % (key, count, total))
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            return {"ok": True, "data": {
                "pKey": key,
                "added": added,
                "count": total,
                "name": (catalog.get(key) or {}).get("name", key) if catalog else key,
            }}

        if op == "explore":
            items = xl_cheat_explore(xl_cheat_str_type(req.get("keyword", "")))
            return {"ok": True, "data": {"count": xl_len(items), "items": items}}

        if op == "affection" or op == "attrs":
            data = xl_cheat_affection_scan()
            xl_cheat_log("属性扫描：%d 项" % data["total"])
            return {"ok": True, "data": data}

        if op == "wallet":
            # 玩家自己的货币 / 成长属性：只看「通用 / 玩家」名下的资源与等级，
            # 跳过列表逐项、概率表 / 奖励表 / 物品表里的同名数据。
            wallet_tables = ("player", "hero", "protag", "inventory", "backpack",
                             "bag", "wallet", "bank", "money", "stats", "status",
                             "save", "data", "main", "玩家", "主角", "背包", "钱包")
            data = xl_cheat_affection_scan()
            entries = []
            for item in data["items"]:
                group = item.get("group") or ""
                character = xl_cheat_str_type(item.get("character") or "").lower()
                name = item.get("name") or ""
                # character 对对象字段来说是所属容器的名字（inventory / player…）
                if character not in ("通用", "玩家", "主角", "player", "hero",
                                     "protagonist", "you", "pc", "mc",
                                     "inventory", "wallet", "bank", "backpack",
                                     "bag", "purse", "money", "stats", "status",
                                     "数据", "钱包", "背包"):
                    continue
                if "[" in name:
                    continue
                if group not in ("资源 · 货币", "等级 · 成长"):
                    continue
                table = xl_cheat_str_type(item.get("table") or "").lower()
                if not table or item.get("scope") == "持久化":
                    entries.append(item)
                    continue
                for hint in wallet_tables:
                    if hint in table:
                        entries.append(item)
                        break
            xl_cheat_log("钱包扫描：%d 项" % xl_len(entries))
            return {"ok": True, "data": {"items": entries[:60], "total": xl_len(entries)}}

        if op == "affection_set":
            changed, failed = xl_cheat_affection_set(
                req.get("paths") or [], req.get("value", ""))
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("好感度修改：%d 项，失败 %d" % (changed, xl_len(failed)))
            return {"ok": True, "data": {"changed": changed, "failed": failed}}

        if op == "find":
            keyword = xl_cheat_str_type(req.get("keyword", "")).strip()
            if not keyword:
                raise ValueError("缺少搜索关键词")
            items = xl_cheat_find_names(keyword, req.get("limit", 300))
            xl_cheat_log("名称搜索 %s：命中 %d" % (keyword, xl_len(items)))
            return {"ok": True, "data": {
                "keyword": keyword,
                "count": xl_len(items),
                "store_size": xl_len(xl_cheat_store_dict()),
                "items": items,
            }}

        if op == "inspect":
            # 崩溃定位专用：逐步打点，进程若被带崩也能从日志看出死在哪一步
            path = xl_cheat_str_type(req.get("path", ""))
            log_path = xl_cheat_str_type(req.get("log", ""))

            def mark(text):
                try:
                    handle = xl_cheat_io.open(log_path, "a")
                    handle.write(xl_cheat_str_type(text).encode("ascii", "replace") + "\n")
                    handle.close()
                except Exception:
                    pass

            mark("start path=" + path)
            table = xl_cheat_store_dict()
            mark("table keys=%d" % xl_len(table))
            value = table.get(path, "<missing>")
            mark("got value")
            mark("type name=" + xl_type(value).__name__)
            try:
                mark("mro=" + ",".join([cls.__name__ for cls in xl_type(value).__mro__]))
            except Exception:
                mark("mro failed")
            mark("text=%s bool=%s num=%s none=%s" % (
                xl_cheat_str_type(xl_isinstance(value, xl_cheat_text_types)),
                xl_cheat_str_type(xl_isinstance(value, xl_bool)),
                xl_cheat_str_type(xl_cheat_is_number(value)),
                xl_cheat_str_type(value is None)))
            try:
                mark("len=%d" % xl_len(value))
            except Exception:
                mark("len failed")
            try:
                mark("slice=" + xl_repr(value[:160]))
            except Exception as error:
                mark("slice failed %s" % error)
            try:
                mark("type_name=" + xl_cheat_type_name(value))
            except Exception as error:
                mark("type_name failed %s" % error)
            try:
                mark("describe=" + xl_repr(xl_cheat_describe(value, 160)))
            except Exception as error:
                mark("describe failed %s" % error)
            mark("safe start")
            try:
                clean = xl_cheat_payload_safe(value)
                mark("clean type=%s" % xl_type(clean).__name__)
            except Exception as error:
                mark("clean failed %s" % error)
            try:
                dumped = xl_cheat_json.dumps({"v": clean}, ensure_ascii=False)
                mark("dumps type=%s len=%d" % (xl_type(dumped).__name__, xl_len(dumped)))
            except Exception as error:
                mark("dumps failed %s" % error)
            try:
                encoded = (dumped + "\n").encode("utf-8")
                mark("encode len=%d" % xl_len(encoded))
            except Exception as error:
                mark("encode failed %s" % error)
            mark("done")
            return {"ok": True, "data": {"path": path}}

        if op == "readsave":
            # 只解析存档里的数据，不调用 unfreeze，因此不会改变游戏当前状态
            slot = xl_cheat_str_type(req.get("slot", ""))
            if not slot:
                raise ValueError("缺少存档槽位")
            max_depth = xl_int(req.get("depth", 4))
            limit = xl_int(req.get("limit", 6000))
            import renpy.loadsave as xl_cheat_loadsave
            import zipfile as xl_cheat_zipfile
            log_data = None
            signature = ""
            # 主菜单阶段 renpy.loadsave.location 还是 None，得自己从存档目录读
            try:
                if xl_cheat_loadsave.location is not None:
                    log_data, signature = xl_cheat_loadsave.location.load(slot)
            except Exception:
                log_data = None
            if log_data is None:
                savedir = xl_cheat_conf("savedir", None)
                if not savedir:
                    raise ValueError("无法定位存档目录")
                name = slot
                if not name.lower().endswith(".save"):
                    name = name + ".save"
                fn = xl_cheat_os.path.join(savedir, name)
                if not xl_cheat_os.path.exists(fn):
                    raise ValueError("存档不存在：" + name)
                with xl_cheat_zipfile.ZipFile(fn, "r") as zf:
                    log_data = zf.read("log")
                    try:
                        signature = zf.read("signatures").decode("utf-8")
                    except Exception:
                        signature = ""
            if not renpy.savetoken.check_load(log_data, signature):
                return {"ok": False, "error": "存档签名校验未通过"}
            roots, log = xl_cheat_loadsave.loads(log_data)
            rows = []
            stats = {"nodes": 0, "capped": False}

            def walk(owner, obj, level, seen):
                if level >= max_depth or stats["capped"] or stats["nodes"] > 200000:
                    return
                stats["nodes"] += 1
                if xl_isinstance(obj, xl_dict_type):
                    pairs = xl_list_type(obj.items())
                elif xl_isinstance(obj, (xl_list_type, xl_tuple_type)):
                    pairs = [(xl_int(i), v) for i, v in enumerate(obj)]
                elif xl_isinstance(obj, xl_set_type):
                    pairs = [(xl_int(i), v) for i, v in enumerate(obj)]
                else:
                    d = xl_getattr(obj, "__dict__", None)
                    if not xl_isinstance(d, xl_dict_type):
                        return
                    pairs = xl_list_type(d.items())
                for key, value in pairs:
                    stats["nodes"] += 1
                    if stats["nodes"] > 200000 or xl_len(rows) >= limit:
                        stats["capped"] = True
                        return
                    text = key
                    if not xl_isinstance(text, xl_cheat_text_types):
                        if not xl_cheat_is_number(text):
                            continue
                        text = xl_cheat_str_type(xl_int(text))
                    else:
                        text = xl_cheat_text_safe(text)
                    if not text:
                        continue
                    if text.startswith("_") and not text.startswith("__"):
                        pass
                    elif text.startswith("__"):
                        continue
                    path = owner + "." + text if owner else text
                    if xl_cheat_scalar(value):
                        rows.append({
                            "path": path,
                            "type": xl_cheat_type_name(value),
                            "value": xl_cheat_describe(value, 160),
                            "level": level,
                            "kind": "value",
                            "editable": xl_cheat_editable(value),
                        })
                        continue
                    if xl_cheat_engine_object(value):
                        continue
                    if value is None:
                        continue
                    if not (xl_cheat_is_container(value) or xl_hasattr(value, "__dict__")):
                        continue
                    ident = xl_id(value)
                    if ident in seen:
                        continue
                    seen[ident] = path
                    rows.append({
                        "path": path,
                        "type": xl_cheat_type_name(value),
                        "value": "",
                        "level": level,
                        "kind": "object",
                        "editable": False,
                    })
                    walk(path, value, level + 1, seen)

            seen = {}
            if xl_isinstance(roots, xl_dict_type):
                for name in roots.keys():
                    text = xl_cheat_text_safe(name)
                    if text:
                        walk(text, roots[name], 0, seen)
            else:
                walk("roots", roots, 0, seen)
            return {"ok": True, "data": {
                "rows": rows,
                "count": xl_len(rows),
                "stats": stats,
                "slot": slot,
                "root_type": xl_cheat_type_name(roots),
            }}

        if op == "dump":
            # 全量导出当前存档里的数据，供生成「变量路径 → 值 → 可读文本」清单
            if xl_bool(req.get("keys_only")):
                store_table = xl_cheat_store_dict()
                keys = []
                for key in store_table.keys():
                    if xl_isinstance(key, xl_cheat_text_types):
                        keys.append(xl_cheat_text_safe(key))
                    elif xl_cheat_is_number(key):
                        keys.append(xl_cheat_str_type(xl_int(key)))
                return {"ok": True, "data": {
                    "keys": xl_sorted(keys),
                    "store_size": xl_len(store_table),
                }}
            scope = xl_cheat_str_type(req.get("scope", "both"))
            max_depth = xl_int(req.get("depth", 6))
            limit = xl_int(req.get("limit", 8000))
            start = xl_int(req.get("start", 0))
            count = xl_int(req.get("count", 0))
            scalars_only = xl_bool(req.get("scalars_only"))
            names = req.get("names")
            wanted = {}
            if xl_isinstance(names, (xl_list_type, xl_tuple_type)):
                for name in names:
                    wanted[xl_cheat_str_type(name)] = True

            tables = []
            if scope in ("store", "both"):
                tables.append(("", xl_cheat_store_dict()))
            if scope in ("default", "both"):
                tables.append(("default.", xl_cheat_default_dict()))

            rows = []
            stats = {"scanned": 0, "skipped_engine": 0, "skipped_callable": 0,
                     "skipped_private": 0, "capped": False}
            visited = {}
            budget = {"nodes": 0}

            def kids(obj):
                try:
                    if xl_isinstance(obj, xl_dict_type):
                        return xl_list_type(obj.items())
                    if xl_hasattr(obj, "__dict__"):
                        return xl_list_type(xl_vars(obj).items())
                    if xl_isinstance(obj, (xl_list_type, xl_tuple_type)):
                        return xl_list_type([(xl_cheat_str_type(i), v)
                                             for i, v in enumerate(obj)])
                except Exception:
                    return []
                return []

            def is_data_object(value):
                if xl_isinstance(value, xl_cheat_types.ModuleType):
                    return False
                if xl_isinstance(value, xl_type) or xl_isinstance(value, xl_cheat_types.FunctionType):
                    return False
                if xl_callable(value) and not xl_hasattr(value, "__dict__"):
                    return False
                if xl_cheat_engine_object(value):
                    return False
                return True

            def emit(path, value, level):
                if xl_len(rows) >= limit:
                    stats["capped"] = True
                    return
                row = {
                    "path": path,
                    "type": xl_cheat_type_name(value),
                    "level": level,
                }
                if xl_cheat_scalar(value):
                    row["kind"] = "value"
                    row["editable"] = xl_cheat_editable(value)
                    # 只对标量做 repr；对对象 repr 会调用游戏自定义的 __repr__，
                    # 这个游戏里某些对象会在 C 层直接把进程带崩（0xc0000005）。
                    row["value"] = xl_cheat_describe(value, 160)
                elif xl_cheat_is_container(value) or xl_hasattr(value, "__dict__"):
                    row["kind"] = "object"
                    row["editable"] = False
                    row["value"] = ""
                    try:
                        row["len"] = xl_len(value)
                    except Exception:
                        pass
                else:
                    row["kind"] = "other"
                    row["editable"] = False
                    row["value"] = ""
                rows.append(row)

            def walk(owner, obj, level):
                if budget["nodes"] > 300000 or stats["capped"]:
                    return
                budget["nodes"] += 1
                pairs = kids(obj)
                if level == 0 and wanted:
                    pairs = [(k, v) for k, v in pairs if k in wanted]
                elif level == 0 and count > 0:
                    pairs = pairs[start:start + count]
                for key, value in pairs[:2000]:
                    stats["scanned"] += 1
                    text = key
                    if not xl_isinstance(text, xl_cheat_text_types):
                        if not xl_cheat_is_number(text):
                            continue
                        text = xl_cheat_str_type(xl_int(text))
                    if not text or "." in text:
                        continue
                    if text.startswith("__"):
                        stats["skipped_private"] += 1
                        continue
                    path = (owner + "." + text) if owner else text
                    if xl_cheat_scalar(value):
                        emit(path, value, level)
                        continue
                    if scalars_only:
                        continue
                    if not is_data_object(value):
                        stats["skipped_engine"] += 1
                        continue
                    # 同一个小对象被多处引用时只展开一次，防止回环与重复
                    key_id = xl_id(value)
                    if key_id in visited:
                        emit(path, value, level)
                        continue
                    visited[key_id] = path
                    emit(path, value, level)
                    if level + 1 < max_depth:
                        walk(path, value, level + 1)

            for prefix, table in tables:
                try:
                    walk(prefix.rstrip("."), table, 0)
                except Exception as error:
                    xl_cheat_log("dump 异常：%s: %s" % (xl_type(error).__name__, error))

            xl_cheat_log("全量导出 %d 行（扫描 %d 节点）" % (xl_len(rows), stats["scanned"]))
            return {"ok": True, "data": {
                "count": xl_len(rows),
                "rows": rows,
                "stats": stats,
                "store_size": xl_len(xl_cheat_store_dict()),
            }}

        if op == "get":
            path = req.get("path", "")
            value = xl_cheat_get(path)
            return {"ok": True, "data": {
                "path": path,
                "type": xl_cheat_type_name(value),
                "value": xl_cheat_describe(value, 100000),
                "editable": xl_cheat_editable(value),
            }}

        if op == "set":
            path = req.get("path", "")
            if not path:
                raise ValueError("缺少变量路径")
            exists = True
            try:
                old = xl_cheat_get(path)
            except Exception:
                exists = False
                old = None
                if not req.get("create"):
                    raise ValueError("变量不存在：%s" % path)
            value = xl_cheat_parse(req.get("value", ""), old, req.get("value_type"))
            xl_cheat_set(path, value)
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("修改 %s = %s" % (path, xl_cheat_describe(value, 60)))
            return {"ok": True, "data": {
                "path": path,
                "type": xl_cheat_type_name(value),
                "value": xl_cheat_describe(value),
                "created": not exists,
            }}

        if op == "scan":
            target = xl_cheat_parse_target(xl_cheat_str_type(req.get("value", "")))
            hits = xl_cheat_scan(target, req.get("mode", "new"))
            items = []
            for name in hits:
                try:
                    value = xl_cheat_get(name)
                except Exception:
                    continue
                items.append({
                    "name": name,
                    "path": name,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value),
                })
            capped = False
            if xl_len(items) > 500:
                items = items[:500]
                capped = True
            return {"ok": True, "data": {
                "count": xl_len(items),
                "capped": capped,
                "scanned": xl_len(hits),
                "store_size": xl_len(xl_cheat_store_dict()),
                "items": items,
            }}

        if op == "freeze":
            path = req.get("path", "")
            if not path:
                raise ValueError("缺少变量路径")
            if req.get("value") is not None and xl_cheat_str_type(req.get("value")).strip() != "":
                old = xl_cheat_get(path)
                value = xl_cheat_parse(xl_cheat_str_type(req.get("value")), old, req.get("value_type"))
            else:
                value = xl_cheat_get(path)
            xl_cheat_frozen[path] = value
            xl_cheat_apply_frozen(force=True)
            xl_cheat_log("锁定 %s = %s" % (path, xl_cheat_describe(value, 60)))
            return {"ok": True, "data": {"path": path, "value": xl_cheat_describe(value)}}

        if op == "unfreeze":
            if req.get("all"):
                xl_cheat_frozen.clear()
                xl_cheat_log("已解除全部锁定")
            else:
                path = req.get("path", "")
                if path in xl_cheat_frozen:
                    del xl_cheat_frozen[path]
                    xl_cheat_log("解除锁定 %s" % path)
            return {"ok": True, "data": {"count": xl_len(xl_cheat_frozen)}}

        if op == "frozen":
            items = []
            for path in xl_list_type(xl_cheat_frozen.keys()):
                value = xl_cheat_frozen[path]
                try:
                    current_text = xl_cheat_describe(xl_cheat_get(path))
                except Exception:
                    current_text = "<已失效>"
                items.append({
                    "path": path,
                    "type": xl_cheat_type_name(value),
                    "value": xl_cheat_describe(value),
                    "current": current_text,
                })
            return {"ok": True, "data": {"count": xl_len(items), "items": items}}

        if op == "diag":
            data = xl_cheat_store_dict()
            sample_path = req.get("path", "")
            info = {
                "store_type": xl_repr(xl_type(data)),
                "store_len": xl_len(data),
                "is_builtin_dict": xl_isinstance(data, xl_dict_type),
            }
            try:
                info["sample"] = xl_repr(xl_cheat_get(sample_path))
            except Exception as error:
                info["sample"] = "%s: %s" % (xl_type(error).__name__, error)
            target = xl_cheat_parse_target(xl_cheat_str_type(req.get("value", "")))
            info["target"] = [target[0], target[1]]
            info["hits"] = xl_len(xl_cheat_scan_hits)
            info["logs"] = xl_list_type(xl_cheat_logs)[-8:]
            # 诊断：各命名空间规模，便于判断游戏变量到底放在哪里
            try:
                import renpy.python as xl_cheat_python_diag
                info["stores"] = [
                    [name, xl_len(table)]
                    for name, table in xl_cheat_python_diag.store_dicts.items()
                ]
            except Exception as error:
                info["stores"] = "%s: %s" % (xl_type(error).__name__, error)
            try:
                target_obj = xl_cheat_persistent()
                keys = xl_list_type(xl_vars(target_obj).keys())
                info["persistent_len"] = xl_len(keys)
                info["persistent_sample"] = [xl_cheat_str_type(k) for k in keys[:20]]
                rows = []
                for key in keys:
                    try:
                        value = xl_getattr(target_obj, key)
                    except Exception:
                        continue
                    row = {"name": xl_cheat_str_type(key),
                           "type": xl_cheat_type_name(value),
                           "value": xl_cheat_describe(value, 60)}
                    if xl_cheat_is_container(value):
                        row["len"] = xl_len(value)
                    rows.append(row)
                info["persistent_all"] = rows
            except Exception as error:
                info["persistent_len"] = "%s: %s" % (xl_type(error).__name__, error)
            return {"ok": True, "data": info}

        if op == "collect":
            data = xl_cheat_collect_scan(
                xl_bool(req.get("include_all")),
                xl_cheat_str_type(req.get("keyword", "")),
            )
            xl_cheat_log("收集项扫描：%d 个，已解锁 %d" % (data["total"], data["unlocked"]))
            return {"ok": True, "data": data}

        if op == "unlock_all":
            paths = req.get("paths")
            if paths is None:
                data = xl_cheat_collect_scan(xl_bool(req.get("include_all")),
                                             xl_cheat_str_type(req.get("keyword", "")))
                paths = []
                for entry in data["items"]:
                    if entry.get("container"):
                        if (entry.get("unlocked") or 0) < (entry.get("total") or 0):
                            paths.append(entry["path"])
                    elif not entry.get("unlocked"):
                        paths.append(entry["path"])
            paths = [xl_cheat_str_type(path) for path in paths]
            changed, failed = xl_cheat_unlock_paths(paths)
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("一键解锁：改动 %d 项，失败 %d 项" % (changed, xl_len(failed)))
            return {"ok": True, "data": {
                "changed": changed,
                "failed": failed,
                "backup": xl_len(xl_cheat_unlock_backup),
            }}

        if op == "unlock_undo":
            restored = xl_cheat_unlock_undo()
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("已撤销解锁，恢复 %d 项" % restored)
            return {"ok": True, "data": {"restored": restored}}

        if op == "sponsor":
            data = xl_cheat_sponsor_scan()
            xl_cheat_log("赞助奖励扫描：%d 项，未解锁 %d" % (data["total"], data["locked"]))
            return {"ok": True, "data": data}

        if op == "sponsor_unlock":
            paths = req.get("paths")
            if paths is not None:
                paths = [xl_cheat_str_type(path) for path in paths]
            changed, failed = xl_cheat_sponsor_unlock(paths)
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("赞助奖励解锁：改动 %d 项，失败 %d 项" % (changed, xl_len(failed)))
            return {"ok": True, "data": {
                "changed": changed,
                "failed": failed,
                "backup": xl_len(xl_cheat_sponsor_backup),
            }}

        if op == "sponsor_undo":
            restored = xl_cheat_sponsor_undo()
            try:
                renpy.restart_interaction()
            except Exception:
                pass
            xl_cheat_log("已撤销赞助奖励解锁，恢复 %d 项" % restored)
            return {"ok": True, "data": {"restored": restored}}

        if op == "unlock_status":
            return {"ok": True, "data": xl_cheat_unlock_status()}

        if op == "unlock_skip":
            return xl_cheat_unlock_set("skip", bool(req.get("on")))

        if op == "unlock_rollback":
            return xl_cheat_unlock_set("rollback", bool(req.get("on")))

        if op == "logs":
            return {"ok": True, "data": {"items": xl_list_type(xl_cheat_logs)}}

        if op == "shutdown":
            state = xl_cheat_server_state()
            sock = state.get("sock")
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
                state["sock"] = None
            xl_cheat_log("调试通道已关闭")
            return {"ok": True, "data": {"shutdown": True}}

        raise ValueError("未知操作：%s" % op)

    def xl_cheat_handle(req):
        try:
            return xl_cheat_dispatch(req)
        except Exception as error:
            return {"ok": False, "error": "%s: %s" % (xl_type(error).__name__, error)}

    # ------------------------------------------------------------------
    # 网络线程 <-> 主线程
    # ------------------------------------------------------------------
    def xl_cheat_server_state():
        state = xl_getattr(xl_cheat_sys, "_xl_cheat_server_state", None)
        if state is None:
            state = {"sock": None, "thread": None, "port": None, "mode": "none"}
            xl_setattr(xl_cheat_sys, "_xl_cheat_server_state", state)
        return state

    def xl_cheat_remote_call(req):
        holder = {"resp": {"ok": False, "error": "主线程无响应"}}
        event = xl_cheat_threading.Event()

        def run():
            holder["resp"] = xl_cheat_handle(req)
            event.set()

        state = xl_cheat_server_state()
        if state.get("mode") == "tick":
            xl_cheat_queue.append(run)
        else:
            invoke = xl_getattr(renpy, "invoke_in_main_thread", None)
            if invoke is not None:
                try:
                    invoke(run)
                except Exception:
                    xl_cheat_queue.append(run)
            else:
                xl_cheat_queue.append(run)

        if not event.wait(5.0):
            return {"ok": False, "error": "主线程无响应（游戏可能正在加载或处于暂停状态）"}
        return holder["resp"]

    def xl_cheat_server_loop(sock):
        while True:
            try:
                conn, address = sock.accept()
            except Exception:
                break
            try:
                conn.settimeout(3.0)
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                line = data.split(b"\n")[0].decode("utf-8", "replace")
                request = xl_cheat_json.loads(line)
                response = xl_cheat_remote_call(request)
                try:
                    clean = xl_cheat_payload_safe(response)
                    payload = (xl_cheat_json.dumps(clean, ensure_ascii=False) + "\n").encode("utf-8")
                except Exception:
                    payload = (xl_cheat_json.dumps(
                        {"ok": False, "error": "serialize failed"}, ensure_ascii=False) + "\n").encode("utf-8")
                conn.sendall(payload)
            except Exception as error:
                xl_cheat_log("通道异常：%s" % error)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def xl_cheat_read_config():
        try:
            path = xl_cheat_os.path.join(xl_cheat_conf("gamedir", ""), "xl_cheat_config.json")
            handle = xl_cheat_io.open(path, "r", encoding="utf-8")
            data = xl_cheat_json.load(handle)
            handle.close()
            return data or {}
        except Exception:
            return {}

    def xl_cheat_start_server():
        state = xl_cheat_server_state()
        old = state.get("sock")
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
            state["sock"] = None
            xl_cheat_time.sleep(0.05)

        try:
            port = xl_int(xl_cheat_read_config().get("port", 47321))
        except Exception:
            port = 47321

        sock = None
        last_error = None
        for offset in xl_range(5):
            candidate = None
            try:
                candidate = xl_cheat_socket.socket(xl_cheat_socket.AF_INET, xl_cheat_socket.SOCK_STREAM)
                candidate.setsockopt(xl_cheat_socket.SOL_SOCKET, xl_cheat_socket.SO_REUSEADDR, 1)
                candidate.bind(("127.0.0.1", port + offset))
                candidate.listen(16)
                sock = candidate
                port = port + offset
                break
            except Exception as error:
                last_error = error
                try:
                    candidate.close()
                except Exception:
                    pass
                xl_cheat_time.sleep(0.1)

        if sock is None:
            xl_cheat_log("调试通道启动失败：%s" % last_error)
            state["mode"] = "none"
            return False

        state["sock"] = sock
        state["port"] = port
        thread = xl_cheat_threading.Thread(target=xl_cheat_server_loop, args=(sock,))
        thread.daemon = True
        state["thread"] = thread
        thread.start()
        xl_cheat_log("调试通道已启动：127.0.0.1:%d" % port)
        return True

    # ------------------------------------------------------------------
    # 帧回调
    # ------------------------------------------------------------------
    def xl_cheat_tick():
        while xl_cheat_queue:
            job = xl_cheat_queue.pop(0)
            try:
                job()
            except Exception as error:
                xl_cheat_log("任务异常：%s" % error)
        try:
            xl_cheat_apply_frozen()
        except Exception:
            pass
        # 对话功能解锁：首次恢复上次状态 + 看护开关不被游戏重置
        try:
            xl_cheat_unlock_tick()
        except Exception:
            pass

    def xl_cheat_register_tick():
        state = xl_cheat_server_state()
        try:
            callbacks = xl_cheat_conf("periodic_callbacks")
            if callbacks is not None:
                if xl_cheat_tick not in callbacks:
                    callbacks.append(xl_cheat_tick)
                state["mode"] = "tick"
                return True
        except Exception:
            pass
        try:
            screens = xl_cheat_conf("overlay_screens")
            if screens is not None:
                if "xl_cheat_bridge" not in screens:
                    screens.append("xl_cheat_bridge")
                state["mode"] = "overlay"
                return True
        except Exception:
            pass
        state["mode"] = "auto"
        return False

    def xl_cheat_boot():
        xl_cheat_dbg("boot v%d" % XL_CHEAT_VERSION)
        xl_cheat_log("加载版本 v%d" % XL_CHEAT_VERSION)
        try:
            xl_cheat_dbg("register_tick mode=%s" % xl_cheat_register_tick())
        except Exception as error:
            xl_cheat_dbg("register_tick error: %r" % (error,))
        try:
            ok = xl_cheat_start_server()
            state = xl_cheat_server_state()
            xl_cheat_dbg("start_server ok=%s port=%s" % (ok, state.get("port")))
        except Exception as error:
            xl_cheat_dbg("start_server error: %r" % (error,))


# 兜底帧驱动：没有 periodic_callbacks 时由屏幕定时器驱动
screen xl_cheat_bridge():
    timer 0.25 repeat True action Function(xl_cheat_tick)


init 999 python:
    xl_cheat_boot()
