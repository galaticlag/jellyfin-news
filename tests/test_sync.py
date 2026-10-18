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
