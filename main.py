"""StayActive desktop entry point. Run with ``python main.py``."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile

from PyQt6.QtCore import QStandardPaths, Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox

from stayactive import __version__
from stayactive.instance import SingleInstance
from stayactive.settings import SettingsStore
from stayactive.ui import StayActiveApp, app_icon


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("StayActive")
    app.setOrganizationName("TomonariWorks")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    temporary = tempfile.TemporaryDirectory(prefix="stayactive-smoke-") if smoke_test else None
    directory = Path(temporary.name) if temporary else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "stayactive.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger("stayactive").addHandler(handler)
        logging.getLogger("stayactive").setLevel(logging.INFO)
        instance = SingleInstance(directory)
        if not instance.acquire():
            if not instance.activate_existing():
                QMessageBox.information(None, "StayActive", "StayActive は起動中です。\nStayActive is already running.")
            return 0
    except OSError as exc:
        QMessageBox.critical(None, "StayActive", f"設定フォルダーを開けません。 / Cannot open app data.\n{exc}")
        return 1
    window = None
    try:
        window = StayActiveApp(SettingsStore(directory / "settings.ini"), integrations=not smoke_test)
        instance.activated.connect(window.restore_window)
        app.aboutToQuit.connect(window.shutdown)

        def handle_exception(kind, value, traceback):
            if issubclass(kind, KeyboardInterrupt):
                app.quit()
                return
            logging.getLogger("stayactive").error("Unexpected application error", exc_info=(kind, value, traceback))
            window.controller.stop("error")
            window.show_error("予期しないエラー / Unexpected error: " + str(value))

        sys.excepthook = handle_exception
        if smoke_test:
            # 配布物の起動・画像プラグイン・正常終了を OS 入力なしで検証する。
            import stayactive.ui
            assets = Path(stayactive.ui.__file__).with_name("assets")
            for name in ("arrow-up-dark.svg", "arrow-down-light.svg", "check-dark.svg"):
                if QPixmap(str(assets / name)).isNull():
                    logging.getLogger("stayactive").error("Missing or invalid bundled asset: %s", name)
                    return 2
            if getattr(sys, "frozen", False):
                root = Path(stayactive.ui.__file__).parent.parent
                for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "LICENSES.txt", "build-info.json"):
                    if not (root / name).is_file():
                        logging.getLogger("stayactive").error("Missing bundled notice: %s", name)
                        return 2
            QTimer.singleShot(500, app.quit)
        else:
            window.show()
        return app.exec()
    finally:
        if window is not None:
            window.shutdown()
        instance.close()
        # Windows ではログのハンドルを閉じてから検証用フォルダーを破棄する。
        if temporary is not None:
            logger = logging.getLogger("stayactive")
            logger.removeHandler(handler)
            handler.close()
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
