import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, Link, RedirectLink
from routes.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_FILE_SIZE = 2 * 1024 * 1024


def _normalize_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


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
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "links": links,
            "redirect_links": redirect_links,
            "assets": assets,
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

    max_order = db.query(Link).filter(Link.user_id == user.id).count()
    new_link = Link(
        user_id=user.id,
        title=title,
        url=_normalize_url(url) or None,
        icon=icon or None,
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

    max_order = db.query(Link).filter(Link.user_id == user.id).count()
    section = Link(
        user_id=user.id,
        title=title,
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
        link.title = title
        if not link.is_section:
            link.url = _normalize_url(url) or None
            link.icon = icon or None
        db.commit()
    return RedirectResponse(url="/dashboard?tab=links", status_code=302)


@router.post("/dashboard/links/reorder")
async def reorder_links(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    data = await request.json()
    for index, link_id in enumerate(data.get("order", [])):
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
        row = RedirectLink(user_id=user.id, title=(title.strip() or "Tracked Link")[:200], url=normalized)
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

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return JSONResponse({"error": "File too large. Max 2MB."}, status_code=400)

    unique_name = f"{user.id}_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(contents)

    asset_url = f"/static/uploads/{unique_name}"
    asset = Asset(
        user_id=user.id,
        filename=unique_name,
        label=label or os.path.splitext(file.filename or "")[0][:100],
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
