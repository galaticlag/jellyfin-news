# jellyfin-news

A **"What's new on streaming"** library for [Jellyfin](https://jellyfin.org): recent and upcoming
movies and series available on the streaming services you care about, each with its synopsis,
rating, poster, the platforms offering it, and its **trailer**.

Jellyfin only knows what is in your own library. `jellyfin-news` fills a dedicated library with
information cards for what is *out there*, so you can browse new releases and watch trailers
right from Jellyfin, on every client (web, TV, mobile), with no plugin and no web-UI patching.

```
Jellyfin
├── Movies          (your media)
├── Shows           (your media)
├── News - Movies   ← new on streaming this month
├── News - Series   ← new series on streaming this month
└── News - Upcoming ← movies releasing in the next weeks
```

## How it works

Once a day, `jellyfin-news` asks [TMDB](https://www.themoviedb.org) what has recently landed on
subscription streaming in **your country**, then writes one small folder per title:

```
/var/lib/jellyfin-news/movies/Some Movie (2026) [tmdbid-123]/
├── Some Movie (2026).nfo    synopsis, rating, genres, cast, platforms, trailer link
├── Some Movie (2026).strm   points to the trailer
├── poster.jpg
└── fanart.jpg
```

Jellyfin reads these natively (NFO + `.strm`). Titles that fall out of the time window are removed
on the next run. Only folders created by this tool (marked with a `.jellyfin-news` file) are ever
deleted.

> **These are information cards, not playable media.** Open a title to read about it and play its
> trailer from the details page; the main *Play* button does not stream the film.

## Requirements

- Jellyfin 10.9 or later (tested with 10.11 and later releases)
- Python 3.11+ (standard library only, no dependencies)
- A free [TMDB](https://www.themoviedb.org/settings/api) API Read Access Token

## Installation

```sh
git clone https://github.com/galaticlag/jellyfin-news.git
cd jellyfin-news
sudo pip install .            # installs the `jellyfin-news` command
```

Or run it straight from the checkout: `PYTHONPATH=src python3 -m jellyfin_news --help`.

## Configuration

1. Copy [`config.example.toml`](config.example.toml) to `/etc/jellyfin-news/config.toml`.
2. Choose your **country** and **language**, and the streaming services you use.
3. Provide your TMDB credentials through the environment (never in the config file):

   ```sh
   export TMDB_READ_TOKEN=...   # v4 "API Read Access Token" (preferred)
   # or
   export TMDB_API_KEY=...      # v3 API key
   ```

| Section       | Key                        | Default           | Description |
|---------------|----------------------------|-------------------|-------------|
| `[locale]`    | `country`                  | `US`              | ISO 3166-1 country used for streaming availability (`FR`, `DE`, `GB`, `CA`, ...) |
| `[locale]`    | `language`                 | `en-US`           | Language of titles, synopses and trailers (`fr-FR`, `de-DE`, ...) |
| `[providers]` | `names`                    | `[]` (all)        | Services to include, by name or TMDB id, e.g. `["Netflix", "Disney Plus"]`. Names unknown in your country are skipped with a warning |
| `[window]`    | `recent_days`              | `45`              | "New" = released in the last N days |
| `[window]`    | `upcoming_days`            | `30`              | "Coming soon" = releasing in the next N days |
| `[limits]`    | `movies` / `series` / `upcoming` | `40` / `40` / `30` | Max titles per library |
| `[labels]`    | `new` / `upcoming`         | `New` / `Coming soon` | Tag added to titles, shown in Jellyfin's tag filter |
| `[output]`    | `dir`                      | *(required)*      | Where cards are written; Jellyfin must be able to read it |
| `[output]`    | `min_items_before_cleanup` | `5`               | Safety net: if TMDB returns fewer titles, nothing is deleted and the run fails |
| `[jellyfin]`  | `url`                      | `""`              | Optional. With `JELLYFIN_API_KEY` set, triggers a library rescan after each run |

Try it without writing anything:

```sh
jellyfin-news --config /etc/jellyfin-news/config.toml --dry-run
```

## Playing the trailers

Out of the box each card links to the trailer on YouTube. Only Jellyfin's **web** client can open
that link, and only if the browser may load YouTube; most TV and mobile apps cannot play remote
trailers at all.

To make trailers play **everywhere** (film-reel button *and* the main Play button), enable local
downloads:

```toml
[trailers]
download    = true
max_height  = 480   # 480p H.264 is typically 3-10 MB per trailer
min_free_gb = 10    # below this, downloads are skipped and the YouTube link is kept
```

This needs [yt-dlp](https://github.com/yt-dlp/yt-dlp) on the host (and `ffmpeg`). Trailers are stored
beside each card, named the way Jellyfin expects (`Movie-trailer.mp4`, or a `trailers/` folder for
shows), and removed together with the card. A failed download simply keeps the YouTube link and is
retried on the next run. Make sure your use complies with YouTube's terms of service.

## Add the libraries to Jellyfin

In *Dashboard → Libraries → Add Media Library*, create three libraries pointing at the sub-folders of
your `output.dir`:

| Name (your choice) | Content type | Folder              |
|--------------------|--------------|---------------------|
| News - Movies      | Movies       | `<output.dir>/movies`   |
| News - Series      | Shows        | `<output.dir>/series`   |
| News - Upcoming    | Movies       | `<output.dir>/upcoming` |

For each of them:

- Enable the **Nfo** metadata reader, so synopsis and trailers come from the cards.
- Disabling *"Automatically refresh metadata from the internet"* is optional: the cards are complete on
  their own, though the TMDB provider can add extra images.
- Untick *"Save artwork into media folders"* and *"Enable real-time monitoring"* if your output
  folder is on a network or removable filesystem; rely on the scheduled scan (or set
  `[jellyfin]`/`JELLYFIN_API_KEY` for an immediate rescan).

You can also hide these libraries from some users in *Dashboard → Users → Library access*.

## Run it every day

Example systemd units are provided in [`contrib/systemd`](contrib/systemd):

```sh
sudo install -d -m 750 /etc/jellyfin-news /var/lib/jellyfin-news
sudo install -m 640 config.example.toml /etc/jellyfin-news/config.toml
echo 'TMDB_READ_TOKEN=your-token' | sudo tee /etc/jellyfin-news/env >/dev/null
sudo chmod 640 /etc/jellyfin-news/env
sudo cp contrib/systemd/jellyfin-news.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jellyfin-news.timer
```

The timer uses `Persistent=true`: if the machine was off at the scheduled time (a server powered
down at night, say), the run happens right after the next boot. Pick a time when the host is normally up.

Adjust `User=` and the folder permissions so the service can write `output.dir` and Jellyfin can
read it. Run once on demand with `sudo systemctl start jellyfin-news.service` and follow it with
`journalctl -u jellyfin-news`. Each run also writes `<output.dir>/status.json` (time, result, per-library
counts), convenient for monitoring.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check . && ruff format --check .
PYTHONPATH=src python -m unittest discover -s tests
```

The code is split into a TMDB client (`tmdb.py`), pure rendering functions (`render.py`), the
synchronisation logic (`sync.py`), configuration (`config.py`) and the CLI (`cli.py`). Tests run
offline against a fake client. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations

- "New on streaming" is based on TMDB release dates and watch-provider data (sourced from JustWatch),
  so very recent additions may take a day or two to appear.
- Series are listed by first air date; new seasons of existing shows are not highlighted.
- Cards are not playable; the trailer is opened from the title's details page.

## Credits

This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming availability
data is provided by JustWatch via TMDB.

## License

[MIT](LICENSE)
