"""Thin ESI client: compatibility-date header, ETag caching, rate-limit awareness."""

import hashlib
import json
import logging
import time
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

ETAG_TTL = 7 * 24 * 3600
BREAKER_KEY = "esi:breaker"
BREAKER_SECONDS = 300


class EsiError(Exception):
    pass


class EsiRateLimited(EsiError):
    def __init__(self, retry_after: int):
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class EsiUnavailable(EsiError):
    pass


def _cache_key(method: str, path: str, params: dict | None, body: Any) -> str:
    raw = json.dumps([method, path, params or {}, body], sort_keys=True, default=str)
    return "esi:etag:" + hashlib.sha1(raw.encode()).hexdigest()


class EsiClient:
    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=base_url or settings.ESI_BASE_URL,
            headers={
                "User-Agent": settings.ESI_USER_AGENT,
                "Accept": "application/json",
                "X-Compatibility-Date": settings.ESI_COMPAT_DATE,
            },
            timeout=20,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        use_etag: bool = True,
    ) -> Any:
        if cache.get(BREAKER_KEY):
            raise EsiUnavailable("ESI circuit breaker open")
        key = _cache_key(method, path, params, json_body)
        cached = cache.get(key) if use_etag else None
        headers = {}
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]

        for attempt in range(2):
            resp = self._client.request(
                method, path, params=params, json=json_body, headers=headers
            )
            self._log_ratelimit(resp)
            if resp.status_code == 304 and cached:
                return cached["body"]
            if resp.status_code in (420, 429):
                retry_after = int(resp.headers.get("Retry-After", "5") or 5)
                if attempt == 0 and retry_after <= 10:
                    time.sleep(retry_after)
                    continue
                raise EsiRateLimited(retry_after)
            if resp.status_code >= 500:
                failures = cache.get("esi:5xx", 0) + 1
                cache.set("esi:5xx", failures, 120)
                if failures >= 3:
                    cache.set(BREAKER_KEY, True, BREAKER_SECONDS)
                    log.error("ESI breaker opened after %d consecutive 5xx", failures)
                raise EsiUnavailable(f"ESI {resp.status_code} on {path}")
            if resp.status_code >= 400:
                raise EsiError(f"ESI {resp.status_code} on {path}: {resp.text[:200]}")
            cache.delete("esi:5xx")
            body = resp.json()
            etag = resp.headers.get("ETag")
            if use_etag and etag:
                cache.set(key, {"etag": etag, "body": body}, ETAG_TTL)
            return body
        raise EsiUnavailable("unreachable")

    @staticmethod
    def _log_ratelimit(resp: httpx.Response) -> None:
        remaining = resp.headers.get("X-Ratelimit-Remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) < 20:
            log.warning(
                "ESI rate budget low: group=%s remaining=%s limit=%s",
                resp.headers.get("X-Ratelimit-Group"),
                remaining,
                resp.headers.get("X-Ratelimit-Limit"),
            )

    def character_public(self, character_id: int) -> dict:
        return self.request("GET", f"/characters/{character_id}/")

    def affiliations(self, character_ids: list[int]) -> list[dict]:
        out: list[dict] = []
        ids = sorted(set(character_ids))
        for i in range(0, len(ids), 1000):
            out.extend(
                self.request("POST", "/characters/affiliation/", json_body=ids[i : i + 1000])
            )
        return out


_default: EsiClient | None = None


def get_client() -> EsiClient:
    global _default
    if _default is None:
        _default = EsiClient()
    return _default
