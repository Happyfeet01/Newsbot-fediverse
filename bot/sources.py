import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import feedparser
import requests
import requests_cache
from bs4 import BeautifulSoup
from dateutil import parser

from .models import BERLIN_TZ, Event

logger = logging.getLogger(__name__)

RATE_LIMIT_DELAY = 1.0


@dataclass
class SourceConfig:
    id: str
    name: str
    base_url: str
    type: str
    enabled: bool = True
    event_selector: Optional[str] = None
    title_selector: Optional[str] = None
    url_selector: Optional[str] = None
    date_selector: Optional[str] = None
    time_selector: Optional[str] = None
    datetime_selector: Optional[str] = None
    location_selector: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None


class HttpClient:
    def __init__(self, cache_name: str = "data/http_cache", expire_after: int = 3600):
        self.session = requests_cache.CachedSession(
            cache_name=cache_name,
            expire_after=expire_after,
            allowable_methods=("GET", "HEAD"),
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.last_request_per_host: Dict[str, float] = {}

    def get(self, url: str, **kwargs) -> requests.Response:
        parsed = requests.utils.urlparse(url)
        host = parsed.netloc
        last = self.last_request_per_host.get(host, 0)
        elapsed = time.time() - last
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", "EventBot/1.0 (+https://github.com/Happyfeet01/Newsbot-fediverse)")
        resp = self.session.get(url, headers=headers, timeout=10, **kwargs)
        self.last_request_per_host[host] = time.time()
        return resp


class SourceAdapter:
    def __init__(self, config: SourceConfig, client: HttpClient):
        self.config = config
        self.client = client

    def fetch_events(self, target_date: date) -> List[Event]:
        raise NotImplementedError


class RssSourceAdapter(SourceAdapter):
    def fetch_events(self, target_date: date) -> List[Event]:
        logger.info("Fetching RSS for %s", self.config.id)
        feed = feedparser.parse(self.config.base_url)
        events = []
        for entry in feed.entries:
            entry_date = self._parse_entry_date(entry)
            if entry_date is None:
                logger.debug("Skipping RSS entry without parsable date for %s", self.config.id)
                continue
            if entry_date != target_date:
                continue
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", self.config.base_url)
            events.append(
                Event(
                    source_id=self.config.id,
                    title=title,
                    url=link,
                    start=datetime.combine(target_date, datetime.min.time(), tzinfo=BERLIN_TZ),
                )
            )
        return events

    def _parse_entry_date(self, entry: Any) -> Optional[date]:
        if getattr(entry, "published", None):
            try:
                dt = parser.parse(entry.published)
                return dt.astimezone(BERLIN_TZ).date()
            except Exception:
                logger.debug("Failed to parse published date", exc_info=True)
        return None


class HtmlSourceAdapter(SourceAdapter):
    def fetch_events(self, target_date: date) -> List[Event]:
        logger.info("Fetching HTML for %s", self.config.id)
        resp = self.client.get(self.config.base_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        events = self._parse_structured_data(soup, target_date)
        if events:
            return events

        if self.config.event_selector and self.config.title_selector:
            return self._parse_with_selectors(soup, target_date)

        logger.warning("No parsing strategy for %s; returning empty list", self.config.id)
        return []

    def _parse_structured_data(self, soup: BeautifulSoup, target_date: date) -> List[Event]:
        events: List[Event] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
            except json.JSONDecodeError:
                continue
            candidates = []
            if isinstance(data, list):
                candidates = data
            elif isinstance(data, dict):
                candidates = [data]
            for item in candidates:
                item_type = item.get("@type")
                if item_type == "Event" or (isinstance(item_type, list) and "Event" in item_type):
                    ev = self._event_from_ld(item, target_date)
                    if ev:
                        events.append(ev)
                elif isinstance(item.get("@graph"), list):
                    for entry in item["@graph"]:
                        ev = self._event_from_ld(entry, target_date)
                        if ev:
                            events.append(ev)
        return events

    def _event_from_ld(self, data: Dict[str, Any], target_date: date) -> Optional[Event]:
        if data.get("@type") != "Event":
            return None
        start_raw = data.get("startDate") or data.get("start_time")
        if not start_raw:
            return None
        try:
            dt = parser.parse(start_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BERLIN_TZ)
            else:
                dt = dt.astimezone(BERLIN_TZ)
        except Exception:
            return None
        if dt.date() != target_date:
            return None
        end = None
        end_raw = data.get("endDate")
        if end_raw:
            try:
                end_dt = parser.parse(end_raw)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=BERLIN_TZ)
                else:
                    end_dt = end_dt.astimezone(BERLIN_TZ)
                end = end_dt
            except Exception:
                end = None
        title = data.get("name") or "(Ohne Titel)"
        url = data.get("url") or self.config.base_url
        location = None
        loc = data.get("location")
        if isinstance(loc, dict):
            location = loc.get("name")
        elif isinstance(loc, str):
            location = loc
        return Event(
            source_id=self.config.id,
            title=title.strip(),
            url=url,
            start=dt,
            end=end,
            location=location,
        )

    def _parse_with_selectors(self, soup: BeautifulSoup, target_date: date) -> List[Event]:
        events: List[Event] = []
        items = soup.select(self.config.event_selector)
        for item in items:
            title_el = item.select_one(self.config.title_selector) if self.config.title_selector else None
            url_el = item.select_one(self.config.url_selector) if self.config.url_selector else None
            date_el = item.select_one(self.config.date_selector) if self.config.date_selector else None
            time_el = item.select_one(self.config.time_selector) if self.config.time_selector else None
            datetime_el = item.select_one(self.config.datetime_selector) if self.config.datetime_selector else None
            location_el = item.select_one(self.config.location_selector) if self.config.location_selector else None

            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
            href = url_el.get("href") if url_el and url_el.has_attr("href") else self.config.base_url
            url = urljoin(self.config.base_url, href)
            location = location_el.get_text(strip=True) if location_el else None
            start_dt = self._parse_date_time(date_el, time_el, datetime_el, target_date)
            if start_dt and start_dt.date() != target_date:
                continue
            events.append(
                Event(
                    source_id=self.config.id,
                    title=title,
                    url=url,
                    start=start_dt,
                    location=location,
                )
            )
        return events

    def _parse_date_time(
        self,
        date_el: Optional[Any],
        time_el: Optional[Any],
        datetime_el: Optional[Any],
        fallback_date: date,
    ) -> Optional[datetime]:
        if datetime_el and datetime_el.get("datetime"):
            try:
                dt = parser.parse(datetime_el["datetime"])
                return dt if dt.tzinfo else dt.replace(tzinfo=BERLIN_TZ)
            except Exception:
                pass
        date_text = date_el.get_text(strip=True) if date_el else None
        time_text = time_el.get_text(strip=True) if time_el else None
        if not date_text and not time_text:
            return datetime.combine(fallback_date, datetime.min.time(), tzinfo=BERLIN_TZ)
        try:
            if date_text and time_text:
                merged = f"{date_text} {time_text}"
            else:
                merged = date_text or time_text
            dt = parser.parse(merged, dayfirst=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BERLIN_TZ)
            return dt
        except Exception:
            logger.debug("Failed to parse date/time for %s", self.config.id, exc_info=True)
            return datetime.combine(fallback_date, datetime.min.time(), tzinfo=BERLIN_TZ)


class SourceManager:
    def __init__(self, configs: Iterable[SourceConfig], client: Optional[HttpClient] = None):
        self.configs = [c for c in configs if c.enabled]
        self.client = client or HttpClient()

    def fetch_for_date(self, target_date: date) -> List[Event]:
        events: List[Event] = []
        for config in self.configs:
            try:
                adapter = self._create_adapter(config)
                events.extend(adapter.fetch_events(target_date))
            except Exception:
                logger.exception("Failed to fetch events for %s", config.id)
        return events

    def _create_adapter(self, config: SourceConfig) -> SourceAdapter:
        if config.type == "rss":
            return RssSourceAdapter(config, self.client)
        if config.type == "html":
            return HtmlSourceAdapter(config, self.client)
        logger.warning("Unknown type %s for %s; defaulting to html", config.type, config.id)
        return HtmlSourceAdapter(config, self.client)


def load_source_configs(path: str) -> List[SourceConfig]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    configs = []
    for entry in raw:
        configs.append(SourceConfig(**entry))
    return configs
