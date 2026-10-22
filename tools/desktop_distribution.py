"""Prepare offline notices/source and audit the exact Windows distribution."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/"build"/"desktop-distribution"
CACHE = ROOT/"build"/"distribution-sources"


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")


def fetch(url, expected=None):
    url = url.replace("http://", "https://", 1)
    lock = ROOT/"packaging"/"windows"/"distribution-sources.lock.json"
    if expected is None and lock.exists():
        expected = next((entry["sha256"] for entry in json.loads(lock.read_text(encoding="utf-8")) if entry["url"] == url), None)
    CACHE.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    if "codeload.github.com/mingw-w64" in url:
        filename = "mingw-w64-v11.0.1.tar.gz"
    target = CACHE/filename
    if not target.exists():
        print("Downloading", url, flush=True)
        temporary = target.with_suffix(target.suffix+".part")
        # An officially listed mirror avoids a broken TLS chain on some of
        # Qt's redirect-selected mirrors; certificate validation stays enabled.
        download_url = url.replace("https://download.qt.io/", "https://qt.mirror.constant.com/")
        request = urllib.request.Request(download_url, headers={"User-Agent": "AVAC-Desktop-source-packaging/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(target)
    digest = sha(target)
    if expected and digest != expected:
        raise ValueError(f"Source checksum mismatch: {url}: {digest} != {expected}")
    return target, dict(url=url, filename=target.name, sha256=digest, bytes=target.stat().st_size)


def recipe_sources(info):
    for filename in ("recipe/rendered_recipe.yaml", "recipe/meta.yaml", "recipe/parent/meta.yaml"):
        path = info/filename
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data = data.get("recipe", data)
        source = data.get("source")
        if source:
            return source if isinstance(source, list) else [source]
    raise ValueError(f"No resolved source recipe in {info}")


def prepare_legal():
    licenses, sources = STAGE/"Licenses", STAGE/"Source"/"third-party"
    licenses.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    components, downloads = [], []
    for path in sorted((Path(sys.prefix)/"conda-meta").glob("*.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        info = Path(package["extracted_package_dir"])/"info"
        name = package["name"]
        destination = licenses/"conda"/name
        destination.mkdir(parents=True, exist_ok=True)
        for child in ("licenses", "recipe"):
            if (info/child).is_dir():
                shutil.copytree(info/child, destination/child, dirs_exist_ok=True)
        write_json(destination/"package.json", {key: package.get(key) for key in
                   ("name", "version", "build", "license", "url", "sha256", "depends")})
        components.append(dict(name=name, version=package["version"], license=package.get("license"),
                               origin="conda-forge", binary_url=package.get("url")))
        if any(word in package.get("license", "") for word in ("GPL", "MPL")):
            for source in recipe_sources(info):
                url = source.get("url")
                if isinstance(url, list):
                    url = url[0]
                if not url or "${" in url or "{{" in url:
                    raise ValueError(f"Unresolved source: {name}: {source}")
                downloads.append((name, url, source.get("sha256")))
    # Include exact pip metadata and all supplied license/copyright notices.
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        destination = licenses/"python"/name
        destination.mkdir(parents=True, exist_ok=True)
        for entry in dist.files or []:
            value = str(entry).lower()
            if any(word in value for word in ("license", "copying", "copyright", "notice")) or entry.name == "METADATA":
                source = Path(dist.locate_file(entry))
                if source.is_file() and ".." not in entry.parts:
                    target = destination/(hashlib.sha256(str(entry).encode()).hexdigest()[:10]+"-"+entry.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        components.append(dict(name=name, version=dist.version, origin="python distribution",
                               license=dist.metadata.get("License-Expression") or dist.metadata.get("License")))
        if name.lower() == "pyinstaller":
            with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{dist.version}/json", timeout=60) as response:
                data = json.load(response)
            item = next(item for item in data["urls"] if item["packagetype"] == "sdist")
            downloads.append((name, item["url"], item["digests"]["sha256"]))
    for module in ("qtbase", "qtsvg", "qtmultimedia", "qtimageformats", "qttranslations", "qttools"):
        url = f"https://download.qt.io/archive/qt/6.8/6.8.3/submodules/{module}-everywhere-src-6.8.3.tar.xz"
        with urllib.request.urlopen(url+".sha256", timeout=60) as response:
            expected = response.read().decode().split()[0]
        downloads.append((module, url, expected))
    downloads.extend([
        ("pyside-setup", "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz", "d2c896f7f1a6a7ea4c9f98cfe317272fd139703ddf612b86999f09e48aeef0e6"),
        ("ffmpeg", "https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz", None),
        ("gcc-runtime", "https://gcc.gnu.org/pub/gcc/releases/gcc-13.2.0/gcc-13.2.0.tar.xz", None),
        ("mingw-w64", "https://codeload.github.com/mingw-w64/mingw-w64/tar.gz/refs/tags/v11.0.1", None),
    ])
    records = []
    def download(item):
        name, url, expected = item
        path, record = fetch(url, expected)
        target = sources/name/path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        record["component"] = name
        # Qt includes bundled codecs/fonts and attribution files. Keep their
        # notices alongside its primary GPL/LGPL texts, not just a URL.
        if name.startswith(("qt", "pyside")) or name == "ffmpeg":
            notice_index = []
            with tarfile.open(path) as archive:
                for member in archive:
                    lower = member.name.lower()
                    if member.isfile() and any(word in lower for word in ("license", "copying", "copyright", "qt_attributions.json")):
                        notice = hashlib.sha256(member.name.encode()).hexdigest()[:12]+"-"+Path(member.name).name
                        target = licenses/"upstream"/name/notice
                        if not target.resolve().is_relative_to(licenses.resolve()):
                            raise ValueError("Unsafe source notice path")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.extractfile(member).read())
                        notice_index.append(dict(original=member.name, notice=notice))
            write_json(licenses/"upstream"/name/"NOTICE_INDEX.json", notice_index)
        return record
    with ThreadPoolExecutor(max_workers=4) as executor:
        for record in executor.map(download, downloads):
            records.append(record)
            print("Source ready:", record["component"], flush=True)
    shutil.copytree(ROOT/"tools"/"windows_runtime_licenses", licenses/"native-runtime", dirs_exist_ok=True)
    nsis = Path(os.environ["AVAC_NSIS_DIR"])/"COPYING"
    if nsis.is_file():
        shutil.copy2(nsis, licenses/"NSIS-COPYING.txt")
    for filename in ("LICENSE", "DISCLAIMER.txt", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT/filename, STAGE/filename)
    write_json(licenses/"COMPONENTS.json", components)
    write_json(sources/"SOURCES.json", records)
    write_json(ROOT/"packaging"/"windows"/"distribution-sources.lock.json", records)
    (STAGE/"Source"/"README.txt").write_text(
        "AVAC Desktop source and dependency sources\n\n"
        "avac-desktop-source.zip contains the matching working-tree source, build\n"
        "scripts, scientific backend sources and source-file hashes. The\n"
        "third-party directory contains corresponding upstream sources for Qt,\n"
        "PySide6/Shiboken, FFmpeg, copyleft GIS libraries and GCC runtime.\n"
        "Conda build recipes and patches are under ../Licenses/conda/<package>/recipe.\n"
        "Versions, binary URLs, copyright and license texts are under ../Licenses.\n"
        "The notices include a superset of the build environment; the exact\n"
        "installed binaries are recorded in INSTALLATION_FILES.json.\n\n"
        "Qt/PySide6 and FFmpeg are dynamically linked. You may replace compatible\n"
        "libraries under ../_internal in accordance with their licenses, and\n"
        "reverse engineer for debugging modifications to those libraries. No\n"
        "installer restriction or integrity check prevents running modified\n"
        "compatible Qt/FFmpeg libraries. Native solver runtime archives separately\n"
        "authenticate their scientific components; source rebuild instructions\n"
        "and the runtime-archive builder are included. No license rights are waived.\n",
        encoding="utf-8")
    print("Offline license/source staging:", STAGE)


def snapshot_source():
    git = shutil.which("git") or "git"
    files = subprocess.check_output([git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT).decode().split("\0")
    roots = {"avac_desktop", "native", "packaging", "tools", "docs"}
    top = {"LICENSE", "DISCLAIMER.txt", "THIRD_PARTY_NOTICES.md", "README.md", "pyproject.toml", "AVACDesktop.spec", "desktop_launcher.py", "Launch AVAC Desktop.cmd", ".gitignore", ".gitattributes", "CONTRIBUTING.md"}
    target = STAGE/"Source"/"avac-desktop-source.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(set(files)):
            path = Path(name)
            if not name or (path.parts[0] not in roots and name not in top):
                continue
            if any(part in {"__pycache__", ".pytest_cache"} for part in path.parts) or not (ROOT/path).is_file():
                continue
            archive.write(ROOT/path, "AVACDesktop/"+path.as_posix())
            records.append(dict(path=path.as_posix(), sha256=sha(ROOT/path)))
        archive.writestr("AVACDesktop/SOURCE_MANIFEST.json", json.dumps(records, indent=2)+"\n")
    print("Matching project source:", len(records), "files;", target.stat().st_size, "bytes")


def installer_files():
    """Record the payload and compile exact, non-recursive uninstall paths."""
    bundle = ROOT/"dist"/"AVACDesktop"
    rows = {}
    for folder, prefix in ((bundle, Path()), (STAGE/"Licenses", Path("Licenses")), (STAGE/"Source", Path("Source"))):
        for path in folder.rglob("*"):
            if path.is_file():
                relative = prefix/path.relative_to(folder)
                rows[relative.as_posix()] = dict(path=relative.as_posix(), bytes=path.stat().st_size, sha256=sha(path))
    for name in ("INSTALL.txt", "LICENSE", "DISCLAIMER.txt", "THIRD_PARTY_NOTICES.md"):
        path = STAGE/name
        rows[name] = dict(path=name, bytes=path.stat().st_size, sha256=sha(path))
    write_json(STAGE/"INSTALLATION_FILES.json", dict(format=1, version="0.1.3-preview.1", files=list(rows.values())))
    paths = [Path(name) for name in rows]+[Path("INSTALLATION_FILES.json")]
    directories = set()
    for path in paths:
        directories.update(p for p in path.parents if p != Path("."))
    def nsis_path(path):
        return str(path).replace("$", "$$").replace('"', '$\\"')
    lines = [f'Delete "$INSTDIR\\{nsis_path(path)}"' for path in paths]
    lines += [f'RMDir "$INSTDIR\\{nsis_path(path)}"' for path in sorted(directories, key=lambda p: (-len(p.parts), str(p)))]
    (STAGE/"uninstall-files.nsh").write_text("\n".join(lines)+"\n", encoding="utf-8-sig")
    size = sum(row["bytes"] for row in rows.values())
    (STAGE/"size-kib.txt").write_text(str((size+1023)//1024), encoding="ascii")
    print("Installer payload:", len(rows), "files;", round(size/1024**2, 1), "MiB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("legal", "source", "installer-files"))
    args = parser.parse_args()
    {"legal": prepare_legal, "source": snapshot_source, "installer-files": installer_files}[args.action]()


if __name__ == "__main__":
    main()
