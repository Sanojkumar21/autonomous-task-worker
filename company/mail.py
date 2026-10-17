"""The team mailbox. Suppliers and colleagues write here."""
from fastapi import Request
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

from company import auth, db

SYSTEM = "mail"


def register(app, templates):
    @app.get("/mail/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/mail/inbox", reason: str = ""):
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Acme Mail", "next": next, "reason": reason, "error": ""})

    @app.post("/mail/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/mail/inbox")):
        if auth.check_password(SYSTEM, username, password):
            return auth.login(RedirectResponse(next or "/mail/inbox", status_code=303), SYSTEM, username)
        return templates.TemplateResponse(request, "login.html", {
            "request": request, "system": SYSTEM, "title": "Acme Mail", "next": next, "reason": "",
            "error": "Invalid username or password."}, status_code=401)

    @app.get("/mail", response_class=HTMLResponse)
    @app.get("/mail/", response_class=HTMLResponse)
    def index(request: Request):
        return RedirectResponse("/mail/inbox", status_code=303)

    @app.get("/mail/inbox", response_class=HTMLResponse)
    def inbox(request: Request, q: str = ""):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            sql = "SELECT * FROM mail WHERE folder = 'inbox'"
            args = []
            if q:
                sql += " AND (subject LIKE ? OR sender LIKE ? OR body LIKE ?)"
                args += [f"%{q}%"] * 3
            sql += " ORDER BY received_at DESC"
            items = db.rows(con, sql, *args)
        return templates.TemplateResponse(request, "mail_inbox.html", {"request": request, "user": user, "items": items, "q": q})

    @app.get("/mail/{mid}", response_class=HTMLResponse)
    def message(request: Request, mid: int):
        user, redirect = auth.require(request, SYSTEM)
        if redirect:
            return redirect
        with db.tx() as con:
            item = db.one(con, "SELECT * FROM mail WHERE id = ?", mid)
            if not item:
                return HTMLResponse("<h1>404 Not found</h1>", status_code=404)
            con.execute("UPDATE mail SET read = 1 WHERE id = ?", (mid,))
            db.audit(con, SYSTEM, user, "read_mail", subject=item["subject"])
        return templates.TemplateResponse(request, "mail_message.html", {"request": request, "user": user, "m": item})
