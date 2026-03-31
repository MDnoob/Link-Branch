import re

import bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import User

router = APIRouter()
templates = Jinja2Templates(directory="templates")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,50}$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def normalize_phone(phone: str) -> str | None:
    raw = (phone or "").strip()
    if not raw:
        return None
    # Keep only digits and optional leading plus for stable matching.
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


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_username = (username or "").strip().lower()
    user = db.query(User).filter(User.username == normalized_username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
        )
    request.session["username"] = user.username
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "show_register": True})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_username = (username or "").strip().lower()
    normalized_email = (email or "").strip().lower()
    normalized_phone = normalize_phone(phone)

    if not USERNAME_RE.match(normalized_username):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "show_register": True,
                "error": "Username must be 3-50 chars and use lowercase letters, numbers, _ or . only.",
            },
        )
    if db.query(User).filter(User.username == normalized_username).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Username already taken"},
        )
    if db.query(User).filter(User.email == normalized_email).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Email already registered"},
        )
    if normalized_phone and db.query(User).filter(User.phone == normalized_phone).first():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": "Phone number already registered"},
        )

    errors = password_policy_errors(password)
    if errors:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "show_register": True, "error": errors[0]},
        )

    new_user = User(
        username=normalized_username,
        email=normalized_email,
        phone=normalized_phone,
        hashed_password=hash_password(password),
        display_name=normalized_username,
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
    normalized_username = (username or "").strip().lower()
    normalized_email = (email or "").strip().lower()
    normalized_phone = normalize_phone(phone)

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
        {"request": request, "success": "Password updated. Please log in."},
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
