"""Build the on-disk libraries from TMDB data and keep them tidy."""

from __future__ import annotations

import logging
import os
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import render, trailers
from .config import Config
from .tmdb import TmdbClient, image_url

log = logging.getLogger(__name__)
MARKER = ".jellyfin-news"  # only folders carrying this file are ever deleted
SECTIONS = ("movies", "series", "upcoming")


class SyncError(RuntimeError):
    pass


@dataclass
class SectionResult:
    kept: int = 0
    removed: int = 0


def write_if_changed(path: Path, content: str | bytes) -> bool:
    """Atomic write that leaves untouched files alone (so Jellyfin sees no change)."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            write_if_changed(dest, resp.read())
    except Exception as exc:  # noqa: BLE001 - a missing image must never abort the run
        log.warning("image %s: %s", dest.name, exc)


def write_item(root: Path, section: str, kind: str, details: dict[str, Any], cfg: Config) -> str | None:
    """Write one title's folder; returns its folder name, or None if it is not worth showing."""
    if not render.item_title(details) or not details.get("overview"):
        return None
    folder = root / section / render.folder_name(details)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARKER).touch()

    trailer = render.pick_trailer(details, cfg.language)
    stem = render.file_stem(details)
    local = _local_trailer(cfg, folder, kind, stem, trailer)
    label = cfg.label_upcoming if section == "upcoming" else cfg.label_new
    tags = render.stream_providers(details, cfg.country) + [label]
    nfo = render.build_nfo(kind, details, tags, trailer)
    strm = f"{local}\n" if local else render.strm_target(details, kind, trailer)
    if kind == "movie":
        write_if_changed(folder / f"{stem}.nfo", nfo)
        write_if_changed(folder / f"{stem}.strm", strm)
    else:
        (folder / "Season 01").mkdir(exist_ok=True)
        write_if_changed(folder / "tvshow.nfo", nfo)
        write_if_changed(
            folder / "Season 01" / f"{render.safe_name(render.item_title(details))} - S01E01.strm", strm
        )
    if details.get("poster_path"):
        _download(image_url(details["poster_path"], "w500"), folder / "poster.jpg")
    if details.get("backdrop_path"):
        _download(image_url(details["backdrop_path"], "w1280"), folder / "fanart.jpg")
    return folder.name


def _local_trailer(cfg: Config, folder: Path, kind: str, stem: str, video_id: str | None) -> Path | None:
    """Download the trailer next to the card (Jellyfin then plays it natively); None if unavailable."""
    if not (cfg.download_trailers and video_id):
        return None
    # Jellyfin conventions: 'Movie-trailer.mp4' beside a movie, a 'trailers' folder for a show.
    dest = folder / f"{stem}-trailer.mp4" if kind == "movie" else folder / "trailers" / f"{stem}.mp4"
    return dest if trailers.download_trailer(cfg, video_id, dest) else None


def cleanup(root: Path, section: str, keep: set[str]) -> int:
    section_dir = root / section
    removed = 0
    if not section_dir.is_dir():
        return 0
    for folder in sorted(section_dir.iterdir()):
        if folder.is_dir() and folder.name not in keep and (folder / MARKER).exists():
            shutil.rmtree(folder)
            removed += 1
    return removed


def refresh_jellyfin(cfg: Config) -> str:
    """Optionally ask Jellyfin to rescan now (otherwise its scheduled scan picks changes up)."""
    if not (cfg.jellyfin_url and cfg.jellyfin_api_key):
        return "skipped"
    req = urllib.request.Request(
        f"{cfg.jellyfin_url}/Library/Refresh", method="POST", headers={"X-Emby-Token": cfg.jellyfin_api_key}
    )
    try:
        urllib.request.urlopen(req, timeout=15).close()
    except Exception as exc:  # noqa: BLE001
        log.warning("Jellyfin refresh failed: %s", exc)
        return "failed"
    return "triggered"


def run_sync(client: TmdbClient, cfg: Config, dry_run: bool = False, workers: int = 6) -> dict[str, Any]:
    today = date.today()
    recent_start = today - timedelta(days=cfg.recent_days)
    provider_ids = client.resolve_providers(cfg.providers, cfg.country) if cfg.providers else []
    if cfg.providers and not provider_ids:
        raise SyncError("none of the configured providers exist in this country")

    plan = {
        "movies": (
            "movie",
            client.discover_available("movie", cfg, provider_ids, cfg.limit_movies, recent_start, today),
        ),
        "series": (
            "tv",
            client.discover_available("tv", cfg, provider_ids, cfg.limit_series, recent_start, today),
        ),
        "upcoming": (
            "movie",
            client.discover_upcoming(
                cfg, cfg.limit_upcoming, today + timedelta(days=1), today + timedelta(days=cfg.upcoming_days)
            ),
        ),
    }
    summary: dict[str, Any] = {}
    root = cfg.output_dir
    for section, (kind, candidates) in plan.items():
        log.info("%s: %d candidates", section, len(candidates))
        if dry_run:
            summary[section] = {"candidates": len(candidates)}
            continue
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = list(pool.map(lambda c, k=kind: _safe_details(client, k, c["id"]), candidates))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            written = pool.map(lambda d, s=section, k=kind: _safe_write(root, s, k, d, cfg), fetched)
            keep = {name for name in written if name}
        if len(keep) < cfg.min_items_before_cleanup:
            # Likely an upstream problem: keep the previous content instead of wiping it.
            raise SyncError(
                f"{section}: only {len(keep)} titles built (minimum {cfg.min_items_before_cleanup})"
            )
        summary[section] = vars(SectionResult(kept=len(keep), removed=cleanup(root, section, keep)))
    if not dry_run:
        summary["jellyfin_refresh"] = refresh_jellyfin(cfg)
    return summary


def _safe_details(client: TmdbClient, kind: str, tmdb_id: int) -> dict[str, Any] | None:
    try:
        return client.details(kind, tmdb_id)
    except Exception as exc:  # noqa: BLE001 - one bad title must not abort the whole run
        log.warning("%s %s: %s", kind, tmdb_id, exc)
        return None


def _safe_write(
    root: Path, section: str, kind: str, details: dict[str, Any] | None, cfg: Config
) -> str | None:
    if not details:
        return None
    try:
        return write_item(root, section, kind, details, cfg)
    except Exception as exc:  # noqa: BLE001 - one bad title must not abort the whole run
        log.warning("%s %s: %s", kind, details.get("id"), exc)
        return None
