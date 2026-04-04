import re

import bcrypt
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import enforce_rate_limit, is_valid_email, normalize_email

router = APIRouter()
templates = Jinja2Templates(directory="templates")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,50}$")

# Curated list of common IANA timezone identifiers.
# The full IANA list has 600+ zones; we surface the most-used ones.
COMMON_TIMEZONES: list[tuple[str, str]] = [
    # UTC
    ("UTC", "UTC"),
    # Americas
    ("America/New_York",      "Eastern Time (New York)"),
    ("America/Chicago",       "Central Time (Chicago)"),
    ("America/Denver",        "Mountain Time (Denver)"),
    ("America/Los_Angeles",   "Pacific Time (Los Angeles)"),
    ("America/Anchorage",     "Alaska Time"),
    ("Pacific/Honolulu",      "Hawaii Time"),
    ("America/Sao_Paulo",     "Brazil (São Paulo)"),
    ("America/Argentina/Buenos_Aires", "Argentina (Buenos Aires)"),
    ("America/Bogota",        "Colombia (Bogotá)"),
    ("America/Lima",          "Peru (Lima)"),
    ("America/Santiago",      "Chile (Santiago)"),
    ("America/Mexico_City",   "Mexico (Mexico City)"),
    ("America/Toronto",       "Canada Eastern (Toronto)"),
    ("America/Vancouver",     "Canada Pacific (Vancouver)"),
    # Europe
    ("Europe/London",         "UK (London)"),
    ("Europe/Dublin",         "Ireland (Dublin)"),
    ("Europe/Lisbon",         "Portugal (Lisbon)"),
    ("Europe/Madrid",         "Spain (Madrid)"),
    ("Europe/Paris",          "France (Paris)"),
    ("Europe/Amsterdam",      "Netherlands (Amsterdam)"),
    ("Europe/Berlin",         "Germany (Berlin)"),
    ("Europe/Rome",           "Italy (Rome)"),
    ("Europe/Warsaw",         "Poland (Warsaw)"),
    ("Europe/Stockholm",      "Sweden (Stockholm)"),
    ("Europe/Oslo",           "Norway (Oslo)"),
    ("Europe/Copenhagen",     "Denmark (Copenhagen)"),
    ("Europe/Helsinki",       "Finland (Helsinki)"),
    ("Europe/Athens",         "Greece (Athens)"),
    ("Europe/Istanbul",       "Turkey (Istanbul)"),
    ("Europe/Kiev",           "Ukraine (Kyiv)"),
    ("Europe/Moscow",         "Russia (Moscow)"),
    # Africa
    ("Africa/Cairo",          "Egypt (Cairo)"),
    ("Africa/Lagos",          "Nigeria (Lagos)"),
    ("Africa/Johannesburg",   "South Africa (Johannesburg)"),
    ("Africa/Nairobi",        "Kenya (Nairobi)"),
    # Asia
    ("Asia/Dubai",            "UAE (Dubai)"),
    ("Asia/Riyadh",           "Saudi Arabia (Riyadh)"),
    ("Asia/Kolkata",          "India (IST)"),
    ("Asia/Dhaka",            "Bangladesh (Dhaka)"),
    ("Asia/Kathmandu",        "Nepal (Kathmandu)"),
    ("Asia/Colombo",          "Sri Lanka (Colombo)"),
    ("Asia/Karachi",          "Pakistan (Karachi)"),
    ("Asia/Kabul",            "Afghanistan (Kabul)"),
    ("Asia/Tashkent",         "Uzbekistan (Tashkent)"),
    ("Asia/Tehran",           "Iran (Tehran)"),
    ("Asia/Baghdad",          "Iraq (Baghdad)"),
    ("Asia/Baku",             "Azerbaijan (Baku)"),
    ("Asia/Tbilisi",          "Georgia (Tbilisi)"),
    ("Asia/Yerevan",          "Armenia (Yerevan)"),
    ("Asia/Bangkok",          "Thailand (Bangkok)"),
    ("Asia/Ho_Chi_Minh",      "Vietnam (Ho Chi Minh)"),
    ("Asia/Jakarta",          "Indonesia (Jakarta)"),
    ("Asia/Kuala_Lumpur",     "Malaysia (Kuala Lumpur)"),
    ("Asia/Singapore",        "Singapore"),
    ("Asia/Manila",           "Philippines (Manila)"),
    ("Asia/Shanghai",         "China (Shanghai)"),
    ("Asia/Hong_Kong",        "Hong Kong"),
    ("Asia/Taipei",           "Taiwan (Taipei)"),
    ("Asia/Seoul",            "South Korea (Seoul)"),
    ("Asia/Tokyo",            "Japan (Tokyo)"),
    # Oceania
    ("Australia/Perth",       "Australia (Perth)"),
    ("Australia/Adelaide",    "Australia (Adelaide)"),
    ("Australia/Sydney",      "Australia (Sydney)"),
    ("Pacific/Auckland",      "New Zealand (Auckland)"),
]

VALID_TIMEZONES = {tz for tz, _ in COMMON_TIMEZONES}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def normalize_phone(phone: str) -> str | None:
    raw = (phone or "").strip()
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("+"):
        digits = "+" + re.sub(r"\D", "", digits[1:])
    else:
        digits = re.sub(r"\D", "", digits)
    return digits or None


def password_policy_state(password: str) -> dict[str, bool]:
    text = password or ""
    return {
        "min_len": len(text) >= 8,
        "has_upper": bool(re.search(r"[A-Z]", text)),
        "has_lower": bool(re.search(r"[a-z]", text)),
        "has_digit": bool(re.search(r"\d", text)),
        "has_symbol": bool(re.search(r"[^A-Za-z0-9]", text)),
    }


def password_policy_errors(password: str) -> list[str]:
    s = password_policy_state(password)
    errors = []
    if not s["min_len"]:
        errors.append("Password must be at least 8 characters.")
    if not s["has_upper"]:
        errors.append("Add at least one uppercase letter.")
    if not s["has_lower"]:
        errors.append("Add at least one lowercase letter.")
    if not s["has_digit"]:
        errors.append("Add at least one number.")
    if not s["has_symbol"]:
        errors.append("Add at least one special character.")
    return errors


def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("username")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


def _auth_rate_limited_template(request: Request, show_register: bool = False):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "show_register": show_register,
            "error": "Too many attempts. Please wait a minute and try again.",
            "timezones": COMMON_TIMEZONES,
        },
        status_code=429,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "timezones": COMMON_TIMEZONES})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        enforce_rate_limit(request, bucket="auth_login", limit=12, window_seconds=60)
    except HTTPException:
        return _auth_rate_limited_template(request)
    normalized_username = (username or "").strip().lower()
    user = db.query(User).filter(User.username == normalized_username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password", "timezones": COMMON_TIMEZONES},
        )
    request.session["username"] = user.username
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "show_register": True, "timezones": COMMON_TIMEZONES})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    timezone: str = Form("UTC"),
    db: Session = Depends(get_db),
):
    try:
        enforce_rate_limit(request, bucket="auth_register", limit=6, window_seconds=300)
    except HTTPException:
        return _auth_rate_limited_template(request, show_register=True)
    normalized_username = (username or "").strip().lower()
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    # Sanitise timezone — fall back to UTC if submitted value is not in our allowlist
    safe_timezone = timezone.strip() if timezone.strip() in VALID_TIMEZONES else "UTC"

    if not USERNAME_RE.match(normalized_username):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "show_register": True,
                "error": "Username must be 3-50 chars and use lowercase letters, numbers, _ or . only.",
                "timezones": COMMON_TIMEZONES,
            },
        )
    if not is_valid_email(normalized_email):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Please enter a valid email address.", "timezones": COMMON_TIMEZONES},
        )
    if db.query(User).filter(User.username == normalized_username).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Username already taken", "timezones": COMMON_TIMEZONES},
        )
    if db.query(User).filter(User.email == normalized_email).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Email already registered", "timezones": COMMON_TIMEZONES},
        )
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Phone number already registered", "timezones": COMMON_TIMEZONES},
        )

    errors = password_policy_errors(password)
    if errors:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": errors[0], "timezones": COMMON_TIMEZONES},
        )

    new_user = User(
        username=normalized_username,
        email=normalized_email,
        phone=normalized_phone,
        hashed_password=hash_password(password),
        display_name=normalized_username,
        timezone=safe_timezone,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    request.session["username"] = new_user.username
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        enforce_rate_limit(request, bucket="auth_forgot_password", limit=6, window_seconds=600)
    except HTTPException:
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "Too many attempts. Please wait and try again."},
            status_code=429,
        )
    normalized_username = (username or "").strip().lower()
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    if not is_valid_email(normalized_email):
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "Please enter a valid email address."},
        )

    user = (
        db.query(User)
        .filter(User.username == normalized_username, User.email == normalized_email)
        .first()
    )
    if not user:
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "We could not verify these account details."},
        )

    if user.phone and normalized_phone != user.phone:
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "Phone number does not match this account."},
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "Passwords do not match."},
        )

    errors = password_policy_errors(new_password)
    if errors:
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": errors[0]},
        )

    if verify_password(new_password, user.hashed_password):
        return templates.TemplateResponse(
            "forgot_password.html",
            {"request": request, "error": "New password cannot be same as old password."},
        )

    user.hashed_password = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "success": "Password updated. Please log in.", "timezones": COMMON_TIMEZONES},
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
