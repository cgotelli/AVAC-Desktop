"""Stable freezer entry point; application modules retain package imports."""
import faulthandler
import os
from pathlib import Path
import sys
import logging

# Capture native/startup diagnostics even for a windowed development build.
_log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AVAC Desktop" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_startup = (_log_dir / "startup.log").open("w", encoding="utf-8")
faulthandler.enable(_startup)
logging.basicConfig(filename=str(_log_dir/"application.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s", encoding="utf-8")
if getattr(sys, "frozen", False):
    _data = Path(sys._MEIPASS)/"Library"/"share"
    os.environ["PROJ_DATA"] = str(_data/"proj")
    os.environ["GDAL_DATA"] = str(_data/"gdal")
from avac_desktop.app import main

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        faulthandler.cancel_dump_traceback_later()
