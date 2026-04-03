from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from src.services.config_loader import load_optional_yaml

_TIMEFRAME_RE = re.compile(r"\b(1D|1H|5M|5m|1m|15m|30m|4H)\b")
_PRICE_RE = re.compile(r"(?<![A-Z])(?:\$)?(\d{1,6}(?:\.\d{1,4})?)")


@dataclass(slots=True)
class OCRScreenConfig:
    enabled: bool = False
    image_path: str | None = None
    window_title: str | None = None
    text_hint: str | None = None
    regions: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCRScreenResult:
    ok: bool
    reason: str | None
    extracted: dict[str, Any]
    missing_fields: list[str]
    warnings: list[str]
    capture_source: str | None
    engine_available: bool
    ocr_confidence: float | None = None


class OCRScreenService:
    """Bounded OCR fallback foundation for visible chart text only."""

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)

    def _load_config(self) -> OCRScreenConfig:
        payload = load_optional_yaml(self.config_path)
        ocr_payload = payload.get("ocr", payload) if isinstance(payload, dict) else {}
        return OCRScreenConfig(
            enabled=bool(ocr_payload.get("enabled", False)),
            image_path=ocr_payload.get("image_path"),
            window_title=ocr_payload.get("window_title"),
            text_hint=ocr_payload.get("text_hint"),
            regions=dict(ocr_payload.get("regions", {})) if isinstance(ocr_payload.get("regions", {}), dict) else {},
        )

    def _engine_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            return False
        return True

    def status_payload(self) -> dict[str, Any]:
        config = self._load_config()
        engine_available = self._engine_available()
        configured = bool(config.enabled and (config.text_hint or config.image_path or config.window_title or config.regions))
        capture_source = (
            f"Image file: {config.image_path}" if config.image_path
            else f"Window: {config.window_title}" if config.window_title
            else "Manual OCR text hint" if config.text_hint
            else "Not configured"
        )
        return {
            "enabled": config.enabled,
            "configured": configured,
            "engine_available": engine_available,
            "capture_source": capture_source,
            "config_path": str(self.config_path),
            "regions_configured": sorted(config.regions.keys()),
            "can_extract_live": bool(configured and (config.text_hint or engine_available)),
        }

    def _read_text(self, config: OCRScreenConfig, engine_available: bool) -> tuple[str | None, list[str]]:
        warnings: list[str] = []
        if config.text_hint:
            return str(config.text_hint), warnings
        if config.image_path:
            if not engine_available:
                warnings.append("OCR engine is not installed. Install pytesseract and pillow to use image OCR.")
                return None, warnings
            try:
                import pytesseract
                from PIL import Image

                text = pytesseract.image_to_string(Image.open(config.image_path))
                return text, warnings
            except Exception as exc:
                warnings.append(f"Failed to OCR image input: {exc}")
                return None, warnings
        warnings.append("No OCR capture source is configured yet.")
        return None, warnings

    def analyze(self, expected_symbol: str) -> OCRScreenResult:
        config = self._load_config()
        engine_available = self._engine_available()
        status = self.status_payload()
        if not config.enabled:
            return OCRScreenResult(
                ok=False,
                reason="Screen-read fallback is disabled. Enable OCR in config/ocr_user.yaml to use it.",
                extracted={},
                missing_fields=["ticker", "timeframe", "price"],
                warnings=[],
                capture_source=status["capture_source"],
                engine_available=engine_available,
            )
        if not status["configured"]:
            return OCRScreenResult(
                ok=False,
                reason="Screen-read fallback is not configured yet. Add OCR settings in config/ocr_user.yaml.",
                extracted={},
                missing_fields=["ticker", "timeframe", "price"],
                warnings=[],
                capture_source=status["capture_source"],
                engine_available=engine_available,
            )

        text, warnings = self._read_text(config, engine_available)
        if not text:
            return OCRScreenResult(
                ok=False,
                reason="Screen-read fallback could not read visible chart text.",
                extracted={},
                missing_fields=["ticker", "timeframe", "price"],
                warnings=warnings,
                capture_source=status["capture_source"],
                engine_available=engine_available,
            )

        upper_text = text.upper()
        extracted_symbol = expected_symbol if expected_symbol.upper() in upper_text else None
        timeframe_match = _TIMEFRAME_RE.search(text)
        price_match = _PRICE_RE.search(text)
        extracted = {
            "symbol": extracted_symbol,
            "timeframe": timeframe_match.group(1) if timeframe_match else None,
            "price": float(price_match.group(1)) if price_match else None,
        }
        missing_fields = [name for name, value in extracted.items() if value in (None, "")]
        if extracted_symbol is None:
            warnings.append(f"Expected ticker {expected_symbol} was not confidently visible in the screen text.")
        if extracted["timeframe"] is None:
            warnings.append("No visible timeframe label was extracted from the screen text.")
        if extracted["price"] is None:
            warnings.append("No visible current price was extracted from the screen text.")

        if missing_fields:
            return OCRScreenResult(
                ok=False,
                reason="Screen-read fallback could not extract enough visible chart context to analyze this symbol.",
                extracted=extracted,
                missing_fields=missing_fields,
                warnings=warnings,
                capture_source=status["capture_source"],
                engine_available=engine_available,
            )

        return OCRScreenResult(
            ok=True,
            reason=None,
            extracted=extracted,
            missing_fields=[],
            warnings=warnings,
            capture_source=status["capture_source"],
            engine_available=engine_available,
        )
