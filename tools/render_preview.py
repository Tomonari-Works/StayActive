"""オフスクリーン描画のレビュー画像。OS に維持要求や入力を送信しない。"""

import argparse
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from stayactive.controller import ActivityController
from stayactive.settings import SessionOptions, SettingsStore
from stayactive.ui import StayActiveApp

parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=["dark", "light"], default="dark")
parser.add_argument("--language", choices=["ja", "en"], default="ja")
parser.add_argument("--width", type=int, default=1000)
parser.add_argument("--height", type=int, default=612)
parser.add_argument("--running", action="store_true")
parser.add_argument("--quick-start", action="store_true")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
app = QApplication([])
app.setStyle("Fusion")
# Windows の offscreen プラグインは OS のフォント一覧を列挙しないため明示的に登録する。
fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
for name in ("YuGothR.ttc", "YuGothB.ttc", "segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
    if (fonts / name).exists():
        QFontDatabase.addApplicationFont(str(fonts / name))
with tempfile.TemporaryDirectory() as directory:
    store = SettingsStore(Path(directory) / "settings.ini")
    store.save(SessionOptions(), args.language, args.theme, False)
    clock = [100.0]
    controller = ActivityController(backend=Mock(available=True, display_supported=True),
        cursor=Mock(available=True, system="Windows", idle_seconds=Mock(return_value=12.0)), clock=lambda: clock[0])
    window = StayActiveApp(store, controller, integrations=False)
    window.show()
    window.resize(args.width, args.height)
    if args.quick_start:
        window.quick_start()
    if args.running or args.quick_start:
        controller.start()
        clock[0] += 137
        controller.tick()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(args.output)):
        raise SystemExit("Could not save preview")
    print(f"{args.output}: {window.width()}x{window.height()}, scroll={window.scroll.verticalScrollBar().maximum()}")
    window.shutdown()
