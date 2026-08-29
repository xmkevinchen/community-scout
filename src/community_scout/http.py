from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .files import atomic_write_json, atomic_write_text
from .models import utc_now


class FetchError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def get_text(self, url: str, *, github_api: bool = False) -> str:
        headers = {
            "Accept": "application/vnd.github+json" if github_api else "text/plain, text/markdown, */*",
            "User-Agent": "community-scout/0.1 (+https://github.com/)",
        }
        token = os.environ.get("GITHUB_TOKEN") if github_api else None
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"

        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} while fetching {url}") from exc
        except URLError as exc:
            raise FetchError(f"Network error while fetching {url}: {exc.reason}") from exc
        except UnicodeDecodeError as exc:
            raise FetchError(f"Response from {url} was not UTF-8 text") from exc

    def get_json(self, url: str, *, github_api: bool = False) -> Any:
        raw = self.get_text(url, github_api=github_api)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FetchError(f"Response from {url} was not valid JSON") from exc


class FileCachingHttpClient:
    """Persist successful HTTP responses so a failed source can resume without refetching them."""

    def __init__(self, cache_dir: Path, upstream: HttpClient) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.upstream = upstream
        self.index_path = cache_dir / "index.json"
        self.cache_hits = 0
        self.network_fetches = 0
        self._entries = self._load_entries()

    def _load_entries(self) -> dict[str, dict[str, str]]:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        return entries if isinstance(entries, dict) else {}

    @staticmethod
    def _cache_key(url: str, github_api: bool) -> str:
        value = f"github_api={github_api}\n{url}"
        return sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _extension(url: str, github_api: bool) -> str:
        if github_api:
            return ".json"
        suffix = Path(urlparse(url).path).suffix.lower()
        return suffix if suffix in {".json", ".md", ".txt"} else ".txt"

    def get_text(self, url: str, *, github_api: bool = False) -> str:
        key = self._cache_key(url, github_api)
        cached = self._entries.get(key)
        if cached:
            cached_path = self.cache_dir / cached["file"]
            if cached_path.is_file():
                self.cache_hits += 1
                return cached_path.read_text(encoding="utf-8")

        raw = self.upstream.get_text(url, github_api=github_api)
        filename = f"{key[:16]}{self._extension(url, github_api)}"
        atomic_write_text(self.cache_dir / filename, raw)
        self._entries[key] = {
            "url": url,
            "file": filename,
            "fetched_at": utc_now(),
            "content_trust": "untrusted",
        }
        atomic_write_json(
            self.index_path,
            {
                "schema_version": 1,
                "content_trust": "untrusted",
                "entries": self._entries,
            },
        )
        self.network_fetches += 1
        return raw

    def get_json(self, url: str, *, github_api: bool = False) -> Any:
        raw = self.get_text(url, github_api=github_api)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FetchError(f"Response from {url} was not valid JSON") from exc

    def raw_files(self) -> list[str]:
        return sorted(
            str((self.cache_dir / entry["file"]).resolve())
            for entry in self._entries.values()
            if (self.cache_dir / entry["file"]).is_file()
        )
