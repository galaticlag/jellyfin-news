"""Pure functions that turn TMDB details into Jellyfin-readable files."""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """Make a string safe to use as a file or folder name on any filesystem."""
    cleaned = re.sub(r"\s+", " ", _ILLEGAL.sub("", name)).strip(" .")
    return cleaned or "Untitled"


def item_title(details: dict[str, Any]) -> str:
    return details.get("title") or details.get("name") or ""


def item_year(details: dict[str, Any]) -> str:
    return (details.get("release_date") or details.get("first_air_date") or "")[:4]


def folder_name(details: dict[str, Any]) -> str:
    """'Title (2026) [tmdbid-123]': the tmdbid tag lets Jellyfin match metadata exactly."""
    year = item_year(details)
    stem = safe_name(item_title(details)) + (f" ({year})" if year else "")
    return f"{stem} [tmdbid-{details['id']}]"


def file_stem(details: dict[str, Any]) -> str:
    year = item_year(details)
    return safe_name(item_title(details)) + (f" ({year})" if year else "")


def trailer_candidates(details: dict[str, Any], language: str, limit: int = 3) -> list[str]:
    """YouTube ids ranked best first: trailers before teasers, user's language, official, newest."""
    lang = language.split("-")[0]
    videos = [
        v
        for v in (details.get("videos") or {}).get("results", [])
        if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser") and v.get("key")
    ]
    videos.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    videos.sort(key=lambda v: (v.get("type") != "Trailer", v.get("iso_639_1") != lang, not v.get("official")))
    return list(dict.fromkeys(v["key"] for v in videos))[:limit]


def pick_trailer(details: dict[str, Any], language: str) -> str | None:
    """The best trailer id, if any."""
    candidates = trailer_candidates(details, language, 1)
    return candidates[0] if candidates else None


def stream_providers(details: dict[str, Any], country: str) -> list[str]:
    flatrate = ((details.get("watch/providers") or {}).get("results", {}).get(country, {})).get(
        "flatrate", []
    )
    names = [p["provider_name"] for p in flatrate if p.get("provider_name")]
    return list(dict.fromkeys(names))[:4]


def strm_target(details: dict[str, Any], kind: str, trailer: str | None) -> str:
    """Content of the .strm file: the trailer if there is one, else the TMDB page."""
    if trailer:
        return f"https://www.youtube.com/watch?v={trailer}\n"
    return f"https://www.themoviedb.org/{kind}/{details['id']}\n"


def build_nfo(kind: str, details: dict[str, Any], tags: list[str], trailer: str | None) -> str:
    """Kodi-style NFO, which Jellyfin reads natively (including the trailer link)."""
    root = "movie" if kind == "movie" else "tvshow"
    title = item_title(details)
    original = details.get("original_title") or details.get("original_name") or title
    premiered = details.get("release_date") or details.get("first_air_date") or ""
    rows = [
        f"<title>{escape(title)}</title>",
        f"<originaltitle>{escape(original)}</originaltitle>",
        f"<year>{item_year(details)}</year>",
        f"<premiered>{escape(premiered)}</premiered>",
        f"<plot>{escape(details.get('overview') or '')}</plot>",
        f"<tagline>{escape(details.get('tagline') or '')}</tagline>",
        f"<rating>{round(details.get('vote_average') or 0, 1)}</rating>",
        f'<uniqueid type="tmdb" default="true">{details["id"]}</uniqueid>',
    ]
    rows += [f"<genre>{escape(g['name'])}</genre>" for g in details.get("genres", [])]
    rows += [f"<tag>{escape(t)}</tag>" for t in tags]
    if trailer:
        rows.append(
            "<trailer>plugin://plugin.video.youtube/?action=play_video"
            f"&amp;videoid={escape(trailer)}</trailer>"
        )
    for order, actor in enumerate((details.get("credits") or {}).get("cast", [])[:6]):
        rows.append(
            f"<actor><name>{escape(actor['name'])}</name>"
            f"<role>{escape(actor.get('character') or '')}</role><order>{order}</order></actor>"
        )
    body = "\n  ".join(rows)
    return f'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n<{root}>\n  {body}\n</{root}>\n'
