"""同じベクター描画から配布用アイコンを作成する。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
from stayactive.ui import app_icon

app = QApplication([])
target = Path(__file__).resolve().parents[1] / "build" / "stayactive.ico"
target.parent.mkdir(parents=True, exist_ok=True)
if not app_icon().pixmap(256, 256).save(str(target), "ICO"):
    raise SystemExit("Could not generate the app icon")
print(target)
