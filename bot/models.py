import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

BERLIN_TZ = ZoneInfo("Europe/Berlin")


def compute_uid(source_id: str, url: str, start: Optional[datetime], title: str) -> str:
    start_str = start.isoformat() if start else ""
    unique = f"{source_id}|{url}|{start_str}|{title}".encode("utf-8")
    return hashlib.sha256(unique).hexdigest()


@dataclass(frozen=True)
class Event:
    source_id: str
    title: str
    url: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    location: Optional[str] = None
    uid: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "uid", compute_uid(self.source_id, self.url, self.start, self.title))

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "location": self.location,
            "uid": self.uid,
        }
