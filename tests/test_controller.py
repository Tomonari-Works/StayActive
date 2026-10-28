"""OS に入力を送らず、競合・期限・失敗時の回帰を検証する。"""

from dataclasses import replace
import unittest
from unittest.mock import Mock

from PyQt6.QtWidgets import QApplication

from stayactive.controller import ActivityController
from stayactive.settings import SessionOptions

APP = QApplication.instance() or QApplication([])


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.backend = Mock(available=True, display_supported=True)
        self.cursor = Mock(available=True)
        self.cursor.pulse.return_value = True
        self.controller = ActivityController(SessionOptions(), self.backend, self.cursor, lambda: self.now)
        self.errors, self.completed = [], []
        self.controller.error.connect(self.errors.append)
        self.controller.completed.connect(lambda: self.completed.append(True))

    def tearDown(self):
        self.controller.timer.stop()

    def advance(self, seconds):
        self.now += seconds
        self.controller.tick()

    def configure(self, **changes):
        self.controller.configure(replace(self.controller.options, **changes))

    def test_start_is_idempotent(self):
        self.assertTrue(self.controller.start())
        self.assertTrue(self.controller.start())
        self.backend.start.assert_called_once_with(True)

    def test_idle_diagnostic_samples_once_per_second_and_after_input(self):
        self.cursor.system = "Windows"
        self.cursor.idle_seconds.return_value = 14.5
        self.configure(mode="cursor", interval_seconds=1)
        self.controller.start()
        self.assertEqual(self.controller.input_idle_seconds, 14.5)
        self.advance(.25)
        self.cursor.idle_seconds.assert_called_once()
        self.advance(.75)
        self.assertEqual(self.cursor.idle_seconds.call_count, 2)
        self.cursor.idle_seconds.return_value = .25
        self.advance(.25)
        self.assertEqual(self.controller.input_idle_seconds, .25)
        self.controller.stop()
        self.assertIsNone(self.controller.input_idle_seconds)

    def test_diagnostic_failure_does_not_cancel_power_request(self):
        self.cursor.system = "Windows"
        self.cursor.idle_seconds.side_effect = OSError("diagnostic unavailable")
        self.assertTrue(self.controller.start())
        self.advance(2)
        self.assertTrue(self.controller.running)
        self.assertIsNone(self.controller.input_idle_seconds)
        self.backend.stop.assert_not_called()
        self.assertFalse(self.errors)

    def test_nonfinite_diagnostics_are_not_displayed(self):
        self.cursor.system = "Windows"
        for value in (float("nan"), float("inf"), -1):
            self.cursor.idle_seconds.return_value = value
            self.controller.start()
            self.assertIsNone(self.controller.input_idle_seconds)
            self.controller.stop()

    def test_rapid_stop_start_never_creates_extra_timer(self):
        self.configure(mode="cursor", interval_seconds=1)
        for _ in range(100):
            self.controller.start()
            self.controller.stop()
        self.controller.start()
        self.advance(1)
        self.cursor.pulse.assert_called_once_with(1)
        self.assertEqual(self.controller.pulses, 1)
        self.assertTrue(self.controller.timer.isActive())

    def test_stop_prevents_late_pulse(self):
        self.configure(mode="cursor")
        self.controller.start()
        self.controller.stop()
        self.advance(100)
        self.cursor.pulse.assert_not_called()
        self.assertFalse(self.controller.timer.isActive())
        self.backend.stop.assert_called_once()

    def test_quiet_mode_never_sends_cursor_input(self):
        self.controller.start()
        self.advance(60)
        self.cursor.pulse.assert_not_called()

    def test_stationary_input_is_optional_and_windows_only(self):
        self.cursor.system = "Windows"
        self.configure(reset_idle=True)
        self.controller.start()
        self.advance(30)
        self.cursor.pulse.assert_called_once_with(30, move=False)
        self.configure(reset_idle=False)
        self.advance(30)
        self.cursor.pulse.assert_called_once()

    def test_stationary_input_is_ignored_on_other_platforms(self):
        self.cursor.system = "Darwin"
        self.configure(reset_idle=True)
        self.controller.start()
        self.advance(30)
        self.cursor.pulse.assert_not_called()

    def test_auto_stop_releases_backend_before_any_cursor_pulse(self):
        self.configure(mode="cursor", duration_minutes=1)
        self.controller.start()
        self.advance(61)
        self.assertFalse(self.controller.running)
        self.assertEqual(self.controller.reason, "completed")
        self.assertEqual(self.completed, [True])
        self.cursor.pulse.assert_not_called()
        self.backend.stop.assert_called_once()

    def test_no_duplicate_completion(self):
        self.configure(duration_minutes=1)
        self.controller.start()
        self.advance(60)
        self.advance(60)
        self.assertEqual(len(self.completed), 1)

    def test_unlimited_has_no_deadline(self):
        self.configure(duration_minutes=0)
        self.controller.start()
        self.advance(1_000_000)
        self.assertTrue(self.controller.running)
        self.assertIsNone(self.controller.remaining)

    def test_long_event_loop_delay_does_not_burst_pulses(self):
        self.configure(mode="cursor", duration_minutes=0, interval_seconds=1)
        self.controller.start()
        self.advance(10_000)
        self.cursor.pulse.assert_called_once()
        self.assertEqual(self.controller.next_pulse, self.now + 1)

    def test_interval_changes_apply_while_running(self):
        self.configure(mode="cursor")
        self.controller.start()
        self.advance(10)
        self.configure(interval_seconds=2)
        self.advance(1)
        self.cursor.pulse.assert_not_called()
        self.advance(1)
        self.cursor.pulse.assert_called_once_with(2)

    def test_mode_switch_preserves_elapsed_and_deadline(self):
        self.controller.start()
        self.advance(20)
        deadline = self.controller.deadline
        self.configure(mode="cursor")
        self.assertEqual(self.controller.elapsed, 20)
        self.assertEqual(self.controller.deadline, deadline)
        self.advance(30)
        self.cursor.pulse.assert_called_once()
        self.configure(mode="quiet")
        self.advance(30)
        self.cursor.pulse.assert_called_once()

    def test_duration_is_total_time_from_start(self):
        self.controller.start()
        self.advance(70)
        self.configure(duration_minutes=1)
        self.assertEqual(self.controller.reason, "completed")

    def test_duration_can_change_to_unlimited_and_back(self):
        self.controller.start()
        self.advance(20)
        self.configure(duration_minutes=0)
        self.assertIsNone(self.controller.remaining)
        self.configure(duration_minutes=1)
        self.assertEqual(self.controller.remaining, 40)

    def test_display_changes_update_os_request_without_restart(self):
        self.controller.start()
        self.advance(4)
        self.configure(keep_display=False)
        self.assertEqual(self.controller.elapsed, 4)
        self.assertEqual(self.backend.start.call_args.args, (False,))
        self.backend.stop.assert_not_called()

    def test_backend_start_failure_is_not_reported_as_active(self):
        self.backend.start.side_effect = RuntimeError("denied")
        with self.assertLogs("stayactive", level="ERROR"):
            self.assertFalse(self.controller.start())
        self.assertFalse(self.controller.running)
        self.assertEqual(self.controller.reason, "error")
        self.assertEqual(self.errors, ["denied"])
        self.backend.stop.assert_called_once()

    def test_cursor_failure_releases_os_request(self):
        self.configure(mode="cursor")
        self.cursor.pulse.side_effect = RuntimeError("input denied")
        self.controller.start()
        with self.assertLogs("stayactive", level="ERROR"):
            self.advance(30)
        self.assertFalse(self.controller.running)
        self.backend.stop.assert_called_once()
        self.assertEqual(self.errors, ["input denied"])

    def test_backend_exit_is_detected(self):
        self.controller.start()
        self.backend.check.side_effect = RuntimeError("exited")
        with self.assertLogs("stayactive", level="ERROR"):
            self.advance(1)
        self.assertFalse(self.controller.running)
        self.assertEqual(self.errors, ["exited"])

    def test_emergency_stop_does_not_wait_for_cursor_interval(self):
        self.configure(mode="cursor", interval_seconds=300)
        self.controller.start()
        self.cursor.check_safety.side_effect = RuntimeError("emergency stop")
        with self.assertLogs("stayactive", level="ERROR"):
            self.advance(0.25)
        self.assertFalse(self.controller.running)
        self.cursor.pulse.assert_not_called()
        self.backend.stop.assert_called_once()

    def test_release_failure_is_visible_and_not_successful_completion(self):
        self.configure(duration_minutes=1)
        self.controller.start()
        self.backend.stop.side_effect = RuntimeError("release failed")
        with self.assertLogs("stayactive", level="ERROR"):
            self.advance(60)
        self.assertEqual(self.controller.reason, "error")
        self.assertEqual(self.errors, ["release failed"])
        self.assertEqual(self.completed, [])

    def test_idle_skip_does_not_increment_count(self):
        self.configure(mode="cursor")
        self.cursor.pulse.return_value = False
        self.controller.start()
        self.advance(30)
        self.assertEqual(self.controller.pulses, 0)

    def test_restart_resets_session(self):
        self.controller.start()
        self.advance(40)
        self.controller.stop()
        self.controller.start()
        self.assertEqual(self.controller.elapsed, 0)
        self.assertEqual(self.controller.remaining, 3600)

    def test_unavailable_mode_fails_cleanly(self):
        self.backend.available = False
        with self.assertLogs("stayactive", level="ERROR"):
            self.assertFalse(self.controller.start())
        self.backend.start.assert_not_called()
        self.assertTrue(self.errors)


if __name__ == "__main__":
    unittest.main()
