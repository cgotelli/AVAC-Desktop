"""Thin desktop use cases around the existing scientific implementation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from avac_desktop.core.configuration import controlled_values, validate_controlled_values, validate_grid_contract
from avac_desktop.core.preprocessing import (AvacRaster, configuration_for_raster, initial_depth_from_release,
                                         release_coverage_from_rings, trim_raster_to_computational_grid)
from avac_desktop.core.run_project import prepare_isolated_runtime_run, read_run_metadata
from avac_desktop.core.runtime_execution import prepare_runtime_execution, runtime_solver
from avac_desktop.core.workspace import create_run_root, materialize_layer_sources

from .geo import sha256_file
from .project import ProjectSession, atomic_text
from .runtime import ensure_runtime
from .native_paths import stage_execution_paths,verify_execution_paths


def signature(session: ProjectSession) -> str:
    payload = dict(configuration=session.configuration, dem=session.terrain.source_hash if session.terrain else None,
                   release=session.release_hash, workspace=str(session.workspace))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate(session: ProjectSession, *, check_sources: bool = True) -> list[str]:
    issues: list[str] = []
    if session.terrain is None:
        return ["Import a terrain DEM first."]
    if not session.configuration:
        return ["No parameters loaded. Use File → Load standard parameters or Load AVAC configuration before preparation."]
    if not session.rings or session.release_path is None:
        issues.append("Import or draw release polygons in the terrain's coordinates.")
    try:
        controls = controlled_values(session.configuration)
        issues.extend(validate_controlled_values(controls))
        # Existing validator is retained; add finite checks before serialization.
        enum_fields = {"rheology.model","computation.boundary","computation.limiter","output.output_format","animation.variable"}
        for key, value in controls.items():
            if key not in enum_fields:
                try:
                    finite = np.all(np.isfinite(np.asarray(value,dtype=float)))
                except (ValueError,TypeError,OverflowError):
                    finite = False
                if not finite:
                    issues.append(f"{key} must contain finite numeric values.")
        required = {"computation.boundary":"extrap","output.output_format":"binary32","output.verbosity":0,"animation.variable":"depth"}
        for key,value in required.items():
            if controls[key] != value:
                issues.append(f"Desktop preparation requires {key} = {value!r}, matching the established production workflow.")
        rho = float(controls["rheology.rho"])
        if not np.isfinite(rho) or rho <= 0:
            issues.append("Avalanche density must be positive and finite.")
        config = configuration_for_raster(session.configuration, session.terrain.raster)
        issues.extend(validate_grid_contract(config, float(session.terrain.raster.metadata["cellsize"])))
        if np.any(~np.isfinite(session.terrain.raster.z)):
            issues.append("Terrain contains NoData/non-finite cells. Select an explicit complete computation domain before preparation.")
        if check_sources:
            if sha256_file(session.terrain.source) != session.terrain.source_hash:
                issues.append("Terrain file changed after import. Reload it and prepare again.")
            if session.release_path and sha256_file(session.release_path) != session.release_hash:
                issues.append("Release file changed after import. Reload it and prepare again.")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        issues.append(str(exc))
    return issues


def preview(session: ProjectSession, task=None) -> tuple[AvacRaster, np.ndarray, np.ndarray]:
    issues = validate(session)
    if issues:
        raise ValueError("\n".join(issues))
    raster = trim_raster_to_computational_grid(session.terrain.raster, float(session.configuration["computation"]["cell_size"]))
    coverage = release_coverage_from_rings(session.rings, raster.x, raster.y, float(raster.metadata["cellsize"]),
                                         cancelled=task.cancelled.is_set if task else None)
    if not np.any(coverage > 0):
        raise ValueError("Release polygons do not intersect the computation grid.")
    depth = initial_depth_from_release(raster, coverage, session.configuration["release"])
    return raster, coverage, depth


def prepare(session: ProjectSession, task=None) -> dict[str, Any]:
    issues = validate(session)
    if issues:
        raise ValueError("\n".join(issues))
    if session.workspace is None:
        raise ValueError("Choose a writable working directory before preparing a run.")
    runtime = ensure_runtime()
    run_id, root = create_run_root(session.workspace)
    provenance = materialize_layer_sources(root, str(session.terrain.source), str(session.release_path),
                                           session.terrain.raster.crs_authid, session.terrain.raster.crs_authid)
    template = root / "inputs" / "desktop_configuration.yaml"
    atomic_text(template, yaml.safe_dump(session.configuration, sort_keys=False))
    metadata = dict(plugin="AVAC Desktop", desktop_version="0.1.2", source_dem=str(session.terrain.source),
                    dem_crs=session.terrain.raster.crs_authid, release_layer=str(session.release_path),
                    runtime=str(runtime), execution_mode="bundled_runtime", input_provenance=provenance,
                    desktop_input_signature=signature(session), desktop_project_id=session.project_id)
    prepared = prepare_isolated_runtime_run(root, runtime/"backend"/"AVAC", session.terrain.raster, session.rings,
                                            template, deepcopy(session.configuration["release"]), metadata,
                                            controlled_values(session.configuration),
                                            progress=task.signals.progress.emit if task else None,
                                            cancelled=task.cancelled.is_set if task else None)
    # Only a newly created, owned run reaches staging; never open/re-stage a
    # completed imported output directory through this use case.
    output = prepare_runtime_execution(runtime, prepared.avac_dir)
    stage_execution_paths(output,root)
    return dict(prepared=prepared, runtime=runtime, output=output, signature=signature(session), run_id=run_id)


def verify_ready(session: ProjectSession) -> tuple[Path, Path]:
    if session.prepared_run is None or session.prepared_signature != signature(session):
        raise ValueError("Inputs changed or no run is prepared. Prepare a new isolated run.")
    root = session.prepared_run
    metadata = read_run_metadata(root)
    if metadata.get("status") != "prepared":
        raise ValueError("Only an unstarted prepared run can be launched. Prepare a new run.")
    issues = validate(session)
    if issues:
        raise ValueError("\n".join(issues))
    runtime = Path(metadata["runtime"])
    verify_execution_paths(root)
    return root, runtime_solver(runtime)
