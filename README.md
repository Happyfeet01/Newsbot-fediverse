# EventBot für Mastodon/Sharkey

Aggregiert lokale Veranstaltungskalender rund um Fulda und postet die Termine des Tages automatisch ins Fediverse.

## Features
- Pluggable Source-Adapter (RSS & HTML mit JSON-LD/Selektor-Support).
- Dedupe pro Lauf und persistente Historie via SQLite (kein Doppel-Posting).
- Rendering mit Thread-Splitting für 500-Zeichen-Limit.
- Robust gegen Fehlersituationen: HTTP-Caching, Retry, Rate-Limit-Verzögerung, Timeouts.
- Konfigurierbare Quellen ohne Codeänderung über `config/sources.yaml`.

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Konfiguration
Alle Quellen liegen in `config/sources.yaml` und können ohne Python-Änderungen erweitert werden.
Minimalstruktur pro Quelle:
```yaml
- id: spuere-fulda
  name: "spuere-fulda.de"
  base_url: "https://spuere-fulda.de/events/"
  type: html # oder rss
  event_selector: ".event"        # optional: CSS-Selektor für Event-Container
  title_selector: ".title"        # optional
  url_selector: "a"               # optional (href wird relativ zur base_url aufgelöst)
  date_selector: ".date"         # optional
  time_selector: ".time"         # optional
  datetime_selector: "time"      # optional (liest datetime-Attribut)
  location_selector: ".location" # optional
```
Initiale Konfiguration enthält die Fulda/Umfeld-Kalender aus der Aufgabenstellung.

## Nutzung (CLI)
```bash
python -m bot.main --config config/sources.yaml --dry-run
```
Argumente:
- `--date YYYY-MM-DD` Datum, Standard: heute (Europe/Berlin)
- `--dry-run` Nur Ausgabe auf Konsole, kein Posten
- `--limit N` Maximal N Events posten
- `--history` Pfad zur SQLite-Historie (Standard: `data/posted_events.db`)
- `--cache` Pfad zum HTTP-Cache (Standard: `data/http_cache`)
- `--no-post` Deaktiviert Posten ohne `--dry-run`

## Posting
Setze vor dem produktiven Betrieb folgende Umgebungsvariablen (z.B. in `.env`):
- `MASTODON_ACCESS_TOKEN`
- `MASTODON_INSTANCE_URL`

Die Bot-Ausgabe wird in Threads gesplittet, wenn >500 Zeichen. Es wird immer nur gepostet, was noch nicht in der Historie liegt.

## Automatisierung (cron)
Beispiel: täglich um 09:00 Uhr lokale Zeit posten:
```
0 9 * * * /path/to/venv/bin/python /path/to/repo/bot/main.py --config /path/to/repo/config/sources.yaml >> /var/log/eventbot.log 2>&1
```
Stelle sicher, dass das System auf `Europe/Berlin` gestellt ist (oder `TZ=Europe/Berlin` setzen).

## Hinweise zu neuen Quellen
- JSON-LD (schema.org/Event) wird automatisch erkannt.
- Bei statischem HTML können CSS-Selektoren in der YAML hinterlegt werden.
- RSS-Feeds einfach mit `type: rss` eintragen.
