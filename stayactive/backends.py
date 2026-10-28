"""OS の維持要求とカーソル移動。Windows API は UI スレッドで取得・解除する。"""

import ctypes
from ctypes import wintypes
import os
import platform
import shutil
import subprocess
import time


class BackendError(RuntimeError):
    pass


class KeepAwakeBackend:
    def __init__(self):
        self.system = platform.system()
        self.process = None
        self.active = False
        self.executable = (shutil.which("caffeinate") if self.system == "Darwin"
                           else shutil.which("systemd-inhibit") if self.system == "Linux" else None)
        self.available = self.system == "Windows" or self.executable is not None
        self.display_supported = self.system in ("Windows", "Darwin")
        if self.system == "Windows":
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
            self.kernel.SetThreadExecutionState.restype = wintypes.DWORD

    def start(self, keep_display: bool):
        if not self.available:
            raise BackendError("この環境では OS のスリープ抑止を利用できません。 / Sleep inhibition is unavailable.")
        if self.system == "Windows":
            flags = 0x80000000 | 0x00000001 | (0x00000002 if keep_display else 0)
            if not self.kernel.SetThreadExecutionState(flags):
                raise BackendError("Windows がスリープ抑止要求を拒否しました。 / Windows rejected the power request.")
        else:
            self.stop()
            if self.system == "Darwin":
                args = [self.executable, "-i", "-w", str(os.getpid())]
                if keep_display:
                    args.append("-d")
            else:
                # 親終了で stdin が閉じると cat も終了し、クラッシュ時も要求を残さない。
                args = [self.executable, "--what=idle:sleep", "--who=StayActive",
                        "--why=StayActive session", "--mode=block", "cat"]
            try:
                self.process = subprocess.Popen(args, stdin=subprocess.PIPE if self.system == "Linux" else subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as exc:
                raise BackendError("スリープ抑止を開始できません。 / Could not start sleep inhibition.") from exc
        self.active = True

    def check(self):
        if self.process is not None and self.process.poll() is not None:
            raise BackendError("OS のスリープ抑止が終了しました。権限・実行環境を確認してください。 / The sleep inhibitor exited; check system support and permissions.")

    def stop(self):
        if self.system == "Windows" and self.active:
            if not self.kernel.SetThreadExecutionState(0x80000000):
                raise BackendError("スリープ抑止を解除できません。終了して再確認してください。 / Could not release the power request; quit the app to release it.")
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.5)
            if process.stdin is not None:
                process.stdin.close()
        self.active = False


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", ctypes.c_uint32),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyboardInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", ctypes.c_uint32), ("data", _InputUnion)]


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("dwTime", ctypes.c_uint32)]


class CursorBackend:
    def __init__(self):
        self.system = platform.system()
        self.available = not (self.system == "Linux" and os.environ.get("XDG_SESSION_TYPE") == "wayland")
        self._direction = 1
        self._last_position = None
        self._last_movement = time.monotonic()
        self._pyautogui = None
        if self.system == "Windows":
            self.user = ctypes.WinDLL("user32", use_last_error=True)
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.user.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            self.user.GetCursorPos.restype = wintypes.BOOL
            self.user.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
            self.user.GetLastInputInfo.restype = wintypes.BOOL
            self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
            self.user.SendInput.restype = wintypes.UINT
            self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self.user.GetAsyncKeyState.restype = ctypes.c_short
            self.kernel.GetTickCount.restype = wintypes.DWORD

    def check_safety(self):
        if self.system == "Windows":
            point = wintypes.POINT()
            if not self.user.GetCursorPos(ctypes.byref(point)):
                raise BackendError("カーソル位置を取得できません。 / Could not read cursor position.")
            if point.x == 0 and point.y == 0:
                raise BackendError("画面左上で緊急停止しました。 / Emergency stop at the top-left corner.")

    def idle_seconds(self):
        """この Windows セッションの入力待機時間。アプリの在席表示ではない。"""
        if self.system != "Windows":
            return None
        last = _LastInputInfo(ctypes.sizeof(_LastInputInfo), 0)
        if not self.user.GetLastInputInfo(ctypes.byref(last)):
            raise BackendError("入力状態を取得できません。 / Could not read input state.")
        return ((self.kernel.GetTickCount() - last.dwTime) & 0xFFFFFFFF) / 1000.0

    def pulse(self, idle_seconds: int, *, move=True) -> bool:
        if not self.available:
            raise BackendError("Wayland ではカーソル移動を利用できません。 / Cursor movement is unavailable on Wayland.")
        if self.system == "Windows":
            self.check_safety()
            if self.idle_seconds() < idle_seconds:
                return False
            if any(self.user.GetAsyncKeyState(key) & 0x8000 for key in (1, 2, 4, 5, 6)):
                return False
            event = _Input()
            event.type = 0
            event.mi = _MouseInput(self._direction if move else 0, 0, 0, 0x0001, 0, 0)
            if self.user.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input)) != 1:
                raise BackendError("カーソル移動を実行できません。 / Cursor input was rejected.")
        else:
            if not move:
                raise BackendError("移動なしの入力信号は Windows 専用です。 / Stationary input is Windows-only.")
            try:
                if self._pyautogui is None:
                    import pyautogui
                    self._pyautogui = pyautogui
                gui = self._pyautogui
                position = tuple(gui.position())
                now = time.monotonic()
                if position != self._last_position:
                    self._last_position, self._last_movement = position, now
                    return False
                if now - self._last_movement < idle_seconds:
                    return False
                width, _ = gui.size()
                delta = self._direction if 0 < position[0] + self._direction < width - 1 else -self._direction
                gui.moveTo(position[0] + delta, position[1], duration=0, _pause=False)
                self._last_position = tuple(gui.position())
                self._last_movement = now
            except Exception as exc:
                raise BackendError("カーソル移動を停止しました。 / Cursor movement stopped: " + str(exc)) from exc
        if move:
            self._direction *= -1
        return True
