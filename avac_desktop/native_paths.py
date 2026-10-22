"""Short run-local execution paths for native 150-character filename fields."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import locale

from .geo import sha256_file
from .project import atomic_text

# Native controls put one quoted filename at the start of a line. Greedy
# matching retains apostrophes inside a legitimate Windows directory name;
# the final delimiter precedes optional whitespace/control description.
QUOTED = re.compile(r"(?m)^([ \t]*)(['\"])([^\r\n]*)\2(?=[ \t]*(?:=:|#|\r?$))")
ABSOLUTE_QUOTED = re.compile(r"(?m)^[ \t]*['\"](?:[A-Za-z]:[\\/]|/)")
MANIFEST = "desktop_execution_paths.json"


def stage_execution_paths(output: Path, root: Path) -> None:
    """Normalize paths in execution copies only; never change numerical text.

    The original AVAC/Wave `.data` files remain untouched. Raw scientific inputs
    stay at their established locations. Every changed reference resolves to
    exactly the same isolated-run file and is recorded with its SHA-256.
    """
    output,root = output.resolve(),root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Native execution output is outside its isolated run.")
    mappings,controls = [],[]
    for control in sorted(output.glob("*.data")):
        raw = control.read_bytes()
        try:
            original = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Legacy Clawpack uses open(...,'w') without an encoding; Windows
            # source runs therefore write their active locale (e.g. cp1252).
            # Decode with that same authoritative writer encoding, then make
            # run-local execution references independent of the parent name.
            original = raw.decode(locale.getencoding())
        def replace(match):
            value = match.group(3)
            target = Path(value)
            if not target.is_absolute():
                return match.group(0)
            target = target.resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"Native input must be an existing isolated-run file: {target}")
            relative = Path(os.path.relpath(target,output)).as_posix()
            if len(relative.encode("utf-8")) >= 150 or (output/relative).resolve() != target:
                raise ValueError("Native input reference cannot be represented safely in the solver filename field.")
            mappings.append(dict(control=control.relative_to(root).as_posix(),original_path=str(target),
                                 execution_path=relative,input_path=target.relative_to(root).as_posix(),sha256=sha256_file(target)))
            return match.group(1)+match.group(2)+relative+match.group(2)
        changed = QUOTED.sub(replace,original)
        if ABSOLUTE_QUOTED.search(changed):
            raise ValueError(f"Unrecognized absolute filename syntax in native control: {control}")
        if changed != original:
            atomic_text(control,changed)
        controls.append(dict(path=control.relative_to(root).as_posix(),sha256=sha256_file(control)))
    atomic_text(root/MANIFEST,json.dumps(dict(format=1,output=output.relative_to(root).as_posix(),
                                            references=mappings,controls=controls),indent=2)+"\n")


def verify_execution_paths(root: Path) -> None:
    root = root.resolve()
    payload = json.loads((root/MANIFEST).read_text(encoding="utf-8"))
    if payload.get("format") != 1:
        raise ValueError("Unsupported native input integrity manifest.")
    for record in [*payload["controls"],*[dict(path=r["input_path"],sha256=r["sha256"]) for r in payload["references"]]]:
        path = (root/record["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Prepared native input changed or is missing: {path}. Prepare a new run.")
