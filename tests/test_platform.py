"""OS API の構造、解除、排他を実入力なしで検証する。"""

import ctypes
from pathlib import Path
import platform
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication

from stayactive.backends import BackendError, CursorBackend, KeepAwakeBackend, _Input
from stayactive.instance import SingleInstance
from stayactive.hotkey import Hotkey

APP = QApplication.instance() or QApplication([])


class InstanceTests(unittest.TestCase):
    def test_stale_lock_is_recovered_after_process_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = str(Path(directory) / "instance.lock")
            script = "import os,sys; from PyQt6.QtCore import QLockFile; lock=QLockFile(sys.argv[1]); os._exit(0 if lock.tryLock(0) else 1)"
            result = subprocess.run([sys.executable, "-c", script, lock_path], timeout=15, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(Path(lock_path).exists())
            instance = SingleInstance(Path(directory))
            try:
                self.assertTrue(instance.acquire())
            finally:
                instance.close()

    def test_exclusive_lock_and_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = SingleInstance(Path(directory)), SingleInstance(Path(directory))
            activated = []
            first.activated.connect(lambda: activated.append(True))
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                self.assertTrue(second.activate_existing())
                APP.processEvents()
                self.assertEqual(activated, [True])
                # ロックを持たないインスタンスの終了で、既存ロックを消してはいけない。
                second.close()
                self.assertFalse(second.acquire())
                first.close()
                self.assertTrue(second.acquire())
            finally:
                first.close()
                second.close()


@unittest.skipUnless(platform.system() == "Windows", "Windows API tests")
class WindowsTests(unittest.TestCase):
    def test_native_hotkey_dispatch_and_cleanup(self):
        from ctypes import wintypes
        from PyQt6.QtWidgets import QWidget
        user = Mock()
        user.RegisterHotKey.return_value = True
        window = QWidget()
        with patch("stayactive.hotkey.ctypes.WinDLL", return_value=user):
            hotkey = Hotkey(window)
        events = []
        hotkey.activated.connect(lambda: events.append(True))
        message = wintypes.MSG()
        message.message, message.wParam = 0x0312, Hotkey.ID
        self.assertEqual(hotkey.filter.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message)), (True, 0))
        self.assertEqual(events, [True])
        hotkey.close()
        hotkey.close()
        user.UnregisterHotKey.assert_called_once_with(None, Hotkey.ID)

    def test_hotkey_conflict_falls_back_to_window_shortcut(self):
        from PyQt6.QtWidgets import QWidget
        user = Mock()
        user.RegisterHotKey.return_value = False
        window = QWidget()
        with patch("stayactive.hotkey.ctypes.WinDLL", return_value=user):
            hotkey = Hotkey(window)
        self.assertFalse(hotkey.registered)
        self.assertIsNotNone(hotkey.shortcut)
        hotkey.close()
        self.assertFalse(hotkey.shortcut.isEnabled())
        user.UnregisterHotKey.assert_not_called()

    def test_sendinput_structure_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(_Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)

    def test_power_flags_and_release(self):
        backend = KeepAwakeBackend()
        backend.kernel = Mock()
        backend.kernel.SetThreadExecutionState.return_value = 0x80000000
        backend.start(True)
        backend.start(False)
        backend.stop()
        self.assertEqual([c.args[0] for c in backend.kernel.SetThreadExecutionState.call_args_list],
                         [0x80000003, 0x80000001, 0x80000000])
        self.assertFalse(backend.active)

    def test_power_failure_is_checked(self):
        backend = KeepAwakeBackend()
        backend.kernel = Mock()
        backend.kernel.SetThreadExecutionState.return_value = 0
        with self.assertRaises(BackendError):
            backend.start(True)
        self.assertFalse(backend.active)

    def make_cursor(self):
        cursor = CursorBackend()
        cursor.user, cursor.kernel = Mock(), Mock()
        cursor.user.GetAsyncKeyState.return_value = 0
        cursor.user.SendInput.return_value = 1
        cursor.kernel.GetTickCount.return_value = 100_000

        def get_last(pointer):
            pointer._obj.dwTime = 0
            return True

        def position(pointer):
            pointer._obj.x, pointer._obj.y = 100, 100
            return True

        cursor.user.GetLastInputInfo.side_effect = get_last
        cursor.user.GetCursorPos.side_effect = position
        return cursor

    def test_cursor_waits_for_idle(self):
        cursor = self.make_cursor()
        cursor.kernel.GetTickCount.return_value = 1000
        self.assertFalse(cursor.pulse(30))
        cursor.user.SendInput.assert_not_called()

    def test_cursor_waits_for_drag(self):
        cursor = self.make_cursor()
        cursor.user.GetAsyncKeyState.return_value = -32768
        self.assertFalse(cursor.pulse(30))
        cursor.user.SendInput.assert_not_called()

    def test_cursor_alternates_relative_direction(self):
        cursor = self.make_cursor()
        directions = []
        cursor.user.SendInput.side_effect = lambda n, ptr, size: directions.append(ptr._obj.mi.dx) or 1
        self.assertTrue(cursor.pulse(30))
        self.assertTrue(cursor.pulse(30))
        self.assertEqual(directions, [1, -1])

    def test_stationary_input_does_not_move_or_change_direction(self):
        cursor = self.make_cursor()
        deltas = []
        cursor.user.SendInput.side_effect = lambda n, ptr, size: deltas.append((ptr._obj.mi.dx, ptr._obj.mi.dy)) or 1
        self.assertTrue(cursor.pulse(30, move=False))
        self.assertEqual(deltas, [(0, 0)])
        self.assertEqual(cursor._direction, 1)

    def test_cursor_emergency_stop(self):
        cursor = self.make_cursor()
        cursor.user.GetCursorPos.side_effect = lambda ptr: True
        with self.assertRaises(BackendError):
            cursor.pulse(30)
        cursor.user.SendInput.assert_not_called()

    def test_cursor_input_failure_is_checked(self):
        cursor = self.make_cursor()
        cursor.user.SendInput.return_value = 0
        with self.assertRaises(BackendError):
            cursor.pulse(30)


class ProcessBackendTests(unittest.TestCase):
    def test_mac_uses_one_owned_process_instead_of_repeated_spawns(self):
        with patch("stayactive.backends.platform.system", return_value="Darwin"), \
                patch("stayactive.backends.shutil.which", return_value="/usr/bin/caffeinate"), \
                patch("stayactive.backends.subprocess.Popen") as popen:
            process = popen.return_value
            process.poll.return_value = None
            backend = KeepAwakeBackend()
            backend.start(True)
            for _ in range(100):
                backend.check()
            popen.assert_called_once()
            self.assertIn("-w", popen.call_args.args[0])
            backend.stop()
            process.terminate.assert_called_once()

    def test_inhibitor_exit_reports_failure(self):
        with patch("stayactive.backends.platform.system", return_value="Linux"), \
                patch("stayactive.backends.shutil.which", return_value="/usr/bin/systemd-inhibit"), \
                patch("stayactive.backends.subprocess.Popen") as popen:
            popen.return_value.poll.return_value = 1
            backend = KeepAwakeBackend()
            backend.start(False)
            with self.assertRaises(BackendError):
                backend.check()
            backend.stop()


if __name__ == "__main__":
    unittest.main()
