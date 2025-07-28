
import sys
import threading
import time
import random
import ctypes
import pyautogui
import keyboard
import platform
import subprocess
import shutil

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QComboBox, QCheckBox,
    QPushButton, QHBoxLayout, QVBoxLayout, QSlider, QLineEdit,
    QFrame, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont, QColor

# --- Multi-language Dictionary ---
LANGS = ['日本語', 'English']
I18N = {
    '日本語': {
        'title': "🔥StayActive",
        'subtitle': "自由な創作を、アクティブに。",
        'start': "アクティブ維持を開始",
        'status_running': "● 維持中（離席になりません）",
        'status_stopped': "■ 停止中",
        'mode_label': "アクティブ維持モード：",
        'mode_move': "見えるジグル（カーソル移動）",
        'mode_stealth': "完全ステルス（バレずに維持）",
        'interval': "動作間隔(ms):",
        'hotkey': "▶ どこでもON/OFF: Ctrl+Alt+J",
        'minimize': "最小化",
        'exit': "終了",
        'language': "言語 / Language",
        'mode_unavailable': "（このOSではステルス非対応・カーソル移動のみ）"
    },
    'English': {
        'title': "🔥StayActive",
        'subtitle': "StayActive: Your device, always awake—never miss a moment.",
        'start': "Stay Active Now",
        'status_running': "● ACTIVE (You will never go idle!)",
        'status_stopped': "■ STOPPED",
        'mode_label': "Active Mode:",
        'mode_move': "Visible Jiggle (Cursor Moves)",
        'mode_stealth': "Stealth Mode (Undetectable)",
        'interval': "Interval (ms):",
        'hotkey': "▶ Hotkey: Ctrl+Alt+J (Toggle from anywhere)",
        'minimize': "Minimize",
        'exit': "Exit",
        'language': "Language / 言語",
        'mode_unavailable': "(Stealth is unavailable on this OS. Only cursor move works.)"
    }
}

def send_stealth_signal():
    system = platform.system()
    if system == "Windows":
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = (('dx', ctypes.c_long),
                        ('dy', ctypes.c_long),
                        ('mouseData', ctypes.c_ulong),
                        ('dwFlags', ctypes.c_ulong),
                        ('time', ctypes.c_ulong),
                        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)))
        class _INPUTunion(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTunion)]
        INPUT_MOUSE = 0
        extra = ctypes.c_ulong(0)
        mi = MOUSEINPUT(0, 0, 0, 0x0001, 0, ctypes.pointer(extra))
        union = _INPUTunion()
        union.mi = mi
        inp = INPUT(INPUT_MOUSE, union)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
    elif system == "Darwin":
        if shutil.which("caffeinate"):
            subprocess.Popen(["caffeinate", "-u", "-t", "2"])
    elif system == "Linux":
        if shutil.which("xdg-screensaver"):
            subprocess.Popen(["xdg-screensaver", "reset"])
        elif shutil.which("xdotool"):
            subprocess.Popen(["xdotool", "mousemove_relative", "--", "0", "0"])
        try:
            import dbus
            bus = dbus.SessionBus()
            scr = bus.get_object('org.gnome.SessionManager', '/org/gnome/SessionManager')
            scr.Inhibit("StayActive", 0, "Jiggle", 8, dbus_interface='org.gnome.SessionManager')
        except Exception:
            pass

def is_stealth_supported():
    system = platform.system()
    if system == "Windows":
        return True
    elif system == "Darwin":
        return shutil.which("caffeinate") is not None
    elif system == "Linux":
        return shutil.which("xdg-screensaver") or shutil.which("xdotool")
    else:
        return False

class ModernButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet("""
            QPushButton {
                background: qlineargradient(y1:0, y2:1,
                    stop:0 #21D4FD, stop:1 #B721FF);
                color: white; font-weight: bold; font-size: 17px;
                border-radius: 16px; padding: 10px 22px;
                border: none; min-width: 120px;
            }
            QPushButton:pressed {
                background: #6C47FF;
                color: #fff;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

class StayActiveApp(QWidget):
    def __init__(self):
        super().__init__()
        self.lang = 'English'
        self.setWindowTitle(I18N[self.lang]['title'])
        self.setWindowIcon(QIcon())
        self.setMinimumSize(560, 540)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.stealth_available = is_stealth_supported()
        self.patterns = [
            I18N[self.lang]['mode_move'],
            I18N[self.lang]['mode_stealth']
        ]
        self.jiggler_running = False
        self.jiggler_thread = None
        self.init_ui()
        keyboard.add_hotkey('ctrl+alt+j', self.toggle_jiggler)

        # Default: Stealth mode selected if available
        if self.stealth_available:
            self.pattern_cb.setCurrentIndex(1)
        else:
            self.pattern_cb.setCurrentIndex(0)

    def init_ui(self):
        self.main_frame = QFrame(self)
        self.main_frame.setStyleSheet("""
            QFrame {
                background: #23243b;
                border-radius: 24px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 9)
        shadow.setColor(QColor(80, 80, 120, 120))
        self.main_frame.setGraphicsEffect(shadow)

        self.title = QLabel()
        self.title.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.title.setStyleSheet("color: #00FFD0; letter-spacing:2px; margin-top:0px;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.title.setMinimumHeight(62)

        self.subtitle = QLabel()
        self.subtitle.setFont(QFont("Meiryo", 15))
        self.subtitle.setStyleSheet("color:#b3e0ef; margin-bottom:8px;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.subtitle.setMinimumHeight(28)

        self.status_label = QLabel()
        self.status_label.setFont(QFont("Meiryo", 17, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.toggle_cb = QCheckBox()
        self.toggle_cb.setStyleSheet("""
            QCheckBox::indicator { width:32px; height:32px; }
            QCheckBox { color:#f7f7f7; font-size:19px; font-weight:bold; padding:7px;}
        """)
        self.toggle_cb.setChecked(False)
        self.toggle_cb.stateChanged.connect(self.toggle_jiggler)

        self.lbl_pattern = QLabel()
        self.lbl_pattern.setStyleSheet("color:#aad5ff; font-size:16px;")
        self.pattern_cb = QComboBox()
        self.pattern_cb.setStyleSheet("""
            QComboBox {
                background:#232F3E; color:#fff; border-radius:11px; font-size:16px;
                padding:7px 13px;
            }
            QComboBox QAbstractItemView {
                background:#232F3E; color:#fff; border-radius:10px;
            }
        """)

        h_pattern = QHBoxLayout()
        h_pattern.addStretch(1)
        h_pattern.addWidget(self.lbl_pattern)
        h_pattern.addWidget(self.pattern_cb)
        h_pattern.addStretch(1)

        self.unavailable_label = QLabel()
        self.unavailable_label.setStyleSheet("color:#ef767a; font-size:13px; font-weight:bold;")

        self.lbl_interval = QLabel()
        self.lbl_interval.setStyleSheet("color:#aad5ff; font-size:16px;")
        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(1000, 30000)
        self.interval_slider.setValue(7000)
        self.interval_slider.setSingleStep(100)
        self.interval_slider.valueChanged.connect(self.update_interval)
        self.interval_edit = QLineEdit(str(self.interval_slider.value()))
        self.interval_edit.setFixedWidth(80)
        self.interval_edit.setStyleSheet("""
            QLineEdit { background:#232F3E; color:#fff; border-radius:10px; padding:4px 9px; font-size:16px;}
        """)
        self.interval_edit.editingFinished.connect(self.sync_slider_edit)

        h_interval = QHBoxLayout()
        h_interval.addStretch(1)
        h_interval.addWidget(self.lbl_interval)
        h_interval.addWidget(self.interval_slider)
        h_interval.addWidget(self.interval_edit)
        h_interval.addStretch(1)

        self.hotkey_label = QLabel()
        self.hotkey_label.setStyleSheet("color: #90bfff; font-size:15px; font-style:italic;")
        self.hotkey_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.lang_label = QLabel()
        self.lang_label.setStyleSheet("color:#aef7cd; font-size:14px;")
        self.lang_cb = QComboBox()
        self.lang_cb.addItems(LANGS)
        self.lang_cb.setCurrentIndex(LANGS.index(self.lang))
        self.lang_cb.setStyleSheet("""
            QComboBox {
                background:#2c3e50; color:#fff; border-radius:7px; font-size:15px;
                padding:5px 12px;
            }
        """)
        self.lang_cb.currentIndexChanged.connect(self.switch_language)
        h_lang = QHBoxLayout()
        h_lang.addStretch()
        h_lang.addWidget(self.lang_label)
        h_lang.addWidget(self.lang_cb)
        h_lang.addStretch()

        btn_min = ModernButton("")
        btn_min.clicked.connect(self.showMinimized)
        btn_exit = ModernButton("")
        btn_exit.clicked.connect(self.close_app)
        self.btn_min = btn_min
        self.btn_exit = btn_exit

        h_btns = QHBoxLayout()
        h_btns.addStretch(1)
        h_btns.addWidget(btn_min)
        h_btns.addWidget(btn_exit)
        h_btns.addStretch(1)

        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(12)
        layout.addSpacing(14)
        layout.addWidget(self.title)
        layout.addSpacing(0)
        layout.addWidget(self.subtitle)
        layout.addSpacing(10)
        layout.addWidget(self.status_label)
        layout.addSpacing(10)
        layout.addWidget(self.toggle_cb, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(2)
        layout.addLayout(h_pattern)
        layout.addWidget(self.unavailable_label)
        layout.addLayout(h_interval)
        layout.addWidget(self.hotkey_label)
        layout.addLayout(h_lang)
        layout.addStretch(1)
        layout.addLayout(h_btns)
        layout.addSpacing(8)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        outer.addWidget(self.main_frame)
        outer.addStretch(1)

        self.update_texts()
        self.set_status_style(False)

    def update_texts(self):
        L = I18N[self.lang]
        self.setWindowTitle(L['title'])
        self.title.setText(L['title'])
        self.subtitle.setText(L['subtitle'])
        self.toggle_cb.setText(L['start'])
        self.lbl_pattern.setText(L['mode_label'])
        self.pattern_cb.clear()
        self.patterns = [L['mode_move'], L['mode_stealth']]
        self.pattern_cb.addItems(self.patterns)
        self.lbl_interval.setText(L['interval'])
        self.hotkey_label.setText(L['hotkey'])
        self.lang_label.setText(L['language'])
        self.btn_min.setText(L['minimize'])
        self.btn_exit.setText(L['exit'])
        self.set_status_style(self.jiggler_running)
        if not self.stealth_available:
            self.unavailable_label.setText(L['mode_unavailable'])
            self.pattern_cb.model().item(1).setEnabled(False)
        else:
            self.unavailable_label.setText("")
            self.pattern_cb.model().item(1).setEnabled(True)

    def set_status_style(self, running: bool):
        L = I18N[self.lang]
        if running:
            self.status_label.setText(L['status_running'])
            self.status_label.setStyleSheet("""
                color: qlineargradient(y1:0, y2:1, stop:0 #00FFD0, stop:1 #21D4FD);
                background: qlineargradient(y1:0, y2:1, stop:0 #232F3E, stop:1 #1A1A28);
                border-radius: 13px; padding: 7px 0; margin-bottom:7px;
                font-size:17px; font-weight:bold;
            """)
        else:
            self.status_label.setText(L['status_stopped'])
            self.status_label.setStyleSheet("""
                color: #ef767a; background: none; padding:7px 0; font-size:17px; font-weight:bold;
            """)

    def switch_language(self, idx):
        self.lang = LANGS[idx]
        self.update_texts()

    def sync_slider_edit(self):
        try:
            val = int(self.interval_edit.text())
            val = min(max(1000, val), 30000)
            self.interval_slider.setValue(val)
        except:
            pass

    def update_interval(self):
        val = self.interval_slider.value()
        self.interval_edit.setText(str(val))

    def toggle_jiggler(self, *args):
        if not self.jiggler_running:
            self.jiggler_running = True
            self.toggle_cb.blockSignals(True)
            self.toggle_cb.setChecked(True)
            self.toggle_cb.blockSignals(False)
            self.set_status_style(True)
            interval = self.interval_slider.value() / 1000.0
            pattern = self.pattern_cb.currentText()
            self.jiggler_thread = threading.Thread(
                target=self.jiggle_loop,
                args=(interval, pattern),
                daemon=True
            )
            self.jiggler_thread.start()
        else:
            self.jiggler_running = False
            self.toggle_cb.blockSignals(True)
            self.toggle_cb.setChecked(False)
            self.toggle_cb.blockSignals(False)
            self.set_status_style(False)

    def jiggle_loop(self, interval, pattern):
        L = I18N[self.lang]
        while self.jiggler_running:
            if pattern == L['mode_move']:
                x, y = pyautogui.position()
                dx, dy = random.randint(-10, 10), random.randint(-10, 10)
                pyautogui.moveRel(dx, dy, duration=0.07)
                pyautogui.moveRel(-dx, -dy, duration=0.07)
            else:
                send_stealth_signal()
            time.sleep(interval)

    def close_app(self):
        self.jiggler_running = False
        self.close()

def main():
    app = QApplication(sys.argv)
    win = StayActiveApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
