"""The worker's hands and eyes: a real Chromium browser via Playwright.

Observation is a compact, text-only view of the page built from the DOM:
headings, paragraphs and table rows, plus every interactive element with a
stable numeric id. The worker acts on those ids, so it never needs CSS
selectors and survives label changes (chaos `ui_drift`), because it reads the
accessible name each step instead of hard-coding it.

A screenshot is taken after every action for the evidence report, and can be
handed to a vision-capable model when the text view is not enough.
"""
from __future__ import annotations

import io
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, sync_playwright
from pypdf import PdfReader

from worker.types import Element, Observation

OBSERVE_JS = r"""
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria) return aria.trim();
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const parentLabel = el.closest('label'); if (parentLabel) return parentLabel.innerText.trim();
    const t = (el.innerText || el.value || el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('title') || '').trim();
    return t.replace(/\s+/g, ' ').slice(0, 120);
  };
  const roleOf = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || type === 'submit' || type === 'button') return 'button';
    if (tag === 'select') return 'select';
    if (tag === 'textarea') return 'textarea';
    if (tag === 'input') return type === 'checkbox' ? 'checkbox' : type === 'radio' ? 'radio' : type === 'password' ? 'password' : 'textbox';
    return el.getAttribute('role') || tag;
  };
  const els = Array.from(document.querySelectorAll('a[href], button, input, select, textarea, [role=button], [role=link]'))
    .filter(visible).filter(el => !(el.tagName === 'INPUT' && el.type === 'hidden'));
  let n = 0; const out = [];
  for (const el of els) {
    n += 1; el.setAttribute('data-wk', String(n));
    const role = roleOf(el);
    const item = { id: n, role, name: nameOf(el), value: '', href: '', options: [], checked: null, disabled: !!el.disabled };
    if (role === 'textbox' || role === 'textarea' || role === 'password') item.value = (el.value || '').slice(0, 200);
    if (role === 'select') { item.value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.trim() : ''; item.options = Array.from(el.options).map(o => o.text.trim()); }
    if (role === 'checkbox' || role === 'radio') item.checked = !!el.checked;
    if (role === 'link') { const h = el.getAttribute('href') || ''; item.href = h.startsWith('http') ? new URL(h).pathname + new URL(h).search : h; }
    out.push(item);
  }
  // page text: headings, paragraphs, definition lists, table rows, alerts
  const textParts = [];
  const seen = new Set();
  const push = (s) => { s = s.replace(/\s+/g, ' ').trim(); if (s && !seen.has(s)) { seen.add(s); textParts.push(s); } };
  document.querySelectorAll('h1, h2, h3, p, li, dt, dd, legend, pre, .muted').forEach(el => {
    if (!visible(el)) return;
    const tag = el.tagName.toLowerCase();
    const t = el.innerText || '';
    if (tag.startsWith('h')) push('# ' + t); else if (tag === 'dt') push(t + ':'); else push(t);
  });
  document.querySelectorAll('table').forEach(tbl => {
    if (!visible(tbl)) return;
    tbl.querySelectorAll('tr').forEach(tr => {
      const cells = Array.from(tr.querySelectorAll('th, td')).map(c => c.innerText.replace(/\s+/g, ' ').trim());
      if (cells.length) push('| ' + cells.join(' | ') + ' |');
    });
  });
  const alerts = Array.from(document.querySelectorAll('[role=alert], [role=status], .flash, .warn, .error')).filter(visible).map(e => e.innerText.replace(/\s+/g, ' ').trim());
  const isLogin = !!document.querySelector('input[type=password]');
  return { url: location.href, title: document.title, text: textParts.join('\n'), alerts, elements: out, isLogin };
}
"""


class Browser:
    def __init__(self, headless: bool = True, screenshots_dir: Path | None = None, slow_mo: int = 0):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        self._ctx = self._browser.new_context(viewport={"width": 1200, "height": 850}, accept_downloads=True)
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(8000)
        self.screenshots_dir = screenshots_dir
        self.last_status: int | None = None
        self.actions = 0
        self.page.on("response", self._on_response)

    def _on_response(self, response):
        try:
            if response.request.is_navigation_request() and response.request.resource_type == "document":
                self.last_status = response.status
        except PlaywrightError:
            pass

    def close(self):
        for fn in (self._ctx.close, self._browser.close, self._pw.stop):
            try:
                fn()
            except Exception:
                pass

    # ---- observing
    def observe(self) -> Observation:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except PlaywrightTimeout:
            pass
        try:
            data = self.page.evaluate(OBSERVE_JS)
        except PlaywrightError as e:
            return Observation(url=self.page.url, title="", text=f"(could not read page: {e})")
        http_error = self.last_status if self.last_status and self.last_status >= 400 else None
        return Observation(url=data["url"], title=data["title"], text=data["text"], alerts=data["alerts"],
                           elements=[Element(**e) for e in data["elements"]], is_login_page=data["isLogin"],
                           http_error=http_error)

    def screenshot(self, name: str) -> str:
        if not self.screenshots_dir:
            return ""
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshots_dir / f"{name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
        except PlaywrightError:
            return ""
        return str(path)

    def screenshot_bytes(self) -> bytes:
        return self.page.screenshot(full_page=False)

    # ---- acting
    def _loc(self, element_id: int):
        return self.page.locator(f'[data-wk="{element_id}"]')

    def navigate(self, url: str) -> str:
        self.actions += 1
        self.last_status = None
        try:
            resp = self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            return f"timeout loading {url}"
        except PlaywrightError as e:
            return f"navigation failed: {e}"
        if resp is not None:
            self.last_status = resp.status
        return f"opened {self.page.url} (HTTP {self.last_status})"

    def click(self, element_id: int) -> str:
        self.actions += 1
        loc = self._loc(element_id)
        if loc.count() == 0:
            return f"no element with id {element_id} (observe again; ids change after each action)"
        desc = loc.first.evaluate("el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0,60)")
        self.last_status = None
        try:
            with self.page.expect_navigation(wait_until="domcontentloaded", timeout=4000):
                loc.first.click()
        except PlaywrightTimeout:
            pass  # no navigation happened; that is fine for in-page clicks
        except PlaywrightError as e:
            return f"click failed: {e}"
        return f'clicked "{desc}"'

    def type(self, element_id: int, text: str) -> str:
        self.actions += 1
        loc = self._loc(element_id)
        if loc.count() == 0:
            return f"no element with id {element_id}"
        try:
            loc.first.fill(str(text))
        except PlaywrightError as e:
            return f"type failed: {e}"
        return f'typed "{text}"'

    def select(self, element_id: int, option: str) -> str:
        self.actions += 1
        loc = self._loc(element_id)
        if loc.count() == 0:
            return f"no element with id {element_id}"
        try:
            loc.first.select_option(label=str(option))
        except PlaywrightError:
            try:
                loc.first.select_option(value=str(option))
            except PlaywrightError as e:
                return f"select failed: no option '{option}' ({e})"
        return f'selected "{option}"'

    def check(self, element_id: int) -> str:
        self.actions += 1
        loc = self._loc(element_id)
        if loc.count() == 0:
            return f"no element with id {element_id}"
        try:
            loc.first.check()
        except PlaywrightError as e:
            return f"check failed: {e}"
        return "checked"

    def go_back(self) -> str:
        self.actions += 1
        try:
            self.page.go_back(wait_until="domcontentloaded")
        except PlaywrightError as e:
            return f"back failed: {e}"
        return f"went back to {self.page.url}"

    def fetch_pdf_text(self, url: str) -> str:
        """Download a PDF with the page's session and return its text."""
        self.actions += 1
        try:
            resp = self.page.request.get(url)
        except PlaywrightError as e:
            return f"download failed: {e}"
        if resp.status != 200:
            return f"download failed: HTTP {resp.status}"
        if "pdf" not in resp.headers.get("content-type", ""):
            return "download failed: not a PDF (are you signed in?)"
        try:
            reader = PdfReader(io.BytesIO(resp.body()))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:  # pypdf raises many types
            return f"could not read PDF: {e}"
        return text.strip()
