"""Fetch and verify the tutorial inputs bundled with AVAC Desktop."""
import argparse
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = '1d6eec1e36ceb95e3c9bab6fd59c58ea91408df2'
FILES = [{'name': 'topo_cut_dam_1m.tif', 'sha256': '138da571816c271716354e508e612ce75f71300c3326045459747b9b71726165'}, {'name': 'avalanches.geojson', 'sha256': '8d4e34b348513510606fd2ee372116fe730cbb7c4d6e311afd0bcb3da0360482'}]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_tutorial(folder):
    for record in FILES:
        path = folder/record['name']
        if not path.is_file() or digest(path) != record['sha256']:
            raise ValueError(f'Missing or changed tutorial input: {path}. Run python tools/fetch_tutorial.py before packaging.')
    return [folder/record['name'] for record in FILES]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT/'tutorial')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    folder = args.directory
    if args.verify_only:
        verify_tutorial(folder)
        return
    folder.mkdir(parents=True, exist_ok=True)
    for record in FILES:
        target = folder/record['name']
        if target.exists():
            if digest(target) != record['sha256']:
                raise ValueError(f'Refusing to overwrite a different existing file: {target}')
            continue
        url = f'https://raw.githubusercontent.com/cgotelli/AVAC-QGIS/{REVISION}/tutorial/{target.name}'
        print('Downloading', target.name, flush=True)
        temporary = target.with_suffix(target.suffix+'.part')
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open('xb') as output:
            import shutil
            shutil.copyfileobj(response, output)
        if digest(temporary) != record['sha256']:
            raise ValueError(f'Tutorial checksum mismatch: {temporary}')
        temporary.replace(target)
    verify_tutorial(folder)
    print('Tutorial ready. Choose Help > Load tutorial in AVAC Desktop.')

if __name__ == '__main__':
    main()
