"""Configuration loading (TOML) with validation and sane defaults."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the configuration file or environment is invalid."""


@dataclass(frozen=True)
class Config:
    output_dir: Path
    country: str = "US"
    language: str = "en-US"
    providers: tuple[str | int, ...] = ()
    recent_days: int = 45
    upcoming_days: int = 30
    limit_movies: int = 40
    limit_series: int = 40
    limit_upcoming: int = 30
    min_items_before_cleanup: int = 5
    label_new: str = "New"
    label_upcoming: str = "Coming soon"
    jellyfin_url: str = ""
    download_trailers: bool = False
    trailer_max_height: int = 480
    trailer_min_free_gb: int = 5
    yt_dlp_path: str = "yt-dlp"
    yt_dlp_extra_args: tuple[str, ...] = ()
    tmdb_token: str = field(default="", repr=False)
    jellyfin_api_key: str = field(default="", repr=False)


def _tmdb_token_from_env(env: dict[str, str]) -> str:
    """TMDB v4 read token (preferred) or v3 API key; v3 keys are prefixed internally."""
    if env.get("TMDB_READ_TOKEN", "").strip():
        return env["TMDB_READ_TOKEN"].strip()
    if env.get("TMDB_API_KEY", "").strip():
        return "v3:" + env["TMDB_API_KEY"].strip()
    raise ConfigError("no TMDB credentials: set TMDB_READ_TOKEN (v4) or TMDB_API_KEY (v3)")


HEIGHTS = (240, 360, 480, 720, 1080)


def _one_of(value: object, name: str, allowed: tuple[int, ...]) -> int:
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(map(str, allowed))}")
    return int(value)  # type: ignore[arg-type]


def _positive(value: object, name: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigError(f"{name} must be an integer >= {minimum}")
    return value


def load_config(path: Path, env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    locale = raw.get("locale", {})
    window = raw.get("window", {})
    limits = raw.get("limits", {})
    labels = raw.get("labels", {})
    output = raw.get("output", {})
    trailers = raw.get("trailers", {})
    if not output.get("dir"):
        raise ConfigError("[output] dir is required")

    country = str(locale.get("country", "US")).upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ConfigError("[locale] country must be an ISO 3166-1 alpha-2 code, e.g. 'FR'")
    language = str(locale.get("language", "en-US"))
    if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", language):
        raise ConfigError("[locale] language must look like 'en-US' or 'fr-FR'")

    providers = tuple(raw.get("providers", {}).get("names", ()))
    if not all(isinstance(p, (str, int)) for p in providers):
        raise ConfigError("[providers] names must be provider names or TMDB provider ids")

    return Config(
        output_dir=Path(output["dir"]),
        country=country,
        language=language,
        providers=providers,
        recent_days=_positive(window.get("recent_days", 45), "[window] recent_days"),
        upcoming_days=_positive(window.get("upcoming_days", 30), "[window] upcoming_days"),
        limit_movies=_positive(limits.get("movies", 40), "[limits] movies"),
        limit_series=_positive(limits.get("series", 40), "[limits] series"),
        limit_upcoming=_positive(limits.get("upcoming", 30), "[limits] upcoming"),
        min_items_before_cleanup=_positive(
            output.get("min_items_before_cleanup", 5), "[output] min_items_before_cleanup", 0
        ),
        label_new=str(labels.get("new", "New")),
        label_upcoming=str(labels.get("upcoming", "Coming soon")),
        jellyfin_url=str(raw.get("jellyfin", {}).get("url", "")).rstrip("/"),
        download_trailers=bool(trailers.get("download", False)),
        trailer_max_height=_one_of(trailers.get("max_height", 480), "[trailers] max_height", HEIGHTS),
        trailer_min_free_gb=_positive(trailers.get("min_free_gb", 5), "[trailers] min_free_gb", 0),
        yt_dlp_path=str(trailers.get("yt_dlp", "yt-dlp")),
        yt_dlp_extra_args=tuple(str(a) for a in trailers.get("extra_args", ())),
        tmdb_token=_tmdb_token_from_env(env),
        jellyfin_api_key=env.get("JELLYFIN_API_KEY", ""),
    )
