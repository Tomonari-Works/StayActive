"""Qt の正確なタグからライセンス・著作権表示を取得する（更新時だけ手動実行）。"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "StayActive-license-collector"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main():
    qt_version = version("PyQt6-Qt6")
    tag = "v" + qt_version
    sources = []
    for repository in ("qtbase", "qtsvg", "qtimageformats"):
        url = f"https://api.github.com/repos/qt/{repository}/git/trees/{tag}?recursive=1"
        tree = json.loads(fetch(url))
        if tree.get("truncated"):
            raise RuntimeError("Incomplete Qt license source tree")
        for item in tree["tree"]:
            path = item["path"]
            filename = path.rsplit("/", 1)[-1].lower()
            if item["type"] == "blob" and (path.startswith("LICENSES/") or
                ("src/3rdparty/" in path and (filename.startswith(("license", "licence", "copying", "copyright"))
                 or filename == "qt_attribution.json"))):
                sources.append((repository, path, f"https://raw.githubusercontent.com/qt/{repository}/{tag}/{path}"))
    if len(sources) < 50:
        raise RuntimeError("Qt notices are unexpectedly incomplete")

    def read_source(source):
        repository, path, url = source
        content = fetch(url)
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1")
        return (f"\n{'=' * 72}\n{repository}/{path}\nSource: {url}\nSHA256: {hashlib.sha256(content).hexdigest()}\n\n"
                + decoded + "\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        sections = list(pool.map(read_source, sources))
    target = ROOT / "licenses" / f"Qt-{qt_version}-upstream-notices.txt"
    target.parent.mkdir(exist_ok=True)
    header = (f"Qt {qt_version}: upstream license and copyright appendix\n"
        "Exact upstream tags: qt/qtbase, qt/qtsvg, qt/qtimageformats " + tag + "\n"
        "This appendix includes cross-platform and optional upstream components; not every component is included in the Windows executable.\n"
        "The original notices and alternative-license statements below are preserved verbatim.\n")
    target.write_text(header + "".join(sections), encoding="utf-8", newline="\n")
    print(f"Collected {len(sources)} upstream notice files: {target.name}")


if __name__ == "__main__":
    main()
