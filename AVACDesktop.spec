# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import sys
import json

hiddenimports = []
hiddenimports += collect_submodules('osgeo')
runtime_data = []
for kind in ('avac','wave'):
    descriptor = Path('avac_desktop/resources')/f'{kind}-runtime.json'
    identity = json.loads(descriptor.read_text(encoding='utf-8'))
    runtime_data.extend([(str(descriptor),'avac_desktop/resources'),
                         (str(descriptor.parent/identity['archive']),'avac_desktop/resources')])


a = Analysis(
    ['desktop_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[('avac_desktop/resources/AVAC_configuration100.yaml', 'avac_desktop/resources'),
           ('avac_desktop/resources/AVAC_app_icon.png', 'avac_desktop/resources'),
           ('avac_desktop/resources/spin-*.svg', 'avac_desktop/resources'),
           (str(Path(sys.prefix)/'Library/share/proj'), 'Library/share/proj'), ('LICENSE', '.'),
           ('DISCLAIMER.txt', '.'), ('THIRD_PARTY_NOTICES.md', '.')]+runtime_data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngine', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
              'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtTest', 'tkinter', 'qgis'],
    noarchive=False,
    optimize=0,
)
# PyInstaller's broad Qt plugin collection includes optional PDF/virtual-keyboard
# engines that this Widgets application never loads. Keep the deployed surface
# limited to the application's actual components and matching Qt version.
unused_qt = ('qt6qml', 'qt6quick', 'qt6pdf', 'qt6virtualkeyboard', 'qt6test', 'qtvirtualkeyboardplugin', 'qpdf.')
a.binaries = [entry for entry in a.binaries if not Path(entry[0]).name.lower().startswith(unused_qt)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AVACDesktop',
    icon='packaging/windows/assets/AVACDesktop.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AVACDesktop',
)
