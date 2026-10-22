"""Small, immutable solver-grid snapshots; never read solution/auxiliary arrays."""
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class MeshLayer:
    name: str
    time: float | None
    # Columns: xlow, ylow, nx, ny, dx, dy, AMR level. No ghost cells.
    patches: np.ndarray
    layout_id: bytes


@dataclass(frozen=True)
class MeshSnapshot:
    layers: tuple[MeshLayer, ...] = ()
    notice: str = ""
    preparation: bool = False

    def description(self):
        parts = []
        for layer in self.layers:
            levels = np.unique(layer.patches[:, 6]).astype(int)
            level = f"L{levels[0]}" if len(levels) == 1 else f"L{levels[0]}–{levels[-1]}"
            if self.preparation:
                parts.append(f"{layer.name} base · {layer.patches[0, 4]:g} m")
            else:
                parts.append(f"{layer.name} {level} · mesh t={layer.time:g} s")
        if self.notice:
            parts.append(self.notice)
        return " | ".join(parts)


def mesh_layer(name, time, patches):
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
    return MeshLayer(name, time, values, hashlib.blake2b(values.tobytes(), digest_size=16).digest())


def preparation_mesh(session):
    """Fit base grids from metadata only, using the same rules as preparation."""
    from .core.preprocessing import AvacRaster, trim_raster_to_computational_grid
    from .core.wave_project import fit_wave_domain
    if session.terrain is None:
        return MeshSnapshot(notice="Import terrain to view the mesh.", preparation=True)
    try:
        source = session.terrain.raster
        empty = np.empty(0)
        metadata_only = AvacRaster(empty, empty, empty, source.metadata, source.crs_authid, 1)
        cell = float(session.configuration['computation']['cell_size'])
        domain = trim_raster_to_computational_grid(metadata_only, cell).metadata
        def layer(name, bounds, step):
            return mesh_layer(name, None, [[bounds['xmin'], bounds['ymin'],
                round((bounds['xmax']-bounds['xmin'])/step),
                round((bounds['ymax']-bounds['ymin'])/step), step, step, 1]])
        layers = [layer('AVAC', domain, cell)]
        if session.wave_enabled:
            step = float(session.wave_setup['cell_size'])
            water = fit_wave_domain(domain, source.metadata, step)
            layers.append(layer('WAVE', water, step))
        return MeshSnapshot(tuple(layers), preparation=True)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return MeshSnapshot(notice=f"Mesh preview unavailable: {exc}", preparation=True)


class SolverMesh:
    """Read binary-output fort.q headers lazily, with a bounded snapshot LRU."""
    MAX_PATCHES = 50_000
    MAX_HEADER_BYTES = 16*1024*1024
    CACHE_BYTES = 4*1024*1024
    CACHE_FRAMES = 8

    def __init__(self, output, name):
        self.output, self.name = Path(output), name
        self.records = None
        self.cache = OrderedDict()
        self.cache_size = 0

    def _index(self):
        records = []
        for path in self.output.glob('fort.t[0-9]*'):
            suffix = path.name.removeprefix('fort.t')
            if not suffix.isdecimal() or path.stat().st_size > 4096:
                continue
            try:
                tokens = [line.split()[0] for line in path.read_text(encoding='ascii').splitlines() if line.strip()]
                time, count = float(tokens[0].replace('D', 'E')), int(tokens[2])
                dimension = int(tokens[4])
                format = tokens[6].lower() if len(tokens) > 6 else ''
                if not math.isfinite(time) or dimension != 2 or not 0 < count <= self.MAX_PATCHES:
                    continue
                records.append((time, suffix, count, format))
            except (OSError, ValueError, IndexError, UnicodeError):
                continue
        self.records = sorted(records)
        self.times = [record[0] for record in self.records]

    def snapshot(self, time):
        try:
            if self.records is None:
                self._index()
            index = bisect_right(self.times, time+max(1., abs(time))*1e-8)-1
            if index < 0:
                return MeshSnapshot(notice=f"{self.name}: native mesh snapshots are unavailable for this time.")
            record = self.records[index]
            if index in self.cache:
                self.cache.move_to_end(index)
                return self.cache[index]
            actual_time, suffix, count, format = record
            if format not in ('binary', 'binary32', 'binary64'):
                return MeshSnapshot(notice=f"{self.name}: mesh headers require native binary output.")
            path = self.output/f'fort.q{suffix}'
            if path.stat().st_size > self.MAX_HEADER_BYTES:
                raise ValueError('Mesh header exceeds the display size limit.')
            patches = np.empty((count, 7), dtype=np.float64)
            def number(stream):
                for _ in range(16):
                    line = stream.readline()
                    if not line:
                        raise ValueError('Incomplete mesh header.')
                    if line.strip():
                        return float(line.split()[0].replace('D', 'E'))
                raise ValueError('Invalid mesh header.')
            with path.open(encoding='ascii') as stream:
                for i in range(count):
                    _, level, nx, ny, x, y, dx, dy = [number(stream) for _ in range(8)]
                    patches[i] = x, y, nx, ny, dx, dy, level
            layer = mesh_layer(self.name, actual_time, patches)
            result = MeshSnapshot((layer,))
            size = layer.patches.nbytes
            while self.cache and (self.cache_size+size > self.CACHE_BYTES or len(self.cache) >= self.CACHE_FRAMES):
                _, removed = self.cache.popitem(last=False)
                self.cache_size -= removed.layers[0].patches.nbytes
            if size <= self.CACHE_BYTES:
                self.cache[index] = result
                self.cache_size += size
            return result
        except (OSError, ValueError, OverflowError, UnicodeError) as exc:
            return MeshSnapshot(notice=f"{self.name} mesh unavailable: {exc}")
