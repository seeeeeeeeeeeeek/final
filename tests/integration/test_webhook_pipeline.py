import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.services.webhook_server import WebhookProcessor, create_webhook_server
from src.services.config_loader import load_scan_config
from src.services.logging import SignalLogger
from src.utils.validation import validate_scan_record


def _valid_payload() -> dict:
    return {
        "symbol": "NVDA",
        "exchange": "NASDAQ",
        "timeframe": "5m",
        "timestamp": "2026-04-01T13:35:00Z",
        "close": 944.2,
        "trend_pass": True,
        "compression_pass": True,
        "breakout_pass": True,
        "trap_risk_elevated": False,
        "compression_high": 942.1,
        "compression_low": 910.4,
        "trigger_level": 942.15,
        "breakout_price": 944.2,
        "breakout_range_vs_base_avg": 2.2,
        "relative_volume": 1.8,
        "rejection_wick_pct": 9.0,
        "overhead_clearance_pct": 4.0,
    }


def test_valid_webhook_payload_accepted_and_maps_to_stable_record_shape(tmp_path) -> None:
    config = load_scan_config("config")
    processor = WebhookProcessor(config=config, signal_logger=SignalLogger(log_path=tmp_path / "signals.log"))
    status_code, response = processor.handle_payload(_valid_payload())
    assert status_code == 200
    assert response["ok"] is True
    record = response["record"]
    assert record["symbol"] == "NVDA"
    assert record["status"] == "qualified"
    assert record["levels"]["compression_high"] == 942.1
    assert record["scores"]["total"] >= 0.0


def test_invalid_webhook_payload_rejected(tmp_path) -> None:
    config = load_scan_config("config")
    processor = WebhookProcessor(config=config, signal_logger=SignalLogger(log_path=tmp_path / "signals.log"))
    payload = _valid_payload()
    payload.pop("symbol")
    status_code, response = processor.handle_payload(payload)
    assert status_code == 400
    assert response["ok"] is False
    assert "symbol" in response["error"]


def test_webhook_processor_scoring_and_logging_path_works(tmp_path) -> None:
    config = load_scan_config("config")
    log_path = tmp_path / "signals.log"
    processor = WebhookProcessor(config=config, signal_logger=SignalLogger(log_path=log_path))
    status_code, response = processor.handle_payload(_valid_payload())
    assert status_code == 200
    logged = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert logged["symbol"] == "NVDA"
    assert logged["scores"]["total"] >= 0.0
    assert logged["explanations"]["summary"]


def test_minimal_contract_payload_is_accepted(tmp_path) -> None:
    config = load_scan_config("config")
    processor = WebhookProcessor(config=config, signal_logger=SignalLogger(log_path=tmp_path / "signals.log"))
    payload = {
        "symbol": "NVDA",
        "exchange": "NASDAQ",
        "timeframe": "5m",
        "timestamp": "2026-04-01T13:35:00Z",
        "close": 944.2,
        "trend_pass": True,
        "compression_pass": True,
        "breakout_pass": True,
        "trap_risk_elevated": False,
    }
    status_code, response = processor.handle_payload(payload)
    assert status_code == 200
    assert response["ok"] is True
    assert response["record"]["symbol"] == "NVDA"


def test_webhook_server_accepts_valid_json_over_http(tmp_path) -> None:
    server = create_webhook_server(host="127.0.0.1", port=0, config_dir="config", log_path=tmp_path / "signals.log")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/webhook"
        request = Request(
            url,
            data=json.dumps(_valid_payload()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["record"]["symbol"] == "NVDA"
        validate_scan_record(processor_record := processor_from_payload(payload["record"]))
    finally:
        server.shutdown()
        server.server_close()


def test_webhook_server_rejects_invalid_json_over_http(tmp_path) -> None:
    server = create_webhook_server(host="127.0.0.1", port=0, config_dir="config", log_path=tmp_path / "signals.log")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/webhook"
        request = Request(
            url,
            data=b"{not-json}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request, timeout=10)
        except HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["ok"] is False
    finally:
        server.shutdown()
        server.server_close()


def processor_from_payload(payload: dict) -> object:
    from src.scanner.models import (
        DebugPayload,
        ExplanationPayload,
        PriceLevels,
        ScanFlags,
        ScanRecord,
        ScanStatus,
        ScoreBreakdown,
        SetupWindow,
        TimeframeConfig,
    )

    return ScanRecord(
        scan_id=payload["scan_id"],
        symbol=payload["symbol"],
        market=payload["market"],
        direction=payload["direction"],
        status=ScanStatus(payload["status"]),
        timestamp_utc=payload["timestamp_utc"],
        timeframes=TimeframeConfig(**payload["timeframes"]),
        setup_window=SetupWindow(**payload["setup_window"]),
        levels=PriceLevels(**payload["levels"]),
        metrics=payload["metrics"],
        scores=ScoreBreakdown(**payload["scores"]),
        flags=ScanFlags(**payload["flags"]),
        explanations=ExplanationPayload(**payload["explanations"]),
        debug=DebugPayload(**payload["debug"]),
    )
