from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
from models import User, Asset
from routes.auth import get_current_user

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

    user.display_name    = display_name[:100] if display_name else None
    user.bio             = bio[:200]           if bio          else None
    user.avatar_url      = avatar_url          or None
    user.avatar_shape    = avatar_shape
    user.avatar_fit      = avatar_fit if avatar_fit in {"cover", "contain"} else "cover"
    user.avatar_scale    = max(70, min(140, avatar_scale))
    user.bg_type         = bg_type
    user.bg_color        = bg_color
    user.bg_gradient     = bg_gradient         or None
    user.bg_image        = bg_image            or None
    user.bg_overlay      = max(0, min(80, bg_overlay))
    user.island_style    = island_style if island_style in {"glass", "solid", "gradient", "image"} else "glass"
    user.island_color    = island_color or "#ffffff"
    user.island_gradient = island_gradient or None
    user.island_image    = island_image or None
    user.island_overlay  = max(0, min(80, island_overlay))
    user.btn_style       = btn_style
    user.btn_fill        = btn_fill
    user.btn_color       = btn_color
    user.btn_text_color  = btn_text_color
    user.btn_hover       = btn_hover
    user.font_family     = font_family
    user.font_size       = font_size
    user.text_name_color = text_name_color
    user.text_bio_color  = text_bio_color
    user.show_branding   = show_branding

    db.commit()
    return RedirectResponse(url="/settings?saved=1", status_code=302)
