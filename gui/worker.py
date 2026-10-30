# -*- coding: utf-8 -*-
"""后台请求派发：网络请求放到线程里，结果回到主线程"""

import threading
import uuid

from PyQt6.QtCore import QObject, pyqtSignal

from core.client import RemoteError, RenpyBridge


class AsyncBridge(QObject):
    _done = pyqtSignal(str, object)
    _failed = pyqtSignal(str, str, bool)  # request_id, message, is_remote_error

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = {}
        self._done.connect(self._on_done)
        self._failed.connect(self._on_failed)

    def call(self, port, op, payload=None, on_ok=None, on_err=None, timeout=8.0):
        request_id = uuid.uuid4().hex
        self._pending[request_id] = (on_ok, on_err)
        thread = threading.Thread(
            target=self._run,
            args=(request_id, int(port), op, dict(payload or {}), float(timeout)),
            daemon=True,
        )
        thread.start()
        return request_id

    def _run(self, request_id, port, op, payload, timeout):
        try:
            data = RenpyBridge(port).request(op, timeout=timeout, **payload)
        except RemoteError as exc:
            self._failed.emit(request_id, str(exc), True)
            return
        except Exception as exc:  # noqa: BLE001 - 传输层异常统一转成提示
            self._failed.emit(request_id, str(exc), False)
            return
        self._done.emit(request_id, data)

    def _on_done(self, request_id, data):
        on_ok, _ = self._pending.pop(request_id, (None, None))
        if on_ok is not None:
            on_ok(data)

    def _on_failed(self, request_id, message, is_remote):
        _, on_err = self._pending.pop(request_id, (None, None))
        if on_err is not None:
            on_err(message, is_remote)
