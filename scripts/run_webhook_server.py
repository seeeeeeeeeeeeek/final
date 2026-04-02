from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.webhook_server import create_webhook_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local TradingView webhook receiver.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument("--config-dir", default=str(ROOT / "config"), help="Config directory.")
    parser.add_argument("--log-path", help="Optional path to append webhook-driven scan records.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = create_webhook_server(
        host=args.host,
        port=args.port,
        config_dir=args.config_dir,
        log_path=args.log_path,
    )
    print(f"webhook_server: http://{args.host}:{args.port}/webhook")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
