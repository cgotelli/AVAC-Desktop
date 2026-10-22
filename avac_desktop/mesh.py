"""Inspect the native initial AVAC grid without advancing a simulation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class MeshLayer:
    name: str
    # Columns: xlow, ylow, nx, ny, dx, dy, AMR level. No ghost cells.
    patches: np.ndarray
    layout_id: bytes


@dataclass(frozen=True)
class MeshSnapshot:
    layers: tuple[MeshLayer, ...] = ()
    notice: str = ""

def mesh_layer(name, patches):
    values = np.array(patches, dtype=np.float64).reshape((-1, 7))
    if (not len(values) or not np.isfinite(values).all() or
            (values[:, 2:7] <= 0).any() or
            (values[:, 2:4] > 1_000_000_000).any() or (values[:, 6] > 100).any() or
            (values[:, [2, 3, 6]] != np.floor(values[:, [2, 3, 6]])).any()):
        raise ValueError("Invalid solver mesh patch geometry.")
    with np.errstate(over='ignore', invalid='ignore'):
        if not np.isfinite(values[:, :2]+values[:, 2:4]*values[:, 4:6]).all():
            raise ValueError("Solver mesh extent is not finite.")
    values.setflags(write=False)
    return MeshLayer(name, values, hashlib.blake2b(values.tobytes(), digest_size=16).digest())


def read_initial_mesh(path):
    path = Path(path)
    if path.stat().st_size > 16*1024*1024:
        raise ValueError("Initial mesh exceeds the display size limit.")
    values = np.loadtxt(path, dtype=np.float64, ndmin=2)
    if values.ndim != 2 or values.shape[1] != 7 or not 0 < len(values) <= 50_000:
        raise ValueError("Invalid initial solver mesh geometry.")
    return MeshSnapshot((mesh_layer('AVAC', values),))


def inspect_initial_mesh(session, task=None):
    """Initialize once in a sibling of _output, preserving relative inputs.

    Prepared controls and simulation outputs remain untouched. Only the small
    patch geometry is retained; temporary initialization files are removed.
    """
    from . import simulation
    from .project import atomic_text
    if task and task.cancelled.is_set():
        raise ValueError('Initial mesh inspection cancelled.')
    root, solver = simulation.verify_ready(session)
    cache = root/'AVAC'/'initial_mesh.txt'
    if cache.is_file():
        return read_initial_mesh(cache)
    environment = dict(os.environ)
    for key in ('CLAW', 'CLAW_PYTHON', 'FC', 'PYTHONPATH'):
        environment.pop(key, None)
    environment['AVAC_INITIAL_MESH_ONLY'] = '1'
    environment['OMP_NUM_THREADS'] = str(session.threads)
    from .core.run_project import read_run_metadata
    runtime = Path(read_run_metadata(root)['runtime'])
    environment['PATH'] = os.pathsep.join((str(runtime/'bin'), str(runtime/'lib'), environment.get('PATH', '')))
    # Same depth as _output: its staged ../ and ../../ references stay valid.
    with tempfile.TemporaryDirectory(prefix='_initial_mesh-', dir=root/'AVAC') as directory:
        directory = Path(directory)
        for control in (root/'AVAC'/'_output').glob('*.data'):
            shutil.copy2(control, directory/control.name)
        with (directory/'inspection.log').open('wb') as log:
            with subprocess.Popen([str(solver)], cwd=directory, env=environment, stdout=log,
                                  stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW) as process:
                while True:
                    try:
                        code = process.wait(timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        if task and task.cancelled.is_set():
                            process.terminate()
                            process.wait()
                            raise ValueError('Initial mesh inspection cancelled.')
            generated = directory/'initial_mesh.txt'
            if code or not generated.is_file():
                detail = (directory/'inspection.log').read_text(encoding='utf-8', errors='replace')[-4000:]
                raise ValueError(f'Initial mesh initialization failed.\n{detail}')
            result = read_initial_mesh(generated)
            atomic_text(cache, generated.read_text(encoding='ascii'))
    return result
