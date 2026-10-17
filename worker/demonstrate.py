"""Learn from a demonstration: watch a person do the task once, keep it as a skill.

    python -m worker demonstrate --intent record_supplier_invoice --system ledger --name "Record a bill in Ledger"

A headed browser opens on the company's home page. Everything the person
does (navigation, clicks, typing, selections) is recorded as semantic events:
the page, the element's role and accessible name, and the value typed
(passwords are masked). Press Enter in the terminal when done. The recording
is turned into a Skill: an app-agnostic workflow plus a concrete procedure
with {placeholders}, saved to memory with the demonstrator as its source.

The recorder is the same mechanism the worker uses to see pages, so a human
demonstration and a worker run are described in the same vocabulary.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from worker.context import CompanyContext
from worker.memory.store import MemoryStore, Skill

RECORDER_JS = r"""
(() => {
  if (window.__wkRecorderInstalled) return; window.__wkRecorderInstalled = true;
  const nameOf = (el) => {
    const aria = el.getAttribute && el.getAttribute('aria-label'); if (aria) return aria.trim();
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const pl = el.closest && el.closest('label'); if (pl) return pl.innerText.trim();
    return ((el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim()).slice(0, 80);
  };
  const roleOf = (el) => {
    const tag = el.tagName.toLowerCase(); const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link'; if (tag === 'button' || type === 'submit') return 'button';
    if (tag === 'select') return 'select'; if (tag === 'textarea') return 'textarea';
    if (tag === 'input') return type === 'checkbox' ? 'checkbox' : type === 'radio' ? 'radio' : type === 'password' ? 'password' : 'textbox';
    return tag;
  };
  const send = (ev) => window.__wkRecord(JSON.stringify({ ...ev, url: location.pathname + location.search, title: document.title, t: Date.now() }));
  document.addEventListener('click', (e) => {
    const el = e.target.closest('a, button, input[type=submit], input[type=radio], input[type=checkbox]');
    if (!el) return;
    send({ type: 'click', role: roleOf(el), name: nameOf(el), href: el.getAttribute('href') || '' });
  }, true);
  document.addEventListener('change', (e) => {
    const el = e.target; if (!el || !el.tagName) return;
    const role = roleOf(el);
    if (['textbox', 'textarea', 'select', 'password'].includes(role)) {
      const value = role === 'password' ? '••••' : (role === 'select' ? el.options[el.selectedIndex].text : el.value);
      send({ type: 'input', role, name: nameOf(el), value: String(value).slice(0, 120) });
    }
  }, true);
  const announce = () => send({ type: 'page', role: 'document', name: document.title });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', announce); else announce();
})();
"""


def placeholderize(events: list[dict]) -> tuple[list[str], dict]:
    """Turn typed values into {placeholders} so the procedure generalises."""
    params = {}
    steps = []
    for ev in events:
        if ev["type"] == "page":
            if ev["url"] in ("blank", "/blank") or "about:blank" in ev["url"]:
                continue
            steps.append(f"open {ev['url']}" + (f" ({ev['name']})" if ev.get("name") else ""))
        elif ev["type"] == "click":
            steps.append(f"click {ev['role']} \"{ev['name']}\" on {ev['url']}")
        elif ev["type"] == "input":
            value = ev["value"]
            if ev["role"] == "password":
                steps.append(f"enter the password into \"{ev['name']}\"")
                continue
            key = re.sub(r"[^a-z0-9]+", "_", ev["name"].lower()).strip("_")[:30] or "value"
            if re.fullmatch(r"PO-\d+", value):
                key = "po_number"
            elif re.fullmatch(r"[A-Z]{2}-\d{4}(?:-R)?", value):
                key = "invoice_number"
            elif re.fullmatch(r"[\d,]+(?:\.\d{2})?", value):
                key = "amount"
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value):
                key = "due_date"
            params[key] = value
            steps.append(f"enter {{{key}}} into \"{ev['name']}\" ({ev['role']}) on {ev['url']}")
    # collapse consecutive identical page opens
    out = []
    for s in steps:
        if not out or out[-1] != s:
            out.append(s)
    return out, params


def workflow_from(events: list[dict], context: CompanyContext) -> list[str]:
    seen, out = set(), []
    for ev in events:
        system = context.system_for_url(context.base_url + ev["url"])
        if system and system not in seen:
            seen.add(system)
            purpose = context.systems[system]["purpose"]
            out.append(f"Use {context.systems[system]['name']}: {purpose}")
    return out


def record(context: CompanyContext, intent: str, system: str, name: str, memory: MemoryStore, brain=None) -> Skill:
    events: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1200, "height": 850})
        ctx.expose_binding("__wkRecord", lambda source, payload: events.append(json.loads(payload)))
        ctx.add_init_script(RECORDER_JS)
        page = ctx.new_page()
        page.goto(context.base_url + "/")
        print("Recording. Do the task in the browser, then press Enter here to stop.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        browser.close()
    return skill_from_events(events, context, intent, system, name, memory, brain)


def skill_from_events(events, context, intent, system, name, memory, brain=None, who="demonstrator") -> Skill:
    procedure, params = placeholderize(events)
    skill = Skill(name=name, intent=intent, system=system, trigger=f"A request to {intent.replace('_', ' ')} in {system}.",
                  workflow=workflow_from(events, context) + ["Verify the record exists before reporting."],
                  procedure=procedure, pitfalls=[], verification=["The list page shows the new record with the entered values."],
                  params=list(params), source_run=f"demonstration by {who} at {time.strftime('%Y-%m-%d %H:%M')}")
    if brain is not None and hasattr(brain, "refine_demonstration"):
        skill = brain.refine_demonstration(skill, events, context) or skill
    memory.add_skill(skill)
    return skill
