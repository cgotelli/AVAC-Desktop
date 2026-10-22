"""Download the optional, hash-checked AVAC terrain and release tutorial."""
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = '1d6eec1e36ceb95e3c9bab6fd59c58ea91408df2'
FILES = [{'name': 'topo_cut_dam_1m.tif', 'sha256': '138da571816c271716354e508e612ce75f71300c3326045459747b9b71726165'}, {'name': 'avalanches.geojson', 'sha256': '8d4e34b348513510606fd2ee372116fe730cbb7c4d6e311afd0bcb3da0360482'}]

def main():
    folder = ROOT/'tutorial'
    folder.mkdir(exist_ok=True)
    for record in FILES:
        target = folder/record['name']
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError(f'Refusing to overwrite a different existing file: {target}')
            continue
        url = f'https://raw.githubusercontent.com/cgotelli/AVAC-QGIS/{REVISION}/tutorial/{target.name}'
        print('Downloading', target.name, flush=True)
        temporary = target.with_suffix(target.suffix+'.part')
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open('xb') as output:
            import shutil
            shutil.copyfileobj(response, output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'Tutorial checksum mismatch: {temporary}')
        temporary.replace(target)
    print('Tutorial ready. Choose Help > Load tutorial in AVAC Desktop.')

if __name__ == '__main__':
    main()
