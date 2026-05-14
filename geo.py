import asyncio
import os
import time
from collections import OrderedDict

import httpx

_IPAPI_URL = "http://ip-api.com/json/{ip}?fields=status,country,city"

_PRIVATE_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
)

_CACHE: OrderedDict[str, tuple[float, tuple[str | None, str | None]]] = OrderedDict()


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int((os.getenv(name) or "").strip())
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


_LOOKUP_CONCURRENCY = _env_int("GEO_LOOKUP_CONCURRENCY", 4, minimum=1, maximum=32)
_LOOKUP_QUEUE_TIMEOUT_SECONDS = _env_int("GEO_LOOKUP_QUEUE_TIMEOUT_SECONDS", 2, minimum=0, maximum=30)
_LOOKUP_TIMEOUT_SECONDS = _env_int("GEO_LOOKUP_TIMEOUT_SECONDS", 3, minimum=1, maximum=30)
_CACHE_TTL_SECONDS = _env_int("GEO_CACHE_TTL_SECONDS", 86400, minimum=60, maximum=604800)
_CACHE_MAX_ITEMS = _env_int("GEO_CACHE_MAX_ITEMS", 4096, minimum=128, maximum=50000)
_LOOKUP_QUEUE = asyncio.Semaphore(_LOOKUP_CONCURRENCY)


def _cache_get(ip: str) -> tuple[str | None, str | None] | None:
    cached = _CACHE.get(ip)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at <= time.monotonic():
        _CACHE.pop(ip, None)
        return None
    _CACHE.move_to_end(ip)
    return value


def _cache_set(ip: str, value: tuple[str | None, str | None]) -> None:
    _CACHE[ip] = (time.monotonic() + _CACHE_TTL_SECONDS, value)
    _CACHE.move_to_end(ip)
    while len(_CACHE) > _CACHE_MAX_ITEMS:
        _CACHE.popitem(last=False)


async def lookup(ip: str | None) -> tuple[str | None, str | None]:
    """Return (country, city) using ip-api.com with bounded outbound pressure."""
    if not ip:
        return None, None
    if ip in ("127.0.0.1", "::1") or ip.startswith(_PRIVATE_PREFIXES):
        return None, None

    cached = _cache_get(ip)
    if cached is not None:
        return cached

    acquired = False
    try:
        await asyncio.wait_for(_LOOKUP_QUEUE.acquire(), timeout=_LOOKUP_QUEUE_TIMEOUT_SECONDS)
        acquired = True
        url = _IPAPI_URL.format(ip=ip)
        async with httpx.AsyncClient(timeout=_LOOKUP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                result = (
                    (data.get("country") or "").strip()[:100] or None,
                    (data.get("city") or "").strip()[:100] or None,
                )
                _cache_set(ip, result)
                return result
    except Exception:
        pass
    finally:
        if acquired:
            _LOOKUP_QUEUE.release()

    result = (None, None)
    _cache_set(ip, result)
    return result
