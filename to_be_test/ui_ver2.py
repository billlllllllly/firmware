"""Light Dance UI: dancer-figure grid with playback controls below.

Exports:
    MonitorWindow  - main window; expects (controller, players, time_provider)
    PART_NAMES     - body part order, shared with the controller
"""
import os
import re
import time as time_module

import numpy as np

from PySide6.QtCore import QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                            QPen, QPolygonF)
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                                QMainWindow, QPushButton, QVBoxLayout, QWidget)

try:
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
except Exception:  # Keep the UI usable even if QtMultimedia decoding is missing.
    QAudioDecoder = None
    QAudioFormat = None

# ---- theme ----
BG       = "#111113"
SURFACE  = "#1a1a1f"
TEXT     = "#f0f0f2"
DIM      = "#7a7a85"
ACCENT   = "#22c55e"
ACCENT_H = "#16a34a"
DANGER   = "#ef4444"
DANGER_H = "#dc2626"

PART_NAMES = ["hat", "face", "chestL", "chestR", "armL", "armR", "tie",
              "belt", "gloveL", "gloveR", "legL", "legR", "shoeL", "shoeR",
              "board"]

# UI labels for the prop boards. Firmware PLAYER_NUM 1/3/4/6 displays as 2/4/5/7.
PROP_PLAYERS = [2, 4, 5, 7]


def parse_player_index(device_id):
    """'player3' -> 3. Returns None on anything else."""
    if not device_id:
        return None
    m = re.match(r"player(\d+)$", device_id.strip())
    return int(m.group(1)) if m else None


def parse_prop_index(device_id):
    """'prop_p3' -> 3. Returns None on anything else."""
    if not device_id:
        return None
    m = re.match(r"prop_p(\d+)$", device_id.strip())
    return int(m.group(1)) if m else None


# ============================================================
# DANCER WIDGET — paints one figure with per-part colors
# ============================================================
class DancerWidget(QWidget):
    def __init__(self, index):
        super().__init__()
        self.index = index
        self.colors = {n: (0, 0, 0) for n in PART_NAMES}
        self.online = False
        self.setFixedSize(170, 290)

    def set_colors(self, colors):
        self.colors = colors
        self.update()

    def set_online(self, online):
        if online != self.online:
            self.online = online
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(SURFACE))

        # online dot + label
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(ACCENT if self.online else DANGER)))
        p.drawEllipse(QPointF(self.width() / 2 - 38, 12), 4, 4)

        p.setPen(QColor(TEXT if self.online else DIM))
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(0, 4, self.width(), 16, Qt.AlignCenter,
                   f"Dancer {self.index + 1}")

        # SVG-like figure (viewBox 10 0 222 360, group translate 0,35)
        vb_x, vb_y, vb_w, vb_h = 10, 0, 222, 360
        avail_h = self.height() - 22
        s = min(self.width() / vb_w, avail_h / vb_h)
        ox = (self.width() - vb_w * s) / 2 - vb_x * s
        oy = 22 + (avail_h - vb_h * s) / 2 - vb_y * s
        p.translate(ox, oy)
        p.scale(s, s)
        p.translate(0, 35)
        p.setPen(Qt.NoPen)

        def br(name):
            r, g, b = self.colors[name]
            return QBrush(QColor(r, g, b))

        # hat
        path = QPainterPath()
        path.moveTo(96.8, 5)
        path.lineTo(145.2, 5)
        path.lineTo(145.2, 23)
        path.lineTo(169.4, 23)
        path.lineTo(169.4, 38)
        path.lineTo(72.6, 38)
        path.lineTo(72.6, 23)
        path.lineTo(96.8, 23)
        path.closeSubpath()
        p.fillPath(path, br("hat"))

        # face
        p.setBrush(br("face"))
        p.drawEllipse(QPointF(121, 68), 30, 30)

        # body rectangles
        for name, x, y, w, h in [
            ("chestL",  72, 103, 28, 65),
            ("chestR", 142, 103, 28, 65),
            ("armL",    35, 103, 32, 65),
            ("armR",   175, 103, 32, 65),
            ("tie",    105, 103, 32, 50),
            ("belt",    78, 173, 86, 35),
            ("gloveL",  35, 173, 32, 35),
            ("gloveR", 175, 173, 32, 35),
            ("legL",    85, 213, 28, 80),
            ("legR",   129, 213, 28, 80),
            ("shoeL",   75, 298, 45, 15),
            ("shoeR",  122, 298, 45, 15),
        ]:
            p.fillRect(x, y, w, h, br(name))

        # tie tip
        p.setBrush(br("tie"))
        p.drawPolygon(QPolygonF([QPointF(105, 153),
                                  QPointF(137, 153),
                                  QPointF(121, 173)]))


# ============================================================
# PROP STATUS — name + connection dot, one per prop player
# ============================================================
class PropWidget(QWidget):
    def __init__(self, player_num):
        super().__init__()
        self.player_num = player_num
        self.online = False
        self.setFixedSize(110, 32)

    def set_online(self, online):
        if online != self.online:
            self.online = online
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(SURFACE))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(ACCENT if self.online else DANGER)))
        p.drawEllipse(QPointF(14, self.height() / 2), 4, 4)

        p.setPen(QColor(TEXT if self.online else DIM))
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(28, 0, self.width() - 32, self.height(),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   f"Prop p{self.player_num}")



# ============================================================
# MP3 WAVEFORM WIDGET — bottom-right future audio preview
# ============================================================
class WaveformWidget(QWidget):
    """Shows the upcoming MP3 waveform using the same playback clock as the show.

    The decoder runs once at startup and stores a compact peak envelope instead
    of the full PCM stream, so repainting the preview is lightweight.
    """
    def __init__(self, time_provider_seconds, future_seconds=12.0):
        super().__init__()
        self.time_provider_seconds = time_provider_seconds
        self.future_seconds = float(future_seconds)
        self.waveform = np.zeros(0, dtype=np.float32)
        self.sample_rate = 44100
        self.frames_per_bin = 1024
        self.duration_seconds = 0.0
        self.status_text = "No MP3"
        self._decoder = None
        self._pending_abs = np.zeros(0, dtype=np.float32)
        self.setMinimumSize(360, 76)
        self.setMaximumHeight(90)

    def load_file(self, file_path):
        if not file_path:
            self.status_text = "No MP3 path"
            self.update()
            return
        if not os.path.exists(file_path):
            self.status_text = "MP3 not found"
            self.update()
            return
        if QAudioDecoder is None or QAudioFormat is None:
            self.status_text = "QAudioDecoder unavailable"
            self.update()
            return

        self.status_text = "Loading waveform..."
        self.waveform = np.zeros(0, dtype=np.float32)
        self._pending_abs = np.zeros(0, dtype=np.float32)
        self.duration_seconds = 0.0

        self._decoder = QAudioDecoder(self)
        self._decoder.bufferReady.connect(self._on_audio_buffer_ready)
        self._decoder.finished.connect(self._on_decode_finished)
        self._decoder.durationChanged.connect(self._on_duration_changed)
        try:
            self._decoder.error.connect(self._on_decoder_error)
        except Exception:
            pass
        self._decoder.setSource(QUrl.fromLocalFile(file_path))
        self._decoder.start()
        self.update()

    def set_future_seconds(self, seconds):
        self.future_seconds = max(1.0, float(seconds))
        self.update()

    def _on_duration_changed(self, duration_ms):
        if duration_ms and duration_ms > 0:
            self.duration_seconds = duration_ms / 1000.0
            self.update()

    def _on_decoder_error(self, *_args):
        msg = self._decoder.errorString() if self._decoder else "Decode error"
        self.status_text = msg or "Decode error"
        self.update()

    def _on_audio_buffer_ready(self):
        if self._decoder is None:
            return
        buf = self._decoder.read()
        samples = self._buffer_to_mono_float(buf)
        if samples.size == 0:
            return

        fmt = buf.format()
        sr = fmt.sampleRate()
        if sr > 0:
            self.sample_rate = sr

        abs_samples = np.abs(samples).astype(np.float32, copy=False)
        if self._pending_abs.size:
            abs_samples = np.concatenate((self._pending_abs, abs_samples))
            self._pending_abs = np.zeros(0, dtype=np.float32)

        usable = (abs_samples.size // self.frames_per_bin) * self.frames_per_bin
        if usable <= 0:
            self._pending_abs = abs_samples
            return

        bins = abs_samples[:usable].reshape(-1, self.frames_per_bin).max(axis=1)
        if self.waveform.size:
            self.waveform = np.concatenate((self.waveform, bins))
        else:
            self.waveform = bins
        self._pending_abs = abs_samples[usable:]
        self.duration_seconds = max(
            self.duration_seconds,
            self.waveform.size * self.frames_per_bin / max(1, self.sample_rate),
        )
        self.update()

    def _on_decode_finished(self):
        if self._pending_abs.size:
            self.waveform = np.concatenate((
                self.waveform,
                np.array([float(self._pending_abs.max())], dtype=np.float32),
            ))
            self._pending_abs = np.zeros(0, dtype=np.float32)
        if self.waveform.size:
            peak = float(self.waveform.max())
            if peak > 0:
                self.waveform = np.clip(self.waveform / peak, 0.0, 1.0)
            self.status_text = ""
            self.duration_seconds = max(
                self.duration_seconds,
                self.waveform.size * self.frames_per_bin / max(1, self.sample_rate),
            )
        else:
            self.status_text = "No waveform data"
        self.update()

    def _buffer_to_mono_float(self, buf):
        if not buf.isValid():
            return np.zeros(0, dtype=np.float32)

        raw = self._buffer_bytes(buf)
        if not raw:
            return np.zeros(0, dtype=np.float32)

        fmt = buf.format()
        channel_count = max(1, fmt.channelCount())
        sample_format = fmt.sampleFormat()

        try:
            if sample_format == QAudioFormat.SampleFormat.UInt8:
                data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                data = (data - 128.0) / 128.0
            elif sample_format == QAudioFormat.SampleFormat.Int16:
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                data /= 32768.0
            elif sample_format == QAudioFormat.SampleFormat.Int32:
                data = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
                data /= 2147483648.0
            elif sample_format == QAudioFormat.SampleFormat.Float:
                data = np.frombuffer(raw, dtype=np.float32).astype(np.float32)
            else:
                return np.zeros(0, dtype=np.float32)
        except ValueError:
            return np.zeros(0, dtype=np.float32)

        frame_count = data.size // channel_count
        if frame_count <= 0:
            return np.zeros(0, dtype=np.float32)
        data = data[:frame_count * channel_count].reshape(frame_count,
                                                           channel_count)
        return data.mean(axis=1).astype(np.float32, copy=False)

    def _buffer_bytes(self, buf):
        byte_count = buf.byteCount()
        for getter_name in ("constData", "data"):
            getter = getattr(buf, getter_name, None)
            if getter is None:
                continue
            try:
                data = getter()
                if isinstance(data, memoryview):
                    return data.tobytes()[:byte_count]
                return bytes(data)[:byte_count]
            except Exception:
                continue
        return b""

    def _format_time(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(SURFACE))

        margin = 10
        label_h = 18
        graph_top = margin + label_h + 4
        graph_bottom = self.height() - margin
        graph_h = max(1, graph_bottom - graph_top)
        graph_w = max(1, self.width() - 2 * margin)

        now_s = max(0.0, float(self.time_provider_seconds()))
        end_s = now_s + self.future_seconds

        p.setPen(QColor(TEXT))
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(margin, 4, graph_w, label_h, Qt.AlignLeft | Qt.AlignVCenter,
                   "MP3 future signal")

        p.setPen(QColor(DIM))
        f.setBold(False)
        p.setFont(f)
        label = f"{self._format_time(now_s)} → {self._format_time(end_s)}"
        p.drawText(margin, 4, graph_w, label_h, Qt.AlignRight | Qt.AlignVCenter,
                   label)

        mid_y = graph_top + graph_h / 2
        p.setPen(QPen(QColor("#2a2a31"), 1))
        p.drawLine(margin, int(mid_y), margin + graph_w, int(mid_y))

        if self.waveform.size == 0:
            p.setPen(QColor(DIM if self.status_text else TEXT))
            p.drawText(margin, graph_top, graph_w, graph_h,
                       Qt.AlignCenter, self.status_text or "Loading...")
            return

        bin_seconds = self.frames_per_bin / max(1, self.sample_rate)
        start_bin = int(now_s / bin_seconds)
        end_bin = int(end_s / bin_seconds) + 1
        if start_bin >= self.waveform.size:
            p.setPen(QColor(DIM))
            p.drawText(margin, graph_top, graph_w, graph_h,
                       Qt.AlignCenter, "End of track")
            return

        segment = self.waveform[start_bin:min(end_bin, self.waveform.size)]
        if segment.size == 0:
            return

        points = min(graph_w, segment.size)
        if points <= 1:
            return

        # Resample the visible future window to one vertical bar per pixel.
        xp = np.linspace(0, segment.size - 1, int(points))
        amps = np.interp(xp, np.arange(segment.size), segment)
        p.setPen(QPen(QColor(ACCENT), 1))
        for x_i, amp in enumerate(amps):
            x = margin + x_i
            half_h = float(amp) * (graph_h * 0.46)
            p.drawLine(x, int(mid_y - half_h), x, int(mid_y + half_h))

        # Left edge is the current playback point; everything right of it is future audio.
        p.setPen(QPen(QColor(TEXT), 1))
        p.drawLine(margin, graph_top, margin, graph_bottom)

# ============================================================
# MAIN WINDOW
# ============================================================
class MonitorWindow(QMainWindow):
    def __init__(self, controller, players, time_provider):
        super().__init__()
        self.controller = controller
        self.players = players
        self.time_provider = time_provider
        self.dancers = []
        self.props = {}  # player_num -> PropWidget

        self._init_ui()
        self._setup_timers()
        self.controller.setup_threads(self)

    def _init_ui(self):
        self.setWindowTitle("Light Dance Controller")
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {BG}; }}
            QWidget    {{ background-color: transparent; color: {TEXT}; }}
            QLabel     {{ border: none; background: transparent; }}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.addSpacing(40)

        # dancer grid (or fallback message if no light data)
        n = len(self.players) if self.players is not None else 0
        if n == 0:
            warn = QLabel("lightdata.npz not found.\n"
                          "Run: python fetch_lightdata.py")
            warn.setAlignment(Qt.AlignCenter)
            warn.setStyleSheet(
                f"font-size: 14px; color: {DANGER}; padding: 60px;")
            root.addWidget(warn, stretch=1)
        else:
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(8)
            cols = 7 if n > 7 else max(n, 1)
            for i in range(n):
                w = DancerWidget(i)
                self.dancers.append(w)
                grid.addWidget(w, i // cols, i % cols)
            root.addWidget(grid_host, stretch=1)

        # prop status row, one indicator per known prop player
        prop_host = QWidget()
        prop_row = QHBoxLayout(prop_host)
        prop_row.setContentsMargins(0, 0, 0, 0)
        prop_row.setSpacing(8)
        prop_row.addStretch()
        for pn in PROP_PLAYERS:
            w = PropWidget(pn)
            self.props[pn] = w
            prop_row.addWidget(w)
        prop_row.addStretch()
        root.addWidget(prop_host)

        root.addSpacing(40)

        # bottom controls: [broadcast] ... [input] seconds [Start] [Exit]
        controls = QWidget()
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)

        self.broadcast_label = QLabel("0")
        self.broadcast_label.setStyleSheet(
            f"font-family: 'Consolas', 'Monaco', monospace; "
            f"font-size: 13px; color: {TEXT};")
        cl.addWidget(self.broadcast_label)

        cl.addStretch()

        # music offset (seconds): +ve = music ahead of broadcast
        self.offset_input = QLineEdit(f"{self.controller.music_offset:g}")
        self.offset_input.setFixedWidth(70)
        self.offset_input.setMinimumHeight(44)
        self.offset_input.setAlignment(Qt.AlignCenter)
        self.offset_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE};
                border: none; border-radius: 8px;
                padding: 8px 14px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 14px; color: {TEXT};
            }}
        """)
        self.offset_input.editingFinished.connect(self._on_offset_changed)
        cl.addWidget(self.offset_input)

        offset_label = QLabel("offset")
        offset_label.setStyleSheet(f"font-size: 13px; color: {TEXT};")
        cl.addWidget(offset_label)

        cl.addSpacing(30)

        self.time_input = QLineEdit("0")
        self.time_input.setFixedWidth(100)
        self.time_input.setMinimumHeight(44)
        self.time_input.setAlignment(Qt.AlignCenter)
        self.time_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE};
                border: none; border-radius: 8px;
                padding: 8px 14px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 16px; color: {TEXT};
            }}
        """)
        self.time_input.editingFinished.connect(self._on_input_changed)
        cl.addWidget(self.time_input)

        sec_label = QLabel("seconds")
        sec_label.setStyleSheet(f"font-size: 13px; color: {DIM};")
        cl.addWidget(sec_label)

        self.toggle_button = QPushButton("Start")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setMinimumHeight(44)
        self.toggle_button.setMinimumWidth(140)
        self._style_toggle(False)
        self.toggle_button.clicked.connect(self._toggle_playback)
        cl.addWidget(self.toggle_button)

        self.exit_button = QPushButton("Exit")
        self.exit_button.setCursor(Qt.PointingHandCursor)
        self.exit_button.setMinimumHeight(44)
        self.exit_button.setMinimumWidth(90)
        self.exit_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DIM};
                border: 1px solid {DIM};
                border-radius: 8px;
                padding: 8px 20px; font-size: 15px;
            }}
            QPushButton:hover {{ color: {TEXT}; border-color: {TEXT}; }}
        """)
        self.exit_button.clicked.connect(self._exit_action)
        cl.addWidget(self.exit_button)

        cl.addSpacing(16)

        self.waveform_widget = WaveformWidget(self._current_music_seconds,
                                              future_seconds=12.0)
        self.waveform_widget.load_file(getattr(self.controller, "music_file", None))
        cl.addWidget(self.waveform_widget)

        root.addWidget(controls)

    def _current_music_seconds(self):
        """Return the actual MP3 time shown in the waveform preview."""
        music_player = getattr(self.controller, "music_player", None)
        if music_player is not None:
            player = music_player.player
            pos_ms = player.position()
            if self.controller.isRunning or pos_ms > 0:
                return max(0.0, pos_ms / 1000.0)
        return max(0.0, self.get_time_value() + self.controller.music_offset)

    def _style_toggle(self, running):
        bg = DANGER if running else ACCENT
        hover = DANGER_H if running else ACCENT_H
        self.toggle_button.setText("Stop" if running else "Start")
        self.toggle_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg}; color: white; border: none;
                border-radius: 8px; padding: 8px 20px;
                font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """)

    def _setup_timers(self):
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start(33)  # ~30 Hz

        self.broadcast_timer = QTimer(self)
        self.broadcast_timer.timeout.connect(self.controller.broadcast_time)
        self.broadcast_timer.start(1000)

    # ---- callbacks the Controller calls back into ----
    def update_toggle_button(self, running):
        self._style_toggle(running)

    def get_time_value(self):
        try:
            time_str_raw = self.time_input.text().strip()
            time_str_raw = time_str_raw.replace(";", ":")
            if ":" in time_str_raw:
                # if format MM:SS return MM*60 + SS
                parts = time_str_raw.split(":")
                if len(parts) == 2:
                    minutes = float(parts[0]) if parts[0] else 0
                    seconds = float(parts[1]) if parts[1] else 0
                    return (minutes * 60) + seconds
            return int(float(time_str_raw))
        except ValueError:
            return 0

    def set_time_value(self, seconds):
        self.time_input.setText(str(int(max(0, seconds))))

    # ---- UI handlers ----
    def _on_input_changed(self):
        try:
            text = self.time_input.text().strip()
            text = text.replace(";", ":")
            if ":" in text:
                parts = text.split(":", 1)
                if len(parts) == 2:
                    minutes = int(parts[0]) if parts[0] else 0
                    seconds = int(parts[1]) if parts[1] else 0
                    v = max(0, minutes * 60 + seconds)
                else:
                    v = 0
            else:
                v = max(0, int(float(text)))
            self.time_input.setText(str(v))
        except ValueError:
            self.time_input.setText("0")

    def _on_offset_changed(self):
        try:
            v = float(self.offset_input.text().strip())
        except ValueError:
            v = self.controller.music_offset
        self.offset_input.setText(f"{v:g}")
        self.controller.set_music_offset(v)

    def _toggle_playback(self):
        if self.controller.isRunning:
            self.controller.stop_function(self)
        else:
            self.controller.start_function(self)

    def _exit_action(self):
        self.controller.exit_event.set()
        self.close()

    def closeEvent(self, event):
        self.controller.exit_event.set()
        event.accept()

    # ---- per-tick refresh ----
    def _update_ui(self):
        msg = self.controller.current_broadcast_message
        self.broadcast_label.setText(msg if msg else "0")

        now = time_module.time()
        online_indices = set()
        online_props = set()
        for device in self.controller.devices.values():
            if device.last_response_time and now - device.last_response_time > 2:
                device.status = "Disconnected"
            if device.status == "Connected":
                idx = parse_player_index(device.device_id)
                if idx is not None:
                    online_indices.add(idx)
                    continue
                pidx = parse_prop_index(device.device_id)
                if pidx is not None:
                    online_props.add(pidx + 1)

        if self.dancers and self.players is not None:
            ticks = self.time_provider()
            for i, w in enumerate(self.dancers):
                w.set_online(i in online_indices)
                w.set_colors(self.players[i].colors_at(ticks))

        for pn, w in self.props.items():
            w.set_online(pn in online_props)

        if hasattr(self, "waveform_widget"):
            self.waveform_widget.update()
