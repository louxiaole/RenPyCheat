# -*- coding: utf-8 -*-
"""「关于 · 赞助」与「更新日志」两个页签"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTextBrowser,
    QVBoxLayout, QWidget,
)

from core import changelog, updater
from core.game import resource_path
from core.version import (
    AFDIAN_URL, APP_NAME, APP_VERSION, AUTHOR, GITHUB_URL, QQ_GROUP,
)


class _QrCard(QFrame):
    """白底收款码卡片（深色界面里二维码要保持白底才扫得出来）"""

    def __init__(self, title: str, image_path: str, accent: str, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #2f4351;"
            " border-radius: 10px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        head = QLabel(title)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet(
            "font-size:15px; font-weight:600; color:%s; background:transparent;" % accent)
        layout.addWidget(head)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("background:transparent;")
        pixmap = QPixmap(image_path) if os.path.isfile(image_path) else QPixmap()
        if pixmap.isNull():
            image.setText("收款码图片缺失\n%s" % image_path)
            image.setWordWrap(True)
            image.setStyleSheet("color:#c0392b; font-size:12px; background:transparent;")
        else:
            image.setPixmap(pixmap.scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        layout.addWidget(image)

        hint = QLabel("扫码支持作者（金额随意）")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size:11px; color:#7f8c8d; background:transparent;")
        layout.addWidget(hint)


class AboutPage(QWidget):
    """关于 · 赞助：版本信息、反馈渠道、收款码"""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        scroll.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        # ---- 标题 ----
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        outer.addWidget(title)
        subtitle = QLabel("版本 v%s　作者：%s" % (APP_VERSION, AUTHOR))
        subtitle.setObjectName("subtitle")
        outer.addWidget(subtitle)

        # ---- 信息卡 ----
        info = QFrame()
        info.setObjectName("card")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(8)
        heading = QLabel("版本与反馈")
        heading.setObjectName("section")
        info_layout.addWidget(heading)

        self._add_info_row(info_layout, "软件版本", "v%s" % APP_VERSION)
        self._add_info_row(info_layout, "作　　者", AUTHOR)

        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("问题反馈 Q 群")
        label.setObjectName("muted")
        label.setFixedWidth(96)
        row.addWidget(label)
        value = QLabel(QQ_GROUP)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(value)
        copy_group = QPushButton("复制群号")
        copy_group.clicked.connect(lambda: self.ctrl.copy_text(QQ_GROUP))
        row.addWidget(copy_group)
        row.addStretch(1)
        info_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        label2 = QLabel("爱发电赞助")
        label2.setObjectName("muted")
        label2.setFixedWidth(96)
        row2.addWidget(label2)
        link = QLabel(AFDIAN_URL)
        link.setObjectName("info")
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row2.addWidget(link)
        open_afdian = QPushButton("打开页面")
        open_afdian.clicked.connect(lambda: self._open_url(AFDIAN_URL))
        row2.addWidget(open_afdian)
        row2.addStretch(1)
        info_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        label3 = QLabel("GitHub 项目")
        label3.setObjectName("muted")
        label3.setFixedWidth(96)
        row3.addWidget(label3)
        gh = QLabel(GITHUB_URL)
        gh.setObjectName("info")
        gh.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row3.addWidget(gh)
        open_gh = QPushButton("打开页面")
        open_gh.clicked.connect(lambda: self._open_url(GITHUB_URL))
        row3.addWidget(open_gh)
        row3.addStretch(1)
        info_layout.addLayout(row3)

        update_row = QHBoxLayout()
        update_row.setSpacing(8)
        label4 = QLabel("版本更新")
        label4.setObjectName("muted")
        label4.setFixedWidth(96)
        update_row.addWidget(label4)
        self.update_btn = QPushButton("检查更新")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._check_update)
        update_row.addWidget(self.update_btn)
        update_row.addStretch(1)
        info_layout.addLayout(update_row)

        outer.addWidget(info)

        # ---- 收款码 ----
        section = QLabel("赞助支持作者")
        section.setObjectName("section")
        outer.addWidget(section)
        tip = QLabel("工具完全免费，没有任何强制广告；觉得好用可以请作者喝杯奶茶。")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        outer.addWidget(tip)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(_QrCard("微信扫码", resource_path("assets/wechat.png"), "#07c160"))
        cards.addWidget(_QrCard("支付宝扫码", resource_path("assets/alipay.png"), "#1677ff"))
        cards.addStretch(1)
        outer.addLayout(cards)

        footer = QLabel("本工具免费提供，赞助纯属自愿，感谢你的支持。")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        outer.addWidget(footer)
        outer.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    @staticmethod
    def _add_info_row(layout, title, value):
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("muted")
        label.setFixedWidth(96)
        row.addWidget(label)
        text = QLabel(value)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(text)
        row.addStretch(1)
        layout.addLayout(row)

    def _open_url(self, url):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))
        self.ctrl.toast("已在浏览器打开：" + url)

    def _check_update(self):
        self.ctrl.toast("正在检查新版本…")
        updater.check_manually(self.ctrl)


class ChangelogPage(QWidget):
    """更新日志页"""

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("更新日志")
        title.setObjectName("section")
        head.addWidget(title)
        head.addStretch(1)
        current = QLabel("当前版本 v%s（最新 %s）" % (APP_VERSION, changelog.latest_version()))
        current.setObjectName("muted")
        head.addWidget(current)
        layout.addLayout(head)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setHtml(changelog.as_html())
        layout.addWidget(self.view, 1)
