"""Company memory: what the worker has learned about how this company works.

Three kinds of memory, all plain JSON a person can read and edit:

- **Skills** (`skills.json`): procedures distilled from verified runs. Each has
  an app-agnostic workflow and an app-specific procedure, so the workflow can
  transfer to a system the worker has never seen.
- **Rules** (`rules.json`): things people told the worker. Policy rules carry
  structured settings the gate enforces (an approval threshold, a vendor to
  avoid); guidelines are advice the planner reads; facts are company-specific
  truths (which vendor record is the real one).

Every entry records where it came from: the run, the person, the time. The
worker never learns silently.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent


class Skill(BaseModel):
    id: str = Field(default_factory=lambda: "skill_" + uuid.uuid4().hex[:8])
    name: str
    intent: str
    system: str                       # the app the concrete procedure is for
    trigger: str                      # when to use it, in one sentence
    workflow: list[str]               # app-agnostic steps (transferable)
    procedure: list[str]              # concrete steps for `system`, with {placeholders}
    pitfalls: list[str] = []
    verification: list[str] = []
    params: list[str] = []
    source_run: str = ""
    created_at: float = Field(default_factory=time.time)
    uses: int = 0
    successes: int = 0


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: "rule_" + uuid.uuid4().hex[:8])
    kind: str                         # policy | guideline | fact
    text: str
    structured: dict = {}
    scope: dict = {}                  # {"system": "ledger"} / {"vendor": "..."} / {}
    source: dict = {}                 # {"run_id": ..., "who": ..., "ts": ..., "quote": ...}
    active: bool = True
    created_at: float = Field(default_factory=time.time)


class MemoryStore:
    def __init__(self, directory: Path | None = None, enabled: bool = True):
        self.dir = Path(directory) if directory else ROOT / "memory"
        self.enabled = enabled
        self.dir.mkdir(parents=True, exist_ok=True)
        self.skills: list[Skill] = []
        self.rules: list[Rule] = []
        self.load()

    # ---- persistence
    def load(self):
        self.skills = [Skill(**s) for s in self._read("skills.json")]
        self.rules = [Rule(**r) for r in self._read("rules.json")]

    def save(self):
        self._write("skills.json", [s.model_dump() for s in self.skills])
        self._write("rules.json", [r.model_dump() for r in self.rules])

    def _read(self, name):
        p = self.dir / name
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text())
        except ValueError:
            return []

    def _write(self, name, data):
        (self.dir / name).write_text(json.dumps(data, indent=1, ensure_ascii=False))

    def clear(self):
        self.skills, self.rules = [], []
        self.save()

    # ---- skills
    def add_skill(self, skill: Skill) -> Skill:
        # replace an older skill for the same intent+system if the new one came from a verified run
        self.skills = [s for s in self.skills if not (s.intent == skill.intent and s.system == skill.system)]
        self.skills.append(skill)
        self.save()
        return skill

    def find_skills(self, intent: str, system: str = "", text: str = "") -> list[Skill]:
        """Exact intent match first; same intent on another system second (its workflow still helps)."""
        if not self.enabled:
            return []
        same = [s for s in self.skills if s.intent == intent and (not system or s.system == system)]
        other = [s for s in self.skills if s.intent == intent and system and s.system != system]
        if not same and not other and text:
            words = set(re.findall(r"[a-z]{4,}", text.lower()))
            scored = []
            for s in self.skills:
                overlap = len(words & set(re.findall(r"[a-z]{4,}", (s.trigger + " " + s.name).lower())))
                if overlap >= 2:
                    scored.append((overlap, s))
            other = [s for _, s in sorted(scored, key=lambda x: -x[0])]
        return same + other

    def record_use(self, skill_id: str, success: bool):
        for s in self.skills:
            if s.id == skill_id:
                s.uses += 1
                s.successes += int(success)
        self.save()

    # ---- rules
    def add_rule(self, rule: Rule) -> Rule:
        # a new structured policy value supersedes older ones of the same key
        for key in rule.structured:
            for old in self.rules:
                if old.active and key in old.structured and old.kind == rule.kind:
                    old.active = False
        self.rules.append(rule)
        self.save()
        return rule

    def active_rules(self, system: str = "") -> list[Rule]:
        if not self.enabled:
            return []
        out = []
        for r in self.rules:
            if not r.active:
                continue
            scope_sys = r.scope.get("system")
            if scope_sys and system and scope_sys != system:
                continue
            out.append(r)
        return out

    def describe(self, system: str = "") -> str:
        """A short, prompt-ready summary of what the worker has learned."""
        lines = []
        rules = self.active_rules(system)
        if rules:
            lines.append("Learned rules and facts (from people at this company):")
            for r in rules:
                lines.append(f"- [{r.kind}] {r.text} (source: {r.source.get('who', '?')}, {r.id})")
        return "\n".join(lines)
