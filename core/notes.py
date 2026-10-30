# -*- coding: utf-8 -*-
"""变量备注：随游戏目录保存，下次打开同一游戏自动载入"""

import json
import os

NOTES_FILENAME = "xl_cheat_notes.json"


class Notes:
    def __init__(self):
        self.game_dir = ""
        self.path = ""
        self.data = {}

    def load(self, game_dir: str):
        self.game_dir = game_dir or ""
        self.data = {}
        self.path = ""
        if not game_dir:
            return
        self.path = os.path.join(game_dir, NOTES_FILENAME)
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                self.data = {str(k): str(v) for k, v in raw.items() if v}
        except Exception:
            self.data = {}

    def get(self, path: str) -> str:
        return self.data.get(path, "")

    def set(self, path: str, text: str):
        text = (text or "").strip()
        if text:
            self.data[path] = text
        else:
            self.data.pop(path, None)
        self.save()

    def save(self):
        if not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except Exception:
            pass
