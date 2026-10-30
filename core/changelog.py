# -*- coding: utf-8 -*-
"""更新日志数据：本地记录每个版本改了什么（「更新日志」页与更新弹窗共用）"""

import html as _html

# 新版本加在最上面
ENTRIES = [
    {
        "version": "1.0.0",
        "date": "2026-10-30",
        "title": "首个正式版",
        "items": [
            "首发：Ren'Py 注入式实时修改器，支持变量列表、数值搜索、角色属性、属性识别、物品、画廊解锁",
            "赞助 · 礼包码页：自动识别赞助 / 会员 / 礼品码相关开关，一键解锁，支持撤销",
            "修改记录与数值锁定、持久化数据（persistent）读写",
            "汉化 · 文本：直接读写游戏 .rpy 文本，支持中文对照表提取",
            "存档保护一键开关（改过的存档也能读取）、跳过未读文本与回退功能解锁",
            "新增「关于 · 赞助」页：版本信息、作者、反馈 Q 群、爱发电链接、微信 / 支付宝收款码",
            "新增「更新日志」页与启动自动更新检查（GitHub Releases）",
        ],
    },
]


def latest_version() -> str:
    return ENTRIES[0]["version"] if ENTRIES else "0.0.0"


def as_html() -> str:
    """整份更新日志渲染成 HTML（深色主题）"""
    blocks = []
    for entry in ENTRIES:
        items = "".join(
            "<li style='margin:3px 0;'>%s</li>" % _html.escape(str(item))
            for item in entry.get("items", [])
        )
        blocks.append(
            "<div style='margin-bottom:18px;'>"
            "<div style='font-size:15px;font-weight:600;color:#e6eef7;'>"
            "v%s　%s</div>"
            "<div style='font-size:11px;color:#8fa4b7;margin:2px 0 8px;'>%s</div>"
            "<ul style='margin:0 0 0 16px;padding:0;color:#b9cad9;font-size:13px;'>%s</ul>"
            "</div>"
            % (
                _html.escape(entry.get("version", "")),
                _html.escape(entry.get("title", "")),
                _html.escape(entry.get("date", "")),
                items,
            )
        )
    return (
        "<html><body style='background:#131a21;color:#e6eef7;"
        "font-family:\"Microsoft YaHei UI\";'>"
        + "".join(blocks)
        + "</body></html>"
    )


def as_plain() -> str:
    """纯文本版本（写入控制台 / 日志用）"""
    lines = []
    for entry in ENTRIES:
        lines.append("v%s %s（%s）" % (entry.get("version", ""),
                                     entry.get("title", ""), entry.get("date", "")))
        for item in entry.get("items", []):
            lines.append("  · " + str(item))
        lines.append("")
    return "\n".join(lines)
