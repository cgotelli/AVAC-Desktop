"""Optional WAVE use cases; existing conservative coupling stays authoritative."""
from __future__ import annotations

import json
from pathlib import Path
import uuid

import numpy as np

from avac_desktop.core.lake_polygon import connected_lake_mask, seed_cell, write_lake_polygon
from avac_desktop.core.preprocessing import AvacRaster, configuration_for_raster
from avac_desktop.core.wave_project import avac_computation_domain, prepare_wave_lake, prepare_wave_scenario
from avac_desktop.core.wave_execution import prepare_wave_runtime_execution
from .runtime import ensure_runtime
from avac_desktop.core.runtime_execution import runtime_solver
from .geo import read_polygons
from .project import atomic_text
from .native_paths import stage_execution_paths


def update_status(root: Path, status: str, **fields) -> None:
    from avac_desktop.core.time_utils import local_now_iso
    marker = root/".avac_qgis_wave_run.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if payload.get("format") != 1:
        raise ValueError("Unsupported WAVE marker.")
    payload.update(status=status, updated_at=local_now_iso(), **fields)
    atomic_text(marker, json.dumps(payload, indent=2)+"\n")


def derive_lake(session, x: float, y: float) -> Path:
    if session.terrain is None or session.workspace is None:
        raise ValueError("Load terrain and choose a workspace before deriving a lake.")
    raster = session.terrain.raster
    level = float(session.wave_setup["water_level"])
    mask = connected_lake_mask(raster.z, seed_cell(raster, x, y), level)
    destination = session.workspace/"derived_inputs"/f"lake-{uuid.uuid4().hex[:12]}.gpkg"
    return write_lake_polygon(destination, raster, mask, water_level=level, seed_x=x, seed_y=y)


def preview_lake(session):
    if session.terrain is None or session.lake_path is None:
        raise ValueError("Select terrain and a persistent lake polygon first.")
    setup = inherited_settings(session)
    for key,value in setup.items():
        if key != "limiter":
            try:
                finite = np.isfinite(float(value))
            except (ValueError,TypeError,OverflowError):
                finite = False
            if not finite:
                raise ValueError(f"WAVE {key} must be finite.")
    if not 0 <= float(setup["damping"]) <= .4:
        raise ValueError("Wave damping must be between 0 and 0.4.")
    if not 0 < float(setup["cfl_target"]) <= float(setup["cfl_max"]) <= 1:
        raise ValueError("Wave CFL target and maximum must satisfy 0 < target <= maximum <= 1.")
    if setup["limiter"] not in {"none", "minmod", "superbee", "mc", "vanleer"}:
        raise ValueError("Wave limiter is not supported by the bundled solver.")
    if any(float(setup[key]) <= 0 for key in ("duration", "dry_limit", "land_strickler", "water_strickler", "friction_depth_limit", "wave_tolerance_flag")):
        raise ValueError("Wave physical and wet/dry parameters must be positive.")
    extent = configuration_for_raster(session.configuration, session.terrain.raster)["dem_extent"]
    domain = {key: float(extent[key]) for key in ("xmin", "xmax", "ymin", "ymax")}
    rings = read_polygons(session.lake_path, session.terrain.wkt)
    lake = prepare_wave_lake(session.terrain.raster, rings, water_level=float(setup["water_level"]),
                             cell_size=float(setup["cell_size"]), domain=domain,
                             dry_tolerance=float(setup.get("dry_limit", .0001)))
    return lake, rings


def inherited_settings(session):
    setup = dict(session.wave_setup)
    if setup.get("duration") is None:
        setup["duration"] = float(session.configuration["computation"]["t_max"])
    for key in ("cfl_target", "cfl_max"):
        setup[key] = session.configuration["computation"][key]
    return setup


def prepare(session):
    if session.workspace is None:
        raise ValueError("Choose a working directory first.")
    if session.selected_run is None:
        raise ValueError("A completed avalanche is required before staging WAVE coupling.")
    lake, rings = preview_lake(session)
    runtime = ensure_runtime("WAVE")
    setup = inherited_settings(session)
    from .preferences import output_count
    interval = float(session.configuration["computation"]["t_max"])/(int(session.configuration["animation"]["n_out"])-1)
    output_count(float(setup["duration"]), interval)
    settings = {key: value for key, value in setup.items() if key not in ("duration", "water_level", "cell_size")}
    root = prepare_wave_scenario(session.workspace, session.selected_run, session.terrain.raster, rings,
                                 water_level=float(session.wave_setup["water_level"]), cell_size=float(session.wave_setup["cell_size"]),
                                 domain=avac_computation_domain(session.selected_run), parameters=settings, prepared_lake=lake,
                                 duration=float(setup["duration"]), output_interval=interval)
    try:
        from .geometry import release_geojson
        atomic_text(root/"lake.geojson", release_geojson(rings, session.terrain.raster.crs_authid))
        output = prepare_wave_runtime_execution(runtime, root, session.selected_run)
        stage_execution_paths(output,root)
        import os
        update_status(root, "prepared", runtime=str(runtime), lake_polygon="lake.geojson", desktop_project_id=session.project_id,
                      source_avac_run_relative=os.path.relpath(session.selected_run, root))
    except Exception as exc:
        update_status(root, "failed", preparation_error=str(exc))
        raise
    return root, runtime_solver(runtime)


class WaveResults:
    """Reuse WAVE readers/field semantics; keep raw AVAC/WAVE output read only."""
    def __init__(self, root: Path):
        from avac_desktop.core.wave_results import discover_wave_results, _wave_frame_fields
        marker = json.loads((root/".avac_qgis_wave_run.json").read_text(encoding="utf-8"))
        if marker.get("status") != "completed":
            raise ValueError("This project's WAVE calculation is not completed.")
        self.discovery = discover_wave_results(root, ensure_runtime("WAVE"))
        self.root = root
        self.cache = {}
        self.cache_bytes = 128*1024*1024
        self.cache_size = 0
        import sys
        from avac_desktop.core.runtime import validate_runtime
        from avac_desktop.core.clawpack_logging import suppress_pyclaw_file_logging
        manifest = validate_runtime(self.discovery.runtime)
        claw = str(self.discovery.runtime/manifest["clawpack"]["root"])
        added = claw not in sys.path
        if added:
            sys.path.insert(0,claw)
        try:
            with suppress_pyclaw_file_logging():
                from clawpack.geoclaw.fgout_tools import FGoutGrid
                self.reader = FGoutGrid(1,str(self.discovery.output),output_format=self.discovery.output_format)
                self.reader.read_fgout_grids_data()
        finally:
            if added:
                sys.path.remove(claw)
        initial = _wave_frame_fields(self.reader.read_frame(self.discovery.frames[0].frame_id))
        self.initial_surface = initial[4]+initial[3]
        self.initial_wet = initial[1], initial[2], initial[3] > 0
        self._lake_outline = None

    def lake_outline(self):
        """Recover legacy scenarios' initial wet-cell boundary without disk IO."""
        if self._lake_outline is None:
            from osgeo import gdal, ogr
            from .geo import spatial_reference
            from .analysis import field_raster
            x, y, wet = self.initial_wet
            raster = field_raster(x, y, wet, self.discovery.crs_authid)
            m = raster.metadata
            image = gdal.GetDriverByName("MEM").Create("", len(x), len(y), 1, gdal.GDT_Byte)
            image.SetGeoTransform((m["xmin"], m["cellsize"], 0, m["ymax"], 0, -m["cellsize"]))
            image.SetProjection(spatial_reference(self.discovery.crs_authid).ExportToWkt())
            image.GetRasterBand(1).WriteArray(wet[::-1].astype(np.uint8))
            vector = ogr.GetDriverByName("Memory").CreateDataSource("")
            layer = vector.CreateLayer("lake", spatial_reference(self.discovery.crs_authid), ogr.wkbPolygon)
            band = image.GetRasterBand(1)
            gdal.Polygonize(band, band, layer, -1, [])
            rings = []
            for feature in layer:
                polygon = feature.GetGeometryRef()
                contours = [np.asarray(polygon.GetGeometryRef(i).GetPoints(), dtype=float)[:, :2]
                            for i in range(polygon.GetGeometryCount())]
                rings.append((contours[0], contours[1:]))
            self._lake_outline = rings
        return self._lake_outline

    def raster(self, variable, index):
        from avac_desktop.core.wave_results import _wave_frame_fields, wave_temporal_values
        from .analysis import field_raster
        if index not in self.cache:
            frame = _wave_frame_fields(self.reader.read_frame(self.discovery.frames[index].frame_id))
            size = sum(array.nbytes for array in frame[1:])
            if self.cache_size+size > self.cache_bytes:
                self.cache.clear()
                self.cache_size = 0
            if size <= self.cache_bytes:
                self.cache[index] = frame
                self.cache_size += size
        else:
            frame = self.cache[index]
        time, x, y, depth, bed, hu, hv = frame
        key = "depth" if variable == "water_depth" else variable
        values = wave_temporal_values(key, bed, depth, self.initial_surface)
        return time, field_raster(x, y, values, self.discovery.crs_authid)

    def gauge(self, x, y, variable, task=None):
        from avac_desktop.core.profiles import bilinear_sample
        times, values = [], []
        for index in range(len(self.discovery.frames)):
            if task and task.cancelled.is_set():
                raise InterruptedError("Gauge extraction cancelled.")
            time, raster = self.raster(variable, index)
            times.append(time)
            values.append(bilinear_sample(raster.x, raster.y, raster.z, np.array([x]), np.array([y]))[0])
        return np.asarray(times), np.asarray(values)
