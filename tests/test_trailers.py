import tempfile
import unittest
from pathlib import Path

from jellyfin_news import trailers
from jellyfin_news.config import Config


class TrailersTest(unittest.TestCase):
    def test_command_prefers_h264_and_respects_height(self):
        cfg = Config(output_dir=Path("/x"), trailer_max_height=360, yt_dlp_extra_args=("--foo",))
        cmd = trailers.build_command(cfg, "abc", Path("/x/t.mp4"))
        self.assertIn("--foo", cmd)
        self.assertIn("height<=360", cmd[cmd.index("-f") + 1])
        self.assertIn("vcodec^=avc1", cmd[cmd.index("-f") + 1])
        self.assertTrue(cmd[-1].endswith("watch?v=abc"))

    def test_existing_file_is_not_downloaded_again(self):
        dest = Path(tempfile.mkdtemp()) / "t.mp4"
        dest.write_bytes(b"x")
        self.assertTrue(
            trailers.download_trailer(Config(output_dir=dest.parent, yt_dlp_path="/nonexistent"), "abc", dest)
        )

    def test_missing_binary_is_a_soft_failure(self):
        dest = Path(tempfile.mkdtemp()) / "t.mp4"
        cfg = Config(output_dir=dest.parent, yt_dlp_path="/nonexistent/yt-dlp", trailer_min_free_gb=0)
        self.assertFalse(trailers.download_trailer(cfg, "abc", dest))

    def test_disk_guard(self):
        self.assertFalse(trailers.has_free_space(Path("/"), 10**9))
        self.assertTrue(trailers.has_free_space(Path("/"), 0))
