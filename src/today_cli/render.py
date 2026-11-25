"""Ausgabe im Terminal: Farben, Überschriften und die einzelnen Bereiche."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from today_cli.calendar_ics import Occurrence
from today_cli.github import GitHubSummary, Item
from today_cli.tasks import Task
from today_cli.weather import Weather

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


class Style:
    """ANSI-Farben, die sich komplett abschalten lassen."""

    CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35", "cyan": "36"}

    def __init__(self, color: bool = True, icons: bool = True, width: int = 72):
        self.color = color
        self.icons = icons
        self.width = width

    def __getattr__(self, name: str):
        if name not in self.CODES:
            raise AttributeError(name)
        code = self.CODES[name]
        return lambda text: f"\033[{code}m{text}\033[0m" if self.color else text

    def icon(self, symbol: str) -> str:
        return f"{symbol} " if self.icons else ""


def german_number(value: float, digits: int = 0) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def long_date(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]} {day.year}"


def greeting(now: datetime, name: str) -> str:
    if now.hour < 5:
        text = "Gute Nacht"
    elif now.hour < 11:
        text = "Guten Morgen"
    elif now.hour < 18:
        text = "Hallo"
    else:
        text = "Guten Abend"
    return f"{text}, {name}!" if name else f"{text}!"


# Steuerzeichen (z. B. ESC) aus fremden Texten entfernen, damit z. B. ein PR-Titel
# keine Terminal-Escape-Sequenzen ausführen oder die Ausgabe fälschen kann
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(text: str) -> str:
    return " ".join(_CONTROL_CHARS.sub(" ", str(text)).split())


def truncate(text: str, length: int) -> str:
    text = clean(text)
    return text if len(text) <= length else text[: max(1, length - 1)] + "…"


def heading(style: Style, title: str, symbol: str = "") -> str:
    label = f" {style.icon(symbol)}{title} "
    line = "──" + label + "─" * max(3, style.width - len(label) - 2)
    return "\n" + style.bold(style.cyan(line))


def render_header(style: Style, now: datetime, name: str) -> list[str]:
    return [style.bold(greeting(now, name)), style.dim(f"{long_date(now.date())} · {now:%H:%M} Uhr")]


def render_weather(style: Style, weather: Weather) -> list[str]:
    title = f"Wetter · {clean(weather.place)}" if weather.place else "Wetter"
    details = [f"↑ {german_number(weather.temp_max)}°  ↓ {german_number(weather.temp_min)}°"]
    if weather.rain_probability is not None:
        details.append(f"Regen {weather.rain_probability} %")
    details.append(f"Wind {german_number(weather.wind_kmh)} km/h")
    return [
        heading(style, title, weather.icon),
        f"  {style.bold(german_number(weather.temperature, 1) + ' °C')}  {weather.description}",
        "  " + style.dim(" · ".join(details)),
    ]


def _event_line(style: Style, occ: Occurrence, now: datetime | None) -> str:
    if occ.start is None:
        when = "ganztägig  "
    else:
        when = occ.start.strftime("%H:%M")
        when += f"–{occ.end:%H:%M}" if occ.end else "      "
    text = occ.summary + (f" ({occ.location})" if occ.location else "")
    text = truncate(text, style.width - len(when) - 4)
    is_past = now is not None and occ.end is not None and occ.end < now
    is_now = now is not None and occ.start is not None and occ.start <= now and (occ.end is None or now < occ.end)
    if is_past:
        return "  " + style.dim(f"{when}  {text}")
    if is_now:
        return f"  {style.green(when)}  {style.bold(text)} {style.green('← jetzt')}"
    return f"  {style.yellow(when)}  {text}"


def render_calendar(style: Style, today_events: list[Occurrence], tomorrow_events: list[Occurrence] | None,
                    now: datetime, errors: list[str]) -> list[str]:
    lines = [heading(style, "Termine", "📅")]
    lines.append("  " + style.bold("Heute"))
    lines += [_event_line(style, occ, now) for occ in today_events] or ["  " + style.dim("Keine Termine.")]
    if tomorrow_events is not None:
        lines.append("  " + style.bold("Morgen"))
        lines += [_event_line(style, occ, None) for occ in tomorrow_events] or ["  " + style.dim("Keine Termine.")]
    lines += ["  " + style.red(f"⚠ {clean(err)}") for err in errors]
    return lines


def _item_line(style: Style, item: Item) -> str:
    kind = style.magenta("PR   ") if item.is_pr else style.green("Issue")
    ref = clean(f"{item.repo}#{item.number}")
    return f"  {kind} {style.dim(ref)}  {truncate(item.title, style.width - len(ref) - 12)}"


def render_github(style: Style, summary: GitHubSummary) -> list[str]:
    parts = [f"{summary.open_total} offen in deinen Repos", f"{summary.review_total} Review-Anfragen"]
    if summary.unread_notifications is not None:
        count = summary.unread_notifications
        parts.append(f"{'50+' if count >= 50 else count} ungelesen")
    lines = [heading(style, f"GitHub · {clean(summary.login)}", "🐙"), "  " + " · ".join(parts)]
    if summary.review_items:
        lines.append("  " + style.bold("Wartet auf dein Review"))
        lines += [_item_line(style, item) for item in summary.review_items]
    if summary.open_items:
        lines.append("  " + style.bold("Zuletzt aktiv"))
        lines += [_item_line(style, item) for item in summary.open_items]
    return lines


def due_label(due: date, today: date) -> str:
    delta = (due - today).days
    if delta < -1:
        return f"seit {-delta} Tagen fällig"
    if delta == -1:
        return "seit gestern fällig"
    if delta == 0:
        return "heute fällig"
    if delta == 1:
        return "morgen"
    if delta < 7:
        return f"in {delta} Tagen"
    return due.strftime("%d.%m.")


def render_tasks(style: Style, tasks: list[Task], today: date, limit: int, errors: list[str]) -> list[str]:
    lines = [heading(style, "Aufgaben", "✅")]
    if not tasks:
        lines.append("  " + style.dim("Keine offenen Aufgaben."))
    for task in tasks[:limit]:
        label = ""
        if task.due is not None:
            text = due_label(task.due, today)
            if task.due < today:
                label = style.red(text)
            elif task.due <= today + timedelta(days=1):
                label = style.yellow(text)
            else:
                label = style.dim(text)
        room = style.width - 6 - (len(due_label(task.due, today)) + 2 if task.due else 0)
        lines.append(f"  • {truncate(task.text, room)}" + (f"  {label}" if label else ""))
    if len(tasks) > limit:
        lines.append("  " + style.dim(f"… und {len(tasks) - limit} weitere"))
    lines += ["  " + style.red(f"⚠ {clean(err)}") for err in errors]
    return lines


def render_error(style: Style, title: str, message: str) -> list[str]:
    return [heading(style, title), "  " + style.red(f"⚠ {clean(message)}")]
