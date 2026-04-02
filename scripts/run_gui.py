from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.gui_api import create_gui_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local stocknogs GUI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8080, help="Bind port.")
    parser.add_argument("--config-dir", default=str(ROOT / "config"), help="Config directory.")
    parser.add_argument("--log-path", default=str(ROOT / "logs" / "gui_signals.log"), help="JSONL log path.")
    parser.add_argument(
        "--config-override",
        default=str(ROOT / "config" / "gui_user.yaml"),
        help="Local GUI settings override path.",
    )
    parser.add_argument(
        "--demo-override",
        default=str(ROOT / "config" / "demo.yaml"),
        help="Demo preset override path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = create_gui_server(
        host=args.host,
        port=args.port,
        config_dir=args.config_dir,
        log_path=args.log_path,
        override_path=args.config_override,
        demo_override_path=args.demo_override,
    )
    print(f"gui_url: http://{args.host}:{args.port}/")
    print(f"webhook_url: http://{args.host}:{args.port}/webhook")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
