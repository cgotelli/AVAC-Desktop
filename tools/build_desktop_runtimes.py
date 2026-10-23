"""Package existing current-source Windows binaries with reviewed DLLs.

Build binaries first with tools/build_windows_solvers.py. This wrapper calls
the existing runtime builder and publishes desktop-only pinned descriptors.
It does not change numerical source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import shutil
import tempfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from avac_desktop.core.runtime import runtime_manifest_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain",type=Path,required=True, help="Solver compiler bin directory")
    parser.add_argument("--libraries",type=Path,default=ROOT/"build/windows-runtime-libraries",
                        help="Reviewed DLLs staged by fetch_windows_runtime.py")
    parser.add_argument("--version",default="0.1.6-dev4")
    args = parser.parse_args()
    output = ROOT/"avac_desktop"/"resources"
    output.mkdir(parents=True,exist_ok=True)
    libraries = ["libgcc_s_seh-1.dll","libgfortran-5.dll","libgomp-1.dll","libquadmath-0.dll","libwinpthread-1.dll","libdl.dll"]
    records = {}
    # Keep original Python bytes but use a normal compact package layout.
    # The upstream namespace __init__ already searches its own directory;
    # putting packages beside it needs no modifications to scientific code.
    # Examples, regression datasets and unused Fortran build trees do not
    # belong in the installed Python runtime and can exceed Windows MAX_PATH.
    source = ROOT/"native"/"clawpack-v5.14.0"
    stage_parent = ROOT/"build"
    stage_parent.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="desktop-clawpack-",dir=stage_parent)
    compact = Path(temporary.name)/"clawpack"
    package = compact/"clawpack"
    package.mkdir(parents=True)
    shutil.copy2(source/"clawpack"/"__init__.py",package/"__init__.py")
    layout = {"clawutil":"clawutil/src/python/clawutil","riemann":"riemann/riemann",
              "visclaw":"visclaw/src/python/visclaw","pyclaw":"pyclaw/src/pyclaw",
              "petclaw":"pyclaw/src/petclaw","forestclaw":"pyclaw/src/forestclaw",
              "classic":"classic/src/python/classic","amrclaw":"amrclaw/src/python/amrclaw",
              "geoclaw":"geoclaw/src/python/geoclaw","dclaw":"dclaw/src/python/dclaw"}
    for name,relative in layout.items():
        origin = source/relative
        if not origin.is_dir():
            continue
        for item in origin.rglob("*"):
            if item.is_file() and "__pycache__" not in item.parts and (item.suffix == ".py" or item.name == "log.config"):
                destination = package/name/item.relative_to(origin)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(item,destination)
    for kind in ("AVAC","WAVE"):
        archive = output/f"{kind.lower()}-desktop-windows-amd64-{args.version}.tar.gz"
        command = [sys.executable,str(ROOT/"tools"/"build_windows_runtime.py"),"--solver",str(ROOT/"native"/"src"/kind/"xgeoclaw.exe"),
                   "--backend",str(ROOT/"native"/"src"/kind),"--backend-name",kind,
                   "--clawpack",str(compact),"--runtime-version",args.version,
                   "--output",str(archive),"--license",str(ROOT/"native"/"clawpack-v5.14.0"/"LICENSE")]
        for library in libraries:
            command.extend(["--library",str(args.libraries.resolve()/library)])
        subprocess.run(command,cwd=ROOT,check=True)
        with tarfile.open(archive,"r:gz") as bundle:
            manifest = json.loads(bundle.extractfile("windows-amd64/runtime-manifest.json").read())
        source_hash = hashlib.sha256()
        for path in sorted([*(ROOT/"native"/"src"/kind).rglob("*"), *source.rglob("*")]):
            if path.is_file() and (path.suffix.lower() in (".f", ".f90", ".py", ".yaml") or path.name.startswith("Makefile")):
                source_hash.update(path.relative_to(ROOT).as_posix().encode()+b"\0"+path.read_bytes())
        descriptor = dict(kind=kind,platform="windows-amd64",runtime_version=args.version,archive=archive.name,
                          runtime_manifest_sha256=runtime_manifest_sha256(manifest),
                          source_repository="https://github.com/cgotelli/AVAC-Desktop",
                          source_tree_sha256=source_hash.hexdigest(),
                          python_layout="compact-clawpack-packages-v1",
                          build_toolchain="WinLibs GCC 13.2.0 / MinGW-w64 11.0.1 UCRT POSIX SEH r8",
                          runtime_libraries="MSYS2 UCRT GCC 16.2.0-6 with libgfortran locale fix; winpthreads 14.0.0.r495.g63ebe6cdb-2; dlfcn-win32 1.4.1")
        (output/f"{kind.lower()}-runtime.json").write_text(json.dumps(descriptor,indent=2)+"\n",encoding="utf-8")
        records[kind] = dict(descriptor=descriptor,solver_sha256=manifest["solver"]["sha256"])
    (ROOT/"build"/"native-runtimes.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    # TemporaryDirectory owns this newly generated path beneath build/.
    assert Path(temporary.name).resolve().parent == stage_parent.resolve()
    temporary.cleanup()


if __name__ == "__main__":
    main()
