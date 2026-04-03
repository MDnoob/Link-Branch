from datetime import datetime, timedelta
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, case, desc, func, or_
from sqlalchemy.orm import Session

from database import get_db
from models import Link, LinkClick, ProfileView, ShareEvent, User
from routes.auth import get_current_user
from security import enforce_rate_limit, get_client_ip, sanitize_text

router = APIRouter()
templates = Jinja2Templates(directory="templates")
REDIRECT_SOURCES = ("public_redirect", "extra_redirect")
logger = logging.getLogger("uvicorn.error")


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _client_ip(request: Request) -> str | None:
    ip = get_client_ip(request)
    return ip if ip != "unknown" else None


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


def _normalize_share_platform(value: str | None) -> str:
    platform = (value or "unknown").strip().lower()[:50]
    if platform == "link_copy":
        return "copy"
    return platform or "unknown"


def _normalize_click_source(payload: dict) -> str:
    source = (
        str(
            payload.get("source")
            or payload.get("click_source")
            or payload.get("ref")
            or "profile_button"
        )
        .strip()
        .lower()
    )
    if source in {"redirect", "dashboard_share"}:
        return "public_redirect"
    if source in {"share", "profile_button", "public_redirect", "extra_redirect"}:
        return source
    return source[:40] or "profile_button"


def _resolve_owner_id(db: Session, request: Request, payload: dict) -> int | None:
    # Never trust owner_id from client payload.
    session_username = request.session.get("username")
    if session_username:
        row = db.query(User.id).filter(User.username == session_username).first()
        if row:
            return row[0]

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

    return None


@router.post("/api/share")
async def api_share(request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, bucket="api_share", limit=120, window_seconds=60)
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
        platform=_normalize_share_platform(payload.get("platform")),
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
    enforce_rate_limit(request, bucket="api_click", limit=240, window_seconds=60)
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
        click_source=_normalize_click_source(payload),
    )
    db.add(event)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"ok": False}, status_code=500)
    return JSONResponse({"ok": True})


@router.post("/api/frontend-error")
async def api_frontend_error(request: Request):
    enforce_rate_limit(request, bucket="api_frontend_error", limit=30, window_seconds=60)
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    message = sanitize_text(payload.get("message"), max_len=500, multiline=True) or "Unknown error"
    kind = sanitize_text(payload.get("type"), max_len=50) or "error"
    page = sanitize_text(payload.get("url"), max_len=255) or "-"
    source = sanitize_text(payload.get("source"), max_len=255) or "-"
    stack = sanitize_text(payload.get("stack"), max_len=2000, multiline=True)
    line = _safe_int(payload.get("line"), "")
    col = _safe_int(payload.get("col"), "")
    ip = _client_ip(request) or "unknown"

    logger.warning(
        "frontend_error type=%s page=%s source=%s line=%s col=%s ip=%s message=%s stack=%s",
        kind,
        page,
        source,
        line,
        col,
        ip,
        message,
        stack or "-",
    )
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

    tab = (request.query_params.get("tab") or request.session.get("analytics_tab") or "overview").strip().lower()
    if tab not in {"overview", "redirects"}:
        tab = "overview"
    request.session["analytics_tab"] = tab

    since = datetime.utcnow() - timedelta(days=days)
    normalized_ref = func.lower(func.coalesce(LinkClick.ref, ""))
    overview_filter = or_(
        LinkClick.click_source == "profile_button",
        and_(LinkClick.click_source.is_(None), normalized_ref == "profile_button"),
    )
    redirect_filter = or_(
        LinkClick.click_source.in_(REDIRECT_SOURCES),
        and_(LinkClick.click_source.is_(None), normalized_ref != "profile_button"),
    )
    active_click_filter = redirect_filter if tab == "redirects" else overview_filter

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

    profile_clicks = (
        db.query(func.count(LinkClick.id))
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, overview_filter)
        .scalar()
        or 0
    )
    redirect_clicks = (
        db.query(func.count(LinkClick.id))
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, redirect_filter)
        .scalar()
        or 0
    )
    active_clicks = int(redirect_clicks if tab == "redirects" else profile_clicks)
    total_clicks = int(profile_clicks) + int(redirect_clicks)

    redirect_unique_visitors = (
        db.query(func.count(func.distinct(LinkClick.viewer_ip)))
        .filter(
            LinkClick.user_id == user.id,
            LinkClick.created_at >= since,
            redirect_filter,
            LinkClick.viewer_ip.isnot(None),
            LinkClick.viewer_ip != "",
        )
        .scalar()
        or 0
    )
    active_unique_clicks = (
        db.query(func.count(func.distinct(LinkClick.viewer_ip)))
        .filter(
            LinkClick.user_id == user.id,
            LinkClick.created_at >= since,
            active_click_filter,
            LinkClick.viewer_ip.isnot(None),
            LinkClick.viewer_ip != "",
        )
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
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, overview_filter)
        .group_by(LinkClick.link_id, Link.title)
        .order_by(desc("clicks"))
        .limit(8)
        .all()
    )
    redirect_top_links = (
        db.query(
            LinkClick.link_id,
            Link.title,
            LinkClick.destination_url,
            func.count(LinkClick.id).label("clicks"),
        )
        .outerjoin(Link, Link.id == LinkClick.link_id)
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, redirect_filter)
        .group_by(LinkClick.link_id, Link.title, LinkClick.destination_url)
        .order_by(desc("clicks"))
        .limit(12)
        .all()
    )

    platform_base = func.lower(func.coalesce(ShareEvent.platform, "unknown"))
    platform_expr = case((platform_base == "link_copy", "copy"), else_=platform_base)
    share_platforms = (
        db.query(
            platform_expr.label("platform"),
            func.count(ShareEvent.id).label("count"),
        )
        .filter(ShareEvent.user_id == user.id, ShareEvent.created_at >= since)
        .group_by(platform_expr)
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
        .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, active_click_filter)
        .group_by(func.date(LinkClick.created_at))
        .all()
    )
    shares_rows = []
    if tab == "overview":
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
    trend_labels = []
    trend_views = []
    trend_clicks = []
    trend_shares = []
    for i in range(days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend_labels.append(day)
        trend_views.append(views_by_day.get(day, 0) if tab == "overview" else 0)
        trend_clicks.append(clicks_by_day.get(day, 0))
        trend_shares.append(shares_by_day.get(day, 0) if tab == "overview" else 0)

    if tab == "overview":
        view_ref_rows = (
            db.query(ProfileView.referrer_domain, func.count(ProfileView.id).label("count"))
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
            db.query(LinkClick.referrer_domain, func.count(LinkClick.id).label("count"))
            .filter(
                LinkClick.user_id == user.id,
                LinkClick.created_at >= since,
                overview_filter,
                LinkClick.referrer_domain.isnot(None),
                LinkClick.referrer_domain != "",
            )
            .group_by(LinkClick.referrer_domain)
            .all()
        )
    else:
        view_ref_rows = []
        click_ref_rows = (
            db.query(LinkClick.referrer_domain, func.count(LinkClick.id).label("count"))
            .filter(
                LinkClick.user_id == user.id,
                LinkClick.created_at >= since,
                redirect_filter,
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

    if tab == "overview":
        view_device_rows = (
            db.query(ProfileView.device_type, func.count(ProfileView.id).label("count"))
            .filter(ProfileView.user_id == user.id, ProfileView.created_at >= since)
            .group_by(ProfileView.device_type)
            .all()
        )
        click_device_rows = (
            db.query(LinkClick.device_type, func.count(LinkClick.id).label("count"))
            .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, overview_filter)
            .group_by(LinkClick.device_type)
            .all()
        )
    else:
        view_device_rows = []
        click_device_rows = (
            db.query(LinkClick.device_type, func.count(LinkClick.id).label("count"))
            .filter(LinkClick.user_id == user.id, LinkClick.created_at >= since, redirect_filter)
            .group_by(LinkClick.device_type)
            .all()
        )
    device_counts: dict[str, int] = {}
    for device, count in list(view_device_rows) + list(click_device_rows):
        key = (device or "unknown").lower()
        device_counts[key] = device_counts.get(key, 0) + int(count or 0)
    device_split = sorted(device_counts.items(), key=lambda x: x[1], reverse=True)

    if tab == "overview":
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
                overview_filter,
                LinkClick.country.isnot(None),
                LinkClick.country != "",
            )
            .group_by(LinkClick.country)
            .all()
        )
    else:
        view_country_rows = []
        click_country_rows = (
            db.query(LinkClick.country, func.count(LinkClick.id).label("count"))
            .filter(
                LinkClick.user_id == user.id,
                LinkClick.created_at >= since,
                redirect_filter,
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

    if tab == "overview":
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
                overview_filter,
                LinkClick.city.isnot(None),
                LinkClick.city != "",
            )
            .group_by(LinkClick.city)
            .all()
        )
    else:
        view_city_rows = []
        click_city_rows = (
            db.query(LinkClick.city, func.count(LinkClick.id).label("count"))
            .filter(
                LinkClick.user_id == user.id,
                LinkClick.created_at >= since,
                redirect_filter,
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

    page = max(1, _safe_int(request.query_params.get("page"), 1))
    per_page = 50
    recent_query = (
        db.query(LinkClick, Link.title)
        .outerjoin(Link, Link.id == LinkClick.link_id)
        .filter(LinkClick.user_id == user.id, active_click_filter)
    )
    total_recent = recent_query.count()
    total_pages = max(1, (total_recent + per_page - 1) // per_page)
    page = min(page, total_pages)
    recent_clicks = (
        recent_query.order_by(LinkClick.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": user,
            "active_page": "analytics",
            "tab": tab,
            "days": days,
            "summary": {
                "views": int(total_views),
                "unique_visitors": int(unique_visitors),
                "profile_clicks": int(profile_clicks),
                "redirect_clicks": int(redirect_clicks),
                "active_clicks": int(active_clicks),
                "active_unique_clicks": int(active_unique_clicks),
                "redirect_unique_visitors": int(redirect_unique_visitors),
                "shares": int(total_shares),
                "profile_ctr": round((profile_clicks / total_views) * 100, 1) if total_views else 0.0,
                "redirect_ctr": round((redirect_clicks / total_views) * 100, 1) if total_views else 0.0,
                "ctr": round((total_clicks / total_views) * 100, 1) if total_views else 0.0,
            },
            "top_links": top_links,
            "redirect_top_links": redirect_top_links,
            "share_platforms": share_platforms,
            "top_referrers": top_referrers,
            "device_split": device_split,
            "countries": country_rows,
            "cities": city_rows,
            "trend_mode": tab,
            "trend_labels": trend_labels,
            "trend_views": trend_views,
            "trend_clicks": trend_clicks,
            "trend_shares": trend_shares,
            "recent_clicks": recent_clicks,
            "recent_page": page,
            "recent_total_pages": total_pages,
        },
    )
