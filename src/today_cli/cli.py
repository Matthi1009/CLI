"""Einstiegspunkt: `today` auf der Kommandozeile."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from today_cli import __version__, calendar_ics, config, github, net, render, tasks, weather

SECTIONS = ["weather", "calendar", "github", "tasks"]
TITLES = {"weather": "Wetter", "calendar": "Termine", "github": "GitHub", "tasks": "Aufgaben"}


def read_file(path: str) -> str:
    return config.expand(path).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="today", description="Dein Tagesüberblick im Terminal.")
    parser.add_argument("--config", type=Path, help="Pfad zur Config (Standard: ~/.config/today/config.toml)")
    parser.add_argument("--only", help="Nur diese Bereiche, kommagetrennt: " + ",".join(SECTIONS))
    parser.add_argument("--no-color", action="store_true", help="Ohne Farben ausgeben")
    parser.add_argument("--init", action="store_true", help="Beispiel-Config anlegen")
    parser.add_argument("--force", action="store_true", help="Mit --init eine bestehende Config überschreiben")
    parser.add_argument("--version", action="version", version=f"today {__version__}")
    return parser


def choose_sections(cfg: dict, only: str | None) -> list[str]:
    if only:
        wanted = [part.strip() for part in only.split(",") if part.strip()]
        unknown = [part for part in wanted if part not in SECTIONS]
        if unknown:
            raise ValueError(f"Unbekannte Bereiche: {', '.join(unknown)}. Erlaubt: {', '.join(SECTIONS)}")
        return [name for name in SECTIONS if name in wanted]
    return [name for name in SECTIONS if cfg.get(name, {}).get("enabled")]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.init:
        try:
            path = config.write_example(args.config, force=args.force)
        except config.ConfigError as err:
            print(err, file=sys.stderr)
            return 1
        print(f"Config angelegt: {path}")
        return 0

    try:
        cfg = config.load_config(args.config)
        sections = choose_sections(cfg, args.only)
    except (config.ConfigError, ValueError) as err:
        print(err, file=sys.stderr)
        return 2

    use_color = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
    width = min(int(cfg["display"].get("width", 72)), shutil.get_terminal_size((80, 24)).columns)
    style = render.Style(color=use_color, icons=bool(cfg["display"].get("icons", True)), width=width)
    now = datetime.now()

    jobs = {
        "weather": lambda: weather.fetch(cfg["weather"], net.get_json),
        "calendar": lambda: calendar_ics.load_events(cfg["calendar"].get("sources", []), net.get_text, read_file),
        "github": lambda: github.fetch(cfg["github"], net.get_json),
        "tasks": lambda: tasks.load_tasks(cfg["tasks"].get("files", []), read_file),
    }

    # Netzwerkabfragen laufen parallel, damit die Ausgabe schnell kommt
    with ThreadPoolExecutor(max_workers=len(SECTIONS)) as pool:
        futures = {name: pool.submit(jobs[name]) for name in sections}
        lines = render.render_header(style, now, cfg.get("name", ""))
        for name in sections:
            try:
                result = futures[name].result()
            except Exception as err:  # noqa: BLE001 – ein Bereich darf die anderen nicht abbrechen
                lines += render.render_error(style, TITLES[name], str(err) or type(err).__name__)
                continue
            lines += render_section(name, result, cfg, style, now)

    print("\n".join(lines))
    return 0


def render_section(name: str, result, cfg: dict, style: render.Style, now: datetime) -> list[str]:
    if name == "weather":
        return render.render_weather(style, result)
    if name == "calendar":
        events, errors = result
        tomorrow = None
        if cfg["calendar"].get("show_tomorrow", True):
            tomorrow = calendar_ics.occurrences_on(events, now.date() + timedelta(days=1))
        return render.render_calendar(style, calendar_ics.occurrences_on(events, now.date()), tomorrow, now, errors)
    if name == "github":
        return render.render_github(style, result)
    if name == "tasks":
        found, errors = result
        return render.render_tasks(style, found, now.date(), int(cfg["tasks"].get("max_items", 8)), errors)
    return []


if __name__ == "__main__":
    raise SystemExit(main())
