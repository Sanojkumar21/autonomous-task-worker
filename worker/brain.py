"""The Brain interface: everything that needs judgement.

The runtime and the loop never call a model directly. They ask the brain
four questions: what does the request mean, what milestones get us there,
what is the next action, and what should we remember afterwards. An LLM
brain answers with a model; the scripted brain answers with code, which lets
the whole runtime be tested deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from worker.context import CompanyContext
from worker.memory.store import MemoryStore, Rule, Skill
from worker.types import Action, Contract, Milestone, Observation, RunRecord, Step


@dataclass
class BrainState:
    run: RunRecord
    context: CompanyContext
    memory: MemoryStore
    observation: Observation
    skills: list[Skill] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)      # runtime detectors talking to the brain
    last_results: list[str] = field(default_factory=list)
    documents: dict[str, str] = field(default_factory=dict)   # PDFs read this run, kept in view so they are read once
    sessions: list[str] = field(default_factory=list)         # systems the browser is currently signed in to


class Brain:
    name = "base"
    model = ""

    def understand(self, request: str, context: CompanyContext, memory: MemoryStore) -> Contract:
        raise NotImplementedError

    def plan(self, contract: Contract, context: CompanyContext, memory: MemoryStore, skills: list[Skill]) -> list[Milestone]:
        raise NotImplementedError

    def decide(self, state: BrainState) -> tuple[str, Action]:
        """Return (thought, action)."""
        raise NotImplementedError

    def distill_skill(self, run: RunRecord, context: CompanyContext) -> Skill | None:
        return None

    def extract_rules(self, feedback: str, who: str, run: RunRecord | None, context: CompanyContext) -> list[Rule]:
        return []

    def usage(self) -> dict:
        return {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
