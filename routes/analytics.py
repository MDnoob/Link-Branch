from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import get_db
from models import Link, LinkClick, ProfileView, ShareEvent, User
from routes.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return None


def _device_type(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if any(k in ua for k in ["bot", "spider", "crawl", "slurp"]):
        return "bot"
    if any(k in ua for k in ["ipad", "tablet"]):
        return "tablet"
    if any(k in ua for k in ["mobile", "android", "iphone"]):
        return "mobile"
    return "desktop"


def _referrer_domain(referer: str | None) -> str | None:
    value = (referer or "").strip()
    if not value:
        return None
    try:
        host = (urlparse(value).netloc or "").lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _geo_context(request: Request) -> tuple[str | None, str | None]:
    country = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("x-country-code")
        or ""
    ).strip()[:100]
    city = (
        request.headers.get("x-vercel-ip-city")
        or request.headers.get("x-city")
        or ""
    ).strip()[:100]
    return (country or None, city or None)


def _resolve_owner_id(db: Session, request: Request, payload: dict) -> int | None:
    owner_id = _safe_int(payload.get("owner_id"))
    if owner_id and db.query(User.id).filter(User.id == owner_id).first():
        return owner_id

    link_id = _safe_int(payload.get("linkid")) or _safe_int(payload.get("link_id"))
    if link_id:
        row = db.query(Link.user_id).filter(Link.id == link_id).first()
        if row:
            return row[0]

    path = str(payload.get("path") or "")
    if path.startswith("/profile/"):
        username = path.split("/profile/", 1)[1].split("/", 1)[0].strip().lower()
        if username:
            row = db.query(User.id).filter(User.username == username).first()
            if row:
                return row[0]

    session_username = request.session.get("username")
    if session_username:
        row = db.query(User.id).filter(User.username == session_username).first()
        if row:
            return row[0]

    return None


@router.post("/api/share")
async def api_share(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    owner_id = _resolve_owner_id(db, request, payload)
    if not owner_id:
        return JSONResponse({"ok": False, "reason": "owner_not_resolved"}, status_code=200)

    event = ShareEvent(
        user_id=owner_id,
        link_id=_safe_int(payload.get("linkid")) or _safe_int(payload.get("link_id")),
        platform=(str(payload.get("platform") or "unknown").strip().lower()[:50] or "unknown"),
        path=(str(payload.get("path") or "")[:500] or None),
    )
    db.add(event)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"ok": False}, status_code=500)
    return JSONResponse({"ok": True})


@router.post("/api/click")
async def api_click(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    owner_id = _resolve_owner_id(db, request, payload)
    if not owner_id:
        return JSONResponse({"ok": False, "reason": "owner_not_resolved"}, status_code=200)

    referer = (request.headers.get("referer") or "")[:500] or None
    user_agent = (request.headers.get("user-agent") or "")[:255] or None
    country, city = _geo_context(request)
    payload_country = (str(payload.get("country") or "")[:100] or None)
    payload_city = (str(payload.get("city") or "")[:100] or None)
    payload_ip = (str(payload.get("viewer_ip") or payload.get("ip") or "")[:64] or None)
    event = LinkClick(
        user_id=owner_id,
        link_id=_safe_int(payload.get("linkid")) or _safe_int(payload.get("link_id")),
        destination_url=(str(payload.get("destination_url") or "")[:500] or None),
        ref=(str(payload.get("ref") or "")[:100] or None),
        viewer_ip=payload_ip or _client_ip(request),
        user_agent=user_agent,
        referer=referer,
        referrer_domain=_referrer_domain(referer),
        device_type=_device_type(user_agent),
        country=payload_country or country,
        city=payload_city or city,
    )
    db.add(event)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"ok": False}, status_code=500)
    return JSONResponse({"ok": True})


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, days: int = 30, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    query_days = request.query_params.get("days")
    if query_days is not None:
        days = max(7, min(365, _safe_int(query_days, 30)))
        request.session["analytics_days"] = days
    else:
        days = max(7, min(365, _safe_int(request.session.get("analytics_days"), days)))

    since = datetime.utcnow() - timedelta(days=days)

    total_views = (
        db.query(func.count(ProfileView.id))
        .filter(ProfileView.user_id == user.id, ProfileView.created_at >= since)
        .scalar()
        or 0
    )
    unique_visitors = (
        db.query(func.count(func.distinct(ProfileView.viewer_ip)))
        .filter(
            ProfileView.user_id == user.id,
            ProfileView.created_at >= since,
            ProfileView.viewer_ip.isnot(None),
            ProfileView.viewer_ip != "",
        )
        .scalar()
        or 0
    )
    total_clicks = (
        db.query(func.count(LinkClick.id))
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since)
        .scalar()
        or 0
    )
    total_shares = (
        db.query(func.count(ShareEvent.id))
        .filter(ShareEvent.user_id == user.id, ShareEvent.created_at >= since)
        .scalar()
        or 0
    )

    top_links = (
        db.query(
            LinkClick.link_id,
            Link.title,
            func.count(LinkClick.id).label("clicks"),
        )
        .outerjoin(Link, Link.id == LinkClick.link_id)
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since)
        .group_by(LinkClick.link_id, Link.title)
        .order_by(desc("clicks"))
        .limit(8)
        .all()
    )

    share_platforms = (
        db.query(
            ShareEvent.platform,
            func.count(ShareEvent.id).label("count"),
        )
        .filter(ShareEvent.user_id == user.id, ShareEvent.created_at >= since)
        .group_by(ShareEvent.platform)
        .order_by(desc("count"))
        .limit(8)
        .all()
    )

    views_rows = (
        db.query(
            func.date(ProfileView.created_at).label("d"),
            func.count(ProfileView.id).label("c"),
        )
        .filter(ProfileView.user_id == user.id, ProfileView.created_at >= since)
        .group_by(func.date(ProfileView.created_at))
        .all()
    )

    clicks_rows = (
        db.query(
            func.date(LinkClick.created_at).label("d"),
            func.count(LinkClick.id).label("c"),
        )
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since)
        .group_by(func.date(LinkClick.created_at))
        .all()
    )

    shares_rows = (
        db.query(
            func.date(ShareEvent.created_at).label("d"),
            func.count(ShareEvent.id).label("c"),
        )
        .filter(ShareEvent.user_id == user.id, ShareEvent.created_at >= since)
        .group_by(func.date(ShareEvent.created_at))
        .all()
    )

    views_by_day = {r.d: int(r.c) for r in views_rows}
    clicks_by_day = {r.d: int(r.c) for r in clicks_rows}
    shares_by_day = {r.d: int(r.c) for r in shares_rows}
    trend_days = []
    trend_labels = []
    trend_views = []
    trend_clicks = []
    trend_shares = []
    for i in range(days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_views = views_by_day.get(day, 0)
        day_clicks = clicks_by_day.get(day, 0)
        day_shares = shares_by_day.get(day, 0)
        trend_days.append({"day": day, "views": day_views, "clicks": day_clicks, "shares": day_shares})
        trend_labels.append(day)
        trend_views.append(day_views)
        trend_clicks.append(day_clicks)
        trend_shares.append(day_shares)

    view_ref_rows = (
        db.query(
            ProfileView.referrer_domain,
            func.count(ProfileView.id).label("count"),
        )
        .filter(
            ProfileView.user_id == user.id,
            ProfileView.created_at >= since,
            ProfileView.referrer_domain.isnot(None),
            ProfileView.referrer_domain != "",
        )
        .group_by(ProfileView.referrer_domain)
        .all()
    )
    click_ref_rows = (
        db.query(
            LinkClick.referrer_domain,
            func.count(LinkClick.id).label("count"),
        )
        .filter(
            LinkClick.user_id == user.id,
            LinkClick.created_at >= since,
            LinkClick.referrer_domain.isnot(None),
            LinkClick.referrer_domain != "",
        )
        .group_by(LinkClick.referrer_domain)
        .all()
    )
    ref_counts: dict[str, int] = {}
    for domain, count in list(view_ref_rows) + list(click_ref_rows):
        if not domain:
            continue
        ref_counts[domain] = ref_counts.get(domain, 0) + int(count or 0)
    top_referrers = sorted(ref_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    view_device_rows = (
        db.query(
            ProfileView.device_type,
            func.count(ProfileView.id).label("count"),
        )
        .filter(ProfileView.user_id == user.id, ProfileView.created_at >= since)
        .group_by(ProfileView.device_type)
        .all()
    )
    click_device_rows = (
        db.query(
            LinkClick.device_type,
            func.count(LinkClick.id).label("count"),
        )
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since)
        .group_by(LinkClick.device_type)
        .all()
    )
    device_counts: dict[str, int] = {}
    for device, count in list(view_device_rows) + list(click_device_rows):
        key = (device or "unknown").lower()
        device_counts[key] = device_counts.get(key, 0) + int(count or 0)
    device_split = sorted(device_counts.items(), key=lambda x: x[1], reverse=True)

    view_country_rows = (
        db.query(ProfileView.country, func.count(ProfileView.id).label("count"))
        .filter(
            ProfileView.user_id == user.id,
            ProfileView.created_at >= since,
            ProfileView.country.isnot(None),
            ProfileView.country != "",
        )
        .group_by(ProfileView.country)
        .all()
    )
    click_country_rows = (
        db.query(LinkClick.country, func.count(LinkClick.id).label("count"))
        .filter(
            LinkClick.user_id == user.id,
            LinkClick.created_at >= since,
            LinkClick.country.isnot(None),
            LinkClick.country != "",
        )
        .group_by(LinkClick.country)
        .all()
    )
    country_counts: dict[str, int] = {}
    for country_name, count in list(view_country_rows) + list(click_country_rows):
        if not country_name:
            continue
        country_counts[country_name] = country_counts.get(country_name, 0) + int(count or 0)
    country_rows = [
        {"country": name, "count": count}
        for name, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    ]

    view_city_rows = (
        db.query(ProfileView.city, func.count(ProfileView.id).label("count"))
        .filter(
            ProfileView.user_id == user.id,
            ProfileView.created_at >= since,
            ProfileView.city.isnot(None),
            ProfileView.city != "",
        )
        .group_by(ProfileView.city)
        .all()
    )
    click_city_rows = (
        db.query(LinkClick.city, func.count(LinkClick.id).label("count"))
        .filter(
            LinkClick.user_id == user.id,
            LinkClick.created_at >= since,
            LinkClick.city.isnot(None),
            LinkClick.city != "",
        )
        .group_by(LinkClick.city)
        .all()
    )
    city_counts: dict[str, int] = {}
    for city_name, count in list(view_city_rows) + list(click_city_rows):
        if not city_name:
            continue
        city_counts[city_name] = city_counts.get(city_name, 0) + int(count or 0)
    city_rows = [
        {"city": name, "count": count}
        for name, count in sorted(city_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    ]

    recent_clicks = (
        db.query(LinkClick, Link.title)
        .outerjoin(Link, Link.id == LinkClick.link_id)
        .filter(LinkClick.user_id == user.id)
        .order_by(LinkClick.created_at.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": user,
            "active_page": "analytics",
            "days": days,
            "summary": {
                "views": int(total_views),
                "unique_visitors": int(unique_visitors),
                "clicks": int(total_clicks),
                "shares": int(total_shares),
                "ctr": round((total_clicks / total_views) * 100, 1) if total_views else 0.0,
            },
            "top_links": top_links,
            "share_platforms": share_platforms,
            "top_referrers": top_referrers,
            "device_split": device_split,
            "countries": country_rows,
            "cities": city_rows,
            "trend_days": trend_days,
            "trend_labels": trend_labels,
            "trend_views": trend_views,
            "trend_clicks": trend_clicks,
            "trend_shares": trend_shares,
            "recent_clicks": recent_clicks,
        },
    )
