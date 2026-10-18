import tempfile
import unittest
from pathlib import Path

from jellyfin_news.config import ConfigError, load_config


def write(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


ENV = {"TMDB_READ_TOKEN": "tok"}


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config(write('[output]\ndir = "/tmp/x"\n'), ENV)
        self.assertEqual((cfg.country, cfg.language, cfg.recent_days), ("US", "en-US", 45))
        self.assertEqual(cfg.tmdb_token, "tok")

    def test_country_is_normalised_and_validated(self):
        cfg = load_config(write('[locale]\ncountry = "fr"\nlanguage = "fr-FR"\n[output]\ndir = "/x"\n'), ENV)
        self.assertEqual(cfg.country, "FR")
        with self.assertRaises(ConfigError):
            load_config(write('[locale]\ncountry = "France"\n[output]\ndir = "/x"\n'), ENV)

    def test_v3_key_is_marked(self):
        cfg = load_config(write('[output]\ndir = "/x"\n'), {"TMDB_API_KEY": "abc"})
        self.assertEqual(cfg.tmdb_token, "v3:abc")

    def test_missing_credentials_and_output(self):
        with self.assertRaises(ConfigError):
            load_config(write('[output]\ndir = "/x"\n'), {})
        with self.assertRaises(ConfigError):
            load_config(write("[locale]\n"), ENV)

    def test_invalid_numbers(self):
        with self.assertRaises(ConfigError):
            load_config(write('[window]\nrecent_days = 0\n[output]\ndir = "/x"\n'), ENV)
