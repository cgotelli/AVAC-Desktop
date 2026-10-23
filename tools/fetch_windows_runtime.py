"""Fetch hash-pinned Windows numerical DLLs, including the libgfortran locale fix."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, required=True,
                        help='WinLibs bin directory (supplies libdl.dll)')
    parser.add_argument('--zstd', default=shutil.which('zstd'),
                        help='zstd executable for unpacking MSYS2 packages')
    parser.add_argument('--output', type=Path, default=ROOT/'build/windows-runtime-libraries')
    args = parser.parse_args()
    if not args.zstd:
        parser.error('Install zstd or supply --zstd with its executable path.')
    manifest = json.loads((ROOT/'tools/windows_runtime_licenses/manifest.json').read_text())
    cache = ROOT/'build/windows-runtime-packages'
    cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for package in manifest['runtime_packages']:
        path = cache/package['url'].rsplit('/', 1)[-1]
        if not path.exists():
            with urllib.request.urlopen(package['url'], timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != package['sha256']:
                raise ValueError(f'Package hash mismatch: {path.name}')
            path.write_bytes(data)
        if hashlib.sha256(path.read_bytes()).hexdigest() != package['sha256']:
            raise ValueError(f'Cached package hash mismatch: {path}')
        data = subprocess.check_output([args.zstd, '-d', '-c', str(path)])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for name, digest in manifest['libraries'].items():
                member = next((m for m in archive if m.name == f'ucrt64/bin/{name}'), None)
                if member is None:
                    continue
                if not member.isfile():
                    raise ValueError(f'Expected an ordinary DLL: {member.name}')
                data = archive.extractfile(member).read()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError(f'DLL hash mismatch: {name}')
                (args.output/name).write_bytes(data)
    # The existing solver also links dlfcn-win32 from the compiler distribution.
    data = (args.toolchain/'libdl.dll').read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest['libraries']['libdl.dll']:
        raise ValueError('Unexpected WinLibs libdl.dll')
    (args.output/'libdl.dll').write_bytes(data)
    for name, digest in manifest['libraries'].items():
        if hashlib.sha256((args.output/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Runtime DLL is missing or changed: {name}')
    print(f'Verified numerical runtime DLLs: {args.output.resolve()}')


if __name__ == '__main__':
    main()
