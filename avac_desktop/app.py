"""AVAC Desktop entry point."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='AVAC Desktop')
    parser.add_argument('project', nargs='?', type=Path)
    parser.add_argument('--tutorial', action='store_true', help='Load the included tutorial dataset')
    parser.add_argument('--appearance', choices=('light', 'dark'), help='Override appearance for this session')
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('AVAC Desktop')
    app.setOrganizationName('AVAC')
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(resource_root()/'avac_desktop/resources/AVAC_app_icon.png')))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AVAC.Desktop')
    from .theme import apply_theme
    from .shell import MainWindow
    apply_theme(app, args.appearance)
    window = MainWindow()
    window.showMaximized()
    if args.project:
        QTimer.singleShot(0, lambda: window.open_project_path(args.project))
    elif args.tutorial:
        QTimer.singleShot(100, window.load_tutorial)
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
