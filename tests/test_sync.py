import tempfile
import unittest
from pathlib import Path

from jellyfin_news.config import Config
from jellyfin_news.sync import MARKER, SyncError, cleanup, run_sync, write_if_changed


def details(i: int) -> dict:
    return {"id": i, "title": f"Movie {i}", "release_date": "2026-01-01", "overview": "plot"}


class FakeClient:
    def __init__(self, ids):
        self.ids = ids

    def resolve_providers(self, wanted, country):
        return [8]

    def discover_available(self, kind, *a, **k):
        return [{"id": i} for i in self.ids]

    def discover_upcoming(self, *a, **k):
        return [{"id": i} for i in self.ids]

    def details(self, kind, tmdb_id):
        return details(tmdb_id)


def make_cfg(out: Path, minimum: int = 1) -> Config:
    return Config(output_dir=out, min_items_before_cleanup=minimum)


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def test_creates_folders_and_removes_stale_managed_ones(self):
        run_sync(FakeClient([1, 2]), make_cfg(self.out, 0))
        self.assertTrue((self.out / "movies" / "Movie 1 (2026) [tmdbid-1]" / "Movie 1 (2026).nfo").exists())
        stale = self.out / "movies" / "Movie 9 (2026) [tmdbid-9]"
        stale.mkdir()
        (stale / MARKER).touch()
        foreign = self.out / "movies" / "My own folder"
        foreign.mkdir()
        run_sync(FakeClient([1, 2]), make_cfg(self.out, 0))
        self.assertFalse(stale.exists())
        self.assertTrue(foreign.exists(), "folders without the marker must never be deleted")

    def test_tiny_result_aborts_without_deleting(self):
        run_sync(FakeClient([1, 2, 3]), make_cfg(self.out, 3))
        with self.assertRaises(SyncError):
            run_sync(FakeClient([1]), make_cfg(self.out, 3))
        self.assertTrue((self.out / "movies" / "Movie 3 (2026) [tmdbid-3]").exists())

    def test_dry_run_writes_nothing(self):
        run_sync(FakeClient([1]), make_cfg(self.out), dry_run=True)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_write_if_changed_is_idempotent(self):
        path = self.out / "a.txt"
        self.assertTrue(write_if_changed(path, "x"))
        self.assertFalse(write_if_changed(path, "x"))
        self.assertTrue(write_if_changed(path, "y"))

    def test_cleanup_on_missing_section(self):
        self.assertEqual(cleanup(self.out, "movies", set()), 0)


class TrailerTest(unittest.TestCase):
    def setUp(self):
        from unittest import mock

        self.out = Path(tempfile.mkdtemp())
        self.mock = mock

    def _details(self):
        d = details(1)
        d["videos"] = {"results": [{"site": "YouTube", "type": "Trailer", "key": "abc", "iso_639_1": "en"}]}
        return d

    def test_local_trailer_becomes_the_strm_target(self):
        cfg = Config(output_dir=self.out, download_trailers=True)

        def fake_download(cfg, video_id, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"x")
            return True

        with self.mock.patch("jellyfin_news.sync.trailers.download_trailer", fake_download):
            from jellyfin_news.sync import write_item

            name = write_item(self.out, "movies", "movie", self._details(), cfg)
        folder = self.out / "movies" / name
        self.assertTrue((folder / "Movie 1 (2026)-trailer.mp4").exists())
        self.assertEqual(
            (folder / "Movie 1 (2026).strm").read_text().strip(), str(folder / "Movie 1 (2026)-trailer.mp4")
        )

    def test_failed_download_falls_back_to_youtube_link(self):
        cfg = Config(output_dir=self.out, download_trailers=True)
        with self.mock.patch("jellyfin_news.sync.trailers.download_trailer", lambda *a: False):
            from jellyfin_news.sync import write_item

            name = write_item(self.out, "movies", "movie", self._details(), cfg)
        strm = (self.out / "movies" / name / "Movie 1 (2026).strm").read_text()
        self.assertEqual(strm.strip(), "https://www.youtube.com/watch?v=abc")

    def test_disabled_by_default(self):
        from jellyfin_news.sync import write_item

        with self.mock.patch("jellyfin_news.sync.trailers.download_trailer") as dl:
            write_item(self.out, "movies", "movie", self._details(), Config(output_dir=self.out))
        dl.assert_not_called()


class FailingWriteTest(unittest.TestCase):
    def test_failed_write_does_not_delete_the_existing_card(self):
        from unittest import mock

        out = Path(tempfile.mkdtemp())
        cfg = make_cfg(out, 0)
        run_sync(FakeClient([1, 2]), cfg)
        existing = out / "movies" / "Movie 2 (2026) [tmdbid-2]"
        self.assertTrue(existing.exists())
        real = __import__("jellyfin_news.sync", fromlist=["write_item"]).write_item

        def flaky(root, section, kind, d, cfg):
            if d["id"] == 2:
                raise OSError("disk hiccup")
            return real(root, section, kind, d, cfg)

        with mock.patch("jellyfin_news.sync.write_item", flaky):
            run_sync(FakeClient([1, 2]), cfg)
        self.assertTrue(existing.exists())
