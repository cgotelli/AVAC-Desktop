"""Exact derived samples cached outside immutable native result directories."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from avac_desktop.core.profiles import ProfileDataset, extract_profile


def dataset_identity(results):
    if hasattr(results, "avalanche"):
        # The combined view's quantitative field is water displacement; land
        # snow is a map overlay, so Wave/combined samples share the same cache.
        return dataset_identity(results.water)
    root = getattr(results, "root", None) or results.discovery.run_root
    # Finished native trees are read only; stat identities detect replaced
    # output without re-reading all binary data on every selection.
    records = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.suffix not in (".log", ".png"):
            stat = path.stat()
            records.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    return hashlib.sha256(json.dumps([str(root), records]).encode()).hexdigest()


def cache_path(workspace, feature, identity, variable, frame=None):
    payload = [2, feature["kind"], feature["coords"], identity, variable, frame, "bilinear-cell-centres"]
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    base = Path(workspace) if workspace else Path(os.environ.get("LOCALAPPDATA", Path.home()/".cache"))/"AVAC Desktop"
    return base/"analysis_results"/key/"samples.npz"


def save_arrays(path, **arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".samples-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(stream, **arrays)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def profile_cached(path, feature, raster, variable, source, time, label):
    if path.is_file():
        with np.load(path, allow_pickle=False) as data:
            return ProfileDataset(data["distance"], data["x"], data["y"], data["values"], variable,
                                  str(source), time, label)
    result = extract_profile(feature["coords"], raster.x, raster.y, raster.z, variable, str(source),
                             simulation_time_s=time, profile_name=label)
    save_arrays(path, distance=result.distance_m, x=result.x, y=result.y, values=result.values)
    return result


def gauge_cached(path, results, feature, variable, task=None):
    if path.is_file():
        with np.load(path, allow_pickle=False) as data:
            return data["times"], data["values"]
    x, y = feature["coords"][0]
    times, values = results.gauge(x, y, variable, task)
    if task and task.cancelled.is_set():
        raise InterruptedError("Gauge extraction cancelled.")
    save_arrays(path, times=times, values=values)
    return times, values
