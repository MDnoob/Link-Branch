from contextlib import asynccontextmanager
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from database import Base, engine, get_db

load_dotenv()
import models  # noqa: F401
from models import User
from routes.auth import router as auth_router
from routes.analytics import router as analytics_router
from routes.admin import router as admin_router
from routes.dashboard import router as dashboard_router
from routes.home import router as home_router
from routes.profile import router as profile_router
from routes.public import router as public_router
from routes.settings import router as settings_router
from security import TRUE_VALUES


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in TRUE_VALUES


def _is_production() -> bool:
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
    return env in {"prod", "production"}


def _session_secret() -> str:
    secret = (os.getenv("SECRET_KEY") or "").strip()
    if secret and secret != "fallback-secret-change-this":
        return secret
    if _is_production():
        raise RuntimeError("SECRET_KEY must be configured for production.")
    return secret or "fallback-secret-change-this"


def _session_same_site() -> str:
    value = (os.getenv("SESSION_SAMESITE") or "lax").strip().lower()
    if value in {"lax", "strict", "none"}:
        return value
    return "lax"


def _cors_allow_origins() -> list[str]:
    raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return []
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def _public_base_url(request: Request) -> str:
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    host = (request.headers.get("host") or request.url.netloc or "").strip()
    if host:
        return f"{request.url.scheme}://{host}"
    return str(request.base_url).rstrip("/")


def _migrate_sqlite_table_columns(table_name: str, new_columns: dict[str, str]) -> None:
    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
        existing = {row[1] for row in rows}
        for column, definition in new_columns.items():
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}")


def _migrate_sqlite_users_table() -> None:
    _migrate_sqlite_table_columns(
        "users",
        {
            "phone": "TEXT",
            "avatar_fit": "TEXT DEFAULT 'cover'",
            "avatar_scale": "INTEGER DEFAULT 100",
            "island_style": "TEXT DEFAULT 'glass'",
            "island_color": "TEXT DEFAULT '#ffffff'",
            "island_gradient": "TEXT",
            "island_image": "TEXT",
            "island_overlay": "INTEGER DEFAULT 18",
        },
    )


def _migrate_sqlite_tracking_tables() -> None:
    _migrate_sqlite_table_columns(
        "profile_views",
        {
            "referrer_domain": "TEXT",
            "device_type": "TEXT",
            "country": "TEXT",
            "city": "TEXT",
        },
    )
    _migrate_sqlite_table_columns(
        "link_clicks",
        {
            "referer": "TEXT",
            "referrer_domain": "TEXT",
            "device_type": "TEXT",
            "country": "TEXT",
            "city": "TEXT",
            "click_source": "TEXT",
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_users_table()
    _migrate_sqlite_tracking_tables()
    print("Database tables ready")
    yield


app = FastAPI(title="Link Branch", version="0.1.1", lifespan=lifespan)

cors_origins = _cors_allow_origins()
if cors_origins:
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    same_site=_session_same_site(),
    https_only=_env_flag("SESSION_HTTPS_ONLY", default=_is_production()),
    max_age=int(os.getenv("SESSION_MAX_AGE_SECONDS", "1209600")),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(home_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(analytics_router)
app.include_router(admin_router)
app.include_router(profile_router)
app.include_router(public_router)
app.include_router(settings_router)


@app.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request):
    base = _public_base_url(request)
    content = f"""User-agent: *
Allow: /
Allow: /profile/
Disallow: /dashboard
Disallow: /settings
Disallow: /analytics
Disallow: /admin
Disallow: /login
Disallow: /register

Sitemap: {base}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request, db: Session = Depends(get_db)):
    base = _public_base_url(request)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    users = db.query(User.username, User.created_at).filter(User.is_active == True).all()

    urls = [
        f"""  <url>
    <loc>{base}/</loc>
    <lastmod>{now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>"""
    ]

    for username, created_at in users:
        lastmod = created_at.strftime("%Y-%m-%d") if created_at else now
        urls.append(f"""  <url>
    <loc>{base}/profile/{username}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"

    return Response(content=xml, media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=str(os.getenv("RELOAD", "false")).strip().lower() in {"1", "true", "yes", "on"},
    )
