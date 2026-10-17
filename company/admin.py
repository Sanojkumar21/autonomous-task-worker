"""Admin API: the verifier's channel.

The worker acts through the browser. The verifier and the evaluation harness
read the truth here, so a claim of success can be checked against what the
systems of record actually contain. The worker never calls these endpoints
(the policy gate forbids it, and the sandbox logs every call).
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from company import chaos, db


def register(app, templates):
    @app.get("/admin/api/snapshot")
    def snapshot():
        return JSONResponse(db.snapshot())

    @app.get("/admin/api/audit")
    def audit(since: float = 0.0):
        with db.tx() as con:
            items = db.rows(con, "SELECT * FROM audit WHERE ts > ? ORDER BY id", since)
        return JSONResponse(items)

    @app.get("/admin/api/chaos")
    def get_chaos():
        return JSONResponse(chaos.load())

    @app.post("/admin/api/chaos")
    async def set_chaos(request: Request):
        cfg = await request.json()
        with db.tx() as con:
            db.audit(con, "admin", "admin", "chaos_config", **{k: v for k, v in cfg.items() if k in chaos.DEFAULT})
        return JSONResponse(chaos.save(cfg))

    @app.post("/admin/api/reset")
    def reset():
        from company.seed import seed
        seed(quiet=True)
        chaos.save(dict(chaos.DEFAULT))
        return JSONResponse({"ok": True})

    @app.get("/admin/api/health")
    def health():
        return JSONResponse({"ok": True})
