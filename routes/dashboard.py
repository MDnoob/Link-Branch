import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, Link, RedirectLink
from routes.auth import get_current_user
from security import (
    normalize_asset_label,
    normalize_http_url,
    normalize_icon_value,
    sanitize_text,
)
from storage import delete_asset, save_asset

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_FILE_SIZE     = 2 * 1024 * 1024   # 2 MB per file
USER_STORAGE_CAP  = 20 * 1024 * 1024  # 20 MB total per user
MAX_UPLOADS_PER_MINUTE = 5            # rate limit: 5 uploads / 60 s per user

# In-memory rate-limit store  {user_id: [datetime, ...]}
# Lightweight enough for a single-process deployment.
_upload_timestamps: dict[int, list] = defaultdict(list)


def _check_upload_rate(user_id: int) -> bool:
    """Return True if the user is within the rate limit, False if exceeded."""
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=60)
    # Keep only timestamps inside the rolling window
    _upload_timestamps[user_id] = [
        t for t in _upload_timestamps[user_id] if t > window_start
    ]
    if len(_upload_timestamps[user_id]) >= MAX_UPLOADS_PER_MINUTE:
        return False
    _upload_timestamps[user_id].append(now)
    return True


def _used_storage(user_id: int, db: Session) -> int:
    """Return total bytes already stored for this user (NULL-safe)."""
    result = (
        db.query(func.coalesce(func.sum(Asset.file_size), 0))
        .filter(Asset.user_id == user_id)
        .scalar()
    )
    return int(result or 0)


def _normalize_url(value: str) -> str:
    return normalize_http_url(value, max_len=500) or ""


def _public_base_url(request: Request) -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    host_header = (request.headers.get("host") or request.url.netloc or "").strip()
    if host_header:
        return f"{request.url.scheme}://{host_header}"
    return str(request.base_url).rstrip("/")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    active_tab = (request.query_params.get("tab") or "links").strip().lower()
    if active_tab not in {"links", "extra"}:
        active_tab = "links"

    links = db.query(Link).filter(Link.user_id == user.id).order_by(Link.sort_order).all()
    redirect_links = (
        db.query(RedirectLink)
        .filter(RedirectLink.user_id == user.id)
        .order_by(RedirectLink.created_at.desc())
        .all()
    )
    assets = db.query(Asset).filter(Asset.user_id == user.id).order_by(Asset.created_at.desc()).all()
    assets_payload = [
        {
            "id": asset.id,
            "url": asset.url,
            "label": sanitize_text(asset.label, max_len=100) or "Asset",
        }
        for asset in assets
    ]

    used_bytes = _used_storage(user.id, db)
    storage_info = {
        "used_mb":  round(used_bytes / (1024 * 1024), 2),
        "cap_mb":   USER_STORAGE_CAP // (1024 * 1024),
        "used_pct": min(100, round(used_bytes / USER_STORAGE_CAP * 100, 1)),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "links": links,
            "redirect_links": redirect_links,
            "assets": assets,
            "assets_payload": assets_payload,
            "active_tab": active_tab,
            "public_base_url": _public_base_url(request),
            "active_page": "dashboard",
            "storage_info": storage_info,
        },
    )


@router.post("/dashboard/links/add")
def add_link(
    request: Request,
    title: str = Form(...),
    url: str = Form(""),
    icon: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    cleaned_title = sanitize_text(title, max_len=200)
    if not cleaned_title:
        return RedirectResponse(url="/dashboard?tab=links", status_code=302)

    max_order = db.query(Link).filter(Link.user_id == user.id).count()
    new_link = Link(
        user_id=user.id,
        title=cleaned_title,
        url=_normalize_url(url) or None,
        icon=normalize_icon_value(icon),
        is_section=False,
        sort_order=max_order,
    )
    db.add(new_link)
    db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/add-section")
def add_section(
    request: Request,
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    cleaned_title = sanitize_text(title, max_len=200)
    if not cleaned_title:
        return RedirectResponse(url="/dashboard?tab=links", status_code=302)

    max_order = db.query(Link).filter(Link.user_id == user.id).count()
    section = Link(
        user_id=user.id,
        title=cleaned_title,
        url=None,
        icon=None,
        is_section=True,
        sort_order=max_order,
    )
    db.add(section)
    db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/{link_id}/delete")
def delete_link(link_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user.id).first()
    if link:
        db.delete(link)
        db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/{link_id}/toggle")
def toggle_link(link_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user.id).first()
    if link and not link.is_section:
        link.is_active = not link.is_active
        db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/{link_id}/edit")
def edit_link(
    link_id: int,
    request: Request,
    title: str = Form(...),
    url: str = Form(""),
    icon: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user.id).first()
    if link:
        cleaned_title = sanitize_text(title, max_len=200)
        if not cleaned_title:
            return RedirectResponse(url="/dashboard?tab=links", status_code=302)
        link.title = cleaned_title
        if not link.is_section:
            link.url = _normalize_url(url) or None
            link.icon = normalize_icon_value(icon)
        db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/reorder")
async def reorder_links(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    raw_order = data.get("order", [])
    if not isinstance(raw_order, list):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    order = [link_id for link_id in raw_order if isinstance(link_id, int) and not isinstance(link_id, bool)]
    for index, link_id in enumerate(order[:500]):
        link = db.query(Link).filter(Link.id == link_id, Link.user_id == user.id).first()
        if link:
            link.sort_order = index
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/dashboard/redirect-links/add")
def add_redirect_link(
    request: Request,
    title: str = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    normalized = _normalize_url(url)
    if normalized:
        safe_title = sanitize_text(title, max_len=200) or "Tracked Link"
        row = RedirectLink(user_id=user.id, title=safe_title, url=normalized)
        db.add(row)
        db.commit()
    return RedirectResponse(url="/dashboard?tab=extra", status_code=302)


@router.post("/dashboard/redirect-links/{redirect_id}/toggle")
def toggle_redirect_link(redirect_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    row = (
        db.query(RedirectLink)
        .filter(RedirectLink.id == redirect_id, RedirectLink.user_id == user.id)
        .first()
    )
    if row:
        row.is_active = not row.is_active
        db.commit()
    return RedirectResponse(url="/dashboard?tab=extra", status_code=302)


@router.post("/dashboard/redirect-links/{redirect_id}/delete")
def delete_redirect_link(redirect_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    row = (
        db.query(RedirectLink)
        .filter(RedirectLink.id == redirect_id, RedirectLink.user_id == user.id)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return RedirectResponse(url="/dashboard?tab=extra", status_code=302)


@router.post("/dashboard/assets/upload")
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    label: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # --- Rate limit: max 5 uploads per 60 seconds per user ---
    if not _check_upload_rate(user.id):
        return JSONResponse(
            {"error": f"Too many uploads. Max {MAX_UPLOADS_PER_MINUTE} per minute."},
            status_code=429,
        )

    # --- File type validation ---
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse({"error": "File type not allowed."}, status_code=400)
    if not (file.content_type or "").lower().startswith("image/"):
        return JSONResponse({"error": "Only image files are allowed."}, status_code=400)

    # --- Read & size check (per-file cap) ---
    contents = await file.read()
    file_size = len(contents)
    if file_size > MAX_FILE_SIZE:
        return JSONResponse({"error": "File too large. Max 2 MB per file."}, status_code=400)

    # --- Per-user total storage quota ---
    used = _used_storage(user.id, db)
    if used + file_size > USER_STORAGE_CAP:
        remaining_mb = round((USER_STORAGE_CAP - used) / (1024 * 1024), 2)
        return JSONResponse(
            {
                "error": (
                    f"Storage quota exceeded. "
                    f"You have {remaining_mb} MB remaining out of "
                    f"{USER_STORAGE_CAP // (1024*1024)} MB total."
                )
            },
            status_code=400,
        )

    # --- Save to OCI or local disk ---
    unique_name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    asset_url = save_asset(contents, unique_name)

    safe_label = normalize_asset_label(label, fallback=os.path.splitext(file.filename or "")[0])
    asset = Asset(
        user_id=user.id,
        filename=unique_name,
        label=safe_label,
        url=asset_url,
        file_size=file_size,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return JSONResponse({"id": asset.id, "url": asset.url, "label": asset.label})


@router.post("/dashboard/assets/{asset_id}/delete")
def delete_asset_route(asset_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user.id).first()
    if asset:
        delete_asset(asset.filename, asset.url)
        db.delete(asset)
        db.commit()
    return RedirectResponse(url="/assets", status_code=302)


@router.get("/assets", response_class=HTMLResponse)
def assets_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    assets = db.query(Asset).filter(Asset.user_id == user.id).order_by(Asset.created_at.desc()).all()
    used_bytes = _used_storage(user.id, db)
    storage_info = {
        "used_mb":  round(used_bytes / (1024 * 1024), 2),
        "cap_mb":   USER_STORAGE_CAP // (1024 * 1024),
        "used_pct": min(100, round(used_bytes / USER_STORAGE_CAP * 100, 1)),
    }
    return templates.TemplateResponse(
        "assets.html",
        {
            "request": request,
            "user": user,
            "assets": assets,
            "active_page": "assets",
            "storage_info": storage_info,
        },
    )
