"""Read-only analysis of existing raw AVAC output with a bounded frame cache."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import csv

import numpy as np

from avac_desktop.core.preprocessing import AvacRaster
from avac_desktop.core.results import discover_results, _avac_frame_fields, _load_fgmax, geometry_from_axes, _write_geotiff
from avac_desktop.core.profiles import bilinear_sample
from .runtime import ensure_runtime

LABELS = {"terrain_elevation": "Terrain elevation [m]", "depth": "Snow depth [m]", "velocity": "Terrain-tangent velocity [m/s]", "pressure": "Kinetic pressure [kPa]",
          "snow_surface_elevation": "Snow surface elevation [m]", "max_depth": "Maximum snow depth [m]",
          "max_velocity": "Maximum velocity [m/s]", "max_pressure": "Maximum kinetic pressure [kPa]",
          "arrival_time": "Arrival time [s]", "time_max_depth": "Time of maximum depth [s]",
          "time_max_velocity": "Time of maximum velocity [s]", "water_depth": "Water depth [m]",
          "water_elevation": "Water surface elevation [m]", "surface_displacement": "Surface displacement [m]"}


def field_raster(x, y, values, crs: str) -> AvacRaster:
    geometry = geometry_from_axes(x, y)
    metadata = dict(xmin=geometry.xmin, xmax=geometry.xmax, ymin=geometry.ymin, ymax=geometry.ymax,
                    cellsize=geometry.dx, ncols=geometry.width, nrows=geometry.height, nodata_value=-9999.)
    return AvacRaster(x, y, values, metadata, crs, 1)


class Results:
    def __init__(self, root: Path, cache_bytes: int = 128*1024*1024):
        self.discovery = discover_results(root)
        self.runtime = ensure_runtime()
        # Authenticate once at dataset open, then retain the existing Clawpack
        # reader. Re-hashing thousands of runtime files on every animation
        # frame would dominate interaction time. Imported metadata never selects
        # a Python backend; only this application-owned runtime does.
        import sys
        from avac_desktop.core.runtime import validate_runtime
        from avac_desktop.core.clawpack_logging import suppress_pyclaw_file_logging
        manifest = validate_runtime(self.runtime)
        claw_root = str(self.runtime/manifest["clawpack"]["root"])
        added = claw_root not in sys.path
        if added:
            sys.path.insert(0, claw_root)
        try:
            with suppress_pyclaw_file_logging():
                from clawpack.geoclaw.fgout_tools import FGoutGrid
                self.reader = FGoutGrid(self.discovery.fgout_grid, str(self.discovery.output_dir), output_format=self.discovery.output_format)
                self.reader.read_fgout_grids_data()
        finally:
            if added:
                sys.path.remove(claw_root)
        self.cache_bytes = cache_bytes
        self.cache: OrderedDict[int, tuple] = OrderedDict()
        self.cache_size = 0
        self._mesh = None

    def mesh(self, index):
        from .mesh import SolverMesh
        if self._mesh is None:
            self._mesh = SolverMesh(self.discovery.output_dir, 'AVAC')
        return self._mesh.snapshot(self.discovery.frames[index].time_seconds)

    def frame(self, index: int):
        if not 0 <= index < len(self.discovery.frames):
            raise ValueError("Frame index is outside the completed run.")
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        raw = self.reader.read_frame(self.discovery.frames[index].frame_id)
        x, y, fields = _avac_frame_fields(raw, self.discovery.rho, self.discovery.frames[index].frame_id)
        frame = float(raw.t), x, y, fields
        size = frame[1].nbytes + frame[2].nbytes + sum(a.nbytes for a in frame[3].values())
        while self.cache and self.cache_size + size > self.cache_bytes:
            _, dropped = self.cache.popitem(last=False)
            self.cache_size -= dropped[1].nbytes + dropped[2].nbytes + sum(a.nbytes for a in dropped[3].values())
        if size <= self.cache_bytes:
            self.cache[index] = frame
            self.cache_size += size
        return frame

    def raster(self, variable: str, index: int) -> tuple[float | None, AvacRaster]:
        if variable in ("depth", "velocity", "pressure", "snow_surface_elevation"):
            time, x, y, fields = self.frame(index)
        else:
            x, y, fields = _load_fgmax(self.discovery)
            time = None
        if variable not in fields:
            raise ValueError(f"This run does not contain {variable}.")
        return time, field_raster(x, y, fields[variable], self.discovery.crs_authid)

    def gauge(self, x: float, y: float, variable: str, task=None) -> tuple[np.ndarray, np.ndarray]:
        times, values = [], []
        for index in range(len(self.discovery.frames)):
            if task and task.cancelled.is_set():
                raise InterruptedError("Gauge extraction cancelled.")
            t, raster = self.raster(variable, index)
            times.append(t)
            values.append(bilinear_sample(raster.x, raster.y, raster.z, np.array([x]), np.array([y]))[0])
        return np.asarray(times), np.asarray(values)


def export_geotiff(path: Path, raster: AvacRaster) -> None:
    # Existing converter retains its documented Float32 derived-product format.
    # Source terrain and raw binary values remain unchanged.
    temporary = path.with_name(path.stem + ".partial.tif")
    _write_geotiff(temporary, [raster.z], geometry_from_axes(raster.x, raster.y), raster.crs_authid)
    temporary.replace(path)


def write_gauge(path: Path, times, values, variable: str, x: float, y: float, source: Path) -> None:
    from .project import atomic_text
    import io
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["time_s", LABELS[variable], "x_m", "y_m", "source_run"])
    for t, value in zip(times, values):
        writer.writerow([format(t, ".17g"), format(value, ".17g"), format(x, ".17g"), format(y, ".17g"), str(source)])
    atomic_text(path, stream.getvalue())
