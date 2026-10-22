"""Per-user defaults. Project scientific values remain independent snapshots."""
from copy import deepcopy
import yaml
from PySide6.QtCore import QSettings
from avac_desktop.core.configuration import controlled_values, load_complete_configuration, validate_controlled_values
from avac_desktop.core.runtime_assets import default_template_path


def settings():
    return QSettings("AVAC", "AVAC Desktop")


def default_configuration():
    saved = settings().value("defaults/avac_yaml", "")
    if saved:
        try:
            config = yaml.safe_load(saved)
            if not validate_controlled_values(controlled_values(config)):
                return deepcopy(config)
        except (ValueError, TypeError, KeyError, yaml.YAMLError):
            pass
    return load_complete_configuration(default_template_path())


def appearance():
    value = settings().value("appearance", "light")
    return value if value in ("light", "dark") else "light"


def default_wave_setup():
    from .project import ProjectSession
    result = ProjectSession().wave_setup
    saved = settings().value("defaults/wave_yaml", "")
    if saved:
        try:
            values = yaml.safe_load(saved)
            if isinstance(values, dict):
                result.update(values)
        except yaml.YAMLError:
            pass
    return result


def save_defaults(config, theme, wave=None):
    issues = validate_controlled_values(controlled_values(config))
    if issues:
        raise ValueError("\n".join(issues))
    store = settings()
    store.setValue("defaults/avac_yaml", yaml.safe_dump(config, sort_keys=False))
    store.setValue("appearance", theme)
    if wave is not None:
        store.setValue("defaults/wave_yaml", yaml.safe_dump(wave, sort_keys=False))
    store.sync()


def set_output_interval(config, interval):
    count = output_count(float(config["computation"]["t_max"]), interval)
    config["computation"]["nb_simul"] = count
    config["animation"]["n_out"] = count+1
    return count


def output_count(duration, interval):
    import math
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duration must be positive and finite.")
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("Output interval must be positive and finite.")
    count = max(1, round(duration/interval))
    if count > 100000 or not math.isclose(count*interval, duration, rel_tol=1e-9, abs_tol=1e-8):
        raise ValueError("Duration must be a whole multiple of the output interval (at most 100,000 intervals).")
    return count
