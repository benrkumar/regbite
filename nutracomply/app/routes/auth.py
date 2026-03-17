from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from jose import JWTError, jwt
import bcrypt

from app.database import get_db
from app.models import User
from app.config import get_settings

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def get_current_user_from_cookie(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if not email:
            return None
        return db.query(User).filter(User.email == email).first()
    except JWTError:
        return None


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })

    token = create_access_token({"sub": user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    return response


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An account with this email already exists"
        })

    user = User(name=name, email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()

    token = create_access_token({"sub": user.email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    return response
