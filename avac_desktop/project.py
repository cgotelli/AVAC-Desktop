"""Shared session and atomic, versioned project persistence (no Qt)."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import uuid

from avac_desktop.core.configuration import load_complete_configuration
from .geo import Rings, Terrain

FORMAT = "avac-desktop-project"
SCHEMA_VERSION = 1


def validate_raster_styles(styles):
    import math
    if not isinstance(styles, dict):
        raise ValueError("Invalid raster appearance settings.")
    for key, style in styles.items():
        if not isinstance(key, str) or not isinstance(style, dict):
            raise ValueError("Invalid raster appearance settings.")
        limits = style.get("limits")
        if limits is not None and (not isinstance(limits, (list, tuple)) or len(limits) != 2 or
            not all(isinstance(v, (int, float)) and math.isfinite(v) for v in limits) or limits[0] >= limits[1]):
            raise ValueError("Invalid raster colour limits.")
        opacity = style.get("opacity", 1.)
        if not isinstance(opacity, (int, float)) or not math.isfinite(opacity) or not 0 <= opacity <= 1:
            raise ValueError("Raster opacity must be between zero and one.")


def atomic_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class ProjectSession:
    name: str = "Untitled avalanche project"
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_path: Path | None = None
    workspace: Path | None = None
    terrain: Terrain | None = None
    release_path: Path | None = None
    release_export_path: Path | None = None
    release_hash: str | None = None
    rings: Rings = field(default_factory=list)
    release_edited: bool = False
    sketch_lines: list = field(default_factory=list)
    analysis_features: list = field(default_factory=list)
    analysis_paths: list[Path] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)
    mode: str = "model_run"
    selected_run: Path | None = None
    variable: str = "depth"
    frame_index: int = 0
    map_extent: list[float] | None = None
    layers: dict[str, bool] = field(default_factory=lambda: {"terrain": True, "release": True})
    raster_styles: dict = field(default_factory=dict)
    dirty: bool = False
    threads: int = field(default_factory=lambda: min(8, os.cpu_count() or 1))
    prepared_run: Path | None = None
    prepared_signature: str | None = None
    runs: list[Path] = field(default_factory=list)
    wave_enabled: bool = False
    lake_path: Path | None = None
    selected_wave: Path | None = None
    analysis_kind: str = "avac"
    result_page: str = "analyze"
    execution_root: Path | None = None
    execution_kind: str | None = None
    execution_registered: bool = True
    result_notice: str = ""
    wave_setup: dict[str, Any] = field(default_factory=lambda: dict(duration=None, water_level=0., cell_size=2., damping=.3,
                        cfl_target=.5, cfl_max=1., dry_limit=.0001, land_strickler=10., water_strickler=30.,
                        friction_depth_limit=20., wave_tolerance_flag=.2, limiter="vanleer"))

    def set_mode(self, mode: str) -> None:
        if mode not in ("model_run", "analyze"):
            raise ValueError(f"Unknown application mode {mode!r}")
        self.mode = mode


def save_project(session: ProjectSession, path: Path) -> None:
    from dataclasses import replace
    from .geo import sha256_file
    from .project_storage import local_input, local_runs, local_terrain
    path = path.expanduser().resolve()
    validate_raster_styles(session.raster_styles)
    # Build a new state first. A copy or manifest failure must not redirect
    # the live project away from its last successfully saved files.
    local = replace(session)
    local.release_export_path = session.release_export_path or (session.release_path if not session.release_edited else None)
    local.terrain = local_terrain(session.terrain, path.parent)
    if not session.release_edited:
        if session.release_path and session.release_hash and sha256_file(session.release_path) != session.release_hash:
            raise ValueError("Release polygons changed since import. Reimport them before saving.")
        local.release_path = local_input(session.release_path, path.parent)
        local.release_hash = sha256_file(local.release_path) if local.release_path else None
    local.lake_path = local_input(session.lake_path, path.parent)
    shapes = dict.fromkeys([*session.analysis_paths, *(feature["path"] for feature in session.analysis_features)])
    shape_map = {source: local_input(source, path.parent) for source in shapes}
    local.analysis_paths = list(dict.fromkeys(shape_map.values()))
    local.analysis_features = [dict(feature, path=shape_map[feature["path"]]) for feature in session.analysis_features]
    runs = local_runs(session, path.parent)
    def relocated(root):
        return runs[Path(root).resolve()] if root is not None else None
    local.selected_run, local.selected_wave = relocated(session.selected_run), relocated(session.selected_wave)
    local.execution_root = relocated(session.execution_root)
    local.runs = [relocated(root) for root in session.runs]
    if session.workspace != path.parent:
        local.prepared_run = local.prepared_signature = None
    _write_project(local, path)
    session.__dict__.update(local.__dict__)


def _write_project(session: ProjectSession, path: Path) -> None:
    import yaml
    path = path.expanduser().resolve()
    validate_raster_styles(session.raster_styles)
    # Immutable configuration snapshot first, then atomically replace the
    # manifest. A power loss cannot leave an old manifest pointing at new YAML.
    config_path = path.parent / f"{path.stem}.config" / f"AVAC-{uuid.uuid4().hex}.yaml"
    atomic_text(config_path, yaml.safe_dump(session.configuration, sort_keys=False))
    release_path, release_hash = session.release_path, session.release_hash
    if session.release_edited and session.terrain and session.rings:
        from .geometry import release_geojson
        from .geo import sha256_file
        release_path = config_path.parent / f"releases-{uuid.uuid4().hex}.geojson"
        atomic_text(release_path, release_geojson(session.rings, session.terrain.raster.crs_authid))
        release_hash = sha256_file(release_path)
    elif session.release_edited and not session.rings:
        release_path = release_hash = None

    def relative(item: Path | None) -> str | None:
        if item is None:
            return None
        try:
            return os.path.relpath(item, path.parent)
        except ValueError:  # Windows volume differs.
            return str(item)

    payload = dict(format=FORMAT, schema_version=SCHEMA_VERSION, project_id=session.project_id,
                   project_name=path.stem, workspace=".",
                   inputs=dict(avac_dem=relative(session.terrain.source) if session.terrain else None,
                               release_polygons=relative(release_path), release_export_source=relative(session.release_export_path or (session.release_path if not session.release_edited else None)),
                               lake_polygon=relative(session.lake_path)),
                   configuration=dict(avac_yaml=relative(config_path)),
                   provenance=dict(dem_sha256=session.terrain.source_hash if session.terrain else None,
                                   release_sha256=release_hash),
                   geometry=dict(release_edited=session.release_edited, sketch_lines=session.sketch_lines,
                                 sampling_shapefiles=[relative(item) for item in dict.fromkeys(
                                     [*session.analysis_paths, *(feature["path"] for feature in session.analysis_features)])]),
                   selected_runs=dict(avac=relative(session.selected_run), wave=relative(session.selected_wave)),
                   execution=(dict(kind=session.execution_kind, run=relative(session.execution_root),
                                   registered=session.execution_registered) if session.execution_root else None),
                   wave_extension=dict(enabled=session.wave_enabled, setup=session.wave_setup),
                   ui=dict(last_mode=session.mode, variable=session.variable, frame_index=session.frame_index, analysis_kind=session.analysis_kind, result_page=session.result_page,
                           map_extent=session.map_extent, layers=session.layers, threads=session.threads,
                           raster_styles=session.raster_styles))
    atomic_text(path, json.dumps(payload, indent=2, allow_nan=False) + "\n")
    session.project_path, session.dirty = path, False
    session.name = path.stem
    session.workspace = path.parent
    session.release_path, session.release_hash = release_path, release_hash


def load_project(path: Path) -> tuple[ProjectSession, Path | None, dict[str, Any]]:
    path = path.expanduser().resolve(strict=True)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Project manifest is too large.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported AVAC project format/version; original file was left unchanged.")

    def resolve(value: str | None) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Project contains an invalid file reference.")
        result = Path(value).expanduser()
        return (result if result.is_absolute() else path.parent / result).resolve()

    ui = payload.get("ui", {})
    config_path = resolve(payload["configuration"]["avac_yaml"])
    import yaml
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = {} if config == {} else load_complete_configuration(config_path)
    mode = ui.get("last_mode", "model_run")
    session = ProjectSession(name=payload["project_name"], project_id=payload["project_id"], project_path=path,
                             workspace=path.parent,
                             release_path=resolve(payload.get("inputs", {}).get("release_polygons")),
                             selected_run=resolve(payload.get("selected_runs", {}).get("avac")),
                             selected_wave=resolve(payload.get("selected_runs", {}).get("wave")),
                             lake_path=resolve(payload.get("inputs", {}).get("lake_polygon")),
                             configuration=config,
                             variable=ui.get("variable", "depth"), frame_index=int(ui.get("frame_index", 0)),
                             map_extent=ui.get("map_extent"), layers=ui.get("layers", {"terrain": True, "release": True}),
                             threads=max(1, min(os.cpu_count() or 1, int(ui.get("threads", 1)))))
    session.set_mode(mode)
    session.raster_styles = ui.get("raster_styles", {})
    validate_raster_styles(session.raster_styles)
    geometry = payload.get("geometry", {})
    session.release_edited = bool(geometry.get("release_edited", False))
    session.sketch_lines = geometry.get("sketch_lines", [])
    session.analysis_paths = [resolve(item) for item in geometry.get("sampling_shapefiles", [])]
    import numpy as np
    for line in session.sketch_lines:
        coords = np.asarray(line, dtype=float)
        if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 2 or not np.all(np.isfinite(coords)):
            raise ValueError("Invalid saved sketch line.")
    session.wave_enabled = bool(payload.get("wave_extension", {}).get("enabled", False))
    session.wave_setup.update(payload.get("wave_extension", {}).get("setup", {}))
    session.analysis_kind = ui.get("analysis_kind", "avac")
    inputs = payload.get("inputs", {})
    session.release_export_path = resolve(inputs["release_export_source"]) if "release_export_source" in inputs else session.release_path
    session.result_page = ui.get("result_page", "analyze")
    if session.result_page not in ("analyze", "profiles", "gauges"):
        raise ValueError("Unsupported results page.")
    if session.analysis_kind not in ("avac", "wave", "combined"):
        raise ValueError("Unsupported analysis dataset kind.")
    execution = payload.get("execution")
    if execution:
        session.execution_kind = execution.get("kind")
        session.execution_root = resolve(execution.get("run"))
        session.execution_registered = bool(execution.get("registered", False))
        if session.execution_kind not in ("AVAC", "WAVE") or session.execution_root is None:
            raise ValueError("Invalid saved execution reference.")
        if not session.execution_registered:
            try:
                avac, water = completed_selection(session.execution_root, session.execution_kind, session.project_id)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                session.result_notice = f"The last simulation is not available as a completed result: {exc}. Previous completed results are retained."
            else:
                session.selected_run, session.selected_wave = avac, water
                session.analysis_kind = "combined" if water else "avac"
                session.variable = "surface_displacement" if water else "depth"
                session.frame_index, session.result_page, session.mode = 0, "analyze", "analyze"
                # A later manual Save should commit the recovered selection,
                # rather than leaving a pending reference to override it again.
                session.execution_registered = True
                session.result_notice = "Recovered completed results from the saved run reference."
    provenance = payload.get("provenance", {})
    # Older manifests can predate result registration. Inspect only their
    # declared project folders and small markers, never arbitrary run trees.
    folders = [path.parent]
    legacy_workspace = resolve(payload.get("workspace"))
    if legacy_workspace and legacy_workspace not in folders:
        folders.append(legacy_workspace)
    discover_project_results(session, provenance, folders)
    return session, resolve(payload.get("inputs", {}).get("avac_dem")), provenance


def discover_project_results(session, provenance, folders):
    """Restore completed project results read only, including older manifests."""
    import hashlib
    from datetime import datetime

    def completed(root, kind):
        if root is None:
            return None
        try:
            marker = _run_marker(root, kind)
            return marker if marker.get("status") == "completed" else None
        except (OSError, ValueError, TypeError):
            return None

    def order(entry):
        root, marker = entry
        try:
            stamp = datetime.fromisoformat(marker.get("updated_at") or marker.get("created_at")).timestamp()
        except (TypeError, ValueError, OverflowError, OSError):
            stamp = 0.
        return stamp, root.name

    def candidates(folder, child, kind):
        directory = folder/child
        if not directory.is_dir():
            return
        try:
            for root in directory.iterdir():
                if root.is_dir():
                    marker = completed(root, kind)
                    if marker:
                        yield root.resolve(), marker
        except OSError:
            return

    avac = {}
    for folder in folders:
        legacy_signature = None
        if session.configuration and provenance.get("dem_sha256") and provenance.get("release_sha256"):
            payload = dict(configuration=session.configuration, dem=provenance["dem_sha256"],
                           release=provenance["release_sha256"], workspace=str(folder))
            legacy_signature = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        for root, marker in candidates(folder, "runs", "AVAC"):
            owner = marker.get("desktop_project_id")
            if owner == session.project_id or (owner is None and legacy_signature
                    and marker.get("desktop_input_signature") == legacy_signature):
                avac[root] = marker

    selected_marker = completed(session.selected_run, "AVAC")
    water_marker = completed(session.selected_wave, "WAVE")
    water_source = None
    if water_marker:
        try:
            from avac_desktop.core.wave_project import resolve_wave_source
            water_source = resolve_wave_source(session.selected_wave, water_marker)
        except (KeyError, TypeError, ValueError):
            water_marker = None
        if completed(water_source, "AVAC") is None:
            water_marker = None
    active_valid = bool(water_marker if session.analysis_kind in ("wave", "combined") else selected_marker)
    changed = False
    # Explicit saved links remain authoritative, including imported older runs.
    if selected_marker:
        avac[session.selected_run] = selected_marker
    elif water_marker:
        source = water_source
        marker = completed(source, "AVAC")
        if marker:
            session.selected_run, selected_marker = source, marker
            avac[source] = marker
            changed = True
    if not selected_marker and avac:
        session.selected_run, selected_marker = max(avac.items(), key=order)
        changed = True
    session.runs = [root for root, _ in sorted(avac.items(), key=order)]

    if session.selected_run and not water_marker:
        water = []
        for folder in folders:
            for root, marker in candidates(folder, "wave_runs", "WAVE"):
                owner = marker.get("desktop_project_id")
                try:
                    from avac_desktop.core.wave_project import resolve_wave_source
                    source = resolve_wave_source(root, marker)
                except (KeyError, TypeError, ValueError):
                    continue
                if (owner is None or owner == session.project_id) and source == session.selected_run and source in avac:
                    water.append((root, marker))
        if water:
            session.selected_wave, water_marker = max(water, key=order)
            changed = True
    if changed:
        if not active_valid:
            session.analysis_kind = "combined" if water_marker else "avac"
            session.variable = "surface_displacement" if water_marker else "depth"
            session.frame_index, session.result_page, session.mode = 0, "analyze", "analyze"
        session.result_notice += ("\n" if session.result_notice else "")+"Automatically detected completed calculations for this project."


def _checkpoint_payload(session):
    if session.project_path is None:
        raise ValueError("Save the project before recording a simulation.")
    path = session.project_path
    if path.stat().st_size > 2_000_000:
        raise ValueError("Project manifest is too large.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("format") != FORMAT or payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("project_id") != session.project_id):
        raise ValueError("The saved project identity changed; save it explicitly before recording results.")
    return path, payload


def _run_marker(root, kind):
    filename = ".avac_qgis_run.json" if kind == "AVAC" else ".avac_qgis_wave_run.json"
    marker = json.loads((root/filename).read_text(encoding="utf-8"))
    if not isinstance(marker, dict) or marker.get("format") != 1:
        raise ValueError("Unsupported simulation marker.")
    return marker


def _owned_marker(root, kind, project_id):
    if kind not in ("AVAC", "WAVE"):
        raise ValueError("Unsupported simulation kind.")
    marker = _run_marker(root, kind)
    if marker.get("desktop_project_id", project_id) != project_id:
        raise ValueError("This simulation belongs to another project.")
    return marker


def completed_selection(root, kind, project_id):
    root = Path(root).resolve()
    marker = _owned_marker(root, kind, project_id)
    if marker.get("status") != "completed":
        raise ValueError(f"{kind} run is marked {marker.get('status', 'unknown')}")
    if kind == "AVAC":
        return root, None
    from avac_desktop.core.wave_project import resolve_wave_source
    source = resolve_wave_source(root, marker)
    if _run_marker(source, "AVAC").get("status") != "completed":
        raise ValueError("The linked avalanche is not completed.")
    return source, root


def record_execution(session, root, kind):
    """Record the explicit owned run before launch, preserving saved inputs."""
    path, payload = _checkpoint_payload(session)
    root = Path(root).resolve()
    if _owned_marker(root, kind, session.project_id).get("status") != "prepared":
        raise ValueError("Record only an unstarted prepared calculation.")
    payload["execution"] = dict(kind=kind, run=os.path.relpath(root, path.parent), registered=False)
    atomic_text(path, json.dumps(payload, indent=2, allow_nan=False)+"\n")
    session.execution_root, session.execution_kind, session.execution_registered = root, kind, False


def record_completed_results(session, root, kind):
    """Atomically save result links/UI defaults without saving parameter edits."""
    path, payload = _checkpoint_payload(session)
    avac, water = completed_selection(root, kind, session.project_id)
    def relative(item):
        if item is None:
            return None
        try:
            return os.path.relpath(item, path.parent)
        except ValueError:
            return str(item)
    payload["selected_runs"] = dict(avac=relative(avac), wave=relative(water))
    payload["execution"] = dict(kind=kind, run=relative(Path(root).resolve()), registered=True)
    payload.setdefault("ui", {}).update(last_mode="analyze", analysis_kind="combined" if water else "avac",
                                       variable="surface_displacement" if water else "depth", frame_index=0, result_page="analyze")
    atomic_text(path, json.dumps(payload, indent=2, allow_nan=False)+"\n")
    session.execution_root, session.execution_kind, session.execution_registered = Path(root).resolve(), kind, True
