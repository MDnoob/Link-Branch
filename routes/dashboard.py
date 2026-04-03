import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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

router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_FILE_SIZE = 2 * 1024 * 1024


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

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return JSONResponse({"error": "File type not allowed."}, status_code=400)
    if not (file.content_type or "").lower().startswith("image/"):
        return JSONResponse({"error": "Only image files are allowed."}, status_code=400)

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return JSONResponse({"error": "File too large. Max 2MB."}, status_code=400)

    unique_name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(contents)

    asset_url = f"/static/uploads/{unique_name}"
    safe_label = normalize_asset_label(label, fallback=os.path.splitext(file.filename or "")[0])
    asset = Asset(
        user_id=user.id,
        filename=unique_name,
        label=safe_label,
        url=asset_url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return JSONResponse({"id": asset.id, "url": asset.url, "label": asset.label})


@router.post("/dashboard/assets/{asset_id}/delete")
def delete_asset(asset_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == user.id).first()
    if asset:
        disk_path = os.path.join(UPLOAD_DIR, asset.filename)
        if os.path.exists(disk_path):
            os.remove(disk_path)
        db.delete(asset)
        db.commit()
    return RedirectResponse(url="/assets", status_code=302)


@router.get("/assets", response_class=HTMLResponse)
def assets_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    assets = db.query(Asset).filter(Asset.user_id == user.id).order_by(Asset.created_at.desc()).all()
    return templates.TemplateResponse(
        "assets.html",
        {"request": request, "user": user, "assets": assets, "active_page": "assets"},
    )
