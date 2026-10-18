"""Optional local trailer download (via yt-dlp), so every Jellyfin client can play them."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)
GIB = 1024**3


def has_free_space(path: Path, min_free_gb: int) -> bool:
    """True when the filesystem holding `path` keeps at least `min_free_gb` GiB free."""
    return shutil.disk_usage(path).free >= min_free_gb * GIB


def build_command(cfg: Config, video_id: str, dest: Path) -> list[str]:
    # Prefer H.264 + AAC in an MP4: it direct-plays on practically every client.
    h = cfg.trailer_max_height
    fmt = (
        f"b[height<={h}][vcodec^=avc1][ext=mp4]"
        f"/bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]"
        f"/b[height<={h}][ext=mp4]"
    )
    return [
        cfg.yt_dlp_path,
        "--quiet",
        "--no-warnings",
        "--no-playlist",
        "--no-progress",
        "-f",
        fmt,
        "--merge-output-format",
        "mp4",
        *cfg.yt_dlp_extra_args,
        "-o",
        str(dest.with_suffix(".part.%(ext)s")),
        f"https://www.youtube.com/watch?v={video_id}",
    ]


def download_trailer(cfg: Config, video_id: str, dest: Path, timeout: int = 300) -> bool:
    """Download a trailer to `dest` (an .mp4 path). Returns True if the file is available."""
    if dest.exists():
        return True
    if not has_free_space(dest.parent, cfg.trailer_min_free_gb):
        log.warning("less than %d GiB free: skipping trailer download", cfg.trailer_min_free_gb)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            build_command(cfg, video_id, dest),
            check=True,
            timeout=timeout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        produced = dest.with_suffix(".part.mp4")
        if not produced.exists() or produced.stat().st_size == 0:
            raise RuntimeError("yt-dlp produced no file")
        produced.replace(dest)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, RuntimeError) as exc:
        stderr = (getattr(exc, "stderr", "") or "").strip()
        log.warning("trailer %s: %s", video_id, stderr.splitlines()[-1] if stderr else exc)
        dest.with_suffix(".part.mp4").unlink(missing_ok=True)
        return False
