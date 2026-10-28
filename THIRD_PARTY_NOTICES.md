# Third-party software and corresponding source

StayActive's own source code is provided under the [MIT License](LICENSE).
The Windows executable combines that code with the GPL-3.0-only distribution of PyQt6. The combined executable is distributed subject to GPL version 3; the separate licenses and permissions of its individual components continue to apply.

| Component | License | Source / license information |
| --- | --- | --- |
| PyQt6 | GPL-3.0-only | https://pypi.org/project/PyQt6/#files · https://www.riverbankcomputing.com/software/pyqt |
| Qt 6 libraries and plugins | LGPL-3.0, with additional third-party notices | https://doc.qt.io/qt-6/licensing.html · https://github.com/qt/qtbase · https://github.com/qt/qtsvg · https://github.com/qt/qtimageformats |
| PyQt6-sip | BSD-2-Clause | https://pypi.org/project/PyQt6-sip/#files |
| CPython and bundled dependencies | Python Software Foundation License and included notices | https://www.python.org/downloads/source/ |
| OpenSSL (from Python) | Apache-2.0 | https://github.com/openssl/openssl · exact runtime version in `build-info.json` |
| PyInstaller bootloader | GPL-2.0-or-later with distribution exception | https://pyinstaller.org/en/stable/license.html |

The complete license texts copied from the installed distributions, the exact-version Qt upstream notices, and a `build-info.json` dependency/version record are embedded in the executable. `LICENSES.txt` and `build-info.json` are also supplied with release assets. The Qt appendix includes optional and cross-platform source components; it does not assert that every listed component is shipped in the Windows binary.

The complete StayActive application source, build scripts, resources, and dependency constraints are available from the commit recorded in `build-info.json` and the corresponding release tag. Dependency source distributions are available from the versioned PyPI links in that file. Qt library sources are available from the same `vX.Y.Z` tag in the three Qt repositories linked above and from https://download.qt.io/official_releases/qt/ . These upstream components have not been modified by StayActive.

System and toolchain runtime libraries retain their vendor licenses. The Windows package uses the operating system's UCRT and API-set libraries; Microsoft Visual C++ redistributable runtime libraries supplied with Python/Qt remain Microsoft components. StayActive's MIT license does not replace any third-party license.

Maintainers: keep the original `LICENSE` unchanged. Run `tools/collect_qt_notices.py` when updating Qt, then `tools/prepare_licenses.py` before packaging. Neither script includes user settings, credentials, logs, or local account information in the release metadata.
