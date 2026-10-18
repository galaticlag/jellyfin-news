# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Optional local trailer download (`[trailers]`, via yt-dlp) so trailers play on every Jellyfin client,
  with a free-disk-space guard and fallback to the YouTube link.
- Cards are now written in parallel.
- Automatic fallback to the next trailer when one is unavailable; titles with no working trailer are
  retried after a week. The default quality is validated (`max_height`: 240, 360, 480, 720 or 1080).

## [0.1.0] - 2026-10-18

### Added
- Daily generation of "new on streaming", "series" and "upcoming" Jellyfin libraries from TMDB.
- Configurable country, language, streaming providers (by name or id) and time windows.
- Trailer links, synopsis, rating, genres, cast, poster and fanart for every title.
- Safe cleanup (only folders created by the tool) with a guard against empty upstream results.
- Optional Jellyfin library rescan, `status.json` report, example systemd units.
