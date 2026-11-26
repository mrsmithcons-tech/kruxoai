"""
gui/cyber_avatar.py — Photorealistic Cyber-Female HUD Avatar for KruxoAI.

Combines high-definition realistic female facial anatomy with dynamic,
audio-reactive lip sync, lifelike facial expressions, and sci-fi HUD overlays:
- True anatomical lip sync with real-time visemes, consonant closures, jaw drop,
  teeth reveal, and oral cavity depth.
- Natural blinking with eyelid sweeps and eyelash closure lines.
- Saccadic eye gaze tracking with cognitive state bias (thoughtful look-away
  when thinking, direct eye contact when listening or speaking).
- Dynamic eyebrow articulation tracking vocal intonation and thinking furrow.
- Syllable emphasis head nod & breathing respiration sway.
- Animated ocular targeting reticle over the right eye with counter-rotating
  notched rings, 360° radar sweep, and micro-telemetry.
- Neural fiber optic data streams with travelling glowing packets.
- Vocal acoustic ripples radiating from moving lips during speech.
"""
from __future__ import annotations

import math
import random
import time
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient
)

from gui.theme import C, qcol
from gui.style import px_font

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "gui" / "assets"

# Viseme & Mouth timing constants (seconds)
_TAU_OPEN = 0.022     # jaw dropping toward a vowel
_TAU_SHUT = 0.012     # lips closing on a consonant, mid-word
_TAU_REST = 0.055     # settling back to rest after speech ends
_TAU_SHAPE = 0.018    # viseme openness following schedule
_MIC_FLOOR = 0.14
_CLOSE_FRAC = 0.10


def _rate(dt: float, tau: float) -> float:
    """Frame-rate independent exponential approach factor."""
    return 1.0 - math.exp(-dt / max(0.001, tau))


class CyberFemaleAvatar:
    """Photorealistic female cybernetic AI avatar with dynamic lip sync,

    talking facial expressions, and sci-fi holographic HUD overlays.
    """

    # Normalized facial landmarks on the 512x512 working canvas
    CANVAS_SIZE = 512

    # Eye center coordinates
    EYE_L_U = 0.333    # viewer's left eye (her right)
    EYE_L_V = 0.420
    EYE_R_U = 0.525    # viewer's right eye (her left, with ocular HUD)
    EYE_R_V = 0.418

    # Mouth & jaw center
    MOUTH_U = 0.428
    MOUTH_V = 0.619

    def __init__(self) -> None:
        self._t = 0.0
        self._amp = 0.0
        self._amp_slow = 0.0

        # ── Lip sync & visemes ───────────────────────────────────────────────
        self._mouth = 0.0          # 0..1 smoothed mouth opening
        self._wide = 0.0           # -1 (round /u/) .. +1 (spread /i/)
        self._v_open = 1.0
        self._v_peak = 0.18
        self._emph = 0.0           # syllable emphasis driving speech head nod

        # ── Expressions & eyes ───────────────────────────────────────────────
        self._blink = 0.0          # 0 = open, 1 = shut
        self._blink_at = 3.2
        self._blink_speed = 9.0
        self._gaze = [0.0, 0.0]    # [gx, gy] saccadic eye gaze
        self._gaze_tgt = [0.0, 0.0]
        self._gaze_at = 0.0
        self._gaze_bias = [0.0, 0.0]
        self._bias_tgt = [0.0, 0.0]
        self._bias_at = 0.0

        # Eyebrows & smile
        self._brow = 0.0           # -0.4 .. 1.2 brow lift / furrow
        self._brow_bias = 0.0
        self._expr = 0.0           # subtle smile/expression
        self._expr_tgt = 0.0
        self._expr_at = 0.0

        # Respiration sway & orientation
        self._sway = 0.0
        self._breathe = 0.0
        self._yaw = 0.0
        self._pitch = 0.0

        # ── HUD reticle & streams ────────────────────────────────────────────
        self._rot_outer = 0.0
        self._rot_inner = 0.0
        self._radar_angle = 0.0
        self._particles = [
            {"t": random.random(), "speed": random.uniform(0.18, 0.42), "path": i % 3}
            for i in range(12)
        ]

        # ── Image processing buffers ─────────────────────────────────────────
        self._base_rgba: np.ndarray | None = None
        self._grid_x: np.ndarray | None = None
        self._grid_y: np.ndarray | None = None
        self._cached_pixmap: QPixmap | None = None
        self._last_mouth = -1.0
        self._last_wide = -1.0
        self._last_blink = -1.0
        self._last_brow = -1.0
        self._last_gaze = [-99.0, -99.0]
        self._last_render_t = 0.0

        self._init_face_buffers()

    def _init_face_buffers(self) -> None:
        """Load and downscale master portrait into a 512x512 RGBA working buffer."""
        candidates = [
            ASSETS_DIR / "cyber_female_face_vignette.png",
            ASSETS_DIR / "cyber_female_face_hd.jpg",
            ASSETS_DIR / "cyber_female_face.jpg",
        ]
        target = None
        for p in candidates:
            if p.exists():
                target = p
                break

        if target is None:
            return

        img = cv2.imread(str(target), cv2.IMREAD_UNCHANGED)
        if img is None:
            return

        if len(img.shape) == 2:
            rgba = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
        elif img.shape[2] == 3:
            rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
        elif img.shape[2] == 4:
            rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        else:
            return

        self._base_rgba = cv2.resize(rgba, (self.CANVAS_SIZE, self.CANVAS_SIZE),
                                     interpolation=cv2.INTER_AREA)

        h, w = self.CANVAS_SIZE, self.CANVAS_SIZE
        self._grid_y, self._grid_x = np.mgrid[0:h, 0:w].astype(np.float32)

        # Pre-render initial resting pixmap
        self._update_face_pixmap(force=True)

    # ── Animation & Step Logic ───────────────────────────────────────────────

    def _mouth_step(self, dt: float, amp: float, live: bool,
                    v_open: float | None, v_level: float | None) -> None:
        """Increment jaw & lip position with true vocal articulation physics."""
        if v_open is None:
            shape = 1.0
        else:
            self._v_open += (v_open - self._v_open) * _rate(dt, _TAU_SHAPE)
            shape = self._v_open

        if v_level is None:
            gated = max(0.0, (amp - _MIC_FLOOR) / (1.0 - _MIC_FLOOR))
            drive = (gated ** 0.6) * (shape ** 0.75)
        else:
            self._v_peak = max(v_level, self._v_peak - dt * 0.55)
            ref = max(0.18, self._v_peak)
            q = (v_level - _CLOSE_FRAC * ref) / (ref * (1.0 - _CLOSE_FRAC))
            drive = (max(0.0, min(1.0, q)) ** 0.85) * (shape ** 0.75)

        target = min(1.0, drive) if live else 0.0
        if target > self._mouth:
            tau = _TAU_OPEN
        elif live:
            tau = _TAU_SHUT      # mid-word consonant: fast closure
        else:
            tau = _TAU_REST      # speech ended: gentle return to rest

        self._mouth += (target - self._mouth) * _rate(dt, tau)
        if self._mouth < 0.003:
            self._mouth = 0.0

    def step(self, dt: float, amp: float, speaking: bool = False,
             muted: bool = False, state: str = "",
             v_open: float | None = None, v_wide: float = 0.0,
             v_level: float | None = None,
             v_seq: list | None = None, v_hop: float = 0.02) -> None:
        """Advance time, lip sync, expressions, saccades, and HUD rotation."""
        dt = max(0.001, min(0.10, float(dt)))
        self._t += dt
        t = self._t
        amp = max(0.0, min(1.0, float(amp)))
        self._amp += (amp - self._amp) * 0.35
        live = speaking and not muted

        # ── 1. Respiration & Idle Sway ───────────────────────────────────────
        speed = (1.0 if not muted else 0.55) * (1.25 if live else 1.0)
        self._sway += dt * speed
        s = self._sway
        self._yaw = 0.015 * math.sin(s * 0.32) + 0.008 * math.sin(s * 0.74 + 1.2)
        self._pitch = 0.012 * math.sin(s * 0.24 + 0.6)
        self._breathe = math.sin(s * 1.4) * 2.8

        # ── 2. Lip Sync & Jaw Articulation ───────────────────────────────────
        if v_seq is not None:
            for lv, op, _wd in v_seq:
                self._mouth_step(v_hop, amp, live, op, lv)
        else:
            self._mouth_step(dt, amp, live, v_open, v_level)

        # Smooth lip width (-1 round .. +1 spread)
        wide_tgt = v_wide if (live and v_open is not None) else 0.0
        self._wide += (max(-1.0, min(1.0, wide_tgt)) - self._wide) * _rate(dt, 0.030)

        # Syllable emphasis head nod
        self._emph += (self._mouth - self._emph) * _rate(
            dt, 0.055 if self._mouth > self._emph else 0.30)
        self._pitch += self._emph * 0.024
        self._yaw += 0.012 * math.sin(t * 1.8) * self._emph

        # Loudness envelope for phrases & brows
        env = amp if live else 0.0
        self._amp_slow += (env - self._amp_slow) * _rate(
            dt, 0.16 if env > self._amp_slow else 0.36)

        # ── 3. Facial Expressions (Brows & Warmth) ───────────────────────────
        if live:
            if t >= self._expr_at:
                self._expr_tgt = random.uniform(0.05, 0.32)
                self._expr_at = t + 1.2 + 2.0 * random.random()
        else:
            self._expr_tgt = 0.0
            self._expr_at = t + 0.8
        self._expr += (self._expr_tgt - self._expr) * 0.08

        # ── 4. Cognitive State & Gaze Bias ───────────────────────────────────
        st = (state or "").upper()
        thinking = st in ("THINKING", "PROCESSING")
        asleep = st in ("SLEEPING", "STANDBY", "OFFLINE")

        if thinking:
            if t >= self._bias_at:
                self._bias_tgt = [random.choice((-1.0, 1.0)) * random.uniform(0.40, 0.75),
                                  random.uniform(-0.45, -0.20)]
                self._bias_at = t + 1.5 + 1.5 * random.random()
            brow_bias = -0.32    # thoughtful furrow
        elif asleep:
            self._bias_tgt = [0.0, 0.25]
            brow_bias = -0.05
        else:
            # Listening or speaking: gaze focuses forward
            self._bias_tgt = [0.0, 0.0]
            self._bias_at = 0.0
            brow_bias = 0.12 if st == "LISTENING" else 0.0

        for i in (0, 1):
            self._gaze_bias[i] += (self._bias_tgt[i] - self._gaze_bias[i]) * 0.06
        self._brow_bias += (brow_bias - self._brow_bias) * 0.06

        # Saccades
        if t >= self._gaze_at:
            reach = 0.85 if live else (0.30 if thinking else 0.50)
            self._gaze_tgt = [random.uniform(-1.0, 1.0) * reach,
                              random.uniform(-1.0, 1.0) * reach * 0.55]
            if live:
                self._gaze_at = t + 0.6 + 1.6 * random.random()
            elif thinking:
                self._gaze_at = t + 1.8 + 2.2 * random.random()
            else:
                self._gaze_at = t + 1.4 + 2.6 * random.random()

        for i in (0, 1):
            tgt = max(-1.0, min(1.0, self._gaze_tgt[i] + self._gaze_bias[i]))
            self._gaze[i] += (tgt - self._gaze[i]) * 0.28

        # Eyebrow lift
        brow_t = 0.60 * self._amp_slow + 0.50 * self._expr + self._brow_bias
        self._brow += (max(-0.4, min(1.2, brow_t)) - self._brow) * 0.20

        # ── 5. Blinking Dynamics ─────────────────────────────────────────────
        if self._blink > 0.0:
            self._blink = max(0.0, self._blink - dt * self._blink_speed)
        elif t >= self._blink_at:
            if asleep:
                self._blink_at = t + 5.0
            else:
                self._blink = 1.0
                gap = 5.2 if thinking else 3.2
                self._blink_at = t + gap + 3.0 * random.random()

        # ── 6. HUD Reticle & Streams ─────────────────────────────────────────
        hud_speed = 2.4 if speaking else (2.8 if thinking else 0.85)
        self._rot_outer += dt * hud_speed * 40.0
        self._rot_inner -= dt * hud_speed * 55.0
        self._radar_angle = (self._radar_angle + dt * hud_speed * 85.0) % 360.0

        for p in self._particles:
            p["t"] = (p["t"] + dt * p["speed"] * (1.8 if speaking else 1.0)) % 1.0

        # Trigger texture update
        self._update_face_pixmap()

    # ── Real-Time Facial Deformation Engine ──────────────────────────────────

    def _update_face_pixmap(self, force: bool = False) -> None:
        """Deform face mesh (mouth/visemes, blinking, gaze, brows) and update pixmap."""
        if self._base_rgba is None or self._grid_x is None:
            return

        now = self._t
        # Throttle deformation calculation when values haven't changed meaningfully
        d_mouth = abs(self._mouth - self._last_mouth)
        d_wide = abs(self._wide - self._last_wide)
        d_blink = abs(self._blink - self._last_blink)
        d_brow = abs(self._brow - self._last_brow)
        d_gaze = abs(self._gaze[0] - self._last_gaze[0]) + abs(self._gaze[1] - self._last_gaze[1])

        if not force and d_mouth < 0.008 and d_wide < 0.015 and d_blink < 0.02 and d_brow < 0.015 and d_gaze < 0.02:
            return

        self._last_mouth = self._mouth
        self._last_wide = self._wide
        self._last_blink = self._blink
        self._last_brow = self._brow
        self._last_gaze = list(self._gaze)
        self._last_render_t = now

        h, w = self.CANVAS_SIZE, self.CANVAS_SIZE
        gx, gy = self._grid_x, self._grid_y
        dx = np.zeros((h, w), dtype=np.float32)
        dy = np.zeros((h, w), dtype=np.float32)

        # ── 1. Eyebrow Motion (Lift & Thinking Furrow) ─────────────────────────
        brow_val = self._brow
        if abs(brow_val) > 0.01:
            for cx_b, sign_b in [(165.0, -1.0), (265.0, 1.0)]:
                dist_xb = np.abs(gx - cx_b)
                dist_yb = np.abs(gy - 180.0)
                wb = np.clip(1.0 - (dist_xb / 35.0)**2, 0.0, 1.0) * np.clip(1.0 - (dist_yb / 18.0)**2, 0.0, 1.0)
                dy -= brow_val * 7.5 * (np.maximum(0.0, wb) ** 1.3)
                if brow_val < 0.0:    # furrow inward
                    dx -= sign_b * brow_val * 3.5 * (np.maximum(0.0, wb) ** 1.3)

        # ── 2. Eye Gaze & Eyelid Blinking ────────────────────────────────────
        gaze_x, gaze_y = self._gaze
        blink_val = self._blink
        eyes = [(170.5, 215.0, 19.0, 10.0), (269.0, 214.0, 19.0, 10.0)]

        for cx_e, cy_e, rx_e, ry_e in eyes:
            dist_xe = np.abs(gx - cx_e)
            dist_ye = np.abs(gy - cy_e)
            we = np.clip(1.0 - (dist_xe / rx_e)**2, 0.0, 1.0) * np.clip(1.0 - (dist_ye / ry_e)**2, 0.0, 1.0)

            # Iris saccade
            if abs(gaze_x) > 0.01 or abs(gaze_y) > 0.01:
                dx -= gaze_x * 3.6 * (np.maximum(0.0, we) ** 1.5)
                dy -= gaze_y * 2.6 * (np.maximum(0.0, we) ** 1.5)

            # Eyelid sweep down on blink
            if blink_val > 0.01:
                y_close = cy_e + 5.0
                mask_lid = (gy <= y_close) & (gy >= cy_e - ry_e * 1.6) & (dist_xe < rx_e * 1.1)
                wx_lid = np.clip(1.0 - (dist_xe / (rx_e * 1.1))**2, 0.0, 1.0)
                dist_to_close = np.clip((y_close - gy) / max(1.0, (y_close - (cy_e - ry_e * 1.6))), 0.0, 1.0)
                drop = blink_val * 12.5 * (np.maximum(0.0, wx_lid) ** 1.2) * (1.0 - dist_to_close**1.4)
                dy[mask_lid] -= drop[mask_lid]

        # ── 3. Mouth & Lower Jaw Articulation ────────────────────────────────
        mouth_val = self._mouth
        wide_val = self._wide
        cx_m, cy_m, rx_m = 219.0, 317.0, 42.5
        dist_xm = np.abs(gx - cx_m)
        wx_m = np.clip(1.0 - (dist_xm / (rx_m * 1.3))**2, 0.0, 1.0)

        # Lower lip & mandible drop
        mask_lower = (gy >= cy_m) & (gy <= 430) & (dist_xm < rx_m * 1.5)
        vert_prog = np.clip((gy - cy_m) / (430.0 - cy_m), 0.0, 1.0)
        wy_lower = np.clip(1.0 - vert_prog**1.2, 0.0, 1.0)
        max_drop = 17.5 * mouth_val
        dy[mask_lower] -= max_drop * (np.maximum(0.0, wx_m[mask_lower]) ** 1.4) * wy_lower[mask_lower]

        # Upper lip slight lift
        mask_upper = (gy < cy_m) & (gy >= 288) & (dist_xm < rx_m * 1.2)
        dist_up_frac = np.clip((cy_m - gy) / max(1.0, (cy_m - 288.0)), 0.0, 1.0)
        wy_upper = np.clip(1.0 - dist_up_frac**1.4, 0.0, 1.0)
        max_lift = 3.6 * mouth_val
        dy[mask_upper] += max_lift * (np.maximum(0.0, wx_m[mask_upper]) ** 1.4) * wy_upper[mask_upper]

        # Lip spread / round (wide_val)
        mask_lips = (gy >= 290) & (gy <= 350) & (dist_xm < rx_m * 1.3)
        sign_xm = np.sign(gx - cx_m)
        dx[mask_lips] -= wide_val * 7.0 * sign_xm[mask_lips] * (np.maximum(0.0, wx_m[mask_lips]) ** 0.8)

        # ── Remap Texture ────────────────────────────────────────────────────
        map_x = gx + dx
        map_y = gy + dy
        warped = cv2.remap(self._base_rgba, map_x, map_y, cv2.INTER_LINEAR)

        # ── 4. Oral Cavity & Teeth Reveal ────────────────────────────────────
        if mouth_val > 0.05:
            gap_h = (max_drop + max_lift) * (np.maximum(0.0, wx_m) ** 1.4)
            y_top = cy_m - max_lift * (np.maximum(0.0, wx_m) ** 1.4) * 0.4
            y_bot = cy_m + max_drop * (np.maximum(0.0, wx_m) ** 1.4) * 0.85
            in_gap = (gy >= y_top) & (gy <= y_bot) & (gap_h > 1.4)

            t_prog = np.clip((gy - y_top) / np.maximum(1.0, (y_bot - y_top)), 0.0, 1.0)
            teeth_mask = in_gap & (t_prog >= 0.04) & (t_prog <= 0.50) & (dist_xm < 25.0)
            teeth_fade = np.clip(1.0 - (dist_xm / 25.0)**2, 0.0, 1.0) * np.sin(t_prog / 0.50 * np.pi)

            # Cavity background (dark burgundy/black)
            for ch, val in enumerate([32, 12, 18]):
                warped[in_gap, ch] = (warped[in_gap, ch] * 0.12 + val * 0.88).astype(np.uint8)

            # Upper teeth arc (soft pearlescent enamel)
            for ch, val in enumerate([230, 218, 198]):
                tf = teeth_fade[teeth_mask]
                warped[teeth_mask, ch] = (warped[teeth_mask, ch] * (1.0 - tf) + val * tf).astype(np.uint8)

            warped[in_gap, 3] = 255

        # ── 5. Eyelash Line on Blink ─────────────────────────────────────────
        if blink_val > 0.65:
            for cx_e, cy_e, rx_e, ry_e in eyes:
                lash_y = int(cy_e + 5.0)
                cv2.ellipse(warped, (int(cx_e), lash_y),
                            (int(rx_e * 0.92), int(2 * (1.0 - blink_val) + 1)),
                            0, 0, 180, (25, 18, 22, 240), 1)

        # Convert warped RGBA array to QPixmap
        qimg = QImage(warped.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._cached_pixmap = QPixmap.fromImage(qimg.copy())

    # ── HUD Painting ─────────────────────────────────────────────────────────

    def paint(self, p: QPainter, cx: float, cy: float, bound_h: float,
              primary: QColor, accent: QColor, bg: QColor) -> None:
        """Render photorealistic cyber-avatar, dynamic lip sync, and cyber HUD."""
        if self._cached_pixmap is None:
            self._update_face_pixmap(force=True)
            if self._cached_pixmap is None:
                return

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        amp = max(0.0, min(1.0, self._amp))

        # Dynamic head bounding box with respiration sway & syllable nod
        draw_h = min(bound_h * 1.15, 480.0)
        draw_w = draw_h * (self._cached_pixmap.width() / max(1.0, self._cached_pixmap.height()))
        draw_x = cx - draw_w * 0.50 + self._yaw * draw_w * 0.25
        draw_y = cy - draw_h * 0.50 + self._breathe + self._pitch * draw_h * 0.35
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

        # ── 2. Expressive Photorealistic Female Face Layer ───────────────────
        p.drawPixmap(rect.toRect(), self._cached_pixmap)

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

        # Traveling glowing data packets
        node_brush = QBrush(QColor(255, 255, 255, int(190 + 65 * amp)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(node_brush)
        for part in self._particles:
            path_idx = part["path"]
            if path_idx < len(paths):
                pt = paths[path_idx].pointAtPercent(part["t"])
                p.drawEllipse(pt, 2.2, 2.2)

        # ── 4. Dynamic Ocular Cyber-HUD Reticle Over Right Eye ────────────────
        eye_x = rect.left() + rect.width() * self.EYE_R_U
        eye_y = rect.top() + rect.height() * self.EYE_R_V
        reticle_r = draw_w * 0.095

        p.save()
        p.translate(eye_x, eye_y)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Outer Notched Ring
        p.save()
        p.rotate(self._rot_outer)
        outer_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), int(160 + 85 * amp)), 1.3)
        p.setPen(outer_pen)
        p.drawEllipse(QPointF(0, 0), reticle_r, reticle_r)

        # 12 Compass Calibration Ticks
        tick_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), int(140 + 80 * amp)), 1.5)
        p.setPen(tick_pen)
        for deg in range(0, 360, 30):
            p.save()
            p.rotate(deg)
            p.drawLine(QPointF(0, reticle_r - 4.5), QPointF(0, reticle_r + 2.5))
            p.restore()
        p.restore()

        # Inner Segmented Arc Ring (Counter-rotating)
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

        # Central Crosshairs
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

        # Micro-Telemetry Readouts
        p.setFont(px_font(7, QFont.Weight.Bold, spacing=1.2))
        p.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 190)))
        p.drawText(QPointF(reticle_r + 6.0, -8.0), "LOCK: ONLINE")
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 180)))
        p.drawText(QPointF(reticle_r + 6.0, 4.0), f"SYNC: {int(98 + 2 * math.sin(self._t * 2))}%")
        p.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 150)))
        p.drawText(QPointF(reticle_r + 6.0, 16.0), "SYS: OPTIMAL")

        p.restore()

        # ── 5. Vocal Acoustic Ripples from Articulating Lips ─────────────────
        if amp > 0.08:
            lip_x = rect.left() + rect.width() * self.MOUTH_U
            lip_y = rect.top() + rect.height() * self.MOUTH_V + self._mouth * 6.0
            for ring_i in range(1, 4):
                wave_r = (22.0 + ring_i * 18.0) * (0.8 + 0.5 * amp)
                wave_alpha = int(max(0.0, (1.0 - ring_i * 0.28) * 160 * amp))
                wave_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), wave_alpha), 1.2)
                p.setPen(wave_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(lip_x, lip_y), wave_r, wave_r * 0.42)
