"""Polite HTTP client shared by all scrapers: identifies itself, rate-limits per host, caches to disk."""

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

USER_AGENT = "darts-data-app/0.1 (+https://github.com/hlinkavl/darts-data-app; non-commercial)"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


class PoliteClient:
    def __init__(self, min_interval: float = 2.0, cache_ttl: float = 24 * 3600, retries: int = 3):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl
        self.retries = retries
        self._last_request: dict[str, float] = {}

    def _cache_path(self, url: str, params: dict | None) -> Path:
        key = hashlib.sha256(f"{url}?{urlencode(sorted((params or {}).items()))}".encode()).hexdigest()
        return CACHE_DIR / urlparse(url).netloc / f"{key}.json"

    def _wait(self, host: str) -> None:
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request[host] = time.monotonic()

    def get_text(self, url: str, params: dict | None = None, use_cache: bool = True) -> str:
        path = self._cache_path(url, params)
        if use_cache and path.exists() and time.time() - path.stat().st_mtime < self.cache_ttl:
            return path.read_text()

        for attempt in range(1, self.retries + 1):
            self._wait(urlparse(url).netloc)
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                # Dropped connections happen on long runs; back off and retry like a 5xx.
                if attempt == self.retries:
                    raise
                time.sleep(10 * attempt)
                continue
            if resp.status_code == 200:
                break
            # Back off on rate limiting / transient errors, fail fast on anything else (403 = blocked).
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                resp.raise_for_status()
            time.sleep(10 * attempt)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text)
        return resp.text

    def get_json(self, url: str, params: dict | None = None, use_cache: bool = True) -> dict:
        text = self.get_text(url, params, use_cache)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            self._cache_path(url, params).unlink(missing_ok=True)  # never keep an invalid response in the cache
            raise
