"""Independent verification: did the work actually happen?

The brain's "done" is a claim. The verifier checks the claim against the
systems of record through the admin API, a channel the worker cannot use,
and it also looks at the audit log for changes nobody declared. Only the
verifier sets a run's final status. No model is involved.
"""
from __future__ import annotations

import httpx

from worker.types import Assertion, RunRecord, Verification

WRITE_ACTIONS = {"create_bill", "post_bill", "record_payable"}


class Verifier:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def snapshot(self) -> dict:
        return httpx.get(f"{self.base}/admin/api/snapshot", timeout=30).json()

    def audit(self, since: float) -> list[dict]:
        return httpx.get(f"{self.base}/admin/api/audit", params={"since": since}, timeout=30).json()

    # ---- rows the assertions can talk about
    @staticmethod
    def entity_rows(snap: dict, system: str, entity: str) -> list[dict]:
        if system == "ledger" and entity == "bill":
            vendors = {v["id"]: v for v in snap["ledger_vendors"]}
            return [{**b, "vendor_name": vendors[b["vendor_id"]]["name"], "vendor_gstin": vendors[b["vendor_id"]]["gstin"]}
                    for b in snap["ledger_bills"]]
        if system == "nova" and entity in ("payable", "bill"):
            sup = {s["id"]: s for s in snap["nova_suppliers"]}
            return [{**p, "vendor_name": sup[p["supplier_id"]]["name"], "vendor_gstin": sup[p["supplier_id"]]["tax_id"],
                     "invoice_number": p["reference"], "amount_paise": p["total_paise"], "due_date": p["pay_by"],
                     "po_number": p["order_ref"], "status": p["state"], "approved_by": p["authorised_by"]}
                    for p in snap["nova_payables"]]
        if system == "mail":
            return snap["mail"]
        if system == "portal":
            return snap["portal_invoices"]
        return []

    @staticmethod
    def _eq(a, b) -> bool:
        if a is None or b is None:
            return a == b
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            try:
                return int(a) == int(b)
            except (TypeError, ValueError):
                return str(a) == str(b)
        return str(a).strip().lower() == str(b).strip().lower()

    def _matches(self, row: dict, match: dict) -> bool:
        return all(self._eq(row.get(k), v) for k, v in match.items())

    def check_assertion(self, snap: dict, a: Assertion) -> dict:
        rows = [r for r in self.entity_rows(snap, a.system, a.entity) if self._matches(r, a.match)]
        result = {"assertion": a.model_dump(), "matched_rows": len(rows), "ok": False, "detail": ""}
        if a.kind == "absent":
            result["ok"] = len(rows) == 0
            result["detail"] = "no such row" if result["ok"] else f"found {len(rows)} row(s) that should not exist"
        elif a.kind == "count":
            want = int(a.expect.get("count", 0))
            result["ok"] = len(rows) == want
            result["detail"] = f"expected {want}, found {len(rows)}"
        else:  # exists
            if not rows:
                result["detail"] = "no row matches"
            else:
                diffs = []
                for row in rows:
                    bad = {k: (row.get(k), v) for k, v in a.expect.items() if not self._eq(row.get(k), v)}
                    if not bad:
                        result["ok"] = True
                        result["row_id"] = row.get("id")
                        result["detail"] = "row exists with the expected values"
                        break
                    diffs.append(bad)
                if not result["ok"]:
                    result["detail"] = f"row found but values differ: {diffs[0]}"
        return result

    def verify(self, run: RunRecord) -> Verification:
        try:
            snap = self.snapshot()
            audit = self.audit(run.started_at)
        except (httpx.HTTPError, ValueError) as e:
            return Verification(status="unverified", summary=f"could not reach the admin API: {e}")
        checks = [self.check_assertion(snap, a) for a in run.assertions]
        declared = set()
        for a in run.assertions:
            if a.kind == "exists":
                declared.add(str(a.match.get("invoice_number") or a.match.get("reference") or "").lower())
        writes = [e for e in audit if e["action"] in WRITE_ACTIONS]
        unexplained = []
        for e in writes:
            try:
                detail = __import__("json").loads(e["detail"])
            except ValueError:
                detail = {}
            key = str(detail.get("invoice_number") or detail.get("reference") or "").lower()
            if e["action"] == "post_bill":
                continue  # posting a declared bill is part of creating it
            if key not in declared:
                unexplained.append({"action": e["action"], **detail})
        all_ok = bool(checks) and all(c["ok"] for c in checks)
        if not run.assertions:
            status = "unverified"
            summary = "the worker declared no assertions"
        elif all_ok and not unexplained:
            status = "completed"
            summary = f"all {len(checks)} assertion(s) hold; no undeclared writes"
        elif all_ok:
            status = "completed_with_exceptions"
            summary = f"assertions hold but {len(unexplained)} undeclared write(s) happened"
        else:
            failed = [c["detail"] for c in checks if not c["ok"]]
            status = "failed"
            summary = "; ".join(failed)
        return Verification(status=status, checks=checks, unexplained_changes=unexplained, summary=summary)
