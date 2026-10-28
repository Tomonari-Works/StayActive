"""ネイティブな操作性とアクセシビリティを保ったデスクトップ UI。"""

from datetime import datetime, timedelta
import math
from pathlib import Path

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QBoxLayout, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QMenu, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import __version__
from .controller import ActivityController
from .hotkey import Hotkey
from .i18n import TEXT
from .settings import SessionOptions, SettingsStore

PALETTES = {
    "dark": dict(bg="#0e141e", panel="#161f2d", elevated="#1c2838", border="#2b394c",
                 text="#f0f5fb", muted="#a5b4c8", accent="#8ce8c3", tint="#203c38", ink="#102a22",
                 track="#2a3948", error="#ffb6ad", errorbg="#3b272b", hover="#26384a"),
    "light": dict(bg="#f1f5f6", panel="#ffffff", elevated="#edf3f5", border="#ccd8dd",
                  text="#172c38", muted="#526b7b", accent="#12765a", tint="#e1f3eb", ink="#ffffff",
                  track="#d9e7e3", error="#a22c27", errorbg="#fff0ed", hover="#e2ecef"),
}


def app_icon(running=False) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#8ce8c3" if running else "#233d41"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * .28, size * .28)
        painter.setPen(QPen(QColor("#102a22" if running else "#a2edcf"), size * .075,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(size * .25, size * .25, size * .5, size * .5), 135 * 16, 270 * 16)
        painter.drawLine(QPointF(size * .5, size * .18), QPointF(size * .5, size * .48))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def clock_text(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def label(text="", name="", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class SessionRing(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(136, 136)
        self.palette_colors = PALETTES["dark"]
        self.progress, self.running = 1.0, False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 36, 9, 34)
        layout.setSpacing(5)
        self.value = label("60:00", "ringValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption = label("", "ringCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value)
        layout.addWidget(self.caption)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(8, 8, self.width() - 16, self.height() - 16)
        painter.setPen(QPen(QColor(self.palette_colors["track"]), 5))
        painter.drawEllipse(rect)
        pen = QPen(QColor(self.palette_colors["accent"]), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        if not self.running:
            color = pen.color()
            color.setAlpha(130)
            pen.setColor(color)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -round(360 * 16 * self.progress))


class ModeCard(QPushButton):
    def __init__(self, symbol):
        super().__init__()
        self.setObjectName("modeCard")
        self.setCheckable(True)
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 13)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.symbol = label(symbol, "modeSymbol")
        self.tag = label("", "modeTag")
        top.addWidget(self.symbol)
        top.addStretch()
        top.addWidget(self.tag)
        self.title = label("", "modeTitle")
        self.description = label("", "muted", True)
        layout.addLayout(top)
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_text(self, title, description, selected):
        self.title.setText(title)
        self.description.setText(description)
        self.tag.setText(selected)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)


class StayActiveApp(QWidget):
    def __init__(self, store: SettingsStore, controller=None, integrations=True):
        super().__init__()
        self.store = store
        options, self.language, self.theme, close_to_tray = store.load()
        self.controller = controller if controller is not None else ActivityController(options, parent=self)
        if not self.controller.backend.available and self.controller.cursor.available:
            options = SessionOptions("cursor", options.interval_seconds, options.duration_minutes, options.keep_display, options.reset_idle)
            self.controller.configure(options)
        self._closed = False
        self._tray_notified = False
        self._last_visual_state = None
        self._last_tooltip = ""
        self.setWindowTitle("StayActive")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(560, 540)
        self.resize(1000, 700)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self.save_settings)
        self.tray_available = integrations and QSystemTrayIcon.isSystemTrayAvailable()
        self._build_ui(options, close_to_tray)
        self._build_tray(integrations)
        self.hotkey = Hotkey(self, enabled=integrations)
        self.hotkey.activated.connect(self.toggle_session)
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self.stop_session)
        self.controller.changed.connect(self.render_state)
        self.controller.error.connect(self.show_error)
        self.controller.completed.connect(self.session_completed)
        self.translate()
        self.apply_theme()
        self.render_state()
        self._restore_geometry()
        if not self.controller.backend.available:
            self.show_error(self.tr("cursor_only") if self.controller.cursor.available else self.tr("no_backend"))

    def tr(self, key):
        return TEXT[self.language][key]

    def _build_ui(self, options, close_to_tray):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(24, 20, 24, 14)
        body.setSpacing(14)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(42, 42))
        brand = QVBoxLayout()
        brand.setSpacing(1)
        brand.addWidget(label("StayActive", "brand"))
        self.tagline = label("", "muted")
        brand.addWidget(self.tagline)
        header.addWidget(logo)
        header.addSpacing(3)
        header.addLayout(brand)
        header.addStretch()
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("smallButton")
        self.theme_button.setFixedSize(38, 34)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.addItem("日本語", "ja")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(0 if self.language == "ja" else 1)
        self.language_combo.currentIndexChanged.connect(self.change_language)
        header.addWidget(self.theme_button)
        header.addWidget(self.language_combo)
        body.addLayout(header)

        self.dashboard = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.dashboard.setSpacing(16)
        body.addLayout(self.dashboard)
        self.config_widget = QWidget()
        configuration = QVBoxLayout(self.config_widget)
        configuration.setContentsMargins(0, 0, 0, 0)
        configuration.setSpacing(12)

        self.hero = QFrame()
        self.hero.setObjectName("hero")
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(22, 20, 22, 18)
        hero_layout.setSpacing(15)
        overview = QHBoxLayout()
        overview.setSpacing(12)
        intro = QVBoxLayout()
        intro.setSpacing(10)
        self.status = label("", "status")
        self.headline = label("", "headline", True)
        self.hero_hint = label("", "muted", True)
        intro.addWidget(self.status)
        intro.addWidget(self.headline)
        intro.addWidget(self.hero_hint)
        intro.addStretch()
        overview.addLayout(intro, 1)
        self.ring = SessionRing()
        overview.addWidget(self.ring)
        hero_layout.addLayout(overview)
        self.start_button = QPushButton()
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(49)
        self.start_button.clicked.connect(self.toggle_session)
        hero_layout.addWidget(self.start_button)
        metrics = QHBoxLayout()
        self.metric_captions, self.metric_values = [], []
        for index in range(3):
            cell = QVBoxLayout()
            cell.setSpacing(4)
            caption, value = label("", "muted"), label("", "metric")
            self.metric_captions.append(caption)
            self.metric_values.append(value)
            cell.addWidget(caption)
            cell.addWidget(value)
            metrics.addLayout(cell, 1)
            if index < 2:
                line = QFrame()
                line.setObjectName("divider")
                line.setFixedWidth(1)
                metrics.addWidget(line)
                metrics.addSpacing(15)
        hero_layout.addLayout(metrics)
        self.dashboard.addWidget(self.hero, 1)

        self.alert = QFrame()
        self.alert.setObjectName("alert")
        alert_layout = QHBoxLayout(self.alert)
        self.alert_text = label("", "alertText", True)
        self.dismiss_button = QPushButton("×")
        self.dismiss_button.setFixedSize(28, 28)
        self.dismiss_button.clicked.connect(self.alert.hide)
        alert_layout.addWidget(self.alert_text, 1)
        alert_layout.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignTop)
        self.alert.hide()
        body.insertWidget(1, self.alert)

        mode_heading = QHBoxLayout()
        self.mode_heading = label("", "section")
        self.mode_hint = label("", "muted")
        mode_heading.addWidget(self.mode_heading)
        mode_heading.addStretch()
        mode_heading.addWidget(self.mode_hint)
        configuration.addLayout(mode_heading)
        modes = QHBoxLayout()
        modes.setSpacing(12)
        self.quiet_card, self.cursor_card = ModeCard("◌"), ModeCard("↗")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.quiet_card, 0)
        self.mode_group.addButton(self.cursor_card, 1)
        self.quiet_card.setEnabled(self.controller.backend.available)
        self.cursor_card.setEnabled(self.controller.cursor.available)
        (self.quiet_card if options.mode == "quiet" else self.cursor_card).setChecked(True)
        self.mode_group.idClicked.connect(self.options_changed)
        modes.addWidget(self.quiet_card)
        modes.addWidget(self.cursor_card)
        configuration.addLayout(modes)

        self.preferences = QFrame()
        self.preferences.setObjectName("panel")
        form = QVBoxLayout(self.preferences)
        form.setContentsMargins(16, 15, 16, 15)
        form.setSpacing(10)
        settings_header = QHBoxLayout()
        self.settings_heading, self.live_hint = label("", "section"), label("", "muted")
        settings_header.addWidget(self.settings_heading)
        settings_header.addStretch()
        settings_header.addWidget(self.live_hint)
        form.addLayout(settings_header)
        self.duration_label, self.duration_hint = label("", "fieldLabel"), label("", "muted", True)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 1440)
        self.duration_spin.setSingleStep(5)
        self.duration_spin.setValue(options.duration_minutes)
        self.duration_spin.setKeyboardTracking(False)
        self.duration_spin.setMinimumWidth(120)
        self.duration_label.setBuddy(self.duration_spin)
        form.addLayout(self._field_row(self.duration_label, self.duration_hint, self.duration_spin))
        presets = QHBoxLayout()
        presets.setSpacing(6)
        self.preset_group = QButtonGroup(self)
        for minutes in (30, 60, 120, 0):
            button = QPushButton()
            button.setObjectName("preset")
            button.setCheckable(True)
            button.setMinimumHeight(31)
            self.preset_group.addButton(button, minutes)
            button.clicked.connect(lambda checked=False, value=minutes: self.duration_spin.setValue(value))
            presets.addWidget(button)
        form.addLayout(presets)
        self.interval_label, self.interval_hint = label("", "fieldLabel"), label("", "muted", True)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 300)
        self.interval_spin.setValue(options.interval_seconds)
        self.interval_spin.setKeyboardTracking(False)
        self.interval_spin.setMinimumWidth(120)
        self.interval_label.setBuddy(self.interval_spin)
        form.addLayout(self._field_row(self.interval_label, self.interval_hint, self.interval_spin))
        self.idle_checkbox = QCheckBox()
        self.idle_checkbox.setChecked(options.reset_idle)
        self.idle_checkbox.toggled.connect(self.options_changed)
        form.addWidget(self.idle_checkbox)
        self.display_checkbox = QCheckBox()
        self.display_checkbox.setChecked(options.keep_display)
        self.display_checkbox.setEnabled(self.controller.backend.available and self.controller.backend.display_supported)
        self.display_hint = label("", "muted", True)
        form.addWidget(self.display_checkbox)
        # 詳細はツールチップに置き、狭い画面でも主操作に届く高さを優先する。
        self.display_hint.hide()
        self.duration_spin.valueChanged.connect(self.options_changed)
        self.interval_spin.valueChanged.connect(self.options_changed)
        self.display_checkbox.toggled.connect(self.options_changed)
        configuration.addWidget(self.preferences)
        self.dashboard.addWidget(self.config_widget, 1)

        self.close_checkbox = QCheckBox()
        self.close_checkbox.setChecked(close_to_tray and self.tray_available)
        self.close_checkbox.setEnabled(self.tray_available)
        self.close_checkbox.toggled.connect(self.queue_save)
        footer_frame = QFrame()
        footer_frame.setObjectName("footer")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(24, 10, 24, 12)
        footer_layout.setSpacing(8)
        footer = QHBoxLayout()
        key_column = QVBoxLayout()
        key_column.setSpacing(3)
        key_column.addWidget(label("Ctrl + Alt + J", "keycap"))
        self.hotkey_hint = label("", "muted", True)
        key_column.addWidget(self.hotkey_hint)
        key_column.addWidget(self.close_checkbox)
        footer.addLayout(key_column, 1)
        self.minimize_button, self.quit_button = QPushButton(), QPushButton()
        self.minimize_button.clicked.connect(self.minimize)
        self.quit_button.clicked.connect(self.quit_app)
        footer.addWidget(self.minimize_button)
        footer.addWidget(self.quit_button)
        footer_layout.addLayout(footer)
        self.note = label("", "footnote", True)
        footer_layout.addWidget(self.note)
        outer.addWidget(footer_frame)
        body.addStretch()
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _field_row(title, hint, control):
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(title)
        text.addWidget(hint)
        row.addLayout(text, 1)
        row.addSpacing(10)
        row.addWidget(control)
        return row

    def _build_tray(self, integrations):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray_menu = QMenu(self)
        self.show_action, self.toggle_action, self.quit_action = QAction(self), QAction(self), QAction(self)
        self.show_action.triggered.connect(self.restore_window)
        self.toggle_action.triggered.connect(self.toggle_session)
        self.quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(self.show_action)
        self.tray_menu.addAction(self.toggle_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        if self.tray_available:
            self.tray.show()

    def translate(self):
        self.tagline.setText(self.tr("tagline"))
        self.language_combo.setAccessibleName(self.tr("language"))
        self.language_combo.setToolTip(self.tr("language"))
        self.mode_heading.setText(self.tr("mode_section"))
        self.mode_hint.setText(self.tr("mode_hint"))
        self.settings_heading.setText(self.tr("preferences"))
        self.live_hint.setText(self.tr("live"))
        self.duration_label.setText(self.tr("duration"))
        self.duration_hint.setText(self.tr("duration_hint"))
        self.duration_spin.setSuffix(self.tr("minutes"))
        self.duration_spin.setSpecialValueText(self.tr("unlimited"))
        self.duration_spin.setAccessibleName(self.tr("duration"))
        self.duration_spin.setToolTip(self.tr("duration_hint"))
        self.interval_label.setText(self.tr("interval"))
        self.interval_hint.setText(self.tr("interval_hint"))
        self.interval_spin.setSuffix(self.tr("seconds"))
        self.interval_spin.setAccessibleName(self.tr("interval"))
        self.interval_spin.setToolTip(self.tr("interval_hint"))
        self.display_checkbox.setText(self.tr("display"))
        self.idle_checkbox.setText(self.tr("reset_idle"))
        self.idle_checkbox.setToolTip(self.tr("reset_idle_hint"))
        self.display_hint.setText(self.tr("display_hint") if self.display_checkbox.isEnabled() else self.tr("display_unavailable"))
        self.display_checkbox.setToolTip(self.display_hint.text())
        self.close_checkbox.setText(self.tr("close_to_tray"))
        self.close_checkbox.setToolTip(self.tr("close_hint"))
        self.hotkey_hint.setText(self.tr("hotkey_global" if self.hotkey.registered else "hotkey_local"))
        self.minimize_button.setText(self.tr("minimize" if self.tray_available else "minimize_window"))
        self.quit_button.setText(self.tr("quit"))
        self.quit_button.setToolTip(self.tr("quit_hint"))
        self.show_action.setText(self.tr("show"))
        self.quit_action.setText(self.tr("quit"))
        self.note.setText(self.tr("note") + "   ·   v" + __version__)
        self.dismiss_button.setAccessibleName(self.tr("dismiss"))
        for caption, key in zip(self.metric_captions, ("elapsed", "end_time", "movements")):
            caption.setText(self.tr(key))
        for button in self.preset_group.buttons():
            minutes = self.preset_group.id(button)
            button.setText(str(minutes) + self.tr("minutes") if minutes else self.tr("unlimited"))
        self._theme_button_text()
        self.render_state()

    def render_state(self):
        controller = self.controller
        running = controller.running
        reason = "running" if running else controller.reason
        self.status.setText("●  " + self.tr(reason))
        self.status.setProperty("error", reason == "error")
        headline = "hero_running" if running else "hero_error" if reason == "error" else "hero_done" if reason == "completed" else "hero_ready"
        hint = "running_hint" if running else "error_hint" if reason == "error" else "done_hint" if reason in ("completed", "stopped") else "ready_hint"
        self.headline.setText(self.tr(headline))
        self.hero_hint.setText(self.tr(hint))
        self.start_button.setText(("■   " if running else "▶   ") + self.tr("stop" if running else "restart" if reason == "completed" else "start"))
        self.start_button.setAccessibleName(self.tr("stop" if running else "start"))
        self.start_button.setToolTip("Ctrl+Alt+J  ·  " + self.tr("escape"))
        self.start_button.setEnabled(controller.backend.available or controller.cursor.available)
        self.toggle_action.setText(self.tr("stop" if running else "start"))
        duration = controller.options.duration_minutes * 60
        remaining = controller.remaining if running else 0 if reason == "completed" else duration
        self.ring.value.setText(clock_text(math.ceil(remaining)) if duration else "∞")
        self.ring.caption.setText(self.tr("remaining" if duration else "unlimited"))
        self.ring.running = running
        self.ring.progress = min(1.0, max(0.0, remaining / duration)) if duration else 1.0
        self.ring.setAccessibleName(self.tr("remaining") + ": " + self.ring.value.text())
        self.ring.update()
        self.metric_values[0].setText(clock_text(controller.elapsed))
        self.metric_values[1].setText((datetime.now() + timedelta(seconds=controller.remaining)).strftime("%H:%M") if running and controller.remaining is not None else "—")
        self.metric_values[2].setText(str(controller.pulses) + self.tr("times"))
        self.interval_spin.setEnabled(controller.options.mode == "cursor" or controller.stationary_input)
        self.idle_checkbox.setEnabled(controller.options.mode == "quiet" and controller.cursor.available and controller.cursor.system == "Windows")
        self.metric_captions[2].setText(self.tr("signals" if controller.stationary_input else "movements"))
        self.preset_group.setExclusive(False)
        for button in self.preset_group.buttons():
            button.setChecked(self.preset_group.id(button) == controller.options.duration_minutes)
        self.preset_group.setExclusive(True)
        for card, mode in ((self.quiet_card, "quiet"), (self.cursor_card, "cursor")):
            description = mode + "_desc"
            if mode == "cursor" and self.controller.cursor.system != "Windows":
                description = "cursor_desc_portable"
            if mode == "quiet" and controller.stationary_input:
                description = "quiet_desc_input"
            card.set_text(self.tr(mode), self.tr(description),
                self.tr("unavailable") if not card.isEnabled() else "✓ " + self.tr("selected") if card.isChecked() else "")
        visual_state = (running, reason == "error")
        if self._last_visual_state != visual_state:
            self._last_visual_state = visual_state
            self.tray.setIcon(app_icon(running))
            self.setWindowIcon(app_icon(running))
            self.status.setProperty("active", running)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        tooltip = "StayActive · " + self.tr(reason)
        if running and controller.remaining is not None:
            tooltip += " · " + clock_text(math.ceil(controller.remaining))
        if tooltip != self._last_tooltip:
            self.tray.setToolTip(tooltip)
            self._last_tooltip = tooltip

    def options_changed(self, *_):
        options = SessionOptions("quiet" if self.quiet_card.isChecked() else "cursor",
            self.interval_spin.value(), self.duration_spin.value(), self.display_checkbox.isChecked(), self.idle_checkbox.isChecked())
        self.controller.configure(options)
        self.render_state()
        self.queue_save()

    def toggle_session(self):
        if not self.controller.running:
            self.alert.hide()
        self.controller.toggle()

    def stop_session(self):
        if self.controller.running:
            self.controller.stop()

    def change_language(self, *_):
        self.language = self.language_combo.currentData()
        self.translate()
        self.queue_save()

    def _theme_button_text(self):
        self.theme_button.setText("☼" if self.theme == "dark" else "◐")
        text = self.tr("theme_light" if self.theme == "dark" else "theme_dark")
        self.theme_button.setToolTip(text)
        self.theme_button.setAccessibleName(text)

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.apply_theme()
        self._theme_button_text()
        self.queue_save()

    def apply_theme(self):
        c = PALETTES[self.theme]
        assets = Path(__file__).with_name("assets").as_posix()
        arrow_down = f'{assets}/arrow-down-{self.theme}.svg'
        arrow_up = f'{assets}/arrow-up-{self.theme}.svg'
        check = f'{assets}/check-{self.theme}.svg'
        self.ring.palette_colors = c
        self.ring.update()
        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Yu Gothic UI', 'Segoe UI', sans-serif; font-size: 13px; color: {c['text']}; }}
            StayActiveApp, QScrollArea, QWidget#content, QFrame#footer {{ background: {c['bg']}; }}
            QFrame#footer {{ border-top: 1px solid {c['border']}; }}
            QLabel {{ background: transparent; border: none; }}
            QLabel#brand {{ font-size: 23px; font-weight: 700; letter-spacing: -0.5px; }}
            QLabel#muted {{ color: {c['muted']}; font-size: 11px; }}
            QLabel#footnote {{ color: {c['muted']}; font-size: 10px; }}
            QLabel#section {{ font-size: 11px; font-weight: 700; letter-spacing: 0.8px; color: {c['muted']}; }}
            QFrame#hero, QFrame#panel {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px; }}
            QFrame#hero {{ border-top: 2px solid {c['accent']}; }}
            QLabel#status {{ color: {c['muted']}; font-size: 10px; font-weight: 700; letter-spacing: 0.7px; }}
            QLabel#status[active="true"] {{ color: {c['accent']}; }}
            QLabel#status[error="true"] {{ color: {c['error']}; }}
            QLabel#headline {{ font-size: 23px; font-weight: 700; }}
            QLabel#ringValue {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 22px; font-weight: 600; color: {c['accent']}; }}
            QLabel#ringCaption {{ font-size: 10px; color: {c['muted']}; letter-spacing: 0.5px; }}
            QLabel#metric {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 18px; font-weight: 600; }}
            QFrame#divider {{ background: {c['border']}; border: none; }}
            QPushButton {{ background: {c['elevated']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 8px 13px; font-weight: 600; }}
            QPushButton:hover {{ background: {c['hover']}; border-color: {c['muted']}; }}
            QPushButton:pressed {{ background: {c['tint']}; }}
            QPushButton:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {c['accent']}; }}
            QPushButton#primary {{ background: {c['accent']}; color: {c['ink']}; border: 2px solid transparent; font-size: 14px; padding: 9px; }}
            QPushButton#primary:hover {{ border-color: {c['text']}; }}
            QPushButton#primary:focus {{ border-color: {c['text']}; }}
            QPushButton#primary:pressed {{ background: {c['tint']}; color: {c['text']}; }}
            QPushButton#modeCard {{ text-align: left; background: {c['panel']}; border-radius: 13px; padding: 0; border: 1px solid {c['border']}; }}
            QPushButton#modeCard:checked {{ background: {c['tint']}; border: 1px solid {c['accent']}; }}
            QPushButton#modeCard:disabled {{ background: {c['elevated']}; border-color: {c['border']}; }}
            QPushButton#modeCard:hover, QPushButton#modeCard:focus {{ border: 2px solid {c['accent']}; }}
            QLabel#modeSymbol {{ color: {c['accent']}; font-size: 19px; }}
            QLabel#modeTitle, QLabel#fieldLabel {{ font-size: 13px; font-weight: 600; }}
            QLabel#modeTag {{ font-size: 9px; font-weight: 700; color: {c['accent']}; letter-spacing: 0.5px; }}
            QPushButton#preset {{ padding: 4px 8px; font-size: 11px; border-radius: 7px; font-weight: 500; }}
            QPushButton#preset:checked {{ background: {c['tint']}; border-color: {c['accent']}; color: {c['accent']}; }}
            QPushButton#smallButton {{ padding: 0; font-size: 20px; }}
            QComboBox, QSpinBox {{ background: {c['elevated']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 7px 10px; min-height: 20px; selection-background-color: {c['accent']}; selection-color: {c['ink']}; }}
            QComboBox {{ padding-right: 24px; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 12px; height: 8px; }}
            QComboBox QAbstractItemView {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; selection-background-color: {c['tint']}; selection-color: {c['text']}; padding: 4px; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: none; background: {c['hover']}; }}
            QSpinBox::up-button {{ border-top-right-radius: 7px; }}
            QSpinBox::down-button {{ border-bottom-right-radius: 7px; }}
            QSpinBox::up-arrow {{ image: url("{arrow_up}"); width: 10px; height: 7px; }}
            QSpinBox::down-arrow {{ image: url("{arrow_down}"); width: 10px; height: 7px; }}
            QCheckBox {{ spacing: 9px; font-size: 12px; }}
            QCheckBox::indicator {{ width: 17px; height: 17px; background: {c['elevated']}; border: 1px solid {c['muted']}; border-radius: 5px; }}
            QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; image: url("{check}"); }}
            QCheckBox::indicator:focus {{ border-color: {c['accent']}; }}
            QLabel#keycap {{ font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 11px; color: {c['text']}; }}
            QFrame#alert {{ background: {c['errorbg']}; border: 1px solid {c['error']}; border-radius: 10px; }}
            QLabel#alertText {{ color: {c['error']}; font-size: 12px; }}
            QWidget:disabled {{ color: {c['muted']}; }}
            QScrollBar:vertical {{ background: {c['bg']}; width: 8px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 30px; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QMenu {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
            QMenu::item {{ padding: 7px 20px; }}
            QMenu::item:selected {{ background: {c['tint']}; }}
            QToolTip {{ background: {c['elevated']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
        """)

    def queue_save(self, *_):
        self.save_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "dashboard"):
            direction = QBoxLayout.Direction.LeftToRight if self.width() >= 900 else QBoxLayout.Direction.TopToBottom
            if self.dashboard.direction() != direction:
                self.dashboard.setDirection(direction)

    def save_settings(self):
        try:
            self.store.save(self.controller.options, self.language, self.theme,
                self.close_checkbox.isChecked(), self.saveGeometry())
        except OSError as exc:
            self.show_error(str(exc))

    def show_error(self, message):
        self.alert_text.setText(message)
        self.alert.show()
        QTimer.singleShot(0, self._reveal_alert)
        if not self.isVisible() and self.tray_available:
            self.tray.showMessage("StayActive", message, QSystemTrayIcon.MessageIcon.Warning)

    def _reveal_alert(self):
        if not self._closed and not self.alert.isHidden():
            self.scroll.ensureWidgetVisible(self.alert, 0, 8)

    def session_completed(self):
        if self.tray_available:
            self.tray.showMessage("StayActive", self.tr("completed_notice"), QSystemTrayIcon.MessageIcon.Information)

    def _restore_geometry(self):
        geometry = self.store.settings.value("window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(self.width(), available.width()), min(self.height(), max(540, available.height() - 60)))
            if not any(s.availableGeometry().intersects(self.frameGeometry()) for s in QApplication.screens()):
                self.move(available.center() - self.rect().center())

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_window()

    def minimize(self):
        if self.tray_available:
            self.hide()
            if not self._tray_notified:
                self._tray_notified = True
                self.tray.showMessage("StayActive", self.tr("tray_hint"), QSystemTrayIcon.MessageIcon.Information)
        else:
            self.showMinimized()

    def closeEvent(self, event):
        if self.close_checkbox.isChecked() and self.tray_available and not self._closed:
            event.ignore()
            self.minimize()
        else:
            self.shutdown()
            event.accept()
            QApplication.instance().quit()

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.save_timer.stop()
        self.controller.stop()
        self.hotkey.close()
        self.save_settings()
        self.tray.hide()

    def quit_app(self):
        self.shutdown()
        self.close()
