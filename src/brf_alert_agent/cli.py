from __future__ import annotations

import argparse
import logging

from brf_alert_agent.agent import BrfAlertAgent
from brf_alert_agent.config import load_config


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    config = load_config(args.config)
    agent = BrfAlertAgent(config)
    try:
        if args.command == "run":
            agent.run_once()
        elif args.command == "daemon":
            agent.run_forever()
        else:  # pragma: no cover - protected by argparse choices
            raise ValueError(f"Unknown command: {args.command}")
    finally:
        agent.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stockholm BRF listing alert agent",
    )
    parser.add_argument(
        "--config",
        default="config.example.yaml",
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "daemon"],
        help="run=one-shot check, daemon=loop forever",
    )
    return parser


if __name__ == "__main__":
    main()

