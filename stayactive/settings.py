"""設定の検証と、ユーザー別の永続化。実行状態は保存しない。"""

from dataclasses import dataclass, replace
import os
from pathlib import Path

from PyQt6.QtCore import QSettings


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
        return value.lower() in ("true", "1")
    return default


@dataclass(frozen=True)
class SessionOptions:
    mode: str = "quiet"
    interval_seconds: int = 30
    duration_minutes: int = 60
    keep_display: bool = True
    reset_idle: bool = False

    def validated(self):
        return replace(self,
            mode=self.mode if self.mode in ("quiet", "cursor") else "quiet",
            interval_seconds=bounded_int(self.interval_seconds, 30, 1, 300),
            duration_minutes=bounded_int(self.duration_minutes, 60, 0, 1440),
            keep_display=as_bool(self.keep_display, True), reset_idle=as_bool(self.reset_idle))


class SettingsStore:
    def __init__(self, path: Path):
        self.settings = QSettings(str(path), QSettings.Format.IniFormat)
        self.settings.setAtomicSyncRequired(True)

    def load(self) -> tuple[SessionOptions, str, str, bool]:
        get = self.settings.value
        options = SessionOptions(mode=get("session/mode", "quiet"),
            interval_seconds=get("session/interval", 30), duration_minutes=get("session/duration", 60),
            keep_display=get("session/display", True), reset_idle=get("session/reset_idle", False)).validated()
        fallback = "en" if os.environ.get("STAYACTIVE_LANG") == "English" else "ja"
        language, theme = get("appearance/language", fallback), get("appearance/theme", "dark")
        return (options, language if language in ("ja", "en") else fallback,
                theme if theme in ("dark", "light") else "dark",
                as_bool(get("window/close_to_tray", False)))

    def save(self, options: SessionOptions, language: str, theme: str, close_to_tray: bool, geometry=None):
        values = {"session/mode": options.mode, "session/interval": options.interval_seconds,
                  "session/duration": options.duration_minutes, "session/display": options.keep_display,
                  "session/reset_idle": options.reset_idle,
                  "appearance/language": language, "appearance/theme": theme,
                  "window/close_to_tray": close_to_tray}
        if geometry is not None:
            values["window/geometry"] = geometry
        for key, value in values.items():
            self.settings.setValue(key, value)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            raise OSError("設定を保存できません。 / Could not save preferences.")
