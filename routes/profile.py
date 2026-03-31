import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, User
from routes.auth import (
    get_current_user,
    hash_password,
    normalize_phone,
    password_policy_errors,
    verify_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"


@router.get("/my-profile", response_class=HTMLResponse)
def my_profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        "my_profile.html",
        {"request": request, "user": user, "active_page": "my_profile"},
    )


@router.post("/my-profile")
def update_my_profile(
    request: Request,
    display_name: str = Form(""),
    email: str = Form(...),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    normalized_email = (email or "").strip().lower()
    normalized_phone = normalize_phone(phone)

    email_owner = db.query(User).filter(User.email == normalized_email, User.id != user.id).first()
    if email_owner:
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "error": "This email is already used by another account.",
            },
        )

    if normalized_phone:
        phone_owner = (
            db.query(User)
            .filter(User.phone == normalized_phone, User.id != user.id)
            .first()
        )
        if phone_owner:
            return templates.TemplateResponse(
                "my_profile.html",
                {
                    "request": request,
                    "user": user,
                    "active_page": "my_profile",
                    "error": "This phone number is already used by another account.",
                },
            )

    user.display_name = (display_name or "").strip()[:100] or None
    user.email = normalized_email
    user.phone = normalized_phone
    db.commit()
    return RedirectResponse(url="/my-profile?saved=1", status_code=302)


@router.post("/my-profile/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not verify_password(current_password, user.hashed_password):
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "password_error": "Current password is incorrect.",
            },
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "password_error": "Passwords do not match.",
            },
        )

    errors = password_policy_errors(new_password)
    if errors:
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "password_error": errors[0],
            },
        )

    if verify_password(new_password, user.hashed_password):
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "password_error": "New password cannot be same as old password.",
            },
        )

    user.hashed_password = hash_password(new_password)
    db.commit()
    return RedirectResponse(url="/my-profile?password_updated=1", status_code=302)


@router.post("/my-profile/delete")
def delete_account(
    request: Request,
    password: str = Form(...),
    confirm_text: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if confirm_text.strip().lower() != "delete":
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "delete_error": 'Type "delete" to confirm.',
            },
        )
    if not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "my_profile.html",
            {
                "request": request,
                "user": user,
                "active_page": "my_profile",
                "delete_error": "Password is incorrect.",
            },
        )

    assets = db.query(Asset).filter(Asset.user_id == user.id).all()
    for asset in assets:
        if asset.filename:
            disk_path = os.path.join(UPLOAD_DIR, asset.filename)
            if os.path.exists(disk_path):
                try:
                    os.remove(disk_path)
                except OSError:
                    pass

    db.delete(user)
    db.commit()
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
