"""Every advertised tool has a handler, and PDF links are read, not clicked."""
from worker.runtime import TOOLS, Runtime


def test_every_tool_has_a_handler():
    missing = [name for name in TOOLS if not hasattr(Runtime, f"t_{name}")]
    assert not missing, missing


def test_pdf_link_pattern():
    assert Runtime.PDF_LINK.search("/portal/invoices/3/pdf")
    assert Runtime.PDF_LINK.search("/files/invoice.pdf?x=1")
    assert not Runtime.PDF_LINK.search("/ledger/bills/new")


class FakeBrowser:
    """Enough of a browser for the knowledge tools: a PDF and a page, no Chromium."""
    actions = 0

    def __init__(self):
        self.pdf_reads = 0
        self.login = False
        self.url = "http://127.0.0.1:8000/portal/invoices"

    def fetch_pdf_text(self, url):
        self.pdf_reads += 1
        return "Northwind Supplies\nInvoice NW-1043-R\nTotal INR 59,800.00"

    def observe(self):
        from worker.types import Observation
        return Observation(url=self.url, title="t", text="", is_login_page=self.login)


def make_runtime():
    from worker.context import CompanyContext
    from worker.policy import PolicyGate, load_policy
    from worker.types import RunRecord
    return Runtime(RunRecord(run_id="t", request="r"), CompanyContext(), FakeBrowser(), PolicyGate(load_policy()))


def test_pdf_is_downloaded_once_and_kept_as_an_open_document():
    rt = make_runtime()
    first = rt.t_read_pdf(3, url="/portal/invoices/3/pdf")
    again = rt.t_read_pdf(5, url="/portal/invoices/3/pdf")
    assert "PDF text" in first.text and rt.browser.pdf_reads == 1
    assert "already read this PDF at step 3" in again.text and rt.browser.pdf_reads == 1
    assert list(rt.documents) == ["3/pdf"] and "59,800.00" in rt.documents["3/pdf"]


def test_note_fact_records_several_facts_in_one_step():
    rt = make_runtime()
    res = rt.t_note_fact(4, facts={"pdf_total:NW-1043-R": 5980000, "due_date:NW-1043-R": "2026-11-08"}, source="NW-1043-R.pdf")
    assert rt.run.fact("pdf_total:NW-1043-R") == "5980000" and rt.run.fact("due_date:NW-1043-R") == "2026-11-08"
    assert "pdf_total" in res.text and "due_date" in res.text
    assert "needs facts" in rt.t_note_fact(5).text


def test_sessions_follow_what_the_pages_show():
    rt = make_runtime()
    rt.observe()
    assert rt.sessions == {"portal"}
    rt.browser.url, rt.browser.login = "http://127.0.0.1:8000/ledger/login", True
    rt.observe()
    assert rt.sessions == {"portal"}          # ledger shows a sign-in form: not signed in there
    rt.browser.login = False
    rt.browser.url = "http://127.0.0.1:8000/ledger/bills"
    rt.observe()
    assert rt.sessions == {"portal", "ledger"}


def test_alternating_between_two_pages_gets_a_hint():
    from worker.loop import Worker
    from worker.types import Action, Observation, RunRecord, Step
    run = RunRecord(run_id="t", request="r")
    for i, eid in enumerate((2, 3, 2, 3), 1):
        run.steps.append(Step(index=i, url="u", action=Action(tool="click", args={"id": eid})))
    hints = Worker._detect(None, run, Observation(url="u"), "clicked")
    assert any("alternating" in h for h in hints)
    run.steps[-1] = Step(index=4, url="u", action=Action(tool="fill_form", args={"fields": {}}))
    assert not any("alternating" in h for h in Worker._detect(None, run, Observation(url="u"), "ok"))


def test_nav_links_are_marked_in_the_observation():
    from worker.types import Element
    assert Element(id=3, role="link", name="Vendors", href="/ledger/vendors", nav=True).line() == '[3] link "Vendors" (nav) -> /ledger/vendors'


def test_bare_invoice_fact_keys_get_the_invoice_or_are_refused():
    rt = make_runtime()
    res = rt.t_note_fact(4, facts={"pdf_total": "5980000", "duplicate_check": "none"}, source="pdf")
    assert "NOT recorded" in res.text and rt.run.fact("pdf_total:NW-1043-R") is None
    rt.t_note_fact(5, facts={"pdf_total": "5980000", "duplicate_check": "none"}, key="NW-1043-R", source="pdf")
    assert rt.run.fact("pdf_total:NW-1043-R") == "5980000" and rt.run.fact("duplicate_check:NW-1043-R") == "none"
    rt.t_note_fact(6, facts={"due_date": "2026-11-08"}, invoice="NW-1043-R")
    assert rt.run.fact("due_date:NW-1043-R") == "2026-11-08"


def test_empty_values_are_never_recorded():
    rt = make_runtime()
    res = rt.t_note_fact(4, key="duplicate_check:NW-1043-R", value="")
    assert "empty value" in res.text and rt.run.fact("duplicate_check:NW-1043-R") is None


def test_commit_accepts_a_flat_intent_and_still_applies_every_check():
    rt = make_runtime()
    seen = {}
    rt._cross_check_form = lambda intent: seen.update(intent) or "stop here"   # the form check is the first gate
    res = rt.t_commit(20, id=5, intent="record_payable", system="nova", invoice_number="NW-1043-R", amount_paise="5980000")
    assert "stop here" in res.text
    assert seen["type"] == "record_payable" and seen["invoice_number"] == "NW-1043-R" and seen["amount_paise"] == 5980000
    assert "unknown arguments" in rt.t_commit(21, id=5, intent="create_bill", colour="red").text
