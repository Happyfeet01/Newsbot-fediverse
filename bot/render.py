from datetime import date
from typing import Iterable, List

from .models import BERLIN_TZ, Event

HEADER_TEMPLATE = "Termine heute ({day}) in Fulda & Umgebung:"
POST_LIMIT = 500


def format_event_line(event: Event) -> str:
    time_part = ""
    if event.start:
        time_part = event.start.astimezone(BERLIN_TZ).strftime("%H:%M")
    parts = []
    if time_part:
        parts.append(time_part)
    parts.append(event.title)
    detail = " — ".join(part for part in [" ".join(parts).strip(), event.location] if part)
    return f"• {detail} ({event.url})"


def render_posts(events: Iterable[Event], target_date: date) -> List[str]:
    events_sorted = sorted(
        events,
        key=lambda e: (
            e.start.astimezone(BERLIN_TZ) if e.start else None,
            e.title.lower(),
        ),
    )
    lines = [HEADER_TEMPLATE.format(day=target_date.isoformat())]
    lines.extend(format_event_line(ev) for ev in events_sorted)

    posts: List[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip()
        if len(candidate) > POST_LIMIT and current:
            posts.append(current)
            current = line
        else:
            current = candidate
    if current:
        posts.append(current)
    return posts
