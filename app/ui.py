
from __future__ import annotations
import os
import re
# -- frameless / title bar -------------------------------------------------
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QHBoxLayout as _HBox, QLabel as _QLabel, QPushButton as _QPushButton, QSizeGrip as _QSizeGrip, QWidget


class TitleBar(QWidget):
    def __init__(self, title: str, context: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(34)
        self._drag_pos = None
        layout = _HBox(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)
        icon = _QLabel()
        icon.setFixedSize(16, 16)
        import qtawesome as _qta
        icon.setPixmap(_qta.icon("fa5s.chart-line", color="#38bdf8").pixmap(14, 14))
        layout.addWidget(icon)
        title_lbl = _QLabel(title)
        title_lbl.setObjectName("titleBarTitle")
        layout.addWidget(title_lbl)
        self.context_label = _QLabel(context)
        self.context_label.setObjectName("titleBarContext")
        layout.addWidget(self.context_label)
        layout.addStretch(1)
        self.min_btn = _QPushButton("—")
        self.max_btn = _QPushButton("□")
        self.close_btn = _QPushButton("×")
        for b in (self.min_btn, self.max_btn):
            b.setFixedSize(32, 24)
            b.setStyleSheet("QPushButton { background: transparent; color: #94a3b8; border: none; font-size: 11px; font-weight: 700; border-radius: 4px; } QPushButton:hover { background: #1e293b; color: #f8fafc; }")
        self.close_btn.setFixedSize(32, 24)
        self.close_btn.setStyleSheet("QPushButton { background: transparent; color: #94a3b8; border: none; font-size: 14px; font-weight: 700; border-radius: 4px; } QPushButton:hover { background: #ef4444; color: #ffffff; }")
        self.min_btn.clicked.connect(lambda: self.window().showMinimized())
        self.max_btn.clicked.connect(self._toggle_max)
        self.close_btn.clicked.connect(lambda: self.window().close())
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def set_context(self, text: str):
        self.context_label.setText(text)

    def _toggle_max(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
            self.max_btn.setText("□")
        else:
            w.showMaximized()
            self.max_btn.setText("❐")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        self._toggle_max()


class FramelessMixin:
    _resize_edge = None
    _resize_start_geom = None
    _resize_start_pos = None
    BORDER = 7

    def setup_frameless(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinMaxButtonsHint)

    def _edge_at(self, pos):
        r = self.rect()
        x, y = pos.x(), pos.y()
        left = x < self.BORDER
        right = x > r.width() - self.BORDER
        top = y < self.BORDER
        bottom = y > r.height() - self.BORDER
        if top and left: return "tl"
        if top and right: return "tr"
        if bottom and left: return "bl"
        if bottom and right: return "br"
        if left: return "l"
        if right: return "r"
        if top: return "t"
        if bottom: return "b"
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.pos())
            if edge:
                self._resize_edge = edge
                self._resize_start_geom = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge and self._resize_start_geom is not None:
            g = self._resize_start_geom
            gp = event.globalPosition().toPoint()
            dx = gp.x() - self._resize_start_pos.x()
            dy = gp.y() - self._resize_start_pos.y()
            new = QRect(g)
            if "l" in self._resize_edge:
                new.setLeft(g.left() + dx)
            if "r" in self._resize_edge:
                new.setRight(g.right() + dx)
            if "t" in self._resize_edge:
                new.setTop(g.top() + dy)
            if "b" in self._resize_edge:
                new.setBottom(g.bottom() + dy)
            if new.width() >= self.minimumWidth() and new.height() >= self.minimumHeight():
                self.setGeometry(new)
            event.accept()
            return
        e = self._edge_at(event.pos())
        cursors = {"l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
                   "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor}
        if e in cursors:
            self.setCursor(cursors[e])
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        self._resize_start_geom = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(event)

"""PySide6 dashboard with pyqtgraph traffic charts (Winbox v4 dark theme)."""

import sys
import threading
import time
from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer,
    QUrl, QVariantAnimation, Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QProgressBar, QPushButton,
    QScrollArea, QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QSizeGrip,
)

from app.alarms import (
    DEFAULT_ALARM_SOUND, DEFAULT_WARNING_SOUND, AlarmSettings, AlarmStore,
    evaluate_entries,
)
from app.collector import InterfaceReading, MonitorState, Snapshot, build_collectors
from app.config import AppConfig, InterfaceConfig, PingTargetConfig
from app.paths import resource_path, user_path
from app.metrics import (
    format_axis_ago, format_axis_clock, format_bps, format_bps_axis,
    format_uptime, median_filter, nice_ceiling, robust_peak, smooth_series,
)
from app.ping import PingStats
import qtawesome as qta

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except Exception:  # pragma: no cover - optional multimedia backend
    QAudioOutput = None
    QMediaPlayer = None

# -- palette (Modern Dark Slate / Obsidian) --------------------------------
BG = "#0f172a"          # Slate 900
PANEL = "#1e293b"       # Slate 800
TOOLBAR = "#0b0f19"     # Deep Header
INPUT_BG = "#0b0f19"    # Input background
BORDER = "#334155"      # Slate 700
GRID = "#1e293b"        # Chart grid line
TEXT = "#f8fafc"        # Slate 50
MUTED = "#94a3b8"       # Slate 400
ACCENT = "#3b82f6"      # Blue 500
RX = "#f43f5e"          # Rose 500
TX = "#38bdf8"          # Sky Blue 400
PURPLE = "#a855f7"      # Purple 500
GREEN = "#10b981"       # Emerald 500
AMBER = "#f59e0b"       # Amber 500
RED = "#ef4444"         # Red 500
CARD = PANEL
CARD_INNER = "#0b0f19"

pg.setConfigOptions(antialias=True, background=CARD_INNER, foreground=MUTED)

FONT_MONO = '"JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Consolas", "Courier New", monospace'
FONT_UI = FONT_MONO

QSS = f"""
QMainWindow, QDialog, QWidget#root {{ background-color: {BG}; }}
QWidget {{ color: {TEXT}; font-family: {FONT_UI}; font-size: 11px; }}
QLabel {{ background: transparent; }}
QFrame#card {{ background-color: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#toolbar {{ background-color: {TOOLBAR}; border-bottom: 1px solid {BORDER}; }}
QLabel#title {{ color: {TEXT}; font-size: 14px; font-weight: 700; letter-spacing: 0.3px; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 11px; }}
QLabel#section {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }}
QLabel#metricSmall {{ color: {TEXT}; font-family: {FONT_MONO}; font-size: 12px; font-weight: 700; }}
QLabel#unit {{ color: {MUTED}; font-size: 10px; }}
QLabel#muted {{ color: {MUTED}; font-size: 10px; }}
QLabel#rate {{ color: {TEXT}; font-family: {FONT_MONO}; font-size: 13px; font-weight: 700; }}
QLabel#big {{ color: {TEXT}; font-family: {FONT_MONO}; font-size: 20px; font-weight: 700; }}
QLabel#bigAccent {{ color: {TX}; font-family: {FONT_MONO}; font-size: 20px; font-weight: 700; }}
QFrame#accentCard {{ background-color: {PANEL}; border: 1px solid {TX}; border-radius: 8px; }}
QLabel#pingName {{ color: {TEXT}; font-size: 11px; font-weight: 600; }}
QLabel#chartTitle {{ color: {TEXT}; font-size: 12px; font-weight: 700; letter-spacing: 0.4px; }}
QLabel#footer {{ color: {MUTED}; font-size: 10px; font-family: {FONT_MONO}; }}
QLineEdit, QSpinBox, QComboBox {{ background-color: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px; font-size: 11px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; background-color: #0f172a; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    outline: none;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item {{ padding: 5px 8px; background-color: {INPUT_BG}; color: {TEXT}; }}
QComboBox QAbstractItemView::item:hover {{ background-color: #1e293b; color: {TX}; }}
QComboBox QAbstractItemView::item:selected {{ background-color: {ACCENT}; color: #ffffff; }}
QPushButton {{ background-color: #1e293b; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 12px; font-size: 11px; font-weight: 500; }}
QPushButton:hover {{ background-color: #334155; border-color: #475569; color: #ffffff; }}
QPushButton#primaryBtn {{ background-color: #2563eb; color: #ffffff; border: 1px solid #3b82f6; font-weight: 600; }}
QPushButton#primaryBtn:hover {{ background-color: #1d4ed8; border-color: #60a5fa; }}
QTableWidget, QListWidget {{ background-color: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; gridline-color: #1e293b; font-size: 11px; alternate-background-color: #0f172a; }}
QTableWidget::item, QListWidget::item {{ padding: 5px 8px; border-bottom: 1px solid #161f30; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background-color: #1d4ed8; color: #ffffff; }}
QTableWidget::item:hover {{ background-color: #1e293b; }}
QHeaderView::section {{ background-color: {TOOLBAR}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; border-right: 1px solid #1e293b; padding: 5px 8px; font-size: 10px; font-weight: 700; }}
QProgressBar {{ background-color: {INPUT_BG}; border: 1px solid {BORDER}; border-radius: 4px; text-align: center; color: {TEXT}; font-family: {FONT_MONO}; font-size: 10px; }}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 3px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 10px; font-weight: 600; padding-top: 14px; background-color: #131b2e; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 12px; padding: 0 6px; color: {TX}; font-size: 11px; font-weight: 700; background-color: transparent; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: {BG}; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #334155; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #475569; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame#titleBar {{ background-color: #080c14; border-bottom: 2px solid {ACCENT}; }}
QLabel#titleBarTitle {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#titleBarContext {{ color: {MUTED}; font-size: 11px; font-family: {FONT_MONO}; }}
"""


UI_SCALE = 1.0


def clamp_ui_scale(value) -> int:
    """Keep the UI scale inside the supported 75-125% range."""
    try:
        return max(75, min(125, int(value)))
    except (TypeError, ValueError):
        return 100


def scaled_qss(scale: float = UI_SCALE) -> str:
    """Return the app stylesheet with every pixel dimension scaled."""
    def scale_px(match):
        return f"{max(1, round(int(match.group(1)) * scale))}px"
    return re.sub(r"(\d+)px", scale_px, QSS)


# -- helpers ---------------------------------------------------------------
def _label(text: str, cls: str = "") -> QLabel:
    lbl = QLabel(text)
    if cls:
        lbl.setObjectName(cls)
    return lbl


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def _vbox(widget) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(4)
    return layout


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"background-color: {GRID}; border: none; max-height: 1px;")
    return line


class CollapsibleCard(QFrame):
    """Folds a dashboard widget into a single icon button with hover tooltip."""

    toggled = Signal(bool, bool)

    def __init__(self, key, title, description, icon_name, body, parent=None):
        super().__init__(parent)
        self.key = key
        self.title = title
        self.description = description
        self.body = body
        self._collapsed = False
        self._anim = None
        self.setObjectName("collapsibleCard")
        self.setToolTip(f"{title} — {description}")
        self._paint(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.bar = QWidget()
        self.bar.setFixedHeight(26)
        bar_layout = QHBoxLayout(self.bar)
        bar_layout.setContentsMargins(0, 0, 6, 2)
        bar_layout.setSpacing(0)
        bar_layout.addStretch(1)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setIcon(qta.icon("fa5s.chevron-up", color="#cbd5e1"))
        self.toggle_btn.setIconSize(QSize(12, 12))
        self.toggle_btn.setFixedSize(22, 22)
        self.toggle_btn.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #e2e8f0; "
            "border: 1px solid #475569; border-radius: 4px; "
            "font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background-color: #334155; border-color: #38bdf8; color: #ffffff; }"
        )
        self.toggle_btn.setToolTip(f"Collapse {title}")
        self.toggle_btn.clicked.connect(self.toggle)
        bar_layout.addWidget(self.toggle_btn)
        root.addWidget(self.bar)
        root.addWidget(body)

        self.icon_btn = QPushButton()
        self.icon_btn.setIcon(qta.icon(icon_name, color=ACCENT))
        self.icon_btn.setIconSize(QSize(16, 16))
        self.icon_btn.setFixedSize(36, 36)
        self.icon_btn.setToolTip(f"{title} — {description} (klik untuk expand)")
        self.icon_btn.clicked.connect(self.toggle)
        self.icon_btn.hide()
        root.addWidget(self.icon_btn)

    def _paint(self, hovered: bool) -> None:
        color = ACCENT if hovered else "transparent"
        background = "#131b2e" if hovered else "transparent"
        self.setStyleSheet(
            f"QFrame#collapsibleCard {{ background: {background}; "
            f"border: 1px solid {color}; border-radius: 8px; }}"
        )

    def enterEvent(self, event):
        self._paint(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._paint(False)
        super().leaveEvent(event)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._animate_flag = animate
        if not animate:
            self._finish(collapsed)
            return
        if collapsed:
            target = 44
        else:
            self.icon_btn.hide()
            self.bar.show()
            self.body.show()
            target = self.sizeHint().height()
        anim = QPropertyAnimation(self, b"maximumHeight")
        anim.setDuration(240)
        anim.setStartValue(self.height())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self._finish(collapsed))
        self._anim = anim
        anim.start()

    def _finish(self, collapsed: bool) -> None:
        self._anim = None
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.bar.setVisible(not collapsed)
        self.body.setVisible(not collapsed)
        self.icon_btn.setVisible(collapsed)
        self.toggle_btn.setIcon(
            qta.icon(
                "fa5s.chevron-down" if collapsed else "fa5s.chevron-up",
                color="#cbd5e1",
            )
        )
        self.toggle_btn.setToolTip(f"{'Expand' if collapsed else 'Collapse'} {self.title}")
        self.toggled.emit(collapsed, getattr(self, "_animate_flag", True))


def _short_log_time(text) -> str:
    """Compact timestamp for the list; the detail window keeps the full value."""
    text = str(text or "").strip()
    if not text:
        return "--:--"
    parts = text.split()
    clock = ":".join(parts[-1].split(":")[:2])
    if len(parts) > 1:
        date_bits = parts[0].split("-")
        date = f"{date_bits[1]}-{date_bits[2]}" if len(date_bits) == 3 else parts[0]
        return f"{date} {clock}"
    return clock


def _format_log_entry(entry: dict, max_message: int = 60) -> str:
    """Compact monospace row: short time, topic and an elided message."""
    time = _short_log_time(entry.get("time"))
    topics = str(entry.get("topics", "") or "")
    message = str(entry.get("message", "") or "")
    if len(message) > max_message:
        message = message[: max_message - 1] + "…"
    return f"{time:<11}  {topics:<14}  {message}"


def _full_log_line(entry: dict) -> str:
    """Tab-separated full row, ready for the clipboard."""
    time = str(entry.get("time", "") or "")
    topics = str(entry.get("topics", "") or "")
    message = str(entry.get("message", "") or "")
    return f"{time}\t{topics}\t{message}"


def _filter_logs(entries, query: str) -> list:
    needle = (query or "").strip().lower()
    if not needle:
        return list(entries)
    return [e for e in entries if needle in str(e.get("message", "") or "").lower()]


class AlarmPlayer:
    """Plays a bundled MP3 once without blocking the UI."""

    def __init__(self, parent=None):
        self.player = QMediaPlayer(parent)
        self.audio = QAudioOutput(parent)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(1.0)
        self.player.mediaStatusChanged.connect(self._on_status)

    def play(self, path, times: int = 1) -> None:
        self._remaining = times
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def _on_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._remaining > 1:
            self._remaining -= 1
            self.player.setPosition(0)
            self.player.play()


_alarm_player = None
_warning_player = None


def _play_audio_once(path, holder_name: str) -> None:
    holder = globals().get(holder_name)
    if path is not None and path.exists() and QMediaPlayer is not None:
        if holder is None:
            from PySide6.QtWidgets import QApplication
            holder = AlarmPlayer(QApplication.instance())
            globals()[holder_name] = holder
        holder.play(path, 1)
        return

    # Fallback when the audio file or multimedia backend is unavailable.
    def fallback_beep():
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass

    if sys.platform == "win32":
        try:
            import winsound

            def win_beep():
                try:
                    winsound.Beep(1000, 120)
                except Exception:
                    pass

            QTimer.singleShot(0, win_beep)
            return
        except Exception:
            pass
    QTimer.singleShot(0, fallback_beep)


def _play_sound(choice: str, holder_name: str = "_alarm_player") -> None:
    """Play a bundled or user-uploaded sound; fall back to a beep if missing."""
    choice = choice or ""
    if choice.startswith("bundled:"):
        path = resource_path(choice.split(":", 1)[1])
    elif choice.startswith("custom:"):
        path = user_path(choice.split(":", 1)[1])
    else:
        path = None
    _play_audio_once(path, holder_name)


def _play_alarm() -> None:
    _play_sound(DEFAULT_ALARM_SOUND, "_alarm_player")


def _play_warning() -> None:
    _play_sound(DEFAULT_WARNING_SOUND, "_warning_player")


def _dns_loss_exceeded(pings) -> bool:
    """True when any DNS target has more than 1% packet loss."""
    return any(
        getattr(p, "loss_pct", None) is not None and p.loss_pct > 1.0
        for p in (pings or [])
    )


def _rgba(hexcolor: str, alpha: float) -> str:
    c = QColor(hexcolor)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


class TimeAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                number = float(v)
                out.append(
                    format_axis_clock(number, spacing < 60) if number > 1e8
                    else format_axis_ago(-number)
                )
            except (TypeError, ValueError):
                out.append(str(v))
        return out


class BpsAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                v = float(v)
                if v <= 0:
                    out.append("0")
                elif v >= 1e9:
                    d = 1 if (v % 1e9 != 0) else 0
                    out.append(f"{v/1e9:.{d}f} Gbps")
                elif v >= 1e6:
                    d = 1 if (v % 1e6 != 0) else 0
                    out.append(f"{v/1e6:.{d}f} Mbps")
                elif v >= 1e3:
                    d = 1 if (v % 1e3 != 0) else 0
                    out.append(f"{v/1e3:.{d}f} Kbps")
                else:
                    out.append(f"{v:.0f} bps")
            except (TypeError, ValueError):
                out.append(str(v))
        return out


# -- widgets ---------------------------------------------------------------
class StatusPill(QLabel):
    def __init__(self):
        super().__init__("WAITING")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(84)
        self.setStyleSheet(
            f"background: {INPUT_BG}; color: {MUTED}; border: 1px solid {BORDER}; "
            "border-radius: 6px; padding: 3px 10px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )

    def set_state(self, state: str):
        state = (state or "").upper()
        if state == "ONLINE":
            color = GREEN
        elif state == "DEGRADED":
            color = AMBER
        elif state == "OFFLINE":
            color = RED
        else:
            color = MUTED
        self.setText(state or "WAITING")
        self.setStyleSheet(
            f"background: {INPUT_BG}; color: {color}; border: 1px solid {color}; "
            "border-radius: 6px; padding: 3px 10px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
        )


class MetricBar(QWidget):
    def __init__(self, title: str, color: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        head = QHBoxLayout()
        head.addWidget(_label(title, "section"))
        head.addStretch(1)
        self.value_label = _label("--", "metricSmall")
        head.addWidget(self.value_label)
        layout.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}")
        layout.addWidget(self.bar)
        self._color = color

    def set_value(self, value):
        if value is None:
            self.value_label.setText("--")
            self.bar.setValue(0)
            return
        self.value_label.setText(f"{value:.0f}%")
        self.bar.setValue(int(max(0, min(100, value))))


class StatTile(QWidget):
    def __init__(self, title: str, unit: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(_label(title, "section"))
        row = QHBoxLayout()
        row.setSpacing(4)
        self.value_label = _label("--", "big")
        row.addWidget(self.value_label)
        row.addWidget(_label(unit, "unit"))
        row.addStretch(1)
        layout.addLayout(row)

    def set_value(self, value):
        if value is None:
            self.value_label.setText("--")
            return
        self.value_label.setText(f"{value:.1f}")


class PingRow(QWidget):
    def __init__(self, target):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)
        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(_label(target.name, "pingName"))
        left.addWidget(_label(target.host, "muted"))
        layout.addLayout(left)
        layout.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(0)
        right.setAlignment(Qt.AlignRight)
        self.avg_label = _label("--", "metricSmall")
        self.avg_label.setAlignment(Qt.AlignRight)
        right.addWidget(self.avg_label)
        self.loss_label = _label("loss --", "muted")
        self.loss_label.setAlignment(Qt.AlignRight)
        right.addWidget(self.loss_label)
        layout.addLayout(right)
        self._target = target

    def update_stats(self, stats: PingStats):
        if stats.avg_ms is None:
            self.avg_label.setText("--")
        else:
            self.avg_label.setText(f"{stats.avg_ms:.1f} ms")
        loss = stats.loss_pct
        if loss is None:
            self.loss_label.setText("loss --")
            self.loss_label.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            return
        color = GREEN if loss <= 0.5 else AMBER if loss < 5 else RED
        self.loss_label.setText(f"loss {loss:.1f}%")
        self.loss_label.setStyleSheet(f"color: {color}; font-size: 10px;")


def _link_speed_text(mbps: float | None) -> str:
    if not mbps or mbps <= 0:
        return "--"
    if mbps >= 1000:
        return f"{mbps / 1000:.0f}G" if (mbps % 1000) < 1 else f"{mbps / 1000:.1f}G"
    return f"{mbps:.0f}M"


class PortRow(QWidget):
    """Compact per-port link status for SwOS switches."""

    def __init__(self, iface):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)
        layout.addWidget(_label(iface.label or iface.name, "pingName"))
        layout.addStretch(1)
        self.speed_lbl = _label("--", "metricSmall")
        self.speed_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self.speed_lbl)
        self.status_lbl = _label("WAITING", "muted")
        self.status_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self.status_lbl)

    def update(self, reading) -> None:
        if reading is None or reading.link_up is None:
            status, color, speed = "WAITING", MUTED, "--"
        elif reading.link_up:
            status, color = "LINK UP", GREEN
            speed = _link_speed_text(reading.speed_mbps)
        else:
            status, color, speed = "LINK DOWN", RED, "--"
        self.status_lbl.setText(status)
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700;")
        self.speed_lbl.setText(speed)


class TrafficChart(QFrame):
    def __init__(self, iface: InterfaceConfig, window_seconds: int):
        super().__init__()
        self.setObjectName("card")
        self.iface = iface
        self.window_seconds = window_seconds
        self._ymax = None
        self._link_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.dot.setStyleSheet(f"background-color: {MUTED}; border-radius: 4px;")
        head.addWidget(self.dot)
        head.addWidget(_label(iface.label.upper() or iface.name.upper(), "chartTitle"))
        head.addWidget(_label(iface.name, "muted"))
        head.addStretch(1)
        self.link = QLabel("WAITING")
        self.link.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 700;")
        head.addWidget(self.link)
        root.addLayout(head)

        rates = QHBoxLayout()
        rates.setSpacing(16)
        rates.addLayout(self._rate_block("RX", RX, "rx"))
        rates.addLayout(self._rate_block("TX", TX, "tx"))
        rates.addStretch(1)
        root.addLayout(rates)

        self.plot = pg.PlotWidget(axisItems={"left": BpsAxis("left"), "bottom": TimeAxis("bottom")})
        self.plot.setBackground(CARD_INNER)
        self.plot.setMinimumHeight(120)
        item = self.plot.getPlotItem()
        item.hideButtons()
        item.setMenuEnabled(False)
        item.setMouseEnabled(x=False, y=False)
        self.plot.setXRange(-window_seconds, 0, padding=0)
        self.plot.setYRange(0, 1_000_000, padding=0)
        self.plot.showGrid(x=True, y=True, alpha=0.06)
        for name in ("left", "bottom"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen(GRID))
            axis.setTextPen(pg.mkPen(MUTED))
            axis.setStyle(tickLength=3, tickTextOffset=4)
        self.plot.getAxis("left").setWidth(68)

        self.rx_curve = self.plot.plot(
            pen=pg.mkPen(RX, width=2), fillLevel=0, brush=pg.mkBrush(244, 63, 94, 35),
        )
        self.tx_curve = self.plot.plot(
            pen=pg.mkPen(TX, width=2), fillLevel=0, brush=pg.mkBrush(56, 189, 248, 35),
        )
        root.addWidget(self.plot)

        self._x_grid = []
        self._target_rx = []
        self._target_tx = []
        self._display_rx = []
        self._display_tx = []
        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._animate)

    def _rate_block(self, label: str, color: str, attr: str):
        layout = QVBoxLayout()
        layout.setSpacing(0)
        title = _label(label, "muted")
        title.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: 700;")
        layout.addWidget(title)
        value = _label("--", "rate")
        value.setStyleSheet(f"color: {color}; font-family: {FONT_MONO}; font-size: 12px; font-weight: 700;")
        setattr(self, f"{attr}_value", value)
        layout.addWidget(value)
        return layout

    def _set_link(self, text: str, color: str):
        self.link.setText(text)
        self.link.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 700;")
        if hasattr(self, "dot"):
            self.dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")

    def _draw(self, history, now, wall_now=None):
        points = [p for p in history if (now - self.window_seconds - 1.0) <= p[0]]
        if not points:
            self.rx_curve.setData([], [])
            self.tx_curve.setData([], [])
            self._anim.stop()
            return
        if wall_now:
            right = float(wall_now)
            xs = [right - (now - p[0]) for p in points]
        else:
            right = 0.0
            xs = [p[0] - now for p in points]
        rx = median_filter([p[1] for p in points])
        tx = median_filter([p[2] for p in points])

        start = right - self.window_seconds
        # Hanya gambar rentang yang benar-benar memiliki sampel. Grid penuh
        # window + np.interp(left/right=...) mengisi waktu tanpa data dengan
        # nilai sampel pertama/terakhir, sehingga garis tampak memanjang
        # sampai NOW walaupun baru beberapa detik datanya masuk.
        first_x, last_x = xs[0], xs[-1]
        steps = max(1, int(round(last_x - first_x)))
        grid = list(np.linspace(first_x, last_x, steps + 1))
        self._x_grid = grid
        self._target_rx = list(np.interp(grid, xs, rx, left=rx[0], right=rx[-1]))
        self._target_tx = list(np.interp(grid, xs, tx, left=tx[0], right=tx[-1]))
        # Render directly; smooth_series already provides enough visual smoothing.
        self._display_rx = list(self._target_rx)
        self._display_tx = list(self._target_tx)

        peak = robust_peak(rx + tx)
        # A percentile alone hides a genuine sustained rise: if several recent
        # samples clearly exceed the current scale, follow them instead.
        reference = max(self._ymax if self._ymax is not None else peak, 1000.0)
        for curve in (rx, tx):
            tail = [v for v in curve[-5:] if v is not None]
            if sum(1 for v in tail if v > reference * 1.25) >= 2:
                peak = max(peak, max(tail))
        if peak > 0:
            target = nice_ceiling(peak * 1.15)
        else:
            target = 1_000_000.0
        if self._ymax is None or target > self._ymax:
            self._ymax = target
        else:
            self._ymax = self._ymax + (target - self._ymax) * 0.2
        self.plot.setXRange(start, right, padding=0)
        self.plot.setYRange(0, max(self._ymax, 1000.0), padding=0)
        self._apply_gradient()
        self._render_curves()

    def _apply_gradient(self) -> None:
        top = max(self._ymax or 1_000_000.0, 1000.0)
        for curve, color in ((self.rx_curve, RX), (self.tx_curve, TX)):
            base = QColor(color)
            gradient = QLinearGradient(0, 0, 0, top)
            gradient.setColorAt(0.0, QColor(base.red(), base.green(), base.blue(), 95))
            gradient.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 4))
            curve.setBrush(QBrush(gradient))

    def _render_curves(self) -> None:
        if not self._x_grid:
            return
        sx, ry = smooth_series(self._x_grid, self._display_rx)
        _, ty = smooth_series(self._x_grid, self._display_tx)
        self.rx_curve.setData(sx, ry)
        self.tx_curve.setData(sx, ty)

    def _animate(self) -> None:
        if not self._x_grid:
            return
        factor = 0.28
        new_rx, new_tx = [], []
        moving = False
        for current, target in zip(self._display_rx, self._target_rx):
            value = current + (target - current) * factor
            if abs(target - value) > 1.0:
                moving = True
            new_rx.append(value)
        for current, target in zip(self._display_tx, self._target_tx):
            value = current + (target - current) * factor
            if abs(target - value) > 1.0:
                moving = True
            new_tx.append(value)
        self._display_rx, self._display_tx = new_rx, new_tx
        self._render_curves()
        if not moving:
            self._anim.stop()

    def update_reading(self, snapshot: Snapshot, history, error_msg: str = ""):
        iface = snapshot.interfaces.get(self.iface.name)
        if iface is not None:
            if iface.link_up is True:
                speed = iface.speed_mbps
                if speed and speed >= 1000:
                    text = f"{speed/1000:.0f}G" if (speed % 1000) < 1 else f"{speed/1000:.1f}G"
                elif speed:
                    text = f"{speed:.0f}M"
                else:
                    text = "LINK UP"
                self._set_link(text, GREEN)
            elif iface.link_up is False:
                self._set_link("Link Down", RED)
            else:
                self._set_link("WAITING", MUTED)
            if iface.rx_bps is not None:
                self.rx_value.setText(format_bps(iface.rx_bps))
            if iface.tx_bps is not None:
                self.tx_value.setText(format_bps(iface.tx_bps))
        if error_msg:
            self._set_link("NOT FOUND", RED)
        self._draw(history, snapshot.now, snapshot.wall_now)


class HeaderBar(QFrame):
    setup_clicked = Signal()
    pause_clicked = Signal()
    scale_changed = Signal(int)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.setObjectName("toolbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(_label("MikroTik Real-Time Monitor", "title"))
        _dev = config.router.ros_version if getattr(config.router, "device_type", "routeros") == "swos" else f"ROS {config.router.ros_version}"
        titles.addWidget(_label(f"{config.router.name}   ·   {config.router.host}   ·   {_dev}", "subtitle"))
        layout.addLayout(titles)
        layout.addStretch(1)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setIcon(qta.icon("fa5s.pause", color="#dee2e6"))
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        layout.addWidget(self.pause_btn, 0, Qt.AlignVCenter)

        self.scale_btn = QPushButton("100%")
        self.scale_btn.setToolTip("UI scale")
        self.scale_menu = QMenu(self.scale_btn)
        for percent in (75, 85, 100, 110, 125):
            action = self.scale_menu.addAction(f"{percent}%")
            action.triggered.connect(lambda _, p=percent: self.scale_changed.emit(p))
        self.scale_btn.setMenu(self.scale_menu)
        layout.addWidget(self.scale_btn, 0, Qt.AlignVCenter)

        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setIcon(qta.icon("fa5s.expand", color="#dee2e6"))
        self.fullscreen_btn.setFixedSize(32, 26)
        self.fullscreen_btn.setToolTip("Toggle fullscreen")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        layout.addWidget(self.fullscreen_btn, 0, Qt.AlignVCenter)

        self.setup_btn = QPushButton("Disconnect")
        self.setup_btn.setIcon(qta.icon("fa5s.power-off", color="#f87171"))
        self.setup_btn.setStyleSheet(
            "QPushButton { background: #1e293b; color: #f87171; border: 1px solid #7f1d1d; "
            "border-radius: 6px; padding: 4px 12px; font-weight: 600; } "
            "QPushButton:hover { background: #dc2626; color: #ffffff; border-color: #ef4444; }"
        )
        self.setup_btn.clicked.connect(self.setup_clicked.emit)
        layout.addWidget(self.setup_btn, 0, Qt.AlignVCenter)

        self.pill = StatusPill()
        layout.addWidget(self.pill, 0, Qt.AlignVCenter)

        uptime = QVBoxLayout()
        uptime.setSpacing(1)
        uptime_label = _label("UPTIME", "muted")
        uptime_label.setAlignment(Qt.AlignRight)
        uptime.addWidget(uptime_label)
        self.uptime = _label("--:--:--", "metricSmall")
        self.uptime.setAlignment(Qt.AlignRight)
        uptime.addWidget(self.uptime)
        layout.addLayout(uptime)

    def _toggle_fullscreen(self) -> None:
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
            self.fullscreen_btn.setIcon(qta.icon("fa5s.expand", color="#dee2e6"))
            self.fullscreen_btn.setToolTip("Toggle fullscreen")
        else:
            window.showFullScreen()
            self.fullscreen_btn.setIcon(qta.icon("fa5s.compress", color="#dee2e6"))
            self.fullscreen_btn.setToolTip("Exit fullscreen")


class LogDetailWindow(FramelessMixin, QDialog):
    """Separate, resizable window with the same custom title bar as the dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Router Logs — Detail")
        self.setStyleSheet(scaled_qss())
        self.setup_frameless()
        self.setMinimumSize(640, 420)
        self.resize(900, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar("Router Logs", "Detail view")
        root.addWidget(self.title_bar)

        tools = QHBoxLayout()
        tools.setContentsMargins(12, 8, 12, 6)
        tools.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter message…")
        self.search_edit.textChanged.connect(self._apply_filter)
        tools.addWidget(self.search_edit, 1)
        copy_btn = QPushButton("Copy selected")
        copy_btn.clicked.connect(self.copy_selected)
        tools.addWidget(copy_btn)
        root.addLayout(tools)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "Topics", "Message"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 180)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        root.addWidget(self.table, 1)
        self._logs = []
        self._visible = []

    def set_logs(self, entries) -> None:
        self._logs = list(entries or [])
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._visible = _filter_logs(self._logs, self.search_edit.text())
        self.table.setRowCount(len(self._visible))
        for row, entry in enumerate(self._visible):
            values = (
                str(entry.get("time", "") or ""),
                str(entry.get("topics", "") or ""),
                str(entry.get("message", "") or ""),
            )
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        suffix = f" / {len(self._logs)}" if len(self._visible) != len(self._logs) else ""
        self.title_bar.set_context(f"{len(self._visible)}{suffix} entries")

    def copy_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        lines = [_full_log_line(self._visible[i]) for i in rows if i < len(self._visible)]
        if lines:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText("\n".join(lines))


class MonitorWindow(FramelessMixin, QMainWindow):
    setup_requested = Signal()  # acts as Disconnect

    def __init__(self, config: AppConfig, state: MonitorState):
        super().__init__()
        self.config = config
        self.state = state
        self._stop = threading.Event()
        self._workers = []
        self._paused = False
        self._disconnecting = False
        self._log_detail = None
        self._last_logs = []
        self._alarm_seen = set()
        self._alarm_cooldowns = {}
        self.alarm_settings: AlarmSettings = AlarmStore().load()
        self._dns_warn_active = False
        self.collapsibles = {}
        self.left_scroll = None
        self.logs_collapsible = None
        self._width_anims = {}

        self.setWindowTitle("MikroTik Real-Time Monitor")
        self.setMinimumSize(1024, 680)
        from PySide6.QtGui import QIcon
        _ip = str(resource_path("assets/icon.png"))
        if os.path.exists(_ip):
            self.setWindowIcon(QIcon(_ip))
        self.setup_frameless()
        screen = None
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None and app.primaryScreen() is not None:
            screen = app.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1280, available.width() - 40), min(820, available.height() - 60))
        else:
            self.resize(1280, 820)
        self.setStyleSheet(scaled_qss())

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        _dev = config.router.ros_version if getattr(config.router, "device_type", "routeros") == "swos" else f"ROS {config.router.ros_version}"
        self.title_bar = TitleBar("MikroTik Real-Time Monitor", f"{config.router.name}  ·  {config.router.host}  ·  {_dev}")
        layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 6)
        body_layout.setSpacing(6)
        layout.addWidget(body, 1)

        self.header = HeaderBar(config)
        self.header.setup_clicked.connect(self._on_disconnect_clicked)
        self.header.pause_clicked.connect(self.toggle_pause)
        self.header.scale_changed.connect(self._apply_ui_scale)
        body_layout.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(6)
        body_layout.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(6)
        _is_swos = getattr(self.config.router, "device_type", "routeros") == "swos"
        if _is_swos:
            self._add_collapsible(
                left, "latency", "Latency", "Ping latency & packet loss",
                "fa5s.wifi", self._build_ping_card(),
            )
            self._add_collapsible(
                left, "ports", "Switch Ports", "Status link & kecepatan port",
                "fa5s.network-wired", self._build_swos_ports_card(),
            )
        else:
            self._add_collapsible(
                left, "system", "System", "CPU, RAM, suhu & voltase",
                "fa5s.microchip", self._build_system_card(),
            )
            self._add_collapsible(
                left, "latency", "Latency", "Ping latency & packet loss",
                "fa5s.wifi", self._build_ping_card(),
            )
            self._add_collapsible(
                left, "users", "Active Users", "PPPoE, HotSpot & DHCP lease",
                "fa5s.users", self._build_users_card(),
            )
        left.addStretch(1)

        left_widget = QWidget()
        left_widget.setLayout(left)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.viewport().setStyleSheet("background: transparent;")
        left_scroll.setFixedWidth(340)
        self.left_scroll = left_scroll
        body.addWidget(left_scroll)

        right = QHBoxLayout()
        right.setSpacing(8)
        self.charts = {}
        if _is_swos and len(config.interfaces) > 3:
            grid = QGridLayout()
            grid.setSpacing(8)
            for index, iface in enumerate(config.interfaces):
                chart = TrafficChart(iface, config.polling.history_seconds)
                self.charts[iface.name] = chart
                grid.addWidget(chart, index // 2, index % 2)
            right.addLayout(grid, 1)
        else:
            charts_col = QVBoxLayout()
            charts_col.setSpacing(8)
            for iface in config.interfaces:
                chart = TrafficChart(iface, config.polling.history_seconds)
                self.charts[iface.name] = chart
                charts_col.addWidget(chart)
            charts_col.addStretch(1)
            right.addLayout(charts_col, 1)
        if not _is_swos:
            self.logs_collapsible = self._add_collapsible(
                right, "logs", "Router Logs", "Log RouterOS terbaru",
                "fa5s.clipboard-list", self._build_logs_card(),
            )
            self.logs_collapsible.setFixedWidth(380)
        right_widget = QWidget()
        right_widget.setLayout(right)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_widget)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setStyleSheet("background: transparent;")
        body.addWidget(scroll, 1)

        self.footer = _label("", "footer")
        body_layout.addWidget(self.footer)

        self._timer = QTimer(self)
        self._timer.setInterval(max(250, int(config.polling.interval * 1000)))
        self._timer.timeout.connect(self._refresh)

    def _add_collapsible(self, layout, key, title, description, icon_name, body):
        card = CollapsibleCard(key, title, description, icon_name, body)
        card.toggled.connect(self._on_widget_collapsed)
        self.collapsibles[key] = card
        layout.addWidget(card)
        return card

    def _animate_width(self, widget, target: int, animate: bool = True) -> None:
        current = widget.width()
        if current == target:
            return
        if not animate:
            widget.setFixedWidth(target)
            return
        anim = QVariantAnimation()
        anim.setDuration(240)
        anim.setStartValue(current)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda value: widget.setFixedWidth(int(value)))
        anim.finished.connect(lambda: widget.setFixedWidth(target))
        self._width_anims[id(widget)] = anim
        anim.start()

    def _on_widget_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        left_keys = [k for k in ("system", "latency", "users", "ports") if k in self.collapsibles]
        if left_keys and self.left_scroll is not None:
            all_collapsed = all(self.collapsibles[k].is_collapsed() for k in left_keys)
            self._animate_width(self.left_scroll, 48 if all_collapsed else 340, animate)
        if self.logs_collapsible is not None:
            target = 48 if self.logs_collapsible.is_collapsed() else 380
            self._animate_width(self.logs_collapsible, target, animate)

    def _apply_ui_scale(self, percent: int) -> None:
        global UI_SCALE
        percent = clamp_ui_scale(percent)
        UI_SCALE = percent / 100.0
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        for widget in app.topLevelWidgets() if app else []:
            try:
                widget.setStyleSheet(scaled_qss(UI_SCALE))
            except Exception:
                pass
        if app is not None:
            if not hasattr(self, "_base_font_point"):
                self._base_font_point = app.font().pointSize()
            font = app.font()
            font.setPointSize(max(1, round(self._base_font_point * UI_SCALE)))
            app.setFont(font)
        self.header.scale_btn.setText(f"{percent}%")

    def _check_dns_warning(self, snapshot) -> None:
        exceeded = _dns_loss_exceeded(snapshot.pings)
        if not self.alarm_settings.ping_warning_enabled:
            self._dns_warn_active = exceeded
            return
        if exceeded and not self._dns_warn_active:
            self._dns_warn_active = True
            _play_sound(self.alarm_settings.ping_warning_sound, "_warning_player")
        elif not exceeded:
            self._dns_warn_active = False

    def _build_system_card(self) -> QFrame:
        card = _card()
        layout = _vbox(card)
        head = QHBoxLayout()
        sys_icon = QLabel()
        sys_icon.setPixmap(qta.icon("fa5s.microchip", color="#adb5bd").pixmap(12, 12))
        head.addWidget(sys_icon)
        head.addWidget(_label("SYSTEM", "section"))
        head.addStretch(1)
        head.addWidget(_label("live", "muted"))
        layout.addLayout(head)
        self.cpu_bar = MetricBar("CPU LOAD", ACCENT)
        self.mem_bar = MetricBar("MEM USED", PURPLE)
        layout.addWidget(self.cpu_bar)
        layout.addWidget(self.mem_bar)
        tiles = QHBoxLayout()
        tiles.setSpacing(18)
        self.temp_tile = StatTile("TEMP", "°C")
        self.volt_tile = StatTile("VOLT", "V")
        tiles.addWidget(self.temp_tile)
        tiles.addWidget(self.volt_tile)
        layout.addLayout(tiles)
        return card

    def _build_ping_card(self) -> QFrame:
        card = _card()
        layout = _vbox(card)
        head = QHBoxLayout()
        ping_icon = QLabel()
        ping_icon.setPixmap(qta.icon("fa5s.wifi", color="#adb5bd").pixmap(12, 12))
        head.addWidget(ping_icon)
        head.addWidget(_label("LATENCY", "section"))
        head.addStretch(1)
        head.addWidget(_label(f"{self.config.ping.window}s window", "muted"))
        layout.addLayout(head)
        self.ping_rows = {}
        if not self.config.ping.targets:
            layout.addWidget(_label("no ping targets configured", "muted"))
        for index, target in enumerate(self.config.ping.targets):
            if index:
                layout.addWidget(_separator())
            row = PingRow(target)
            self.ping_rows[target.name] = row
            layout.addWidget(row)
        return card

    def _build_swos_ports_card(self) -> QFrame:
        card = _card()
        layout = _vbox(card)
        head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon("fa5s.network-wired", color="#38bdf8").pixmap(12, 12))
        head.addWidget(icon)
        head.addWidget(_label("SWITCH PORTS", "section"))
        head.addStretch(1)
        head.addWidget(_label(f"{len(self.config.interfaces)} ports", "muted"))
        layout.addLayout(head)
        self.port_rows = {}
        for index, iface in enumerate(self.config.interfaces):
            if index:
                layout.addWidget(_separator())
            row = PortRow(iface)
            self.port_rows[iface.name] = row
            layout.addWidget(row)
        return card

    def _build_users_card(self) -> QFrame:
        card = _card()
        card.setObjectName("accentCard")
        layout = _vbox(card)
        layout.setSpacing(3)
        head = QHBoxLayout()
        usr_icon = QLabel()
        usr_icon.setPixmap(qta.icon("fa5s.users", color="#adb5bd").pixmap(12, 12))
        head.addWidget(usr_icon)
        head.addWidget(_label("ACTIVE USERS", "section"))
        head.addStretch(1)
        self.users_source = _label("NO SOURCE", "muted")
        head.addWidget(self.users_source)
        layout.addLayout(head)

        total_row = QHBoxLayout()
        self.users_value = _label("--", "bigAccent")
        total_row.addWidget(self.users_value)
        total_row.addStretch(1)
        total_row.addWidget(_label("PPPoE + HotSpot", "muted"))
        layout.addLayout(total_row)

        split = QHBoxLayout()
        split.setSpacing(10)
        for caption, attr, color in (("PPPOE", "pppoe_value", TX), ("HOTSPOT", "hotspot_value", PURPLE)):
            column = QVBoxLayout()
            column.setSpacing(0)
            column.addWidget(_label(caption, "section"))
            value = _label("--", "metricSmall")
            value.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
            setattr(self, attr, value)
            column.addWidget(value)
            split.addLayout(column)
        split.addStretch(1)
        layout.addLayout(split)

        layout.addWidget(_separator())
        dhcp_head = QHBoxLayout()
        dhcp_head.addWidget(_label("DHCP LEASES", "section"))
        dhcp_head.addStretch(1)
        self.dhcp_value = _label("--", "metricSmall")
        dhcp_head.addWidget(self.dhcp_value)
        layout.addLayout(dhcp_head)

        bar_row = QHBoxLayout()
        self.dhcp_bar = QProgressBar()
        self.dhcp_bar.setRange(0, 100)
        self.dhcp_bar.setValue(0)
        self.dhcp_bar.setTextVisible(False)
        self.dhcp_bar.setFixedHeight(6)
        bar_row.addWidget(self.dhcp_bar)
        self.dhcp_pct = _label("--", "metricSmall")
        self.dhcp_pct.setAlignment(Qt.AlignRight)
        bar_row.addWidget(self.dhcp_pct)
        layout.addLayout(bar_row)

        self.dhcp_warning = _label("", "muted")
        layout.addWidget(self.dhcp_warning)
        return card

    def _build_logs_card(self) -> QFrame:
        card = _card()
        layout = _vbox(card)
        self._logs_signature = None
        head = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setPixmap(qta.icon("fa5s.clipboard-list", color="#38bdf8").pixmap(12, 12))
        head.addWidget(log_icon)
        head.addWidget(_label("ROUTER LOGS", "section"))
        head.addStretch(1)
        self.logs_source_lbl = _label("live", "muted")
        head.addWidget(self.logs_source_lbl)
        layout.addLayout(head)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addStretch(1)
        copy_btn = QPushButton("Copy")
        copy_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 10px; }")
        copy_btn.clicked.connect(self._copy_selected_log)
        actions.addWidget(copy_btn)
        self.alarm_btn = QPushButton("Alarm on", checkable=True)
        self.alarm_btn.setChecked(True)
        self.alarm_btn.toggled.connect(self._on_alarm_toggled)
        self.alarm_btn.setStyleSheet(f"QPushButton {{ padding: 2px 8px; font-size: 10px; color: {GREEN}; }}")
        actions.addWidget(self.alarm_btn)
        detail_btn = QPushButton("View detail")
        detail_btn.setStyleSheet("QPushButton { padding: 2px 8px; font-size: 10px; }")
        detail_btn.clicked.connect(self._open_log_detail)
        actions.addWidget(detail_btn)
        layout.addLayout(actions)

        self.logs_list = QListWidget()
        self.logs_list.setMinimumHeight(120)
        self.logs_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.logs_list.setStyleSheet(
            "QListWidget { background-color: #0b0f19; border: 1px solid #334155; border-radius: 6px; padding: 2px; } "
            "QListWidget::item { padding: 3px 6px; border-bottom: 1px solid #161f30; font-family: 'Consolas', monospace; font-size: 10px; } "
            "QListWidget::item:hover { background-color: #1e293b; }"
        )
        layout.addWidget(self.logs_list)
        return card

    def _update_logs(self, snapshot: Snapshot) -> None:
        if not hasattr(self, "logs_list"):
            return
        entries = snapshot.logs or []
        signature = tuple(
            (str(e.get("time", "") or ""), str(e.get("topics", "") or ""), str(e.get("message", "") or ""))
            for e in entries
        )
        if signature == getattr(self, "_logs_signature", None):
            return
        self._logs_signature = signature
        self._last_logs = list(reversed(entries))  # newest first, in both views
        if self._log_detail is not None and self._log_detail.isVisible():
            self._log_detail.set_logs(self._last_logs)

        if len(self._alarm_seen) > 200:
            self._alarm_seen.clear()
        device_type = str(getattr(self.config.router, "device_type", "routeros")).lower()
        is_routeros = (
            device_type == "routeros"
            and str(self.config.router.ros_version).upper() in ("V6", "V7")
        )
        if is_routeros:
            fired = evaluate_entries(
                entries,
                self.alarm_settings.log_rules,
                self._alarm_seen,
                time.monotonic(),
                self._alarm_cooldowns,
                master_on=(
                    self.alarm_btn.isChecked()
                    if hasattr(self, "alarm_btn") else True
                ),
            )
            for rule in fired:
                _play_sound(rule.sound, "_alarm_player")

        self.logs_list.clear()
        api_enabled = self.config.router.api.enabled
        if self._last_logs:
            for entry in self._last_logs:
                self.logs_list.addItem(_format_log_entry(entry))
            self.logs_source_lbl.setText("live")
        else:
            placeholder = "waiting for API logs" if api_enabled else "API disabled"
            item = QListWidgetItem(placeholder)
            item.setForeground(QColor(MUTED))
            self.logs_list.addItem(item)
            self.logs_source_lbl.setText("waiting" if api_enabled else "off")

    def _on_alarm_toggled(self, checked: bool) -> None:
        self.alarm_btn.setText("Alarm on" if checked else "Alarm off")
        color = GREEN if checked else MUTED
        self.alarm_btn.setStyleSheet(f"QPushButton {{ padding: 2px 8px; font-size: 10px; color: {color}; }}")

    def _copy_selected_log(self) -> None:
        item = self.logs_list.currentItem()
        if item is None:
            return
        row = self.logs_list.row(item)
        if 0 <= row < len(self._last_logs):
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(_full_log_line(self._last_logs[row]))

    def _open_log_detail(self) -> None:
        if self._log_detail is None:
            self._log_detail = LogDetailWindow(self)
        self._log_detail.set_logs(self._last_logs)
        self._log_detail.show()
        self._log_detail.raise_()
        self._log_detail.activateWindow()

    def start(self, demo: bool = False) -> None:
        self._workers = build_collectors(self.config, self.state, self._stop, demo=demo)
        for worker in self._workers:
            worker.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._stop.set()
        for worker in self._workers:
            worker.join(timeout=2.0)
        self._workers = []

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._timer.stop()
            self.header.pause_btn.setText("Resume")
            self.header.pause_btn.setIcon(qta.icon("fa5s.play", color="#dee2e6"))
        else:
            self._timer.start()
            self.header.pause_btn.setText("Pause")
            self.header.pause_btn.setIcon(qta.icon("fa5s.pause", color="#dee2e6"))

    def _on_disconnect_clicked(self) -> None:
        self._disconnecting = True
        self.setup_requested.emit()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
        if not self._disconnecting:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()

    def _refresh(self) -> None:
        snapshot = self.state.snapshot()
        self.header.pill.set_state(snapshot.status)
        self.header.uptime.setText(format_uptime(snapshot.uptime_s))
        if hasattr(self, "cpu_bar"):
            self.cpu_bar.set_value(snapshot.cpu_pct)
            self.mem_bar.set_value(snapshot.mem_pct)
            self.temp_tile.set_value(snapshot.temp_c)
            self.volt_tile.set_value(snapshot.volt_v)
        if hasattr(self, "users_value"):
            self.users_value.setText(str(snapshot.active_users) if snapshot.active_users is not None else "--")
            self.users_source.setText(snapshot.active_users_source.upper() if snapshot.active_users_source else "NO SOURCE")
            self.pppoe_value.setText(str(snapshot.pppoe_users) if snapshot.pppoe_users is not None else "--")
            self.hotspot_value.setText(str(snapshot.hotspot_users) if snapshot.hotspot_users is not None else "--")

            used, size = snapshot.dhcp_pool_used, snapshot.dhcp_pool_size
            if used is not None and size:
                leases = snapshot.dhcp_leases
                self.dhcp_value.setText(f"{leases} active" if leases is not None else "--")
                pct = min(100.0, used / size * 100.0)
                self.dhcp_bar.setValue(int(round(pct)))
                self.dhcp_pct.setText(f"{pct:.0f}%")
                color = GREEN if pct < 80 else AMBER if pct < 90 else RED
                self.dhcp_bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}"
                )
                self.dhcp_pct.setStyleSheet(f"color: {color}; font-weight: 700;")
                detail = f"{used}/{size} IPs"
                self.dhcp_warning.setText(f"POOL NEARLY FULL · {detail}" if pct >= 80 else detail)
                self.dhcp_warning.setStyleSheet(
                    f"color: {color if pct >= 80 else MUTED}; font-size: 10px; font-weight: 700;"
                )
            else:
                self.dhcp_value.setText("--")
                self.dhcp_bar.setValue(0)
                self.dhcp_pct.setText("--")
                self.dhcp_warning.setText("")
        if hasattr(self, "port_rows"):
            for name, row in self.port_rows.items():
                row.update(snapshot.interfaces.get(name))
        for stats in snapshot.pings:
            row = self.ping_rows.get(stats.name)
            if row is not None:
                row.update_stats(stats)
        self._check_dns_warning(snapshot)
        if hasattr(self, "logs_list"):
            self._update_logs(snapshot)
        for iface in self.config.interfaces:
            chart = self.charts.get(iface.name)
            if chart is not None:
                chart.update_reading(snapshot, snapshot.history.get(iface.name, []), snapshot.interface_errors.get(iface.name, ""))
        self._update_footer(snapshot)

    def _update_footer(self, snapshot: Snapshot):
        detail = snapshot.status_detail or ""
        color = MUTED
        if snapshot.status == "DEGRADED":
            color = AMBER
        elif snapshot.status == "OFFLINE":
            color = RED
        parts = [snapshot.status]
        if detail:
            parts.append(detail)
        api_state = "API on" if self.config.router.api.enabled else "API off"
        parts.append(api_state)
        parts.append(f"SNMP {self.config.polling.interval:.1f}s")
        parts.append(f"{len(self.config.interfaces)} interfaces")
        parts.append(f"{len(self.config.ping.targets)} ping targets")
        text = "  ·  ".join(parts)
        self.footer.setText(text[:180])
        self.footer.setStyleSheet(f"color: {color}; font-size: 10px; font-family: {FONT_MONO};")
        self.footer.setToolTip(detail)

