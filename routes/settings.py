from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models import User, Asset
from routes.auth import get_current_user
from security import (
    normalize_color_hex,
    normalize_enum,
    normalize_http_url,
    sanitize_text,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    assets = db.query(Asset).filter(Asset.user_id == user.id).order_by(Asset.created_at.desc()).all()
    return templates.TemplateResponse("settings.html", {
        "request":     request,
        "user":        user,
        "assets":      assets,
        "active_page": "settings"
    })


@router.post("/settings")
def save_settings(
    request: Request,
    display_name:    str  = Form(""),
    bio:             str  = Form(""),
    avatar_url:      str  = Form(""),
    avatar_shape:    str  = Form("circle"),
    avatar_fit:      str  = Form("cover"),
    avatar_scale:    int  = Form(100),
    bg_type:         str  = Form("solid"),
    bg_color:        str  = Form("#f7f6f2"),
    bg_gradient:     str  = Form(""),
    bg_image:        str  = Form(""),
    bg_overlay:      int  = Form(0),
    island_style:    str  = Form("glass"),
    island_color:    str  = Form("#ffffff"),
    island_gradient: str  = Form(""),
    island_image:    str  = Form(""),
    island_overlay:  int  = Form(18),
    btn_style:       str  = Form("pill"),
    btn_fill:        str  = Form("filled"),
    btn_color:       str  = Form("#1a1a18"),
    btn_text_color:  str  = Form("#ffffff"),
    btn_hover:       str  = Form("lift"),
    font_family:     str  = Form("Inter"),
    font_size:       str  = Form("medium"),
    text_name_color: str  = Form("#1a1a18"),
    text_bio_color:  str  = Form("#555555"),
    show_branding:   bool = Form(False),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.display_name    = sanitize_text(display_name, max_len=100) or None
    user.bio             = sanitize_text(bio, max_len=200, multiline=True) or None
    user.avatar_url      = normalize_http_url(avatar_url, max_len=500, allow_static_upload_path=True)
    user.avatar_shape    = normalize_enum(avatar_shape, allowed={"circle", "rounded", "square"}, default="circle")
    user.avatar_fit      = normalize_enum(avatar_fit, allowed={"cover", "contain"}, default="cover")
    user.avatar_scale    = max(70, min(140, avatar_scale))
    user.bg_type         = normalize_enum(bg_type, allowed={"solid", "gradient", "image"}, default="solid")
    user.bg_color        = normalize_color_hex(bg_color, default="#f7f6f2")
    user.bg_gradient     = sanitize_text(bg_gradient, max_len=120) or None
    user.bg_image        = normalize_http_url(bg_image, max_len=500, allow_static_upload_path=True)
    user.bg_overlay      = max(0, min(80, bg_overlay))
    user.island_style    = normalize_enum(
        island_style,
        allowed={"glass", "solid", "gradient", "image"},
        default="glass",
    )
    user.island_color    = normalize_color_hex(island_color, default="#ffffff")
    user.island_gradient = sanitize_text(island_gradient, max_len=120) or None
    user.island_image    = normalize_http_url(island_image, max_len=500, allow_static_upload_path=True)
    user.island_overlay  = max(0, min(80, island_overlay))
    user.btn_style       = normalize_enum(btn_style, allowed={"pill", "rounded", "sharp"}, default="pill")
    user.btn_fill        = normalize_enum(btn_fill, allowed={"filled", "outline", "shadow"}, default="filled")
    user.btn_color       = normalize_color_hex(btn_color, default="#1a1a18")
    user.btn_text_color  = normalize_color_hex(btn_text_color, default="#ffffff")
    user.btn_hover       = normalize_enum(btn_hover, allowed={"lift", "glow", "darken", "none"}, default="lift")
    font_key = normalize_enum(
        font_family,
        allowed={"inter", "satoshi", "poppins", "playfair display", "merriweather", "dm sans"},
        default="inter",
    )
    font_map = {
        "inter": "Inter",
        "satoshi": "Satoshi",
        "poppins": "Poppins",
        "playfair display": "Playfair Display",
        "merriweather": "Merriweather",
        "dm sans": "DM Sans",
    }
    user.font_family     = font_map.get(font_key, "Inter")
    user.font_size       = normalize_enum(font_size, allowed={"small", "medium", "large", "xlarge"}, default="medium")
    user.text_name_color = normalize_color_hex(text_name_color, default="#1a1a18")
    user.text_bio_color  = normalize_color_hex(text_bio_color, default="#555555")
    user.show_branding   = show_branding

    db.commit()
    return RedirectResponse(url="/settings?saved=1", status_code=302)
