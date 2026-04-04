import os
from urllib.parse import quote_plus, urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from geo import lookup as _geo_lookup
from models import Link, LinkClick, ProfileView, RedirectLink, User

router = APIRouter()
templates = Jinja2Templates(directory="templates")
TRUE_VALUES = {"1", "true", "on", "yes"}


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


async def _geo_context(request: Request) -> tuple[str | None, str | None]:
    """Resolve visitor geo via IPstack (server-side, reliable).
    Falls back to proxy headers (Cloudflare / Vercel) when IPSTACK_KEY is absent.
    """
    ip = _client_ip(request)
    country, city = await _geo_lookup(ip)
    if not country:
        # Fallback: proxy-injected headers (Cloudflare / Vercel deployments)
        country = (
            request.headers.get("cf-ipcountry")
            or request.headers.get("x-vercel-ip-country")
            or ""
        ).strip()[:100] or None
        city = (
            request.headers.get("x-vercel-ip-city") or ""
        ).strip()[:100] or None
    return country, city


def _normalize_destination(url: str | None) -> str:
    destination = (url or "").strip()
    if destination and not destination.startswith(("http://", "https://")):
        destination = "https://" + destination
    return destination


def _public_base_url(request: Request) -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")

    host_header = (request.headers.get("host") or request.url.netloc or "").strip()
    if host_header:
        return f"{request.url.scheme}://{host_header}"
    return str(request.base_url).rstrip("/")


def _log_link_click(
    db: Session,
    request: Request,
    *,
    owner_id: int,
    link_id: int | None,
    destination: str,
    ref: str | None,
    click_source: str,
    country: str | None = None,
    city: str | None = None,
) -> None:
    click = LinkClick(
        user_id=owner_id,
        link_id=link_id,
        destination_url=destination,
        ref=ref,
        viewer_ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
        referer=(request.headers.get("referer") or "")[:500] or None,
        referrer_domain=_referrer_domain(request.headers.get("referer")),
        device_type=_device_type(request.headers.get("user-agent")),
        country=country,
        city=city,
        click_source=click_source,
    )
    db.add(click)
    try:
        db.commit()
    except Exception:
        db.rollback()


@router.get("/profile/{username}", response_class=HTMLResponse)
async def public_profile(username: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": f"@{username} doesn't exist on Link Branch."},
            status_code=404,
        )

    links = db.query(Link).filter(Link.user_id == user.id).order_by(Link.sort_order).all()
    visible = [l for l in links if l.is_section or l.is_active]

    params = dict(request.query_params)
    in_preview = bool(params.get("preview"))
    view_id: int | None = None

    if in_preview:
        for attr in [
            "display_name", "bio", "avatar_url", "avatar_shape", "avatar_size",
            "avatar_fit", "avatar_scale", "bg_type", "bg_color", "bg_gradient",
            "bg_image", "island_style", "island_color", "island_gradient",
            "island_image", "btn_style", "btn_fill", "btn_color", "btn_text_color",
            "btn_hover", "font_family", "font_size", "text_name_color", "text_bio_color",
        ]:
            if attr in params:
                setattr(user, attr, params[attr])
        for int_attr, default, lo, hi in [
            ("bg_overlay", 0, 0, 100),
            ("island_overlay", 18, 0, 100),
            ("avatar_scale", 100, 70, 140),
        ]:
            if int_attr in params:
                try:
                    setattr(user, int_attr, max(lo, min(hi, int(params[int_attr]))))
                except ValueError:
                    pass
        if "show_branding" in params:
            user.show_branding = str(params["show_branding"]).strip().lower() in TRUE_VALUES
    else:
        country, city = await _geo_context(request)
        view = ProfileView(
            user_id=user.id,
            path=str(request.url.path)[:255],
            viewer_ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
            referer=(request.headers.get("referer") or "")[:500] or None,
            referrer_domain=_referrer_domain(request.headers.get("referer")),
            device_type=_device_type(request.headers.get("user-agent")),
            country=country,
            city=city,
        )
        db.add(view)
        try:
            db.commit()
            db.refresh(view)
            view_id = view.id
        except Exception:
            db.rollback()

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "links": visible,
            "public_base_url": _public_base_url(request),
            "view_id": view_id,
        },
    )


@router.get("/l/{link_id}")
async def open_link(link_id: int, request: Request, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link or link.is_section:
        return RedirectResponse(url="/", status_code=302)

    destination = _normalize_destination(link.url)
    if not destination:
        return RedirectResponse(url="/", status_code=302)

    ref = (request.query_params.get("ref") or "")[:100] or None
    country, city = await _geo_context(request)
    _log_link_click(
        db,
        request,
        owner_id=link.user_id,
        link_id=link.id,
        destination=destination,
        ref=ref,
        click_source="public_redirect",
        country=country,
        city=city,
    )
    return RedirectResponse(url=destination, status_code=302)


@router.get("/r/{redirect_id}")
async def open_redirect_link(redirect_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.query(RedirectLink).filter(RedirectLink.id == redirect_id).first()
    if not row or not row.is_active:
        return RedirectResponse(url="/", status_code=302)

    destination = _normalize_destination(row.url)
    if not destination:
        return RedirectResponse(url="/", status_code=302)

    ref = (request.query_params.get("ref") or "")[:100] or None
    country, city = await _geo_context(request)
    _log_link_click(
        db,
        request,
        owner_id=row.user_id,
        link_id=None,
        destination=destination,
        ref=ref,
        click_source="extra_redirect",
        country=country,
        city=city,
    )
    return RedirectResponse(url=destination, status_code=302)
