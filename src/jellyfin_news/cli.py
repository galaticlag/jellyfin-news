"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .sync import SyncError, run_sync, write_if_changed
from .tmdb import TmdbClient

DEFAULT_CONFIG = Path("/etc/jellyfin-news/config.toml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jellyfin-news", description=__doc__)
    parser.add_argument(
        "-c", "--config", type=Path, default=DEFAULT_CONFIG, help=f"TOML config (default: {DEFAULT_CONFIG})"
    )
    parser.add_argument("-n", "--dry-run", action="store_true", help="query TMDB but write nothing")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )

    cfg = None
    status: dict = {"time": datetime.now(UTC).isoformat(timespec="seconds"), "ok": False}
    try:
        cfg = load_config(args.config)
        status["summary"] = run_sync(TmdbClient(cfg.tmdb_token, cfg.language), cfg, dry_run=args.dry_run)
        status["ok"] = True
    except (ConfigError, SyncError) as exc:
        status["error"] = str(exc)
        logging.error("%s", exc)
    except Exception as exc:  # noqa: BLE001
        status["error"] = f"{type(exc).__name__}: {exc}"
        logging.exception("unexpected failure")

    print(json.dumps(status, indent=2))
    if cfg is not None and not args.dry_run and cfg.output_dir.is_dir():
        # Machine-readable result of the last run, handy for monitoring.
        write_if_changed(cfg.output_dir / "status.json", json.dumps(status, indent=2))
    return 0 if status["ok"] else 1
