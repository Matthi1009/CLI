"""Konfiguration laden (TOML) und mit Standardwerten zusammenführen."""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

# Standardwerte: alles, was in der Config-Datei fehlt, kommt von hier
DEFAULTS: dict = {
    "name": "",
    "display": {"icons": True, "width": 72},
    "weather": {"enabled": True, "latitude": 48.21, "longitude": 16.37, "place": "Wien"},
    "calendar": {"enabled": False, "sources": [], "show_tomorrow": True},
    "github": {"enabled": True, "max_items": 5},
    "tasks": {"enabled": False, "files": [], "max_items": 8},
}

# Wird von `today --init` geschrieben. Muss mit config.example.toml übereinstimmen (siehe Tests).
EXAMPLE_CONFIG = """\
# Konfiguration für today-cli
# Speicherort: ~/.config/today/config.toml

# Dein Name für die Begrüßung (leer lassen für eine neutrale Begrüßung)
name = ""

[display]
icons = true      # Emoji-Symbole anzeigen
width = 72        # maximale Breite der Ausgabe

[weather]
enabled = true
# Koordinaten deines Orts, z. B. von https://www.latlong.net
latitude = 48.21
longitude = 16.37
place = "Wien"

[calendar]
enabled = false
# .ics-Dateien oder https-Links (z. B. die geheime iCal-Adresse aus Google Kalender)
sources = []
show_tomorrow = true

[github]
enabled = true
# Token kommt aus `gh auth token` oder der Umgebungsvariable GITHUB_TOKEN
max_items = 5

[tasks]
enabled = false
# Markdown-Dateien mit Aufgaben im Format "- [ ] Aufgabe 📅 2026-12-01"
files = []
max_items = 8
"""


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "today" / "config.toml"


def merge(base: dict, override: dict) -> dict:
    """Verschachtelte Dicts zusammenführen, ohne die Eingaben zu verändern."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> dict:
    target = path or config_path()
    if not target.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"Fehler in {target}: {err}") from err
    cfg = merge(DEFAULTS, data)
    validate(cfg, target)
    return cfg


# (Abschnitt, Schlüssel, erwarteter Typ, Beschreibung für die Fehlermeldung)
_CHECKS = [
    ("display", "width", int, "eine ganze Zahl"),
    ("display", "icons", bool, "true oder false"),
    ("weather", "latitude", (int, float), "eine Zahl"),
    ("weather", "longitude", (int, float), "eine Zahl"),
    ("weather", "place", str, "ein Text"),
    ("calendar", "sources", list, "eine Liste"),
    ("calendar", "show_tomorrow", bool, "true oder false"),
    ("github", "max_items", int, "eine ganze Zahl"),
    ("tasks", "files", list, "eine Liste"),
    ("tasks", "max_items", int, "eine ganze Zahl"),
]


def validate(cfg: dict, source: Path | None = None) -> None:
    """Falsche Typen früh und verständlich melden statt mit Traceback abzustürzen."""
    where = f" in {source}" if source else ""
    if not isinstance(cfg.get("name"), str):
        raise ConfigError(f"name muss ein Text sein{where}.")
    for section in ("display", "weather", "calendar", "github", "tasks"):
        if not isinstance(cfg.get(section), dict):
            raise ConfigError(f"[{section}] muss ein Abschnitt sein{where}.")
        if not isinstance(cfg[section].get("enabled", True), bool):
            raise ConfigError(f"{section}.enabled muss true oder false sein{where}.")
    for section, key, expected, label in _CHECKS:
        value = cfg[section].get(key)
        # bool ist in Python auch ein int, deshalb extra ausschließen
        if not isinstance(value, expected) or (expected is not bool and isinstance(value, bool)):
            raise ConfigError(f"{section}.{key} muss {label} sein{where}.")
    for section, key in (("calendar", "sources"), ("tasks", "files")):
        if not all(isinstance(item, str) for item in cfg[section][key]):
            raise ConfigError(f"{section}.{key} darf nur Texte enthalten{where}.")
    for section, key in (("display", "width"), ("github", "max_items"), ("tasks", "max_items")):
        if cfg[section][key] < 1:
            raise ConfigError(f"{section}.{key} muss mindestens 1 sein{where}.")


def write_example(path: Path | None = None, force: bool = False) -> Path:
    target = path or config_path()
    if target.exists() and not force:
        raise ConfigError(f"{target} gibt es schon. Mit --force überschreiben.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    return target


def expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()
