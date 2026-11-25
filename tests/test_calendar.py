import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from today_cli.calendar_ics import (load_events, occurrences_on, parse_ics, parse_property, source_label,
                                    starts_on, unescape, unfold)

VIENNA = ZoneInfo("Europe/Vienna")


def ics(*events: str) -> str:
    body = "\n".join(f"BEGIN:VEVENT\n{e.strip()}\nEND:VEVENT" for e in events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{body}\nEND:VCALENDAR\n"


def on(text: str, day: date):
    return occurrences_on(parse_ics(text, VIENNA).events, day)


class ParsingTest(unittest.TestCase):
    def test_unfold_joins_continuation_lines(self):
        self.assertEqual(unfold("SUMMARY:Lange\r\n  Zeile\r\nUID:1"), ["SUMMARY:Lange Zeile", "UID:1"])

    def test_parse_property_with_quoted_colon(self):
        name, params, value = parse_property('DTSTART;TZID="Custom:Zone":20261125T080000')
        self.assertEqual(name, "DTSTART")
        self.assertEqual(params["TZID"], "Custom:Zone")
        self.assertEqual(value, "20261125T080000")

    def test_unescape_in_one_pass(self):
        self.assertEqual(unescape("Mathe\\, Physik"), "Mathe, Physik")
        self.assertEqual(unescape("Zeile1\\nZeile2"), "Zeile1\nZeile2")
        self.assertEqual(unescape("C:\\\\new"), "C:\\new")  # escapter Backslash + n bleibt so

    def test_utc_time_is_converted_to_local(self):
        result = on(ics("SUMMARY:Call\nDTSTART:20261125T120000Z\nDTEND:20261125T130000Z"), date(2026, 11, 25))
        self.assertEqual(result[0].start, datetime(2026, 11, 25, 13, 0))
        self.assertEqual(result[0].end, datetime(2026, 11, 25, 14, 0))

    def test_tzid_time_is_converted_to_local(self):
        result = on(ics("SUMMARY:NY\nDTSTART;TZID=America/New_York:20261125T080000"), date(2026, 11, 25))
        self.assertEqual(result[0].start, datetime(2026, 11, 25, 14, 0))

    def test_conversion_can_move_event_to_next_day(self):
        text = ics("SUMMARY:Spät in NY\nDTSTART;TZID=America/New_York:20261125T200000")
        self.assertEqual(on(text, date(2026, 11, 25)), [])
        self.assertEqual(on(text, date(2026, 11, 26))[0].start, datetime(2026, 11, 26, 2, 0))

    def test_escaped_text_and_all_day(self):
        events = parse_ics(ics("SUMMARY:Mathe\\, Physik\nDTSTART;VALUE=DATE:20261125"), VIENNA).events
        self.assertEqual(events[0].summary, "Mathe, Physik")
        self.assertTrue(events[0].all_day)

    def test_broken_event_is_skipped_not_whole_file(self):
        result = parse_ics(ics("SUMMARY:Kaputt\nDTSTART:2026-11-25", "SUMMARY:Gut\nDTSTART;VALUE=DATE:20261125"), VIENNA)
        self.assertEqual([e.summary for e in result.events], ["Gut"])
        self.assertEqual(result.skipped, 1)


class RecurrenceTest(unittest.TestCase):
    def test_all_day_multi_day_event(self):
        text = ics("SUMMARY:Ferien\nDTSTART;VALUE=DATE:20261223\nDTEND;VALUE=DATE:20261226")
        self.assertEqual(len(on(text, date(2026, 12, 25))), 1)
        self.assertEqual(on(text, date(2026, 12, 26)), [])

    def test_recurring_multi_day_event_shows_on_every_day(self):
        text = ics("SUMMARY:Camp\nDTSTART;VALUE=DATE:20260105\nDTEND;VALUE=DATE:20260108\nRRULE:FREQ=MONTHLY")
        self.assertEqual(len(on(text, date(2026, 2, 7))), 1)
        self.assertEqual(on(text, date(2026, 2, 8)), [])

    def test_event_over_midnight(self):
        text = ics("SUMMARY:LAN-Party\nDTSTART:20261125T220000\nDTEND:20261126T020000")
        self.assertEqual(len(on(text, date(2026, 11, 25))), 1)
        next_day = on(text, date(2026, 11, 26))
        self.assertEqual(next_day[0].end, datetime(2026, 11, 26, 2, 0))
        self.assertEqual(on(text, date(2026, 11, 27)), [])

    def test_weekly_byday_with_count(self):
        # Mo und Mi, insgesamt 4 Termine ab Mo, 23.11.2026
        event = parse_ics(ics("SUMMARY:POS\nDTSTART:20261123T080000\nRRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4"), VIENNA).events[0]
        self.assertTrue(starts_on(event, date(2026, 11, 25)))
        self.assertTrue(starts_on(event, date(2026, 12, 2)))
        self.assertFalse(starts_on(event, date(2026, 12, 7)))  # wäre der 5. Termin
        self.assertFalse(starts_on(event, date(2026, 11, 24)))

    def test_weekly_until_and_interval(self):
        text = ics("SUMMARY:Sport\nDTSTART:20261102T150000\nRRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=20261201T000000Z")
        event = parse_ics(text, VIENNA).events[0]
        self.assertTrue(starts_on(event, date(2026, 11, 16)))
        self.assertFalse(starts_on(event, date(2026, 11, 9)))
        self.assertTrue(starts_on(event, date(2026, 11, 30)))
        self.assertFalse(starts_on(event, date(2026, 12, 14)))

    def test_series_keeps_local_time_across_dst(self):
        # Wöchentlich 08:00 Wiener Zeit, angelegt im Sommer: auch im Winter 08:00
        text = ics("SUMMARY:Schule\nDTSTART;TZID=Europe/Vienna:20260907T080000\nRRULE:FREQ=WEEKLY")
        self.assertEqual(on(text, date(2026, 11, 23))[0].start, datetime(2026, 11, 23, 8, 0))

    def test_utc_series_follows_utc(self):
        # In UTC angelegte Serie: 06:00 UTC = 08:00 im Sommer, 07:00 im Winter
        text = ics("SUMMARY:Call\nDTSTART:20260907T060000Z\nRRULE:FREQ=WEEKLY")
        self.assertEqual(on(text, date(2026, 9, 14))[0].start, datetime(2026, 9, 14, 8, 0))
        self.assertEqual(on(text, date(2026, 11, 23))[0].start, datetime(2026, 11, 23, 7, 0))

    def test_monthly_skips_invalid_days(self):
        event = parse_ics(ics("SUMMARY:Miete\nDTSTART;VALUE=DATE:20260131\nRRULE:FREQ=MONTHLY"), VIENNA).events[0]
        self.assertTrue(starts_on(event, date(2026, 3, 31)))
        self.assertFalse(starts_on(event, date(2026, 2, 28)))

    def test_unsupported_rule_only_shows_first_date(self):
        text = ics("SUMMARY:Elternabend\nDTSTART:20261110T180000\nRRULE:FREQ=MONTHLY;BYDAY=2TU")
        result = parse_ics(text, VIENNA)
        self.assertEqual(result.unsupported, 1)
        self.assertEqual(len(occurrences_on(result.events, date(2026, 11, 10))), 1)
        self.assertEqual(occurrences_on(result.events, date(2026, 12, 10)), [])

    def test_exdate_and_override(self):
        text = ics(
            "UID:abc\nSUMMARY:Nachhilfe\nDTSTART:20261102T170000\nRRULE:FREQ=WEEKLY\nEXDATE:20261109T170000",
            "UID:abc\nSUMMARY:Nachhilfe (verschoben)\nRECURRENCE-ID:20261116T170000\nDTSTART:20261117T180000",
            "UID:abc\nSUMMARY:Nachhilfe\nRECURRENCE-ID:20261123T170000\nDTSTART:20261123T170000\nSTATUS:CANCELLED",
        )
        self.assertEqual(on(text, date(2026, 11, 9)), [])
        self.assertEqual(on(text, date(2026, 11, 16)), [])
        self.assertEqual([o.summary for o in on(text, date(2026, 11, 17))], ["Nachhilfe (verschoben)"])
        self.assertEqual(on(text, date(2026, 11, 23)), [])
        self.assertEqual(len(on(text, date(2026, 11, 30))), 1)

    def test_occurrences_sorted_all_day_first(self):
        text = ics(
            "SUMMARY:Spät\nDTSTART:20261125T180000\nDTEND:20261125T190000",
            "SUMMARY:Früh\nDTSTART:20261125T080000",
            "SUMMARY:Geburtstag\nDTSTART;VALUE=DATE:20261125",
        )
        result = on(text, date(2026, 11, 25))
        self.assertEqual([o.summary for o in result], ["Geburtstag", "Früh", "Spät"])
        self.assertEqual(result[2].end, datetime(2026, 11, 25, 19, 0))


class LoadTest(unittest.TestCase):
    def test_label_hides_credentials_and_paths(self):
        self.assertEqual(source_label("https://user:geheim@cal.example.com/private/abc123/basic.ics"), "cal.example.com")
        self.assertEqual(source_label("~/kalender.ics"), "~/kalender.ics")

    def test_failing_source_does_not_stop_others(self):
        def read_file(path):
            if path == "kaputt.ics":
                raise OSError("nicht gefunden")
            return ics("SUMMARY:Ok\nDTSTART;VALUE=DATE:20261125")

        events, messages = load_events(["kaputt.ics", "gut.ics"], lambda url: "", read_file)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(messages), 1)
        self.assertIn("kaputt.ics", messages[0])


if __name__ == "__main__":
    unittest.main()
