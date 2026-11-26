"""Live Feature Monitor widget for KruxoAI.

Displays real-time operational status, live metrics, and updates for all active
features (Voice Engine, Cognitive Core / LLM, Call Shield, Plugins, Vision, Tasks).
"""

import time
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy
)

from gui.theme import C
from gui.style import px_font, hud_font, scroll_css


def _badge_style(color_key: str) -> tuple[str, str, str]:
    """Returns (text_color, bg_color, border_color) for a status badge."""
    ck = (color_key or "GREEN").upper()
    if ck in ("GREEN", "ACTIVE", "ONLINE", "LISTENING", "SPEAKING"):
        return C.GREEN, "rgba(0, 255, 136, 0.12)", C.GREEN_D
    elif ck in ("PRI", "CYAN", "PROCESSING", "THINKING"):
        return C.PRI, "rgba(0, 212, 255, 0.12)", C.PRI_DIM
    elif ck in ("RED", "MUTED", "ISOLATED", "STOPPED", "ERROR"):
        return C.RED, "rgba(255, 51, 85, 0.14)", C.RED
    elif ck in ("YELLOW", "ACC", "STANDBY", "IDLE", "PAUSED"):
        return C.ACC2, "rgba(255, 204, 0, 0.12)", C.ACC
    return C.TEXT, "rgba(143, 252, 255, 0.10)", C.BORDER


class FeatureCard(QFrame):
    """An individual feature status card with glowing badge, icon, and live detail."""

    clicked = pyqtSignal(str)

    def __init__(self, feature_id: str, icon: str, name: str, status: str,
                 detail: str = "", color_key: str = "GREEN", parent=None):
        super().__init__(parent)
        self.feature_id = feature_id
        self._name = name
        self._status = status
        self._detail = detail
        self._color_key = color_key
        self._last_time = time.time()

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_frame_style()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(7, 5, 7, 5)
        lay.setSpacing(2)

        # Top row: [ICON] [NAME] ... [STATUS BADGE]
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(5)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFont(px_font(11))
        self._icon_lbl.setStyleSheet("background: transparent;")
        top.addWidget(self._icon_lbl)

        self._name_lbl = QLabel(name)
        self._name_lbl.setFont(px_font(9, QFont.Weight.Bold, spacing=1.1))
        self._name_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        top.addWidget(self._name_lbl, stretch=1)

        self._badge_lbl = QLabel(f"● {status}")
        self._badge_lbl.setFont(px_font(8, QFont.Weight.Bold, spacing=0.8))
        self._badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_badge_style()
        top.addWidget(self._badge_lbl)

        lay.addLayout(top)

        # Bottom row: [DETAIL / LIVE METRIC] ... [TIME/STATE]
        btm = QHBoxLayout()
        btm.setContentsMargins(0, 0, 0, 0)
        btm.setSpacing(4)

        self._detail_lbl = QLabel(detail)
        self._detail_lbl.setFont(px_font(8, mono=True))
        self._detail_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._detail_lbl.setWordWrap(False)
        btm.addWidget(self._detail_lbl, stretch=1)

        self._time_lbl = QLabel("LIVE")
        self._time_lbl.setFont(px_font(7, QFont.Weight.Medium))
        self._time_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        btm.addWidget(self._time_lbl)

        lay.addLayout(btm)

    def _apply_frame_style(self):
        self.setStyleSheet(f"""
            FeatureCard {{
                background: rgba(1, 15, 24, 0.70);
                border: 1px solid {C.BORDER};
                border-radius: 4px;
            }}
            FeatureCard:hover {{
                background: rgba(1, 24, 38, 0.90);
                border: 1px solid {C.BORDER_B};
            }}
        """)

    def _update_badge_style(self):
        fg, bg, border = _badge_style(self._color_key)
        self._badge_lbl.setText(f"● {self._status}")
        self._badge_lbl.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background: {bg};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 1px 5px;
            }}
        """)

    def update_status(self, status: str, detail: str = "", color_key: str | None = None):
        """Update live status, detail and timestamp."""
        if status:
            self._status = status
        if detail:
            self._detail = detail
            self._detail_lbl.setText(detail)
        if color_key:
            self._color_key = color_key

        self._update_badge_style()
        self._last_time = time.time()
        now_str = time.strftime("%H:%M:%S")
        self._time_lbl.setText(now_str)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.feature_id)
        super().mousePressEvent(event)


class FeatureMonitorWidget(QWidget):
    """Container widget for live feature cards with smooth scroll."""

    feature_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, FeatureCard] = {}
        self._handlers: dict[str, callable] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            {scroll_css()}
        """)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 4, 0)
        self._inner_lay.setSpacing(4)

        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

        # Register default core features
        self._setup_defaults()

    def _setup_defaults(self):
        defaults = [
            ("voice", "🎙️", "VOICE ENGINE", "LISTENING",
             "Gemini Live · Kore (Realistic) · 24kHz", "GREEN"),
            ("brain", "🧠", "COGNITIVE CORE", "ONLINE",
             "Gemini 3.1 Flash · Groq Fallback Armed", "GREEN"),
            ("call_shield", "📞", "CALL SHIELD", "ARMED",
             "1-Click Audio Cut & Mute [F4 / Pause]", "GREEN"),
            ("plugins", "🧩", "PLUGIN SUITE", "45 ACTIVE",
             "45 Tools Loaded · Click to Manage", "GREEN"),
            ("vision", "👁️", "VISION SYSTEM", "READY",
             "Screen Capture & Camera Feed Armed", "PRI"),
            ("tasks", "⚙️", "BACKGROUND TASKS", "RUNNING",
             "MCP Server (Port 8000) · Auto-Routines", "GREEN"),
        ]
        for fid, icon, name, status, detail, ck in defaults:
            self.add_feature(fid, icon, name, status, detail, ck)

    def add_feature(self, feature_id: str, icon: str, name: str, status: str,
                    detail: str = "", color_key: str = "GREEN") -> FeatureCard:
        if feature_id in self._cards:
            self._cards[feature_id].update_status(status, detail, color_key)
            return self._cards[feature_id]

        card = FeatureCard(feature_id, icon, name, status, detail, color_key, parent=self._inner)
        card.clicked.connect(self._on_card_clicked)
        self._cards[feature_id] = card
        self._inner_lay.addWidget(card)
        return card

    def update_feature(self, feature_id: str, status: str, detail: str = "",
                       color_key: str | None = None):
        """Thread-safe update entry point for any feature."""
        if feature_id in self._cards:
            self._cards[feature_id].update_status(status, detail, color_key)
        else:
            self.add_feature(feature_id, "◈", feature_id.upper(), status, detail, color_key or "GREEN")

    def set_click_handler(self, feature_id: str, handler: callable):
        self._handlers[feature_id] = handler

    def _on_card_clicked(self, feature_id: str):
        handler = self._handlers.get(feature_id)
        if handler:
            handler()
        self.feature_clicked.emit(feature_id)

    def active_count(self) -> int:
        return sum(1 for c in self._cards.values()
                   if c._color_key.upper() in ("GREEN", "ACTIVE", "PRI", "ONLINE", "LISTENING", "SPEAKING"))
