"""One user action for AVAC followed by optional conservative WAVE coupling."""
from copy import copy
import hashlib
import json

from avac_desktop.core.run_project import read_run_metadata
from . import simulation, wave
from .analysis import Results
from .geo import sha256_file
from .native_paths import verify_execution_paths
from .runtime import ensure_runtime


def signature(session):
    payload = dict(avac=simulation.signature(session), wave=session.wave_enabled)
    if session.wave_enabled:
        payload.update(setup=wave.inherited_settings(session), lake=sha256_file(session.lake_path))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def check_cancel(task):
    if task and task.cancelled.is_set():
        raise ValueError("Preparation cancelled.")


def reusable_avalanche(session):
    """Reuse only a completed owned calculation with the exact current inputs."""
    candidates = [session.selected_run, *reversed(session.runs)]
    if session.workspace and (session.workspace/"runs").is_dir():
        candidates.extend(sorted((session.workspace/"runs").iterdir(), reverse=True))
    expected = simulation.signature(session)
    for root in dict.fromkeys(candidates):
        if root is None:
            continue
        try:
            metadata = read_run_metadata(root)
            if metadata.get("status") == "completed" and metadata.get("desktop_input_signature") == expected:
                Results(root)  # Check actual discoverable output, not just the marker.
                return root
        except (ValueError, OSError, KeyError):
            continue
    return None


def prepare(session, task=None):
    issues = simulation.validate(session)
    if issues:
        raise ValueError("\n".join(issues))
    check_cancel(task)
    if session.wave_enabled:
        wave.preview_lake(session)
        ensure_runtime("WAVE")
    stamp = signature(session)
    check_cancel(task)
    source = reusable_avalanche(session) if session.wave_enabled else None
    plan = dict(signature=stamp, source=source, wave=None, avac=None)
    if source:
        snapshot = copy(session)
        snapshot.selected_run = source
        plan["wave"] = wave.prepare(snapshot)
    else:
        plan["avac"] = simulation.prepare(session, task)
    check_cancel(task)
    if signature(session) != stamp:
        raise ValueError("Inputs changed during preparation. Prepare again.")
    return plan


def verify(session, plan):
    if not plan or signature(session) != plan["signature"]:
        raise ValueError("Inputs changed. Prepare again before running.")
    issues = simulation.validate(session)
    if issues:
        raise ValueError("\n".join(issues))
    if plan["source"]:
        if reusable_avalanche(session) != plan["source"]:
            raise ValueError("The completed avalanche is no longer reusable. Prepare again.")
        root, solver = plan["wave"]
        marker = json.loads((root/".avac_qgis_wave_run.json").read_text(encoding="utf-8"))
        if marker.get("status") != "prepared":
            raise ValueError("Prepare a new WAVE scenario before running.")
        verify_execution_paths(root)
        return root, solver, "WAVE"
    root, solver = simulation.verify_ready(session)
    return root, solver, "AVAC"


def continue_wave(session, plan, task=None):
    check_cancel(task)
    if signature(session) != plan["signature"]:
        raise ValueError("Inputs changed before WAVE coupling. Prepare again.")
    result = wave.prepare(session)
    check_cancel(task)
    return result
