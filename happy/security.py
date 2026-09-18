"""Single-user password gate and request safeguards; not multi-user identity."""

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()
sessions = {}
attempts = defaultdict(deque)
COOKIE = "happy_session"


def enabled():
    return bool(os.getenv("HAPPY_PASSWORD"))


def authenticated(request):
    if not enabled():
        return True
    token = request.cookies.get(COOKIE, "")
    entry = sessions.get(hashlib.sha256(token.encode()).hexdigest())
    fingerprint = hashlib.sha256(os.environ["HAPPY_PASSWORD"].encode()).digest()
    return bool(
        entry and entry[0] > time.time() and hmac.compare_digest(entry[1], fingerprint)
    )


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


@router.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(Path(__file__).parent / "static" / "login.html")


@router.get("/auth/status")
def auth_status(request: Request):
    return {"protected": enabled(), "authenticated": authenticated(request)}


@router.post("/auth/login")
async def login(data: Login, request: Request):
    now = time.time()
    # Rate limit by direct peer, never a client-supplied forwarding header.
    peer = request.client.host if request.client else "unknown"
    for key in list(attempts):
        if not attempts[key] or attempts[key][-1] < now - 60:
            del attempts[key]
    if peer not in attempts and len(attempts) >= 1024:
        raise HTTPException(429, "Too many login attempts. Try again later.")
    queue = attempts[peer]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= 10:
        raise HTTPException(429, "Too many login attempts. Try again in a minute.")
    queue.append(now)
    expected = os.getenv("HAPPY_PASSWORD", "")
    if not expected or not hmac.compare_digest(
        data.password.encode(), expected.encode()
    ):
        raise HTTPException(
            401, "Incorrect password or password protection is not configured."
        )
    for key in list(sessions):
        if sessions[key][0] < now:
            del sessions[key]
    if len(sessions) >= 100:
        sessions.pop(next(iter(sessions)))
    token = secrets.token_urlsafe(32)
    sessions[hashlib.sha256(token.encode()).hexdigest()] = (
        now + 28800,
        hashlib.sha256(expected.encode()).digest(),
    )
    response = JSONResponse({"ok": True})
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=28800,
    )
    return response


@router.post("/auth/logout")
async def logout(request: Request):
    token = request.cookies.get(COOKIE, "")
    sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


class GuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = request.url.path

        async def protected_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'",
                        ),
                    ]
                )
            await send(message)

        async def reject(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(
                scope, receive, protected_send
            )

        mutation = request.method not in ("GET", "HEAD", "OPTIONS")
        if mutation:
            origin = request.headers.get("origin")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return await reject(403, "Cross-origin changes are not allowed.")
        public = path in (
            "/login",
            "/auth/login",
            "/auth/status",
            "/healthz",
            "/style.css",
            "/login.js",
        )
        if not public and not authenticated(request):
            if path.startswith(("/api/", "/auth/")):
                return await reject(401, "Sign in to your Happy workspace.")
            from fastapi.responses import RedirectResponse

            return await RedirectResponse("/login", status_code=303)(
                scope, receive, protected_send
            )
        # Cap actual streamed bytes, not just a client-supplied Content-Length.
        if mutation:
            limit = 32 * 1024 * 1024 if path == "/api/knowledge/import" else 128 * 1024
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return await reject(413, "Request exceeds the upload limit.")
                if not message.get("more_body", False):
                    break
            sent = False

            async def buffered_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            await self.app(scope, buffered_receive, protected_send)
        else:
            await self.app(scope, receive, protected_send)
