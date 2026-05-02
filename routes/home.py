from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from database import get_db
from models import LinkClick, ProfileView, User

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _public_base_url(request: Request) -> str:
    configured = __import__('os').getenv('PUBLIC_BASE_URL', '').strip()
    if configured:
        return configured.rstrip('/')
    host = (request.headers.get('host') or request.url.netloc or '').strip()
    if host:
        return f"{request.url.scheme}://{host}"
    return str(request.base_url).rstrip('/')


def _get_stats(db: Session) -> dict:
    total_clicks = db.query(func.count(LinkClick.id)).scalar() or 0
    total_views = db.query(func.count(ProfileView.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0

    # Distinct countries from both clicks and views combined
    click_countries = db.query(distinct(LinkClick.country)).filter(LinkClick.country.isnot(None))
    view_countries = db.query(distinct(ProfileView.country)).filter(ProfileView.country.isnot(None))
    all_countries = {row[0] for row in click_countries.all()} | {row[0] for row in view_countries.all()}
    total_countries = len(all_countries)

    # Top 5 countries by click count
    top_raw = (
        db.query(LinkClick.country, func.count(LinkClick.id).label('cnt'))
        .filter(LinkClick.country.isnot(None))
        .group_by(LinkClick.country)
        .order_by(func.count(LinkClick.id).desc())
        .limit(5)
        .all()
    )
    max_cnt = top_raw[0][1] if top_raw else 1
    top_countries = [
        {"country": r[0], "clicks": r[1], "pct": round(r[1] / max_cnt * 100)}
        for r in top_raw
    ]
    # Pad to 5 rows so the mockup always looks full
    placeholders = [("—", 0, 0)] * (5 - len(top_countries))
    top_countries += [{"country": p[0], "clicks": p[1], "pct": p[2]} for p in placeholders]

    return {
        "total_clicks":        total_clicks,
        "total_profile_views": total_views,
        "total_users":         total_users,
        "total_countries":     total_countries,
        "top_countries":       top_countries,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    stats = _get_stats(db)
    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats":   stats,
        "year":    datetime.utcnow().year,
        "public_base_url": _public_base_url(request),
    })
