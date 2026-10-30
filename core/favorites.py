# -*- coding: utf-8 -*-
"""收藏的变量：随游戏目录保存，下次打开同一游戏自动带出"""

import json
import os

FAVORITES_FILENAME = "xl_cheat_favorites.json"


class Favorites:
    def __init__(self):
        self.game_dir = ""
        self.path = ""
        self.items = []

    def load(self, game_dir: str):
        self.game_dir = game_dir or ""
        self.items = []
        self.path = ""
        if not game_dir:
            return
        self.path = os.path.join(game_dir, FAVORITES_FILENAME)
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return
        if not isinstance(raw, list):
            return
        seen = set()
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "")
            if not path or path in seen:
                continue
            seen.add(path)
            self.items.append({
                "path": path,
                "name": str(entry.get("name") or path.split(".")[-1]),
                "cn": str(entry.get("cn") or ""),
                "type": str(entry.get("type") or ""),
                "value": str(entry.get("value") or ""),
            })

    def has(self, path: str) -> bool:
        return any(item.get("path") == path for item in self.items)

    def add(self, path: str, cn: str = "", type_name: str = ""):
        if not path or self.has(path):
            return False
        self.items.insert(0, {
            "path": path,
            "name": path.split(".")[-1],
            "cn": cn or "",
            "type": type_name or "",
            "value": "",
        })
        self.save()
        return True

    def set_value(self, path: str, value=None, type_name: str = ""):
        for item in self.items:
            if item.get("path") != path:
                continue
            item["value"] = "" if value is None else str(value)
            if type_name and item.get("type") != type_name:
                item["type"] = str(type_name)
                self.save()
            break

    def remove(self, path: str):
        before = len(self.items)
        self.items[:] = [item for item in self.items if item.get("path") != path]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def save(self):
        if not self.path:
            return
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.items, handle, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception:
            pass
