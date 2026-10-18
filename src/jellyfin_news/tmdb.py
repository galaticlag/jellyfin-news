"""Minimal TMDB v3 client (standard library only)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from .config import Config

log = logging.getLogger(__name__)
API = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"


class TmdbClient:
    def __init__(self, token: str, language: str, retries: int = 3, timeout: float = 25.0):
        self._token, self._language = token, language
        self._retries, self._timeout = retries, timeout

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        params.setdefault("language", self._language)
        headers = {"accept": "application/json"}
        if self._token.startswith("v3:"):
            params["api_key"] = self._token[3:]
        else:
            headers["Authorization"] = f"Bearer {self._token}"
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(1, self._retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                # Retry only on rate limiting / server errors.
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self._retries:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == self._retries:
                    raise
            time.sleep(2 * attempt)
        raise RuntimeError("unreachable")  # pragma: no cover

    # -- helpers -------------------------------------------------------------
    def resolve_providers(self, wanted: tuple[str | int, ...], country: str) -> list[int]:
        """Turn provider names / ids from the config into TMDB provider ids."""
        ids = [p for p in wanted if isinstance(p, int)]
        names = {str(p).casefold(): str(p) for p in wanted if isinstance(p, str)}
        if names:
            known: dict[str, int] = {}
            for kind in ("movie", "tv"):
                for item in self.get(f"/watch/providers/{kind}", watch_region=country).get("results", []):
                    known.setdefault(item["provider_name"].casefold(), item["provider_id"])
            for key, original in names.items():
                if key in known:
                    ids.append(known[key])
                else:
                    log.warning("provider %r is not available in %s; ignored", original, country)
        return sorted(set(ids))

    def discover_available(
        self, kind: str, cfg: Config, provider_ids: list[int], limit: int, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Titles that became available on subscription streaming within [start, end]."""
        params: dict[str, Any] = {
            "watch_region": cfg.country,
            "region": cfg.country,
            "sort_by": "popularity.desc",
            "with_watch_monetization_types": "flatrate",
            "include_adult": "false",
        }
        if provider_ids:
            params["with_watch_providers"] = "|".join(map(str, provider_ids))
        if kind == "movie":
            # 4 = digital, 6 = TV: the release types that match streaming premieres.
            params.update(
                {
                    "with_release_type": "4|6",
                    "release_date.gte": start.isoformat(),
                    "release_date.lte": end.isoformat(),
                }
            )
        else:
            params.update({"first_air_date.gte": start.isoformat(), "first_air_date.lte": end.isoformat()})
        return self._paged(f"/discover/{kind}", params, limit)

    def discover_upcoming(self, cfg: Config, limit: int, start: date, end: date) -> list[dict[str, Any]]:
        """Movies releasing soon (theatrical, limited or digital) in the user's country."""
        params = {
            "region": cfg.country,
            "sort_by": "popularity.desc",
            "with_release_type": "2|3|4",
            "include_adult": "false",
            "release_date.gte": start.isoformat(),
            "release_date.lte": end.isoformat(),
        }
        return self._paged("/discover/movie", params, limit)

    def details(self, kind: str, tmdb_id: int) -> dict[str, Any]:
        lang = self._language.split("-")[0]
        return self.get(
            f"/{kind}/{tmdb_id}",
            append_to_response="videos,watch/providers,credits",
            include_video_language=f"{lang},en,null",
        )

    def _paged(self, path: str, params: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while len(results) < limit:
            data = self.get(path, page=page, **params)
            results += data.get("results", [])
            if page >= data.get("total_pages", 1) or page >= 5:
                break
            page += 1
        return results[:limit]


def image_url(path: str, size: str) -> str:
    return f"{IMAGE_BASE}/{size}{path}"
