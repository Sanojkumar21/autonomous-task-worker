"""The simulated company: Acme Robotics Pvt Ltd.

Four web systems a clerk uses every day, plus an admin API that only the
verifier and the evaluation harness call:

    /portal   supplier invoice portal (invoices + PDFs)
    /ledger   the Ledger ERP where supplier bills are recorded
    /nova     NovaBooks, a second ERP with different words and flow (the "unseen" app)
    /mail     the team mailbox
    /admin    read-only snapshot, audit diff, chaos controls, reset

Run: uvicorn company.app:app --port 8000
"""
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from company import admin, chaos, db, ledger, mail, nova, portal

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.globals["label"] = chaos.label
templates.env.globals["rupees"] = lambda p: f"{p / 100:,.2f}"

app = FastAPI(title="Acme Robotics sandbox", docs_url=None, redoc_url=None)


@app.middleware("http")
async def chaos_middleware(request: Request, call_next):
    """Slow responses and pre-request 503s. Commit-then-502 lives in the handlers."""
    if not request.url.path.startswith("/admin"):
        delay = chaos.slow_ms()
        if delay:
            await asyncio.sleep(delay / 1000)
        if request.method == "POST" and chaos.roll("http_503"):
            with db.tx() as con:
                db.audit(con, "chaos", "chaos", "http_503", path=request.url.path)
            return HTMLResponse("<h1>503 Service Unavailable</h1><p>The service is temporarily unavailable. "
                                "Please try again.</p>", status_code=503)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"request": request})


for module in (portal, ledger, nova, mail, admin):
    module.register(app, templates)


@app.on_event("startup")
def _ensure_db():
    if not db.DB_PATH.exists():
        from company.seed import seed
        seed(quiet=True)
