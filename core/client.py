# -*- coding: utf-8 -*-
"""与游戏内注入模块通信的客户端（行分隔 JSON over 127.0.0.1）"""

import json
import socket


APP_MARKER = "xl_renpy_cheat"


class BridgeError(Exception):
    """通信失败，message 直接展示给用户"""


class RemoteError(BridgeError):
    """游戏端返回了业务错误（如变量不存在），连接本身正常"""


class RenpyBridge:
    def __init__(self, port: int):
        self.port = int(port)

    def request(self, op: str, timeout: float = 8.0, **payload):
        payload["op"] = op
        try:
            sock = socket.create_connection(("127.0.0.1", self.port), timeout=min(timeout, 4.0))
        except OSError as exc:
            raise BridgeError(f"未连接到游戏调试通道（端口 {self.port}）：{exc}")

        try:
            sock.settimeout(timeout)
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            buffer = b""
            while b"\n" not in buffer:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
        except socket.timeout:
            raise BridgeError("游戏端响应超时，请确认游戏没有卡在加载/暂停界面")
        except OSError as exc:
            raise BridgeError(f"通信中断：{exc}")
        finally:
            try:
                sock.close()
            except OSError:
                pass

        if not buffer:
            raise BridgeError("游戏端没有返回数据，注入模块可能未加载")

        try:
            raw = buffer.split(b"\n")[0]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                # 个别游戏文本是非 UTF-8 字节，不能让一条脏数据毁掉整次通信
                text = raw.decode("utf-8", "replace")
            response = json.loads(text)
        except ValueError as exc:
            raise BridgeError(f"返回数据格式异常：{exc}")

        if not response.get("ok"):
            raise RemoteError(response.get("error") or "游戏端返回失败")
        return response.get("data") or {}

    # ---------------- 常用封装 ----------------

    def ping(self, timeout: float = 3.0):
        return self.request("ping", timeout=timeout)

    def probe(self, timeout: float = 2.0):
        data = self.ping(timeout=timeout)
        if data.get("app") != APP_MARKER:
            raise BridgeError("该端口不是小乐修改器的调试通道")
        return data


def probe_ports(ports, timeout: float = 1.2):
    """依次探测端口，返回 (端口, ping 数据)；全部失败返回 None"""
    for port in ports:
        try:
            data = RenpyBridge(port).probe(timeout=timeout)
            return int(port), data
        except BridgeError:
            continue
    return None
