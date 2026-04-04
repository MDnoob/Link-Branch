import httpx

_IPAPI_URL = "http://ip-api.com/json/{ip}?fields=status,country,city"

_PRIVATE_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                     "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")


async def lookup(ip: str | None) -> tuple[str | None, str | None]:
    """Return (country, city) using ip-api.com — free, no key required."""
    if not ip:
        return None, None
    if ip in ("127.0.0.1", "::1") or ip.startswith(_PRIVATE_PREFIXES):
        return None, None
    try:
        url = _IPAPI_URL.format(ip=ip)
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                country = (data.get("country") or "").strip()[:100] or None
                city = (data.get("city") or "").strip()[:100] or None
                return country, city
    except Exception:
        pass
    return None, None
