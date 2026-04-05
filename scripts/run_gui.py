from __future__ import annotations

import argparse
import errno
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.gui_api import create_gui_server

_PORT_CANDIDATES = (8080, 8090, 8100, 8180)


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
    ports_to_try = [args.port]
    for candidate in _PORT_CANDIDATES:
        if candidate not in ports_to_try:
            ports_to_try.append(candidate)

    server = None
    last_error: Exception | None = None
    for port in ports_to_try:
        try:
            server = create_gui_server(
                host=args.host,
                port=port,
                config_dir=args.config_dir,
                log_path=args.log_path,
                override_path=args.config_override,
                demo_override_path=args.demo_override,
            )
            break
        except OSError as exc:
            last_error = exc
            if exc.errno not in {errno.EACCES, errno.EADDRINUSE, 10013, 10048}:
                raise

    if server is None:
        message = str(last_error) if last_error is not None else "Unknown socket bind failure."
        raise RuntimeError(f"Could not bind the GUI to any startup port {ports_to_try}: {message}")

    actual_port = server.server_port
    print(f"gui_url: http://{args.host}:{actual_port}/")
    print(f"webhook_url: http://{args.host}:{actual_port}/webhook")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
