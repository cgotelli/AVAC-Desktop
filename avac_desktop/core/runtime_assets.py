"""Application-owned configuration and source locations."""
from pathlib import Path

APPLICATION_ROOT = Path(__file__).resolve().parents[2]
RESOURCES = Path(__file__).resolve().parents[1] / 'resources'

def default_template_path() -> Path:
    return RESOURCES / 'AVAC_configuration100.yaml'
