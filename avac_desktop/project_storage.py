"""Copy required case data into the manifest folder without altering sources."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import uuid

from .geo import sha256_file


def inside(path, folder):
    return Path(path).resolve().is_relative_to(Path(folder).resolve())


def local_input(source, folder, *, raster=False):
    """Keep owned files; snapshot external GIS datasets including sidecars."""
    if source is None:
        return None
    source = Path(source).resolve(strict=True)
    materialize = False
    if raster:
        from osgeo import gdal
        with gdal.Open(str(source)) as dataset:
            files = [Path(item).resolve() for item in dataset.GetFileList()]
            # VRTs and datasets with remote/nested dependencies are materialized
            # without reprojection, resampling or a change of sample data type.
            materialize = source.suffix.lower() == ".vrt" or any(
                p.parent != source.parent or not p.is_file() for p in files)
    elif source.suffix.lower() == ".shp":
        files = [p for p in source.parent.iterdir() if p.is_file() and
                 p.name.lower().startswith(source.stem.lower()+".")]
    else:
        files = [source]
        materialize = source.suffix.lower() in (".vrt", ".ovf")
    if inside(source, folder) and not materialize:
        return source
    destination = Path(folder)/"inputs"/uuid.uuid4().hex
    destination.mkdir(parents=True)
    if materialize:
        from osgeo import gdal
        target = destination/(source.stem+(".tif" if raster else ".gpkg"))
        result = (gdal.Translate(str(target), str(source), format="GTiff") if raster else
                  gdal.VectorTranslate(str(target), str(source), format="GPKG"))
        result = None
        return target
    if source.suffix.lower() == ".gpkg" and source.with_name(source.name+"-wal").exists():
        import sqlite3
        with sqlite3.connect(source.as_uri()+"?mode=ro", uri=True) as original:
            with sqlite3.connect(destination/source.name) as copied:
                original.backup(copied)
    else:
        for item in files:
            shutil.copy2(item, destination/item.name)
    return destination/source.name


def collect_runs(session):
    """Include owned history and explicitly referenced legacy calculations."""
    from avac_desktop.core.wave_project import resolve_wave_source
    roots = {}
    for root, kind in [(p, "AVAC") for p in session.runs]+[
            (session.selected_run, "AVAC"), (session.selected_wave, "WAVE"),
            (session.execution_root, session.execution_kind), (session.prepared_run, "AVAC")]:
        if root is not None:
            roots[Path(root).resolve(strict=True)] = kind
    if session.workspace:
        for child, kind, filename in (("runs", "AVAC", ".avac_qgis_run.json"),
                                      ("wave_runs", "WAVE", ".avac_qgis_wave_run.json")):
            parent = Path(session.workspace)/child
            for path in parent.glob("*/"+filename):
                try:
                    marker = json.loads(path.read_text(encoding="utf-8"))
                    owned = marker.get("desktop_project_id") == session.project_id
                    legacy_wave = kind == "WAVE" and not marker.get("desktop_project_id") and resolve_wave_source(path.parent, marker) in roots
                    if owned or legacy_wave:
                        roots[path.parent.resolve()] = kind
                except (OSError, ValueError, TypeError):
                    continue
    for root, kind in list(roots.items()):
        if kind == "WAVE":
            marker = json.loads((root/".avac_qgis_wave_run.json").read_text(encoding="utf-8"))
            source = resolve_wave_source(root, marker)
            roots[source.resolve(strict=True)] = "AVAC"
    return roots


def local_runs(session, folder):
    """Copy complete run trees, then link scenarios to the owned avalanche."""
    import os
    from .project import atomic_text
    from avac_desktop.core.wave_project import resolve_wave_source
    roots = collect_runs(session)
    mapping = {}
    for source, kind in roots.items():
        target = source
        if not inside(source, folder):
            parent = folder/("runs" if kind == "AVAC" else "wave_runs")
            target = parent/source.name
            if target.exists():
                target = parent/(source.name+"-"+uuid.uuid4().hex[:12])
            if inside(target, source):
                raise ValueError("A copied run cannot be placed inside its source run.")
            shutil.copytree(source, target, copy_function=shutil.copy2)
        mapping[source] = target
    for source, kind in roots.items():
        if kind == "WAVE":
            target = mapping[source]
            filename = target/".avac_qgis_wave_run.json"
            marker = json.loads(filename.read_text(encoding="utf-8"))
            avalanche = mapping[resolve_wave_source(source, marker)]
            relative = os.path.relpath(avalanche, target)
            if marker.get("source_avac_run_relative") != relative:
                marker["source_avac_run_relative"] = relative
                atomic_text(filename, json.dumps(marker, indent=2)+"\n")
    if session.workspace and Path(session.workspace).resolve() != folder:
        cache = Path(session.workspace)/"analysis_results"
        target = folder/"analysis_results"
        if cache.is_dir():
            if inside(target, cache):
                raise ValueError("A copied sample cache cannot be placed inside itself.")
            shutil.copytree(cache, target, dirs_exist_ok=True, copy_function=shutil.copy2)
    return mapping


def local_terrain(terrain, folder):
    if terrain is None:
        return None
    if sha256_file(terrain.source) != terrain.source_hash:
        raise ValueError("Terrain changed since import. Reimport it before saving.")
    source = local_input(terrain.source, folder, raster=True)
    if source == terrain.source:
        return terrain
    digest = sha256_file(source)
    if digest != terrain.source_hash:
        # Materialized virtual rasters must retain the exact scientific grid.
        import numpy as np
        from .geo import read_terrain
        actual = read_terrain(source, terrain.raster.band)
        if not all(np.array_equal(getattr(actual.raster, key), getattr(terrain.raster, key), equal_nan=True)
                   for key in ("x", "y", "z")) or actual.raster.crs_authid != terrain.raster.crs_authid:
            raise ValueError("The copied terrain does not preserve the imported scientific grid.")
        return actual
    return replace(terrain, source=source)
