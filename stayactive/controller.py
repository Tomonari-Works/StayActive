"""単一の Qt タイマーによるセッション制御。状態・期限は単調時計で管理する。"""

import logging
import math
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .backends import CursorBackend, KeepAwakeBackend
from .settings import SessionOptions

LOG = logging.getLogger("stayactive")


class ActivityController(QObject):
    changed = pyqtSignal()
    error = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, options=None, backend=None, cursor=None, clock=time.monotonic, parent=None):
        super().__init__(parent)
        self.options = (options or SessionOptions()).validated()
        self.backend = backend if backend is not None else KeepAwakeBackend()
        self.cursor = cursor if cursor is not None else CursorBackend()
        self.clock = clock
        self.running = False
        self.started_at = None
        self.deadline = None
        self.next_pulse = None
        self.elapsed = 0.0
        self.pulses = 0
        self.input_idle_seconds = None
        self._next_idle_sample = 0.0
        self.reason = "ready"
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)

    @property
    def remaining(self):
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - self.clock()) if self.running else 0.0

    @property
    def stationary_input(self):
        return self.options.mode == "quiet" and self.options.reset_idle and self.cursor.system == "Windows"

    def _validate_capability(self, options):
        if options.mode == "quiet" and not self.backend.available:
            raise RuntimeError("OS のスリープ抑止が利用できません。 / Sleep inhibition is unavailable.")
        if options.mode == "cursor" and not self.cursor.available:
            raise RuntimeError("カーソル移動が利用できません。 / Cursor movement is unavailable.")

    def start(self):
        if self.running:
            return True
        try:
            self._validate_capability(self.options)
            if self.backend.available:
                self.backend.start(self.options.keep_display)
            now = self.clock()
            self.started_at = now
            self.deadline = now + self.options.duration_minutes * 60 if self.options.duration_minutes else None
            self.next_pulse = now + self.options.interval_seconds
            self.elapsed, self.pulses = 0.0, 0
            self.reason = "running"
            self.running = True
            self._next_idle_sample = 0.0
            self._sample_input_idle(now)
            self.timer.start()
            self.changed.emit()
            return True
        except Exception as exc:
            self._fail(exc)
            return False

    def stop(self, reason="stopped"):
        was_running = self.running
        if was_running:
            self.elapsed = max(0.0, self.clock() - self.started_at)
        self.running = False
        self.timer.stop()
        self.next_pulse = None
        self.input_idle_seconds = None
        self.reason = reason
        try:
            self.backend.stop()
        except Exception as exc:
            self.reason = "error"
            LOG.exception("Could not release sleep inhibition")
            self.error.emit(str(exc))
        self.changed.emit()
        if was_running and reason == "completed" and self.reason != "error":
            self.completed.emit()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def configure(self, options):
        options = options.validated()
        previous = self.options
        self.options = options
        if not self.running and self.reason == "completed" and previous.duration_minutes != options.duration_minutes:
            self.reason = "ready"
        if self.running:
            try:
                self._validate_capability(options)
                if previous.keep_display != options.keep_display and self.backend.available:
                    self.backend.start(options.keep_display)
                if previous.duration_minutes != options.duration_minutes:
                    self.deadline = self.started_at + options.duration_minutes * 60 if options.duration_minutes else None
                if (previous.interval_seconds != options.interval_seconds or previous.mode != options.mode
                        or previous.reset_idle != options.reset_idle):
                    self.next_pulse = self.clock() + options.interval_seconds
                self.tick()
            except Exception as exc:
                self._fail(exc)
        self.changed.emit()

    def tick(self):
        if not self.running:
            return
        now = self.clock()
        self.elapsed = max(0.0, now - self.started_at)
        if self.deadline is not None and now >= self.deadline:
            self.stop("completed")
            return
        try:
            self.backend.check()
            self._sample_input_idle(now)
            sends_input = self.options.mode == "cursor" or self.stationary_input
            if sends_input:
                self.cursor.check_safety()
            if sends_input and now >= self.next_pulse:
                sent = (self.cursor.pulse(self.options.interval_seconds, move=False) if self.stationary_input
                        else self.cursor.pulse(self.options.interval_seconds))
                if sent:
                    self.pulses += 1
                    # SendInput の受理と OS が観測する待機時間は別。次の tick で再計測する。
                    self._next_idle_sample = now
                self.next_pulse = now + self.options.interval_seconds
        except Exception as exc:
            self._fail(exc)
            return
        self.changed.emit()

    def _sample_input_idle(self, now):
        if now < self._next_idle_sample:
            return
        self._next_idle_sample = now + 1.0
        self.input_idle_seconds = None
        if self.cursor.system != "Windows":
            return
        try:
            value = self.cursor.idle_seconds()
            if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
                self.input_idle_seconds = value
        except Exception:
            # 診断表示の失敗だけでスリープ抑止を解除しない。入力送信の失敗は pulse が扱う。
            pass

    def _fail(self, exc):
        LOG.error("Session failed: %s", exc, exc_info=True)
        self.stop("error")
        self.error.emit(str(exc))
