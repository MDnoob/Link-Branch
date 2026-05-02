import os
import re
import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlparse

from fastapi import HTTPException, Request

TRUE_VALUES = {"1", "true", "yes", "on"}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ICON_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
UPLOAD_PATH_RE = re.compile(r"^/static/uploads/[A-Za-z0-9_.-]+$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_text(value: str | None, *, max_len: int = 100, multiline: bool = False) -> str:
    text = (value or "").strip()
    text = CONTROL_CHARS_RE.sub("", text)
    if not multiline:
        text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def normalize_email(value: str | None) -> str:
    return sanitize_text(value, max_len=320).lower()


def is_valid_email(value: str | None) -> bool:
    email = normalize_email(value)
    if not EMAIL_RE.match(email):
        return False
    domain = email.split("@", 1)[1]
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


def normalize_http_url(
    value: str | None,
    *,
    max_len: int = 500,
    allow_static_upload_path: bool = False,
) -> str | None:
    raw = sanitize_text(value, max_len=max_len)
    if not raw:
        return None
    if allow_static_upload_path and UPLOAD_PATH_RE.match(raw):
        return raw
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return raw[:max_len]


def normalize_color_hex(value: str | None, *, default: str) -> str:
    candidate = sanitize_text(value, max_len=7)
    if HEX_COLOR_RE.match(candidate):
        return candidate.lower()
    return default


def normalize_enum(value: str | None, *, allowed: set[str], default: str) -> str:
    candidate = sanitize_text(value, max_len=64).lower()
    if candidate in allowed:
        return candidate
    return default


def normalize_icon_value(value: str | None) -> str | None:
    candidate = sanitize_text(value, max_len=255)
    if not candidate:
        return None
    if UPLOAD_PATH_RE.match(candidate):
        return candidate
    slug = candidate.lower()
    if ICON_SLUG_RE.match(slug):
        return slug
    return None


def normalize_asset_label(label: str | None, *, fallback: str = "Asset") -> str:
    cleaned = sanitize_text(label, max_len=100)
    if cleaned:
        return cleaned
    fallback_clean = sanitize_text(fallback, max_len=100)
    return fallback_clean or "Asset"


def get_client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return "unknown"


class SlidingWindowRateLimiter:
    def __init__(self):
        self._store: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> float:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._store[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1.0, window_seconds - (now - bucket[0]))
                return retry_after
            bucket.append(now)
        return 0.0


_rate_limiter = SlidingWindowRateLimiter()


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    username = sanitize_text(request.session.get("username"), max_len=50)
    identity = username or get_client_ip(request)
    key = f"{bucket}:{identity}"
    retry_after = _rate_limiter.hit(key, limit=limit, window_seconds=window_seconds)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again soon.",
            headers={"Retry-After": str(int(retry_after))},
        )


def verify_admin_token(token: str | None) -> bool:
    """Timing-safe comparison of the submitted token against ADMIN_TOKEN env var.
    Returns False if ADMIN_TOKEN is not configured or the token doesn't match.
    """
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected or not token:
        return False
    return secrets.compare_digest(expected, token.strip())
