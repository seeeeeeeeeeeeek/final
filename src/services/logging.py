from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.scanner.models import ScanRecord, ScanStatus


@dataclass(slots=True)
class SignalLogger:
    logger_name: str = "stocknogs"
    log_path: Path | None = None
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.logger_name)
        if not self._logger.handlers:
            self._logger.setLevel(logging.INFO)
            self._logger.addHandler(logging.StreamHandler())

    def build_payload(self, record: ScanRecord) -> dict[str, object]:
        module_summary: dict[str, dict[str, object]] = {}
        for module_name, module_result in record.module_results.items():
            module_summary[module_name] = {
                "outcome": module_result.outcome.value,
                "passed": module_result.passed,
                "reasons": module_result.reasons,
            }

        payload = record.to_dict()
        payload["modules"] = module_summary
        return payload

    def log_signal(self, record: ScanRecord) -> None:
        payload = self.build_payload(record)
        self._logger.info(json.dumps(payload, sort_keys=True))
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def supports_status(self, status: ScanStatus) -> bool:
        return status in {
            ScanStatus.QUALIFIED,
            ScanStatus.SKIPPED,
            ScanStatus.REJECTED,
            ScanStatus.NO_TRADE,
        }
