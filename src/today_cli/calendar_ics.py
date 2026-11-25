"""Minimaler iCalendar-Parser (.ics) mit einfachen Wiederholungen.

Unterstützt: ganztägige und mehrtägige Termine, Termine über Mitternacht, UTC- und TZID-Zeiten,
RRULE mit FREQ=DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY (nur wöchentlich),
EXDATE, geänderte Einzeltermine (RECURRENCE-ID) und abgesagte Termine (STATUS:CANCELLED).

Serien werden in ihrer eigenen Zeitzone berechnet und erst danach in die lokale Zeit
umgerechnet, damit Uhrzeiten auch nach einer Sommerzeit-Umstellung stimmen.
Komplexere Regeln (z. B. "jeder 2. Dienstag im Monat") werden erkannt und nur am
ersten Termin angezeigt, statt still falsche Tage zu liefern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from today_cli.net import safe_host

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
SUPPORTED_FREQ = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
SUPPORTED_RULE_KEYS = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST"}

# Schutz vor Endlosschleifen bei kaputten Regeln
MAX_ITERATIONS = 20000


@dataclass
class Event:
    summary: str
    start: datetime | date  # in der Zeitzone der Quelle (naiv)
    end: datetime | date | None = None
    tz: tzinfo | None = None  # Zeitzone der Quelle, None = "schwebende" lokale Zeit
    local_tz: tzinfo | None = None  # Zielzeitzone, None = Systemzeitzone
    all_day: bool = False
    location: str = ""
    uid: str = ""
    rrule: dict[str, str] | None = None
    until: date | None = None
    exdates: set[date] = field(default_factory=set)
    recurrence_id: date | None = None
    cancelled: bool = False
    unsupported_rule: bool = False

    @property
    def start_date(self) -> date:
        return self.start.date() if isinstance(self.start, datetime) else self.start


@dataclass
class Occurrence:
    summary: str
    start: datetime | None  # None bei ganztägigen Terminen
    end: datetime | None
    location: str = ""


@dataclass
class ParseResult:
    events: list[Event]
    skipped: int = 0  # Termine, die wegen Fehlern übersprungen wurden

    @property
    def unsupported(self) -> int:
        return sum(1 for e in self.events if e.unsupported_rule)


def unfold(text: str) -> list[str]:
    """Gefaltete Zeilen (RFC 5545, Abschnitt 3.1) wieder zusammensetzen."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def parse_property(line: str) -> tuple[str, dict[str, str], str]:
    """'DTSTART;TZID=Europe/Vienna:20261125T080000' -> (name, params, value)."""
    in_quotes = False
    split_at = -1
    for index, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ":" and not in_quotes:
            split_at = index
            break
    if split_at < 0:
        return line.upper(), {}, ""
    head, value = line[:split_at], line[split_at + 1 :]
    parts = head.split(";")
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value


_ESCAPES = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}


def unescape(value: str) -> str:
    # In einem Durchgang, damit "\\n" (escapter Backslash + n) nicht zum Zeilenumbruch wird
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), value)


def parse_raw(value: str, params: dict[str, str]) -> tuple[datetime | date, bool, tzinfo | None]:
    """Liefert (naiver Wert, ganztägig, Zeitzone der Angabe)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return datetime.strptime(value[:8], "%Y%m%d").date(), True, None
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S"), False, timezone.utc
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    tzid = params.get("TZID")
    if tzid:
        try:
            return naive, False, ZoneInfo(tzid)
        except (ZoneInfoNotFoundError, ValueError):
            pass  # Unbekannte Zeitzone: als lokale Zeit behandeln
    return naive, False, None


def to_local(value: datetime, tz: tzinfo | None, local_tz: tzinfo | None) -> datetime:
    if tz is None:
        return value
    return value.replace(tzinfo=tz).astimezone(local_tz).replace(tzinfo=None)


def _date_in(value: datetime | date, value_tz: tzinfo | None, target_tz: tzinfo | None) -> date:
    """Datum eines Zeitpunkts in der Zeitzone des Termins (für EXDATE, UNTIL, RECURRENCE-ID)."""
    if not isinstance(value, datetime):
        return value
    if value_tz is not None and target_tz is not None and value_tz is not target_tz:
        value = value.replace(tzinfo=value_tz).astimezone(target_tz).replace(tzinfo=None)
    return value.date()


def parse_rrule(value: str) -> dict[str, str]:
    rule: dict[str, str] = {}
    for part in value.split(";"):
        if "=" in part:
            key, val = part.split("=", 1)
            rule[key.upper()] = val.upper() if key.upper() != "UNTIL" else val
    return rule


def rule_is_supported(rule: dict[str, str]) -> bool:
    freq = rule.get("FREQ", "")
    if freq not in SUPPORTED_FREQ:
        return False
    allowed = SUPPORTED_RULE_KEYS | ({"BYDAY"} if freq == "WEEKLY" else set())
    if not set(rule) <= allowed:
        return False
    if "BYDAY" in rule and any(day[-2:] not in WEEKDAYS or len(day) != 2 for day in rule["BYDAY"].split(",")):
        return False  # z. B. "2TU" mit Ordnungszahl
    return True


def parse_ics(text: str, local_tz: tzinfo | None = None) -> ParseResult:
    events: list[Event] = []
    skipped = 0
    current: dict | None = None
    for line in unfold(text):
        name, params, value = parse_property(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            current = {"props": []}
        elif name == "END" and value.upper() == "VEVENT" and current is not None:
            try:
                event = _build_event(current["props"], local_tz)
            except (ValueError, KeyError):
                event = None
                skipped += 1  # Ein kaputter Termin soll nicht die ganze Datei kosten
            if event is not None:
                events.append(event)
            current = None
        elif current is not None:
            current["props"].append((name, params, value))
    return ParseResult(_apply_overrides(events), skipped)


def _build_event(props: list[tuple[str, dict[str, str], str]], local_tz: tzinfo | None) -> Event | None:
    fields: dict = {}
    raw_exdates: list[tuple[datetime | date, tzinfo | None]] = []
    raw_recurrence = None
    for name, params, value in props:
        if name == "SUMMARY":
            fields["summary"] = unescape(value)
        elif name == "LOCATION":
            fields["location"] = unescape(value)
        elif name == "UID":
            fields["uid"] = value
        elif name == "STATUS":
            fields["cancelled"] = value.upper() == "CANCELLED"
        elif name == "DTSTART":
            fields["start"], fields["all_day"], fields["tz"] = parse_raw(value, params)
        elif name == "DTEND":
            end, _, end_tz = parse_raw(value, params)
            fields["end_raw"] = (end, end_tz)
        elif name == "RRULE":
            fields["rrule"] = parse_rrule(value)
        elif name == "EXDATE":
            for item in value.split(","):
                parsed, _, item_tz = parse_raw(item, params)
                raw_exdates.append((parsed, item_tz))
        elif name == "RECURRENCE-ID":
            parsed, _, rec_tz = parse_raw(value, params)
            raw_recurrence = (parsed, rec_tz)

    if "start" not in fields:
        return None
    tz = fields.get("tz")
    event = Event(
        summary=fields.get("summary", "(ohne Titel)"),
        start=fields["start"],
        tz=tz,
        local_tz=local_tz,
        all_day=fields.get("all_day", False),
        location=fields.get("location", ""),
        uid=fields.get("uid", ""),
        cancelled=fields.get("cancelled", False),
    )
    if "end_raw" in fields:
        end, end_tz = fields["end_raw"]
        if isinstance(end, datetime) and end_tz is not None and tz is not None and end_tz is not tz:
            end = end.replace(tzinfo=end_tz).astimezone(tz).replace(tzinfo=None)
        event.end = end
    event.exdates = {_date_in(value, value_tz, tz) for value, value_tz in raw_exdates}
    if raw_recurrence:
        event.recurrence_id = _date_in(raw_recurrence[0], raw_recurrence[1], tz)

    rule = fields.get("rrule")
    if rule:
        if rule_is_supported(rule):
            event.rrule = rule
            if rule.get("UNTIL"):
                until, _, until_tz = parse_raw(rule["UNTIL"], {})
                event.until = _date_in(until, until_tz, tz)
        else:
            event.unsupported_rule = True  # Nur den ersten Termin zeigen
    return event


def _apply_overrides(events: list[Event]) -> list[Event]:
    """Geänderte Einzeltermine ersetzen den Termin der Serie an diesem Tag."""
    masters = {e.uid: e for e in events if e.uid and e.recurrence_id is None and e.rrule}
    result: list[Event] = []
    for event in events:
        if event.recurrence_id is not None:
            master = masters.get(event.uid)
            if master is not None:
                master.exdates.add(event.recurrence_id)
            event.rrule = None  # Ein Override ist immer ein Einzeltermin
        if not event.cancelled:
            result.append(event)
    return result


def _iter_dates(start: date, rule: dict[str, str], limit: date):
    """Alle Termindaten einer Serie von start bis einschließlich limit."""
    freq = rule.get("FREQ", "")
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    steps = 0
    if freq == "DAILY":
        current = start
        while current <= limit and steps < MAX_ITERATIONS:
            yield current
            current += timedelta(days=interval)
            steps += 1
    elif freq == "WEEKLY":
        bydays = sorted({WEEKDAYS[d] for d in rule.get("BYDAY", "").split(",") if d in WEEKDAYS})
        bydays = bydays or [start.weekday()]
        week_start = start - timedelta(days=start.weekday())
        while week_start <= limit and steps < MAX_ITERATIONS:
            for weekday in bydays:
                candidate = week_start + timedelta(days=weekday)
                if start <= candidate <= limit:
                    yield candidate
            week_start += timedelta(weeks=interval)
            steps += 1
    elif freq in ("MONTHLY", "YEARLY"):
        months = interval if freq == "MONTHLY" else 12 * interval
        index = 0
        while steps < MAX_ITERATIONS:
            year, month = divmod(start.month - 1 + index * months, 12)
            year += start.year
            if date(year, month + 1, 1) > limit:
                break
            try:
                candidate = date(year, month + 1, start.day)
            except ValueError:
                candidate = None  # z. B. 31. in einem Monat mit 30 Tagen: RFC sagt überspringen
            if candidate is not None and candidate <= limit:
                yield candidate
            index += 1
            steps += 1


def starts_on(event: Event, day: date) -> bool:
    """Beginnt ein Termin (oder eine Wiederholung) an diesem Tag? Datum in der Zeitzone der Quelle."""
    first = event.start_date
    if day < first:
        return False
    if not event.rrule:
        return first == day
    if event.until is not None and day > event.until:
        return False
    count = int(event.rrule["COUNT"]) if event.rrule.get("COUNT", "").isdigit() else None
    for number, candidate in enumerate(_iter_dates(first, event.rrule, day), start=1):
        if count is not None and number > count:
            return False
        if candidate == day:
            return day not in event.exdates
    return False


def _span_days(event: Event) -> int:
    """Wie viele Kalendertage ein einzelner Termin berührt (mindestens 1)."""
    if event.end is None:
        return 1
    if event.all_day:
        end = event.end.date() if isinstance(event.end, datetime) else event.end
        return max(1, (end - event.start_date).days)  # DTEND ist exklusiv
    last_moment = event.end - timedelta(microseconds=1)
    return max(1, (last_moment.date() - event.start_date).days + 1)


def occurrences_on(events: list[Event], day: date) -> list[Occurrence]:
    found: list[Occurrence] = []
    for event in events:
        span = _span_days(event)
        if event.all_day or not isinstance(event.start, datetime):
            # Mehrtägige Termine auch an den Folgetagen zeigen
            if any(starts_on(event, day - timedelta(days=k)) for k in range(span)):
                found.append(Occurrence(event.summary, None, None, event.location))
            continue
        duration = (event.end - event.start) if isinstance(event.end, datetime) else None
        # Durch Zeitzonen-Umrechnung kann sich das Datum um einen Tag verschieben
        for offset in range(-1, span + 1):
            source_day = day - timedelta(days=offset)
            if not starts_on(event, source_day):
                continue
            source_start = datetime.combine(source_day, event.start.time())
            start = to_local(source_start, event.tz, event.local_tz)
            end = to_local(source_start + duration, event.tz, event.local_tz) if duration else None
            last_day = (end - timedelta(microseconds=1)).date() if end and end > start else start.date()
            if start.date() <= day <= last_day:
                found.append(Occurrence(event.summary, start, end, event.location))
                break
    # Ganztägige Termine zuerst, dann nach Uhrzeit
    found.sort(key=lambda occ: (occ.start is not None, occ.start or datetime.min, occ.summary))
    return found


def load_events(sources: list[str], get_text, read_file) -> tuple[list[Event], list[str]]:
    """Alle Quellen laden. Liefert (Termine, Hinweise/Fehler pro Quelle)."""
    events: list[Event] = []
    messages: list[str] = []
    for source in sources:
        label = source_label(source)
        try:
            text = get_text(source) if is_url(source) else read_file(source)
            result = parse_ics(text)
        except Exception as err:  # noqa: BLE001 – eine kaputte Quelle soll die anderen nicht stoppen
            messages.append(f"{label}: {err}")
            continue
        events.extend(result.events)
        if result.skipped:
            messages.append(f"{label}: {result.skipped} fehlerhafte Termine übersprungen")
        if result.unsupported:
            messages.append(f"{label}: {result.unsupported} Serientermine mit komplexer Wiederholung "
                            "werden nur am ersten Tag angezeigt")
    return events, messages


def is_url(source: str) -> bool:
    return source.startswith(("https://", "http://"))


def source_label(source: str) -> str:
    # Bei Links nur den Host zeigen, weil iCal-Links oft einen geheimen Schlüssel enthalten
    return safe_host(source) if is_url(source) else source
