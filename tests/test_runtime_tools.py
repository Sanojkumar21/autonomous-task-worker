"""Every advertised tool has a handler, and PDF links are read, not clicked."""
from worker.runtime import TOOLS, Runtime


def test_every_tool_has_a_handler():
    missing = [name for name in TOOLS if not hasattr(Runtime, f"t_{name}")]
    assert not missing, missing


def test_pdf_link_pattern():
    assert Runtime.PDF_LINK.search("/portal/invoices/3/pdf")
    assert Runtime.PDF_LINK.search("/files/invoice.pdf?x=1")
    assert not Runtime.PDF_LINK.search("/ledger/bills/new")
