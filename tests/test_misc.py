import contextlib
import io
import tomllib
import unittest
from datetime import datetime
from pathlib import Path

from today_cli import config, github, weather
from today_cli.cli import choose_sections, main
from today_cli.render import Style, clean, greeting, render_weather

ROOT = Path(__file__).resolve().parent.parent


class ConfigTest(unittest.TestCase):
    def test_example_file_matches_embedded_text(self):
        self.assertEqual((ROOT / "config.example.toml").read_text(encoding="utf-8"), config.EXAMPLE_CONFIG)

    def test_example_parses_and_covers_defaults(self):
        parsed = tomllib.loads(config.EXAMPLE_CONFIG)
        self.assertEqual(set(parsed), set(config.DEFAULTS))

    def test_merge_keeps_defaults(self):
        merged = config.merge(config.DEFAULTS, {"weather": {"place": "Graz"}})
        self.assertEqual(merged["weather"]["place"], "Graz")
        self.assertEqual(merged["weather"]["latitude"], config.DEFAULTS["weather"]["latitude"])
        self.assertEqual(config.DEFAULTS["weather"]["place"], "Wien")  # Original unverändert

    def test_invalid_values_raise_config_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            for content in ('[display]\nwidth = "abc"', '[tasks]\nfiles = "notiz.md"', '[github]\nmax_items = 0',
                            '[weather]\nlatitude = true', 'name = 5'):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(config.ConfigError):
                    config.load_config(path)
            path.write_text('[weather]\nlatitude = 47\nplace = "Graz"', encoding="utf-8")
            self.assertEqual(config.load_config(path)["weather"]["latitude"], 47)

    def test_choose_sections(self):
        cfg = config.merge(config.DEFAULTS, {"tasks": {"enabled": True}})
        self.assertEqual(choose_sections(cfg, None), ["weather", "github", "tasks"])
        self.assertEqual(choose_sections(cfg, "tasks,calendar"), ["calendar", "tasks"])
        with self.assertRaises(ValueError):
            choose_sections(cfg, "mail")


class WeatherTest(unittest.TestCase):
    PAYLOAD = {
        "current": {"temperature_2m": 4.46, "weather_code": 3, "wind_speed_10m": 12.2},
        "daily": {"temperature_2m_max": [6.1], "temperature_2m_min": [0.9], "precipitation_probability_max": [40]},
    }

    def test_parse_and_render(self):
        result = weather.parse(self.PAYLOAD, "Wien")
        self.assertEqual(result.description, "Bedeckt")
        text = "\n".join(render_weather(Style(color=False, icons=False), result))
        self.assertIn("4,5 °C", text)
        self.assertIn("Regen 40 %", text)

    def test_fetch_uses_coordinates(self):
        seen = []
        weather.fetch({"latitude": 47.07, "longitude": 15.44, "place": "Graz"}, lambda url: seen.append(url) or self.PAYLOAD)
        self.assertIn("latitude=47.07", seen[0])

    def test_unexpected_payload_gives_readable_error(self):
        with self.assertRaises(weather.WeatherError):
            weather.fetch({"latitude": 1, "longitude": 2}, lambda url: {"error": True, "reason": "Kaputt"})

    def test_unknown_code(self):
        self.assertEqual(weather.describe(1234)[0], "Unbekannt")


class GitHubTest(unittest.TestCase):
    def test_fetch_with_fake_api(self):
        def fake_get_json(url, headers=None):
            if url.endswith("/user"):
                return {"login": "octo"}
            if "review-requested" in url:
                return {"total_count": 0, "items": []}
            if "/notifications" in url:
                raise RuntimeError("kein Scope")
            return {"total_count": 1, "items": [{
                "repository_url": "https://api.github.com/repos/octo/demo", "number": 7,
                "title": "Bug", "html_url": "https://github.com/octo/demo/issues/7"}]}

        summary = github.fetch({"max_items": 3}, fake_get_json, token="x")
        self.assertEqual(summary.login, "octo")
        self.assertEqual(summary.open_items[0].repo, "octo/demo")
        self.assertFalse(summary.open_items[0].is_pr)
        self.assertIsNone(summary.unread_notifications)


class RenderTest(unittest.TestCase):
    def test_clean_removes_terminal_escapes(self):
        self.assertEqual(clean("Fix\x1b[2J bug\x07\nnow"), "Fix [2J bug now")


class CliTest(unittest.TestCase):
    def test_greeting(self):
        self.assertEqual(greeting(datetime(2026, 1, 1, 8), "Max"), "Guten Morgen, Max!")
        self.assertEqual(greeting(datetime(2026, 1, 1, 20), ""), "Guten Abend!")

    def test_init_does_not_overwrite(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "today" / "config.toml"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--init", "--config", str(path)]), 0)
                self.assertEqual(main(["--init", "--config", str(path)]), 1)
                self.assertEqual(main(["--init", "--force", "--config", str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
