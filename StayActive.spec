# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import os
from pathlib import Path
import sys

# 開発ツールの PATH にある別製品の UCRT/OpenSSL を取り込まない。
# Python、同じ環境の Qt、Windows の標準 DLL だけを探索する。
qt_bin = Path(importlib.util.find_spec('PyQt6').origin).parent / 'Qt6' / 'bin'
windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
os.environ['PATH'] = os.pathsep.join(str(path) for path in (
    Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs',
    qt_bin, windows / 'System32', windows,
))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('stayactive/assets', 'stayactive/assets'), ('LICENSE', '.'),
           ('THIRD_PARTY_NOTICES.md', '.'), ('build/LICENSES.txt', '.'), ('build/build-info.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide2', 'PySide6', 'tkinter', 'unittest'],
    noarchive=False,
    optimize=0,
)

# Windows 10/11 の UCRT と API-set は OS のものを使う。
# PATH の別アプリから混入したコピーでシステム DLL を置き換えない。
a.binaries = [item for item in a.binaries if not (
    Path(item[0]).name.lower() == 'ucrtbase.dll'
    or Path(item[0]).name.lower().startswith(('api-ms-win-', 'ext-ms-win-'))
)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StayActive',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='build/stayactive.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
