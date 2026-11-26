"""
gui/cyber_avatar.py — Photorealistic Cyber-Female HUD Avatar for KruxoAI.

Combines high-definition realistic female facial imagery with dynamic,
audio-reactive holographic cyber-HUD overlays:
- Interactive rotating ocular targeting scanner around the eye
- Breathing idle sway & life pulse
- Flowing neural data stream lines and cyber-grid nodes
- Real-time vocal acoustic energy glow responding to speech & mic
"""
from __future__ import annotations

import math
import random
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient, QTransform
)

from gui.theme import C, qcol
from gui.style import px_font

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "gui" / "assets"


class CyberFemaleAvatar:
    """Photorealistic female cybernetic AI avatar with dynamic HUD overlays."""

    # Eye reticle normalized coordinates on the 1024x1024 master portrait
    EYE_U = 0.525
    EYE_V = 0.418

    # Lip normalized coordinates for vocal acoustic ripples
    LIP_U = 0.435
    LIP_V = 0.615

    def __init__(self) -> None:
        self._t = 0.0
        self._amp = 0.0
        self._rot_outer = 0.0
        self._rot_inner = 0.0
        self._radar_angle = 0.0
        self._breathe = 0.0
        self._particles = [
            {"t": random.random(), "speed": random.uniform(0.15, 0.45), "path": i % 3}
            for i in range(12)
        ]

        # Load avatar visual asset
        self._pixmap = None
        self._load_pixmap()

    def _load_pixmap(self) -> None:
        """Load the soft-vignetted photorealistic female cyber face."""
        candidates = [
            ASSETS_DIR / "cyber_female_face_vignette.png",
            ASSETS_DIR / "cyber_female_face_hd.jpg",
            ASSETS_DIR / "cyber_female_face.jpg",
        ]
        for path in candidates:
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self._pixmap = pm
                    break

    def step(self, dt: float, amp: float, speaking: bool = False,
             muted: bool = False, state: str = "") -> None:
        """Advance time, rotation phases, breathing, and data streams."""
        dt = max(0.001, min(0.10, float(dt)))
        self._t += dt
        self._amp += (amp - self._amp) * 0.35

        st = (state or "").upper()
        speed = 2.4 if speaking else (2.8 if st in ("THINKING", "PROCESSING") else 0.85)
        self._rot_outer += dt * speed * 40.0
        self._rot_inner -= dt * speed * 55.0
        self._radar_angle = (self._radar_angle + dt * speed * 85.0) % 360.0

        # Gentle floating respiration sway
        self._breathe = math.sin(self._t * 1.5) * 3.2

        # Advance data stream particles
        for p in self._particles:
            p["t"] = (p["t"] + dt * p["speed"] * (1.8 if speaking else 1.0)) % 1.0

    def paint(self, p: QPainter, cx: float, cy: float, bound_h: float,
              primary: QColor, accent: QColor, bg: QColor) -> None:
        """Render photorealistic female cyber-avatar and live animated HUD overlays."""
        if self._pixmap is None:
            self._load_pixmap()
            if self._pixmap is None:
                return

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        amp = max(0.0, min(1.0, self._amp))
        dim_col = QColor(primary)
        dim_col.setAlpha(120)

        # Scale portrait to fit HUD canvas
        draw_h = min(bound_h * 1.15, 480.0)
        draw_w = draw_h * (self._pixmap.width() / max(1.0, self._pixmap.height()))
        draw_y = cy - draw_h * 0.50 + self._breathe
        draw_x = cx - draw_w * 0.50
        rect = QRectF(draw_x, draw_y, draw_w, draw_h)

        # ── 1. Ambient Background Halo ───────────────────────────────────────
        aura_r = draw_w * 0.58
        aura_grad = QRadialGradient(cx, cy + self._breathe * 0.5, aura_r)
        aura_grad.setColorAt(0.0, QColor(primary.red(), primary.green(), primary.blue(), int(35 + 45 * amp)))
        aura_grad.setColorAt(0.65, QColor(primary.red(), primary.green(), primary.blue(), int(15 + 20 * amp)))
        aura_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura_grad))
        p.drawEllipse(QRectF(cx - aura_r, cy - aura_r + self._breathe * 0.5, aura_r * 2, aura_r * 2))

        # ── 2. Photorealistic Female Face Layer ──────────────────────────────
        p.drawPixmap(rect.toRect(), self._pixmap)

        # ── 3. Animated Neural Fiber Streams (Temple to Edge) ─────────────────
        temple_x = rect.left() + rect.width() * 0.72
        temple_y = rect.top() + rect.height() * 0.32
        fiber_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 110), 1.2)
        p.setBrush(Qt.BrushStyle.NoBrush)

        paths = []
        for i, off_y in enumerate((-25.0, 10.0, 48.0)):
            path = QPainterPath()
            path.moveTo(temple_x, temple_y + i * 8.0)
            c1_x = temple_x + 55.0
            c1_y = temple_y + off_y * 0.6
            c2_x = temple_x + 110.0
            c2_y = temple_y + off_y
            end_x = min(cx + draw_w * 0.68, temple_x + 160.0)
            end_y = temple_y + off_y * 1.35
            path.cubicTo(c1_x, c1_y, c2_x, c2_y, end_x, end_y)
            paths.append(path)
            p.setPen(fiber_pen)
            p.drawPath(path)

        # Traveling glowing data packets along fibers
        node_brush = QBrush(QColor(255, 255, 255, int(190 + 65 * amp)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(node_brush)
        for part in self._particles:
            path_idx = part["path"]
            if path_idx < len(paths):
                pt = paths[path_idx].pointAtPercent(part["t"])
                p.drawEllipse(pt, 2.2, 2.2)

        # ── 4. Ocular Cyber-HUD Reticle (Around Her Eye) ───────────────────────
        eye_x = rect.left() + rect.width() * self.EYE_U
        eye_y = rect.top() + rect.height() * self.EYE_V
        reticle_r = draw_w * 0.095

        p.save()
        p.translate(eye_x, eye_y)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Reticle Outer Notched Tech Ring
        p.save()
        p.rotate(self._rot_outer)
        outer_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), int(160 + 85 * amp)), 1.3)
        p.setPen(outer_pen)
        p.drawEllipse(QPointF(0, 0), reticle_r, reticle_r)

        # 12 Compass Tick Marks on Outer Ring
        tick_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), int(140 + 80 * amp)), 1.5)
        p.setPen(tick_pen)
        for deg in range(0, 360, 30):
            p.save()
            p.rotate(deg)
            p.drawLine(QPointF(0, reticle_r - 4.5), QPointF(0, reticle_r + 2.5))
            p.restore()
        p.restore()

        # Reticle Inner Segmented Ring (Rotating Reverse)
        p.save()
        p.rotate(self._rot_inner)
        inner_r = reticle_r * 0.76
        inner_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), int(190 + 65 * amp)), 1.6)
        p.setPen(inner_pen)
        p.drawArc(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2), 20 * 16, 75 * 16)
        p.drawArc(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2), 140 * 16, 85 * 16)
        p.drawArc(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2), 260 * 16, 70 * 16)
        p.restore()

        # Radar Sweep Beam
        p.save()
        p.rotate(self._radar_angle)
        sweep_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), int(70 + 80 * amp)), 1.2)
        p.setPen(sweep_pen)
        p.drawLine(QPointF(0, 0), QPointF(reticle_r * 0.95, 0))
        p.restore()

        # Center Eye Crosshairs
        cross_pen = QPen(QColor(255, 255, 255, int(150 + 90 * amp)), 1.1)
        p.setPen(cross_pen)
        p.drawLine(QPointF(-reticle_r * 0.28, 0), QPointF(reticle_r * 0.28, 0))
        p.drawLine(QPointF(0, -reticle_r * 0.28), QPointF(0, reticle_r * 0.28))

        # Dynamic Audio-Reactive Pulse Ring
        if amp > 0.05:
            pulse_r = reticle_r * (1.05 + 0.35 * amp)
            pulse_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), int(180 * (1.0 - amp * 0.6))), 1.2)
            p.setPen(pulse_pen)
            p.drawEllipse(QPointF(0, 0), pulse_r, pulse_r)

        # Micro Telemetry Readout Beside Eye
        p.setFont(px_font(7, QFont.Weight.Bold, spacing=1.2))
        p.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 190)))
        p.drawText(QPointF(reticle_r + 6.0, -8.0), "LOCK: ONLINE")
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 180)))
        p.drawText(QPointF(reticle_r + 6.0, 4.0), f"SYNC: {int(98 + 2 * math.sin(self._t * 2))}%")
        p.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 150)))
        p.drawText(QPointF(reticle_r + 6.0, 16.0), "SYS: OPTIMAL")

        p.restore()

        # ── 5. Vocal Acoustic Waves (Speaking Reactivity) ─────────────────────
        if amp > 0.08:
            lip_x = rect.left() + rect.width() * self.LIP_U
            lip_y = rect.top() + rect.height() * self.LIP_V
            for ring_i in range(1, 4):
                wave_r = (22.0 + ring_i * 18.0) * (0.8 + 0.5 * amp)
                wave_alpha = int(max(0.0, (1.0 - ring_i * 0.28) * 160 * amp))
                wave_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), wave_alpha), 1.2)
                p.setPen(wave_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(lip_x, lip_y), wave_r, wave_r * 0.42)
