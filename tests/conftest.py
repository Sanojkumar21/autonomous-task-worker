"""Unit tests get their own company database so they never touch a running sandbox."""
import os
import tempfile

os.environ.setdefault("COMPANY_VAR", tempfile.mkdtemp(prefix="company-test-"))
