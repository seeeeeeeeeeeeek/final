from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.scanner.models import ScanConfig


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping at {path}")
    return payload


def load_optional_yaml(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return load_yaml(file_path)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = _deep_merge(base_value, override_value)
        else:
            merged[key] = override_value
    return merged


def save_yaml(path: str | Path, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def reset_yaml(path: str | Path) -> None:
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink()


def load_scan_config(config_dir: str | Path, *, override_path: str | Path | None = None) -> ScanConfig:
    config_path = Path(config_dir)
    defaults = load_yaml(config_path / "defaults.yaml")
    scoring = load_yaml(config_path / "scoring.yaml")
    universe = load_yaml(config_path / "universe.yaml")

    if override_path is not None:
        override = load_optional_yaml(override_path)
        defaults = _deep_merge(defaults, override.get("defaults", {}))
        scoring = _deep_merge(scoring, override.get("scoring", {}))
        universe = _deep_merge(universe, override.get("universe", {}))

    return ScanConfig(defaults=defaults, scoring=scoring, universe=universe)
