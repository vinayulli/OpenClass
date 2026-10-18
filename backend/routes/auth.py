import hashlib
import os
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from ..schemas import Login
from ..store import all_of, check_password, db
from ..services import user, public_user, rate_limit

router = APIRouter()

@router.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    rate_limit("login:" + (request.client.host if request.client else "local"), 10)
    with db() as conn:
        account = next((u for u in all_of(conn, "user") if u["email"] == body.email.strip().lower()), None)
        if not account or not check_password(body.password, account["password"]):
            raise HTTPException(401, "Email or password is incorrect")
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires<%s", (time.time(),))
        conn.execute("INSERT INTO sessions VALUES(%s,%s,%s)", (hashlib.sha256(token.encode()).hexdigest(), account["id"], time.time()+28800))
    response.set_cookie("openclass_session", token, httponly=True, samesite="strict", secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", max_age=28800)
    return public_user(account)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token=%s", (hashlib.sha256(request.cookies.get("openclass_session", "").encode()).hexdigest(),))
    response.delete_cookie("openclass_session")
    return {"ok": True}


@router.get("/api/auth/me")
def me(current=Depends(user)):
    return public_user(current)


