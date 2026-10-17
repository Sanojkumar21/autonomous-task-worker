"""Fault injection for the simulated company.

Real company systems fail in boring, annoying ways. The worker has to survive
them without doing damage, so the sandbox can be told to misbehave:

- ``http_503``: a request fails with 503 before doing anything (safe to retry).
- ``commit_then_502``: a write succeeds in the database, but the response is a
  502. A naive retry creates a duplicate. The worker must read back first.
- ``session_expiry``: every Nth authenticated request is logged out.
- ``ui_drift``: labels and button texts are renamed ("Amount" -> "Invoice
  total"), so hard-coded selectors break while the meaning stays the same.
- ``slow``: responses are delayed.

Faults are deterministic for a given seed so evaluation runs are repeatable.
Configuration lives in var/chaos.json and is changed through /admin/api/chaos.
"""
import json
import os
import random
import threading
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("COMPANY_VAR") or Path(__file__).resolve().parent.parent / "var") / "chaos.json"
DEFAULT = {"enabled": False, "seed": 7, "http_503": 0.0, "commit_then_502": 0.0,
           "session_expiry_every": 0, "ui_drift": False, "slow_ms": 0}

_lock = threading.Lock()
_state = {"rng": None, "seed": None, "auth_requests": 0}


def load():
    try:
        cfg = {**DEFAULT, **json.loads(CONFIG_PATH.read_text())}
    except (OSError, ValueError):
        cfg = dict(DEFAULT)
    return cfg


def save(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = {**DEFAULT, **{k: v for k, v in cfg.items() if k in DEFAULT}}
    CONFIG_PATH.write_text(json.dumps(merged, indent=1))
    with _lock:
        _state["rng"], _state["seed"], _state["auth_requests"] = None, None, 0
    return merged


def _rng(cfg):
    with _lock:
        if _state["rng"] is None or _state["seed"] != cfg["seed"]:
            _state["rng"], _state["seed"] = random.Random(cfg["seed"]), cfg["seed"]
        return _state["rng"]


def roll(kind):
    """True if fault ``kind`` should fire on this request."""
    cfg = load()
    if not cfg["enabled"]:
        return False
    p = float(cfg.get(kind, 0.0) or 0.0)
    return p > 0 and _rng(cfg).random() < p


def session_should_expire():
    cfg = load()
    every = int(cfg.get("session_expiry_every") or 0)
    if not cfg["enabled"] or every <= 0:
        return False
    with _lock:
        _state["auth_requests"] += 1
        return _state["auth_requests"] % every == 0


def drift():
    cfg = load()
    return bool(cfg["enabled"] and cfg.get("ui_drift"))


def slow_ms():
    cfg = load()
    return int(cfg.get("slow_ms") or 0) if cfg["enabled"] else 0


# Label variants used when ui_drift is on. Templates call label(key).
LABELS = {
    "vendor": ("Vendor", "Supplier"),
    "invoice_number": ("Invoice number", "Supplier invoice #"),
    "amount": ("Amount (INR)", "Invoice total (INR)"),
    "due_date": ("Due date", "Payment due"),
    "po_number": ("PO number", "Purchase order"),
    "save_bill": ("Save bill", "Record invoice"),
    "new_bill": ("New bill", "Add invoice"),
    "bills": ("Bills", "Payables"),
}


def label(key):
    a, b = LABELS[key]
    return b if drift() else a
