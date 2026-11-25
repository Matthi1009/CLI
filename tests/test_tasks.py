import unittest
from datetime import date

from today_cli.render import due_label
from today_cli.tasks import parse_tasks, sort_tasks

NOTE = """
# Lernziele
- [ ] SQL-Joins üben 📅 2026-11-27
- [x] Erledigt 📅 2026-11-01
* [ ] Referat vorbereiten due:2026-11-24
- [ ] Ohne Datum
- [ ]
Text - [ ] keine Aufgabe
  - [ ] Eingerückt @2026-12-10
"""


class TaskTest(unittest.TestCase):
    def test_only_open_tasks_with_due_dates(self):
        tasks = parse_tasks(NOTE, "note.md")
        self.assertEqual([t.text for t in tasks], ["SQL-Joins üben", "Referat vorbereiten", "Ohne Datum", "Eingerückt"])
        self.assertEqual(tasks[0].due, date(2026, 11, 27))
        self.assertIsNone(tasks[2].due)

    def test_sorting_and_overdue(self):
        tasks = sort_tasks(parse_tasks(NOTE))
        self.assertEqual(tasks[0].text, "Referat vorbereiten")
        self.assertEqual(tasks[-1].text, "Ohne Datum")
        self.assertTrue(tasks[0].is_overdue(date(2026, 11, 25)))

    def test_invalid_date_is_ignored(self):
        tasks = parse_tasks("- [ ] Kaputt 📅 2026-13-40")
        self.assertIsNone(tasks[0].due)
        self.assertEqual(tasks[0].text, "Kaputt")

    def test_due_labels(self):
        today = date(2026, 11, 25)
        self.assertEqual(due_label(date(2026, 11, 22), today), "seit 3 Tagen fällig")
        self.assertEqual(due_label(date(2026, 11, 24), today), "seit gestern fällig")
        self.assertEqual(due_label(today, today), "heute fällig")
        self.assertEqual(due_label(date(2026, 11, 26), today), "morgen")
        self.assertEqual(due_label(date(2026, 11, 28), today), "in 3 Tagen")
        self.assertEqual(due_label(date(2026, 12, 24), today), "24.12.")


if __name__ == "__main__":
    unittest.main()
