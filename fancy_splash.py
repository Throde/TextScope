# fancy_splash.py
from PySide6.QtCore import Qt, QRectF, QTimer, QPoint, QSize
from PySide6.QtGui import QPainter, QFont, QLinearGradient, QColor, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QApplication

class FancySplash(QWidget):
    def __init__(self, title: str = "TextScope", subtitle: str = "Launching…", logo: QPixmap | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.SplashScreen | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._title = title
        self._subtitle = subtitle
        self._progress = 0            # 0..100
        self._message = ""            # 状态文本
        self._logo = logo if logo and not logo.isNull() else None
        self._dots = 0

        # 尺寸与布局变量
        self._w, self._h = 360, 200
        self.resize(self._w, self._h)

        # 小动画（… 跑马点）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)

        # DPI 缩放：可选，根据平台需要
        self._maybe_center_on_primary()

    def _maybe_center_on_primary(self):
        scr = QApplication.primaryScreen()
        if scr:
            geo = scr.availableGeometry()
            self.move(geo.center() - self.rect().center())

    # ------- 对外 API -------
    def set_progress(self, percent: int, message: str | None = None, subtitle: str | None = None):
        self._progress = max(0, min(100, int(percent)))
        if message is not None:
            self._message = message
        if subtitle is not None:
            self._subtitle = subtitle
        self.update()

    def set_title(self, title: str):
        self._title = title
        self.update()

    def set_logo(self, px: QPixmap):
        self._logo = px
        self.update()

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self.update()

    # ------- 绘制 -------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # ---- 背景阴影（手绘柔和阴影）----
        shadow_color = QColor(0, 0, 0, 80)
        for i in range(10):
            alpha = int(80 * (1 - i / 10))
            shadow_color.setAlpha(alpha)
            r = QRectF(10 - i, 10 - i, self._w - (10 - i)*2, self._h - (10 - i)*2)
            p.setPen(Qt.NoPen)
            p.setBrush(shadow_color)
            p.drawRoundedRect(r, 18, 18)

        # ---- 主卡片 ----
        card_rect = QRectF(10, 10, self._w - 20, self._h - 20)
        grad = QLinearGradient(card_rect.topLeft(), card_rect.bottomRight())
        grad.setColorAt(0.0, QColor(255, 255, 255, 245))
        grad.setColorAt(1.0, QColor(245, 247, 250, 240))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(card_rect, 14, 14)

        # 分割线
        p.setPen(QPen(QColor(0, 0, 0, 18), 1))
        p.drawLine(int(card_rect.left())+24, int(card_rect.top())+92, int(card_rect.right())-24, int(card_rect.top())+92)

        # ---- Logo（可选）----
        x_cursor = int(card_rect.left()) + 24
        top_y = int(card_rect.top()) + 20
        if self._logo:
            size = 48
            px = self._logo.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(x_cursor, top_y+2, px)
            x_cursor += size + 14

        # ---- Title / Subtitle ----
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setWeight(QFont.DemiBold)
        p.setFont(title_font)
        p.setPen(QColor(28, 28, 30))
        p.drawText(x_cursor, top_y + 18, self._title)

        sub_font = QFont()
        sub_font.setPointSize(10)
        p.setFont(sub_font)
        p.setPen(QColor(90, 90, 95))
        p.drawText(x_cursor, top_y + 42, self._subtitle)

        # ---- 进度条 ----
        bar_left = int(card_rect.left()) + 24
        bar_top  = int(card_rect.top()) + 120
        bar_w    = int(card_rect.width()) - 48
        bar_h    = 10

        # 背槽
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 238, 242))
        p.drawRoundedRect(QRectF(bar_left, bar_top, bar_w, bar_h), 5, 5)

        # 已完成
        done_w = int(bar_w * (self._progress / 100.0))
        grad2 = QLinearGradient(QPoint(bar_left, bar_top), QPoint(bar_left + done_w, bar_top + bar_h))
        grad2.setColorAt(0.0, QColor(74, 144, 226))  # 温和蓝
        grad2.setColorAt(1.0, QColor(88, 86, 214))   # 紫蓝过渡
        p.setBrush(grad2)
        p.drawRoundedRect(QRectF(bar_left, bar_top, max(8, done_w), bar_h), 5, 5)

        # 文字状态（带 … 动画）
        msg_font = QFont()
        msg_font.setPointSize(10)
        p.setFont(msg_font)
        dots = "." * self._dots
        status_text = self._message + dots if self._message else ""
        p.setPen(QColor(70, 70, 75))
        p.drawText(QRectF(bar_left, bar_top + 18, bar_w, 20), Qt.AlignLeft | Qt.AlignVCenter, status_text)

        # 右下角小版本号（可选）
        p.setPen(QColor(150, 150, 155))
        p.setFont(QFont("", 8))
        p.drawText(QRectF(card_rect.right()-90, card_rect.bottom()-26, 80, 16),
                   Qt.AlignRight | Qt.AlignVCenter, f"{self._progress}%")
