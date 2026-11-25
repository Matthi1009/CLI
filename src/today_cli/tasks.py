"""Offene Aufgaben aus Markdown-Dateien (z. B. Obsidian) lesen."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

TASK_RE = re.compile(r"^\s*[-*+]\s+\[(?P<state>[ xX])\]\s+(?P<text>.+?)\s*$")
# Fälligkeitsdatum: Obsidian-Tasks-Format "📅 2026-12-01", "due:2026-12-01" oder "@2026-12-01"
DUE_RE = re.compile(r"(?:📅\s*|\bdue:\s*|@)(?P<date>\d{4}-\d{2}-\d{2})")


@dataclass
class Task:
    text: str
    due: date | None
    source: str

    def is_overdue(self, today: date) -> bool:
        return self.due is not None and self.due < today


def parse_tasks(text: str, source: str = "") -> list[Task]:
    """Nur offene Aufgaben ("- [ ]") zurückgeben."""
    tasks: list[Task] = []
    for line in text.splitlines():
        match = TASK_RE.match(line)
        if not match or match.group("state") != " ":
            continue
        body = match.group("text")
        due = None
        due_match = DUE_RE.search(body)
        if due_match:
            try:
                due = date.fromisoformat(due_match.group("date"))
            except ValueError:
                due = None
            body = (body[: due_match.start()] + body[due_match.end() :]).strip()
        body = re.sub(r"\s{2,}", " ", body)
        if body:
            tasks.append(Task(text=body, due=due, source=source))
    return tasks


def sort_tasks(tasks: list[Task]) -> list[Task]:
    # Mit Datum zuerst (früheste oben), dann ohne Datum in Datei-Reihenfolge
    return sorted(tasks, key=lambda t: (t.due is None, t.due or date.max))


def load_tasks(files: list[str], read_file) -> tuple[list[Task], list[str]]:
    tasks: list[Task] = []
    errors: list[str] = []
    for path in files:
        try:
            tasks.extend(parse_tasks(read_file(path), source=path))
        except OSError as err:
            errors.append(f"{path}: {err.strerror or err}")
        except UnicodeDecodeError:
            errors.append(f"{path}: keine gültige UTF-8-Datei")
    return sort_tasks(tasks), errors
