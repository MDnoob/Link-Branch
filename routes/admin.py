from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, Link, LinkClick, ProfileView, RedirectLink, ShareEvent, User
from routes.auth import get_current_user
from security import is_super_admin_username

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not is_super_admin_username(user.username):
        return HTMLResponse("Forbidden", status_code=403)

    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    summary = {
        "users_total": db.query(func.count(User.id)).scalar() or 0,
        "users_active": db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0,
        "links_total": db.query(func.count(Link.id)).filter(Link.is_section.is_(False)).scalar() or 0,
        "sections_total": db.query(func.count(Link.id)).filter(Link.is_section.is_(True)).scalar() or 0,
        "redirect_links_total": db.query(func.count(RedirectLink.id)).scalar() or 0,
        "assets_total": db.query(func.count(Asset.id)).scalar() or 0,
        "profile_views_total": db.query(func.count(ProfileView.id)).scalar() or 0,
        "clicks_total": db.query(func.count(LinkClick.id)).scalar() or 0,
        "shares_total": db.query(func.count(ShareEvent.id)).scalar() or 0,
        "new_users_7d": db.query(func.count(User.id)).filter(User.created_at >= seven_days_ago).scalar() or 0,
        "views_7d": db.query(func.count(ProfileView.id)).filter(ProfileView.created_at >= seven_days_ago).scalar() or 0,
        "clicks_7d": db.query(func.count(LinkClick.id)).filter(LinkClick.created_at >= seven_days_ago).scalar() or 0,
        "shares_7d": db.query(func.count(ShareEvent.id)).filter(ShareEvent.created_at >= seven_days_ago).scalar() or 0,
    }

    top_profiles = (
        db.query(
            User.username,
            func.count(func.distinct(ProfileView.id)).label("views"),
            func.count(func.distinct(LinkClick.id)).label("clicks"),
        )
        .outerjoin(ProfileView, ProfileView.user_id == User.id)
        .outerjoin(LinkClick, LinkClick.user_id == User.id)
        .group_by(User.id, User.username)
        .order_by(func.count(func.distinct(ProfileView.id)).desc())
        .limit(10)
        .all()
    )

    latest_users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "top_profiles": top_profiles,
            "latest_users": latest_users,
            "active_page": "admin",
        },
    )
