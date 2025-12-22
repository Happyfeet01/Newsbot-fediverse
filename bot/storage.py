import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .models import Event

logger = logging.getLogger(__name__)


@dataclass
class EventRecord:
    uid: str
    source_id: str
    url: str
    start: str
    posted_at: str


class EventHistory:
    def __init__(self, db_path: str = "data/posted_events.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posted_events (
                    uid TEXT PRIMARY KEY,
                    source_id TEXT,
                    url TEXT,
                    start TEXT,
                    posted_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def is_posted(self, uid: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("SELECT 1 FROM posted_events WHERE uid=?", (uid,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def mark_posted(self, events: Iterable[Event]):
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO posted_events(uid, source_id, url, start, posted_at) VALUES(?,?,?,?,?)",
                [
                    (
                        event.uid,
                        event.source_id,
                        event.url,
                        event.start.isoformat() if event.start else "",
                        now,
                    )
                    for event in events
                ],
            )
            conn.commit()
        finally:
            conn.close()
