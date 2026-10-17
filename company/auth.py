"""Per-system login with signed session cookies.

Each system (portal, ledger, nova, mail) has its own login page and cookie,
like separate SaaS products. Chaos can expire sessions mid-task; the worker
must notice the login page and sign in again.
"""
from itsdangerous import BadSignature, URLSafeSerializer
from fastapi import Request
from fastapi.responses import RedirectResponse

from company import chaos, db

SECRET = "acme-sandbox-not-a-secret"
_signer = URLSafeSerializer(SECRET, salt="session")


def cookie_name(system):
    return f"{system}_session"


def current_user(request: Request, system):
    raw = request.cookies.get(cookie_name(system))
    if not raw:
        return None
    try:
        data = _signer.loads(raw)
    except BadSignature:
        return None
    if data.get("system") != system:
        return None
    if chaos.session_should_expire():
        return None
    return data.get("user")


def login(response, system, username):
    response.set_cookie(cookie_name(system), _signer.dumps({"system": system, "user": username}),
                        httponly=True, samesite="lax")
    return response


def logout(response, system):
    response.delete_cookie(cookie_name(system))
    return response


def check_password(system, username, password):
    with db.tx() as con:
        row = db.one(con, "SELECT password, role FROM users WHERE username = ? AND system = ?", username, system)
    if row and row["password"] == password:
        return row["role"]
    return None


def require(request: Request, system):
    """Return the username, or a redirect to the login page (with `next`)."""
    user = current_user(request, system)
    if user:
        return user, None
    nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    from urllib.parse import quote
    return None, RedirectResponse(f"/{system}/login?next={quote(nxt, safe='/')}&reason=signed_out", status_code=303)
