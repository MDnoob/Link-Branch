import os
import httpx

IPSTACK_KEY = os.getenv("IPSTACK_KEY", "")
_IPSTACK_URL = "http://api.ipstack.com/{ip}?access_key={key}&fields=country_name,city&output=json"

# Private / loopback prefixes — skip geo lookup for these
_PRIVATE_PREFIXES = ("10.", "192.168.", "127.", "::1", "fc", "fd")


async def lookup(ip: str | None) -> tuple[str | None, str | None]:
    """Return (country, city) for a visitor IP via IPstack.
    Returns (None, None) on any failure so callers can fall back gracefully.
    """
    if not ip or not IPSTACK_KEY:
        return None, None
    if any(ip.startswith(p) for p in _PRIVATE_PREFIXES):
        return None, None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            url = _IPSTACK_URL.format(ip=ip, key=IPSTACK_KEY)
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                # IPstack signals errors via {"success": false, "error": {...}}
                if not data.get("error") and data.get("success") is not False:
                    country = (data.get("country_name") or "").strip()[:100] or None
                    city = (data.get("city") or "").strip()[:100] or None
                    return country, city
    except Exception:
        pass
    return None, None
