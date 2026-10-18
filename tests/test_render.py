import unittest

from jellyfin_news import render

MOVIE = {
    "id": 42,
    "title": 'Fast & "Furious": Part/2?',
    "original_title": "Original",
    "release_date": "2026-10-16",
    "overview": "A <heist> & more.",
    "vote_average": 7.249,
    "genres": [{"name": "Action"}],
    "credits": {"cast": [{"name": "Jane Doe", "character": "Hero"}]},
    "videos": {
        "results": [
            {"site": "YouTube", "type": "Teaser", "key": "teaser", "iso_639_1": "fr"},
            {"site": "YouTube", "type": "Trailer", "key": "en_trailer", "iso_639_1": "en", "official": True},
            {"site": "YouTube", "type": "Trailer", "key": "fr_trailer", "iso_639_1": "fr", "official": True},
            {"site": "Vimeo", "type": "Trailer", "key": "vimeo", "iso_639_1": "fr"},
        ]
    },
    "watch/providers": {
        "results": {"FR": {"flatrate": [{"provider_name": "Netflix"}, {"provider_name": "Netflix"}]}}
    },
}


class RenderTest(unittest.TestCase):
    def test_safe_name_strips_illegal_characters(self):
        self.assertEqual(render.safe_name('A: B/C?*"'), "A BC")
        self.assertEqual(render.safe_name("???"), "Untitled")

    def test_folder_name_carries_tmdb_id(self):
        self.assertEqual(render.folder_name(MOVIE), "Fast & Furious Part2 (2026) [tmdbid-42]")

    def test_trailer_prefers_language_then_official_trailer(self):
        self.assertEqual(render.pick_trailer(MOVIE, "fr-FR"), "fr_trailer")
        self.assertEqual(render.pick_trailer(MOVIE, "en-US"), "en_trailer")
        self.assertIsNone(render.pick_trailer({"videos": {"results": []}}, "en-US"))

    def test_providers_are_deduplicated_per_country(self):
        self.assertEqual(render.stream_providers(MOVIE, "FR"), ["Netflix"])
        self.assertEqual(render.stream_providers(MOVIE, "US"), [])

    def test_nfo_is_escaped_and_contains_trailer(self):
        nfo = render.build_nfo("movie", MOVIE, ["Netflix", "New"], "fr_trailer")
        self.assertIn("<plot>A &lt;heist&gt; &amp; more.</plot>", nfo)
        self.assertIn("videoid=fr_trailer</trailer>", nfo)
        self.assertIn("<rating>7.2</rating>", nfo)
        self.assertIn("<tag>New</tag>", nfo)

    def test_tv_uses_tvshow_root(self):
        show = {"id": 1, "name": "Show", "first_air_date": "2026-01-02", "overview": "x"}
        self.assertIn("<tvshow>", render.build_nfo("tv", show, [], None))

    def test_strm_falls_back_to_tmdb_page(self):
        self.assertEqual(render.strm_target(MOVIE, "movie", None), "https://www.themoviedb.org/movie/42\n")
