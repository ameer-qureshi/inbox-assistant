from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import LoginIn, UserOut
from app.security import SESSION_COOKIE, authenticate, create_session, current_user, delete_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)) -> User:
    user = authenticate(db, body.email, body.password)
    if user is None:
        # Same message whether the email exists or not
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_session(db, user, settings)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
        max_age=settings.session_ttl_hours * 3600, path="/",
    )
    return user


@router.post("/logout", status_code=204, response_class=Response)
def logout(response: Response, session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
           db: Session = Depends(get_db)) -> None:
    if session:
        delete_session(db, session)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
