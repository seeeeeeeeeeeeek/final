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


def load_source_settings(path: str | Path) -> dict[str, Any]:
    payload = load_optional_yaml(path)
    if not isinstance(payload, dict):
        return {}
    twelvedata = payload.get("twelvedata", {})
    source_preferences = payload.get("source_preferences", {})
    browser = payload.get("browser", {})
    tradingview = browser.get("tradingview", {}) if isinstance(browser, dict) else {}
    thinkorswim = browser.get("thinkorswim", {}) if isinstance(browser, dict) else {}
    return {
        "twelvedata": {
            "api_key": str(twelvedata.get("api_key", "") or "").strip(),
        },
        "source_preferences": {
            "default_mode": str(source_preferences.get("default_mode", "thinkorswim_web") or "thinkorswim_web").strip().lower(),
            "webhook_fallback_enabled": bool(source_preferences.get("webhook_fallback_enabled", True)),
            "browser_fallback_enabled": bool(source_preferences.get("browser_fallback_enabled", True)),
            "ocr_fallback_enabled": bool(source_preferences.get("ocr_fallback_enabled", True)),
        },
        "browser": {
            "provider": str(browser.get("provider", "thinkorswim") or "thinkorswim").strip().lower(),
            "headless": bool(browser.get("headless", False)),
            "persist_screenshots": bool(browser.get("persist_screenshots", True)),
            "screenshot_dir": str(browser.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts").strip(),
            "tradingview": {
                "enabled": bool(tradingview.get("enabled", False)),
                "chart_url_template": str(tradingview.get("chart_url_template", "") or "").strip(),
                "exchange_prefix": str(tradingview.get("exchange_prefix", "") or "").strip(),
                "page_load_timeout_ms": int(tradingview.get("page_load_timeout_ms", 15000) or 15000),
                "settle_wait_ms": int(tradingview.get("settle_wait_ms", 2500) or 2500),
            },
            "thinkorswim": {
                "enabled": bool(thinkorswim.get("enabled", True)),
                "base_url": str(thinkorswim.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/").strip(),
                "profile_dir": str(thinkorswim.get("profile_dir", "data/browser_profiles/thinkorswim_web") or "data/browser_profiles/thinkorswim_web").strip(),
                "page_load_timeout_ms": int(thinkorswim.get("page_load_timeout_ms", 20000) or 20000),
                "settle_wait_ms": int(thinkorswim.get("settle_wait_ms", 2000) or 2000),
                "keep_browser_open": bool(thinkorswim.get("keep_browser_open", True)),
                "launch_on_startup": bool(thinkorswim.get("launch_on_startup", False)),
            },
        },
    }


def save_source_settings(path: str | Path, payload: dict[str, Any]) -> None:
    source_settings = load_source_settings(path)
    twelvedata = dict(source_settings.get("twelvedata", {}))
    incoming_twelvedata = dict(payload.get("twelvedata", {}))
    if "api_key" in incoming_twelvedata:
        api_key = str(incoming_twelvedata.get("api_key", "") or "").strip()
        twelvedata["api_key"] = api_key

    source_preferences = dict(source_settings.get("source_preferences", {}))
    source_preferences.update(
        {
            "default_mode": str(payload.get("source_preferences", {}).get("default_mode", source_preferences.get("default_mode", "auto")) or "auto").strip().lower(),
            "webhook_fallback_enabled": bool(payload.get("source_preferences", {}).get("webhook_fallback_enabled", source_preferences.get("webhook_fallback_enabled", True))),
            "browser_fallback_enabled": bool(payload.get("source_preferences", {}).get("browser_fallback_enabled", source_preferences.get("browser_fallback_enabled", True))),
            "ocr_fallback_enabled": bool(payload.get("source_preferences", {}).get("ocr_fallback_enabled", source_preferences.get("ocr_fallback_enabled", True))),
        }
    )
    browser = dict(source_settings.get("browser", {}))
    incoming_browser = dict(payload.get("browser", {}))
    browser.update(
        {
            "provider": str(incoming_browser.get("provider", browser.get("provider", "yahoo")) or "yahoo").strip().lower(),
            "headless": bool(incoming_browser.get("headless", browser.get("headless", True))),
            "persist_screenshots": bool(
                incoming_browser.get("persist_screenshots", browser.get("persist_screenshots", True))
            ),
            "screenshot_dir": str(
                incoming_browser.get("screenshot_dir", browser.get("screenshot_dir", "out/browser_artifacts"))
                or "out/browser_artifacts"
            ).strip(),
        }
    )
    browser_tradingview = dict(browser.get("tradingview", {}))
    incoming_tradingview = dict(incoming_browser.get("tradingview", {}))
    browser_tradingview.update(
        {
            "enabled": bool(incoming_tradingview.get("enabled", browser_tradingview.get("enabled", False))),
            "chart_url_template": str(
                incoming_tradingview.get("chart_url_template", browser_tradingview.get("chart_url_template", ""))
                or ""
            ).strip(),
            "exchange_prefix": str(
                incoming_tradingview.get("exchange_prefix", browser_tradingview.get("exchange_prefix", ""))
                or ""
            ).strip(),
            "page_load_timeout_ms": int(
                incoming_tradingview.get("page_load_timeout_ms", browser_tradingview.get("page_load_timeout_ms", 15000))
                or 15000
            ),
            "settle_wait_ms": int(
                incoming_tradingview.get("settle_wait_ms", browser_tradingview.get("settle_wait_ms", 2500))
                or 2500
            ),
        }
    )
    browser["tradingview"] = browser_tradingview
    browser_thinkorswim = dict(browser.get("thinkorswim", {}))
    incoming_thinkorswim = dict(incoming_browser.get("thinkorswim", {}))
    browser_thinkorswim.update(
        {
            "enabled": bool(incoming_thinkorswim.get("enabled", browser_thinkorswim.get("enabled", True))),
            "base_url": str(
                incoming_thinkorswim.get("base_url", browser_thinkorswim.get("base_url", "https://trade.thinkorswim.com/"))
                or "https://trade.thinkorswim.com/"
            ).strip(),
            "profile_dir": str(
                incoming_thinkorswim.get("profile_dir", browser_thinkorswim.get("profile_dir", "data/browser_profiles/thinkorswim_web"))
                or "data/browser_profiles/thinkorswim_web"
            ).strip(),
            "page_load_timeout_ms": int(
                incoming_thinkorswim.get("page_load_timeout_ms", browser_thinkorswim.get("page_load_timeout_ms", 20000))
                or 20000
            ),
            "settle_wait_ms": int(
                incoming_thinkorswim.get("settle_wait_ms", browser_thinkorswim.get("settle_wait_ms", 2000))
                or 2000
            ),
            "keep_browser_open": bool(
                incoming_thinkorswim.get("keep_browser_open", browser_thinkorswim.get("keep_browser_open", True))
            ),
            "launch_on_startup": bool(
                incoming_thinkorswim.get("launch_on_startup", browser_thinkorswim.get("launch_on_startup", False))
            ),
        }
    )
    browser["thinkorswim"] = browser_thinkorswim

    save_yaml(
        path,
        {
            "twelvedata": twelvedata,
            "source_preferences": source_preferences,
            "browser": browser,
        },
    )


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
