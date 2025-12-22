import argparse
import logging
from datetime import date, datetime
from typing import List

from .models import BERLIN_TZ, Event
from .poster import MastodonPoster
from .render import render_posts
from .sources import HttpClient, SourceManager, load_source_configs
from .storage import EventHistory

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Event bot for Mastodon/Sharkey")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD date for events (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Only print posts, do not publish")
    parser.add_argument("--config", type=str, default="config/sources.yaml", help="Path to sources config")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of events to post")
    parser.add_argument("--history", type=str, default="data/posted_events.db", help="Path to SQLite history")
    parser.add_argument("--cache", type=str, default="data/http_cache", help="HTTP cache path")
    parser.add_argument("--no-post", action="store_true", help="Disable posting even without dry-run")
    return parser.parse_args()


def determine_date(date_arg: str | None) -> date:
    if date_arg:
        return datetime.fromisoformat(date_arg).date()
    return datetime.now(tz=BERLIN_TZ).date()


def dedupe_events(events: List[Event]) -> List[Event]:
    seen = set()
    unique: List[Event] = []
    for event in events:
        if event.uid in seen:
            continue
        seen.add(event.uid)
        unique.append(event)
    return unique


def main():
    args = parse_args()
    target_date = determine_date(args.date)
    logger.info("Gathering events for %s", target_date.isoformat())

    configs = load_source_configs(args.config)
    client = HttpClient(cache_name=args.cache)
    manager = SourceManager(configs, client=client)
    history = EventHistory(db_path=args.history)

    events = manager.fetch_for_date(target_date)
    events = dedupe_events(events)
    logger.info("Fetched %s events before history filter", len(events))

    new_events = [ev for ev in events if not history.is_posted(ev.uid)]
    if args.limit is not None and args.limit > 0:
        new_events = new_events[: args.limit]
    logger.info("%s new events to share", len(new_events))

    if not new_events:
        logger.info("No new events for %s", target_date.isoformat())
        return

    posts = render_posts(new_events, target_date)
    if args.dry_run or args.no_post:
        logger.info("DRY RUN - would post %s messages", len(posts))
        for idx, post in enumerate(posts, start=1):
            print(f"--- Post {idx} ---\n{post}\n")
        return

    access_token = environ_required("MASTODON_ACCESS_TOKEN")
    base_url = environ_required("MASTODON_INSTANCE_URL")
    poster = MastodonPoster(access_token=access_token, base_url=base_url)
    poster.post_thread(posts)
    history.mark_posted(new_events)
    logger.info("Posted %s events", len(new_events))


def environ_required(name: str) -> str:
    import os

    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Environment variable {name} is required")
    return value


if __name__ == "__main__":
    main()
