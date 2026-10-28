"""Windows の OS ホットキー。キーボードフックやワーカースレッドは使わない。"""

import ctypes
from ctypes import wintypes
import platform

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.owner.ID:
                self.owner.activated.emit()
                return True, 0
        return False, 0


class Hotkey(QObject):
    activated = pyqtSignal()
    ID = 0x5341

    def __init__(self, window, enabled=True):
        super().__init__(window)
        self.registered = False
        self.filter = None
        self.shortcut = None
        self.user = None
        if enabled and platform.system() == "Windows":
            self.user = ctypes.WinDLL("user32", use_last_error=True)
            self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user.RegisterHotKey.restype = wintypes.BOOL
            self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user.UnregisterHotKey.restype = wintypes.BOOL
            self.registered = bool(self.user.RegisterHotKey(None, self.ID, 0x4003, ord("J")))
            if self.registered:
                self.filter = _Filter(self)
                QApplication.instance().installNativeEventFilter(self.filter)
        if not self.registered:
            self.shortcut = QShortcut(QKeySequence("Ctrl+Alt+J"), window)
            self.shortcut.activated.connect(self.activated.emit)

    def close(self):
        if self.registered:
            self.user.UnregisterHotKey(None, self.ID)
            self.registered = False
        if self.filter is not None:
            QApplication.instance().removeNativeEventFilter(self.filter)
            self.filter = None
        if self.shortcut is not None:
            self.shortcut.setEnabled(False)
