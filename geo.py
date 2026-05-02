import os

import httpx

IPSTACK_KEY = os.getenv("IPSTACK_KEY", "")
_IPSTACK_URL = "http://api.ipstack.com/{ip}?access_key={key}&fields=country_name,city&output=json"

_PRIVATE_PREFIXES = (
    "10.", "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
)


async def lookup(ip: str | None) -> tuple[str | None, str | None]:
    """Return (country, city) for a given IP via IPstack.
    Returns (None, None) if IPSTACK_KEY is unset, the IP is private/loopback,
    or the request fails for any reason.
    """
    if not ip or not IPSTACK_KEY:
        return None, None
    if ip in ("127.0.0.1", "::1") or ip.startswith(_PRIVATE_PREFIXES):
        return None, None
    try:
        url = _IPSTACK_URL.format(ip=ip, key=IPSTACK_KEY)
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            # IPstack returns {"success": false, "error": {...}} on bad key/IP
            if not data.get("error"):
                country = (data.get("country_name") or "").strip()[:100] or None
                city = (data.get("city") or "").strip()[:100] or None
                return country, city
    except Exception:
        pass
    return None, None
