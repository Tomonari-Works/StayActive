"""設定破損、言語切替、終了処理と小さい画面の回帰テスト。"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from stayactive.controller import ActivityController
from stayactive.i18n import TEXT
from stayactive.settings import SessionOptions, SettingsStore
from stayactive.ui import StayActiveApp

APP = QApplication.instance() or QApplication([])
APP.setStyle("Fusion")


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "settings.ini"

    def tearDown(self):
        self.directory.cleanup()

    def test_round_trip(self):
        store = SettingsStore(self.path)
        options = SessionOptions("cursor", 4, 120, False, True)
        store.save(options, "en", "light", True)
        self.assertEqual(SettingsStore(self.path).load(), (options, "en", "light", True))

    def test_corrupt_settings_are_validated(self):
        self.path.write_text("[session]\ninterval=oops\nduration=-200\nmode=unexpected\ndisplay=what\n[appearance]\nlanguage=unknown\ntheme=bad\n", encoding="utf-8")
        options, language, theme, close = SettingsStore(self.path).load()
        self.assertEqual(options.interval_seconds, 30)
        self.assertEqual(options.duration_minutes, 0)
        self.assertEqual(options.mode, "quiet")
        self.assertTrue(options.keep_display)
        self.assertIn(language, ("ja", "en"))
        self.assertEqual(theme, "dark")
        self.assertFalse(close)

    def test_validation_clamps_bounds(self):
        options = SessionOptions("x", 99999, "bad", "false").validated()
        self.assertEqual(options, SessionOptions("quiet", 300, 60, False))
        self.assertEqual(SessionOptions(interval_seconds=-1, duration_minutes=99999).validated().interval_seconds, 1)
        self.assertEqual(SessionOptions(duration_minutes=99999).validated().duration_minutes, 1440)

    def test_translation_keys_match(self):
        self.assertEqual(set(TEXT["ja"]), set(TEXT["en"]))


class UITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = SettingsStore(Path(self.directory.name) / "settings.ini")
        self.backend = Mock(available=True, display_supported=True)
        self.cursor = Mock(available=True, system="Windows")
        self.controller = ActivityController(backend=self.backend, cursor=self.cursor, clock=lambda: 100)
        self.window = StayActiveApp(self.store, self.controller, integrations=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        APP.processEvents()
        self.directory.cleanup()

    def test_language_switch_preserves_active_mode_and_time(self):
        self.window.cursor_card.click()
        self.window.duration_spin.setValue(120)
        self.window.start_button.click()
        self.window.language_combo.setCurrentIndex(1)
        self.assertEqual(self.controller.options.mode, "cursor")
        self.assertEqual(self.controller.options.duration_minutes, 120)
        self.assertTrue(self.controller.running)
        self.assertTrue(self.window.cursor_card.isChecked())
        self.assertIn("Stop", self.window.start_button.text())
        self.backend.start.assert_called_once()

    def test_quick_start_applies_complete_profile_and_starts_once(self):
        self.window.quick_start_button.click()
        self.assertEqual(self.controller.options, SessionOptions("cursor", 30, 0, True, False))
        self.assertTrue(self.controller.running)
        self.assertTrue(self.window.cursor_card.isChecked())
        self.assertEqual(self.window.duration_spin.value(), 0)
        self.assertEqual(self.window.interval_spin.value(), 30)
        self.window.quick_start_button.click()
        self.backend.start.assert_called_once_with(True)
        self.cursor.pulse.assert_not_called()

    def test_quick_start_switches_expiring_session_atomically(self):
        self.window.duration_spin.setValue(1)
        self.controller.clock = lambda: 100
        self.controller.start()
        self.controller.clock = lambda: 161
        self.window.quick_start_button.click()
        self.assertTrue(self.controller.running)
        self.assertIsNone(self.controller.deadline)
        self.assertEqual(self.controller.started_at, 100)
        self.backend.stop.assert_not_called()

    def test_input_diagnostic_is_localized_and_cleared_on_stop(self):
        self.cursor.idle_seconds.return_value = 17.5
        self.controller.start()
        self.assertIn("17", self.window.input_status.text())
        self.window.language_combo.setCurrentIndex(1)
        self.assertIn("Windows input idle", self.window.input_status.text())
        self.controller.stop()
        self.assertIn("Measured after start", self.window.input_status.text())

    def test_quick_start_is_unavailable_without_os_inhibition(self):
        self.window.quick_available = False
        self.window.quick_start()
        self.assertFalse(self.controller.running)
        self.backend.start.assert_not_called()
        self.backend.available = False
        self.window.cursor_card.click()
        self.controller.start()
        self.assertIn("OS 抑止なし", self.window.status.text())

    def test_button_stops_and_escape_stops(self):
        self.window.start_button.click()
        self.window.start_button.click()
        self.assertFalse(self.controller.running)
        self.window.start_button.click()
        self.window.activateWindow()
        QTest.qWait(30)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertFalse(self.controller.running)

    def test_presets_and_custom_duration_stay_in_sync(self):
        self.window.preset_group.button(30).click()
        self.assertEqual(self.controller.options.duration_minutes, 30)
        self.window.duration_spin.setValue(45)
        self.assertFalse(any(button.isChecked() for button in self.window.preset_group.buttons()))
        self.window.preset_group.button(0).click()
        self.assertEqual(self.controller.options.duration_minutes, 0)
        self.assertEqual(self.window.ring.value.text(), "∞")

    def test_interval_only_enabled_for_cursor(self):
        self.assertFalse(self.window.interval_spin.isEnabled())
        self.window.cursor_card.click()
        self.assertTrue(self.window.interval_spin.isEnabled())
        self.window.interval_spin.setValue(4)
        self.assertEqual(self.controller.options.interval_seconds, 4)

    def test_idle_signal_option_controls_interval_in_quiet_mode(self):
        self.assertTrue(self.window.idle_checkbox.isEnabled())
        self.window.idle_checkbox.click()
        self.assertTrue(self.controller.options.reset_idle)
        self.assertTrue(self.window.interval_spin.isEnabled())
        self.window.cursor_card.click()
        self.assertFalse(self.window.idle_checkbox.isEnabled())

    def test_error_is_visible_and_start_recovers(self):
        self.window.show_error("test error")
        self.assertFalse(self.window.alert.isHidden())
        self.window.start_button.click()
        self.assertTrue(self.window.alert.isHidden())

    def test_theme_language_and_preferences_persist(self):
        self.window.toggle_theme()
        self.window.language_combo.setCurrentIndex(1)
        self.window.duration_spin.setValue(42)
        self.window.shutdown()
        options, language, theme, close = self.store.load()
        self.assertEqual(options.duration_minutes, 42)
        self.assertEqual((language, theme), ("en", "light"))
        self.assertFalse(close)

    def test_shutdown_is_idempotent_and_releases_resources(self):
        self.controller.start()
        self.window.shutdown()
        self.window.shutdown()
        self.assertFalse(self.controller.running)
        self.backend.stop.assert_called_once()
        self.assertFalse(self.window.save_timer.isActive())

    def test_small_window_scrolls_without_horizontal_overflow(self):
        self.window.resize(560, 540)
        APP.processEvents()
        self.assertEqual(self.window.scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreater(self.window.scroll.verticalScrollBar().maximum(), 0)

    def test_wide_window_fits_without_scroll(self):
        self.window.resize(1000, 612)
        APP.processEvents()
        self.assertEqual(self.window.scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.window.scroll.horizontalScrollBar().maximum(), 0)

    def test_completed_session_shows_zero_remaining(self):
        self.controller.start()
        self.controller.stop("completed")
        self.assertEqual(self.window.ring.value.text(), "00:00")
        self.window.duration_spin.setValue(120)
        self.assertEqual(self.window.ring.value.text(), "02:00:00")


if __name__ == "__main__":
    unittest.main()
