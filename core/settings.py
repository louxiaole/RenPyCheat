# -*- coding: utf-8 -*-
"""工具本地配置（保存在工具根目录的 config 文件夹）"""

import json
import os

from core.game import tool_root


DEFAULTS = {
    "last_game": "",
    "recent": [],
    "port": 47321,
    "auto_refresh": True,
    "show_objects": False,
    # 修改记录：{游戏根目录: [{path, note, type, before, after, frozen, updated}, ...]}
    "records": {},
}


class Settings:
    def __init__(self):
        self.folder = os.path.join(tool_root(), "config")
        self.path = os.path.join(self.folder, "settings.json")
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.data.update(data)
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            os.makedirs(self.folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add_recent(self, path: str):
        recent = [item for item in self.data.get("recent", []) if item != path]
        recent.insert(0, path)
        self.data["recent"] = recent[:8]
        self.data["last_game"] = path
        self.save()
