"""ローカルの依存から配布物のライセンス一覧とビルド情報を作る。"""

from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import re
import ssl
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "build" / "licenses"
    destination.mkdir(parents=True, exist_ok=True)
    components = []
    for package in ("PyQt6", "PyQt6-Qt6", "PyQt6-sip", "PyInstaller"):
        installed = distribution(package)
        files = [file for file in installed.files if file.name.lower() in ("license", "copying.txt")
                 and ".dist-info/" in str(file)]
        if not files:
            raise RuntimeError(f"Missing license text: {package}")
        text = "\n\n".join(Path(installed.locate_file(file)).read_text(encoding="utf-8-sig") for file in files)
        name = package + "-LICENSE.txt"
        (destination / name).write_text(text, encoding="utf-8", newline="\n")
        components.append({"name": package, "version": installed.version,
            "license": installed.metadata.get("License-Expression") or installed.metadata.get("License"),
            "license_file": name, "source": f"https://pypi.org/project/{package}/{installed.version}/#files"})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python LICENSE.txt is required for redistribution")
    (destination / "Python-LICENSE.txt").write_text(python_license.read_text(encoding="utf-8-sig"), encoding="utf-8")
    openssl_version = re.search(r"OpenSSL (\d+\.\d+\.\d+)", ssl.OPENSSL_VERSION)
    if openssl_version:
        openssl_version = openssl_version.group(1)
        tag = "openssl-" + openssl_version
        source = f"https://raw.githubusercontent.com/openssl/openssl/{tag}/LICENSE.txt"
        with urllib.request.urlopen(source, timeout=30) as response:
            text = response.read().decode("utf-8-sig")
        (destination / "OpenSSL-LICENSE.txt").write_text(text, encoding="utf-8")
        components.append({"name": "OpenSSL", "version": openssl_version, "license": "Apache-2.0",
            "license_file": "OpenSSL-LICENSE.txt", "source": f"https://github.com/openssl/openssl/tree/{tag}"})
    qt_version = distribution("PyQt6-Qt6").version
    qt_notices = ROOT / "licenses" / f"Qt-{qt_version}-upstream-notices.txt"
    if not qt_notices.is_file():
        raise RuntimeError("Exact-version Qt notices missing; run tools/collect_qt_notices.py")
    (destination / qt_notices.name).write_text(qt_notices.read_text(encoding="utf-8"), encoding="utf-8")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    metadata = {"source_revision": revision, "python": platform.python_version(), "platform": platform.system(),
        "architecture": platform.machine(), "openssl": ssl.OPENSSL_VERSION, "components": components,
        "application_source": "https://github.com/Tomonari-Works/StayActive", "qt_source_tag": "v" + qt_version}
    (ROOT / "build" / "build-info.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    combined = ["StayActive third-party license texts\n", (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")]
    for file in sorted(destination.glob("*.txt")):
        combined.extend(["\n" + "=" * 72 + "\n" + file.name + "\n", file.read_text(encoding="utf-8")])
    (ROOT / "build" / "LICENSES.txt").write_text("\n".join(combined), encoding="utf-8")
    print("Prepared dependency licenses and build-info.json")


if __name__ == "__main__":
    main()
