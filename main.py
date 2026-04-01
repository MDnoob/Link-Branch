from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from database import Base, engine

load_dotenv()
import models  # noqa: F401
from routes.auth import router as auth_router
from routes.analytics import router as analytics_router
from routes.dashboard import router as dashboard_router
from routes.profile import router as profile_router
from routes.public import router as public_router
from routes.settings import router as settings_router


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

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback-secret-change-this"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(analytics_router)
app.include_router(profile_router)
app.include_router(public_router)
app.include_router(settings_router)


@app.get("/")
def root():
    return RedirectResponse(url="/login")


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
