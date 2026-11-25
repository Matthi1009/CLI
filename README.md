# today-cli

Dein Tagesüberblick im Terminal. Ein Befehl, und du siehst Wetter, Termine, offene GitHub-Issues und deine Aufgaben.

```
Guten Morgen, Matthi!
Mittwoch, 25. November 2026 · 07:42 Uhr

── ☁️ Wetter · Wien ──────────────────────────────────────────
  4,5 °C  Bedeckt
  ↑ 6°  ↓ 1° · Regen 40 % · Wind 12 km/h

── 📅 Termine ────────────────────────────────────────────────
  Heute
  08:00–09:40  POS (Raum 204)
  13:00–14:40  DBMM
  Morgen
  ganztägig    Wandertag

── 🐙 GitHub · Matthi1009 ────────────────────────────────────
  3 offen in deinen Repos · 1 Review-Anfragen · 2 ungelesen
  Wartet auf dein Review
  PR    demo#12  Neue Startseite

── ✅ Aufgaben ───────────────────────────────────────────────
  • Referat vorbereiten  seit gestern fällig
  • SQL-Joins üben  morgen
  • Bewerbung schreiben
```

## Funktionen

- **Wetter** von [Open-Meteo](https://open-meteo.com), kostenlos und ohne API-Key
- **Termine** aus `.ics`-Dateien oder iCal-Links (Google Kalender, Nextcloud, Outlook, WebUntis-Export …), inklusive wiederkehrender Termine
- **GitHub**: offene Issues und PRs in deinen Repos, Review-Anfragen und ungelesene Benachrichtigungen
- **Aufgaben** aus Markdown-Dateien, zum Beispiel aus deinem Obsidian-Vault (`- [ ] Aufgabe 📅 2026-12-01`)
- Keine Abhängigkeiten, nur die Python-Standardbibliothek (ab Python 3.11)
- Alle Abfragen laufen parallel, und fällt ein Bereich aus, laufen die anderen trotzdem

## Installation

**Mit pipx (empfohlen):**

```bash
pipx install git+https://github.com/Matthi1009/today-cli
```

**Ohne Installation, direkt aus dem Repo:**

```bash
git clone https://github.com/Matthi1009/today-cli
cd today-cli
./today
```

Damit `today` überall funktioniert, kannst du einen Link anlegen, z. B. `ln -s "$PWD/today" ~/.local/bin/today`.

## Einrichtung

```bash
today --init        # legt ~/.config/today/config.toml an
```

Danach die Datei anpassen. Alle Optionen stehen in [`config.example.toml`](config.example.toml):

| Bereich    | Wichtige Einstellungen |
|------------|------------------------|
| `weather`  | `latitude`, `longitude`, `place` |
| `calendar` | `sources`: Liste von Dateipfaden oder `https://`-Links |
| `github`   | nutzt automatisch `gh auth token`, sonst die Umgebungsvariable `GITHUB_TOKEN` |
| `tasks`    | `files`: Liste von Markdown-Dateien |

Jeder Bereich lässt sich mit `enabled = false` abschalten.

### Beim Öffnen des Terminals anzeigen

Füge am Ende deiner `~/.zshrc` oder `~/.bashrc` hinzu:

```bash
command -v today >/dev/null && today
```

## Benutzung

```bash
today                          # alles anzeigen
today --only weather,tasks     # nur bestimmte Bereiche
today --no-color               # ohne Farben (auch über NO_COLOR)
today --config pfad/zur.toml   # andere Config verwenden
```

### Aufgaben-Format

Erkannt werden offene Markdown-Checkboxen. Ein Fälligkeitsdatum ist optional:

```markdown
- [ ] SQL-Joins üben 📅 2026-11-27
- [ ] Referat vorbereiten due:2026-11-24
- [ ] Bewerbung schreiben @2026-12-10
- [x] Erledigte Aufgaben werden ausgeblendet
```

Überfällige Aufgaben werden rot angezeigt, Aufgaben für heute und morgen gelb.

### Kalender: was unterstützt wird

Ganztägige und mehrtägige Termine, UTC- und Zeitzonen-Angaben, Wiederholungen (`DAILY`, `WEEKLY` mit `BYDAY`, `MONTHLY`, `YEARLY`) mit `INTERVAL`, `COUNT` und `UNTIL`, Ausnahmen (`EXDATE`), verschobene Einzeltermine und abgesagte Termine. Komplexere Regeln wie „jeder zweite Dienstag im Monat“ werden nicht erkannt.

## Entwicklung

```bash
PYTHONPATH=src python -m unittest discover -s tests
# oder
pytest
```

Projektaufbau:

```
src/today_cli/
├── cli.py            Befehlszeile und Ablauf
├── config.py         Config laden und Standardwerte
├── weather.py        Open-Meteo
├── calendar_ics.py   iCalendar-Parser mit Wiederholungen
├── github.py         GitHub-API
├── tasks.py          Aufgaben aus Markdown
├── render.py         Ausgabe und Farben
└── net.py            HTTP-Helfer
```

## Lizenz

[MIT](LICENSE)
