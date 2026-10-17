"""Company context: what a new employee is given on day one.

Loaded from company_context/: the systems and how to sign in, the handbook
(SOPs), and the policy file. The worker reads these the way a person would:
it does not get a hand-written script for each task.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTEXT_DIR = ROOT / "company_context"


class CompanyContext:
    def __init__(self, directory: Path | None = None, base_url: str | None = None):
        self.dir = Path(directory) if directory else CONTEXT_DIR
        self.systems_cfg = yaml.safe_load((self.dir / "systems.yaml").read_text())
        self.base_url = (base_url or self.systems_cfg.get("base_url", "http://127.0.0.1:8000")).rstrip("/")
        self.handbook = (self.dir / "handbook.md").read_text()
        self.policy = yaml.safe_load((self.dir / "policy.yaml").read_text())

    @property
    def systems(self) -> dict:
        return self.systems_cfg["systems"]

    def url(self, system: str, key: str = "home") -> str:
        return self.base_url + self.systems[system][key]

    def credentials(self, system: str) -> tuple[str, str]:
        s = self.systems[system]
        return s["username"], s["password"]

    def system_for_url(self, url: str) -> str:
        path = url.replace(self.base_url, "")
        for name in self.systems:
            if path.startswith(f"/{name}"):
                return name
        return ""

    def systems_summary(self) -> str:
        lines = [f"Base URL: {self.base_url}"]
        for name, s in self.systems.items():
            lines.append(f"- {name} ({s['name']}): {s['purpose']} Home: {s['home']}. Sign-in: {s['login']} "
                         f"with username '{s['username']}' and password '{s['password']}'."
                         + (f" Notes: {s['notes']}" if s.get("notes") else ""))
        return "\n".join(lines)

    def sop_sections(self) -> dict[str, str]:
        sections, current, buf = {}, "intro", []
        for line in self.handbook.splitlines():
            m = re.match(r"^##\s+(.*)", line)
            if m:
                sections[current] = "\n".join(buf).strip()
                current, buf = m.group(1).strip(), []
            else:
                buf.append(line)
        sections[current] = "\n".join(buf).strip()
        return sections

    def relevant_handbook(self, request: str) -> str:
        """The whole handbook is short; return it all, SOP first when the request mentions invoices."""
        return self.handbook

    def approval_threshold_paise(self) -> int:
        return int(self.policy["approval"]["threshold_paise"])

    def limits(self) -> dict:
        return self.policy.get("limits", {"max_steps": 60, "max_minutes": 20})
