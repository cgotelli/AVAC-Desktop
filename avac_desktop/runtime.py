"""Desktop-owned, source-versioned managed runtime identities."""
from __future__ import annotations

import json
from pathlib import Path

from avac_desktop.core.runtime import install_runtime_archive, runtime_install_root, platform_key

RESOURCES = Path(__file__).resolve().parent/"resources"


def ensure_runtime(kind: str = "AVAC") -> Path:
    if kind not in ("AVAC", "WAVE"):
        raise ValueError("Unsupported solver runtime kind.")
    descriptor = RESOURCES/f"{kind.lower()}-runtime.json"
    if not descriptor.is_file():
        raise RuntimeError("Desktop runtime descriptor is missing. Build the versioned desktop runtimes before native execution.")
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    if payload.get("kind") != kind or payload.get("platform") != platform_key():
        raise ValueError("Desktop native runtime does not match this solver/platform.")
    archive_name = payload["archive"]
    if Path(archive_name).name != archive_name:
        raise ValueError("Unsafe desktop runtime archive name.")
    # A separate leaf under the legacy data area preserves existing workspace
    # protections and cannot replace an installed QGIS release runtime.
    return install_runtime_archive(RESOURCES/archive_name,payload["runtime_version"],
                    destination_root=runtime_install_root()/"desktop"/kind.lower(),
                    expected_manifest_sha256=payload["runtime_manifest_sha256"])


def runtime_available(kind: str = "AVAC") -> bool:
    descriptor = RESOURCES/f"{kind.lower()}-runtime.json"
    if not descriptor.is_file():
        return False
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    return (RESOURCES/payload["archive"]).is_file()
