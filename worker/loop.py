"""The worker's loop: Goal → Understand → Plan → (Observe → Decide → Act)* → Verify → Learn → Report.

The brain decides; the runtime acts and enforces; the verifier judges; the
memory remembers. This module just wires them together and watches for the
ways agents go wrong: loops, dead ends, expired sessions, server errors.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from worker.brain import Brain, BrainState
from worker.browser import Browser
from worker.context import CompanyContext
from worker.human import Human, NoHuman
from worker.memory.store import MemoryStore
from worker.policy import PolicyGate
from worker.report import write_report
from worker.runtime import Runtime
from worker.types import Action, Clarification, RunRecord, Step
from worker.verifier import Verifier

ROOT = Path(__file__).resolve().parent.parent
BROWSER_TOOLS = {"navigate", "click", "type", "select", "check", "back", "commit", "fill_form"}


def _relative(path: str, run_dir: Path) -> str:
    """Screenshots are stored relative to the run folder, so a run can be moved or published as it is."""
    try:
        return str(Path(path).relative_to(run_dir)) if path else ""
    except ValueError:
        return path


class Worker:
    def __init__(self, brain: Brain, context: CompanyContext, memory: MemoryStore, human: Human | None = None,
                 headless: bool = True, runs_dir: Path | None = None, learn: bool = True, verbose: bool = False):
        self.brain = brain
        self.ctx = context
        self.memory = memory
        self.human = human or NoHuman()
        self.headless = headless
        self.runs_dir = Path(runs_dir) if runs_dir else ROOT / "runs"
        self.learn = learn
        self.verbose = verbose
        self.verifier = Verifier(context.base_url)

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)
        path = getattr(self, "_log_path", None)
        if path:
            with open(path, "a") as fh:
                fh.write(time.strftime("%H:%M:%S ") + msg + "\n")

    def run(self, request: str, run_id: str | None = None) -> RunRecord:
        run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        run = RunRecord(run_id=run_id, request=request, brain=self.brain.name, model=self.brain.model,
                        memory_mode="on" if self.memory.enabled else "off")
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = run_dir / "worker.log"    # every step, hint and model warning, readable while the run is live
        limits = self.ctx.limits()
        browser = Browser(headless=self.headless, screenshots_dir=run_dir / "screens")
        gate = PolicyGate(self.ctx.policy, self.memory.active_rules())
        rt = Runtime(run, self.ctx, browser, gate, self.human, run_dir)
        status = "running"
        try:
            # 1. understand
            contract = self.brain.understand(request, self.ctx, self.memory)
            run.contract = contract
            self.log(f"[understand] {contract.intent} on {contract.target_system}: {contract.summary}")

            # 2. ask before acting if the request is ambiguous
            for q in contract.questions:
                run.usage.human_interventions += 1
                ans = self.human.clarify(q, [], request)
                run.clarifications.append(Clarification(step=0, question=q, answer=ans.text))
                if not ans.text:
                    run.final_status = "needs_clarification"
                    run.final_summary = f"I need an answer before I can proceed: {q}"
                    status = "stopped"
                    break
                rt.add_fact("clarification", f"{q} -> {ans.text}", "human", 0)
                self.log(f"[clarify] {q} -> {ans.text}")
            if status == "stopped":
                return self._finish(run, run_dir, browser)

            # 3. memory
            skills = self.memory.find_skills(contract.intent, contract.target_system, request)
            run.skills_used = [s.id for s in skills]
            run.rules_applied = [r.id for r in self.memory.active_rules(contract.target_system)]

            # 4. plan
            run.milestones = self.brain.plan(contract, self.ctx, self.memory, skills)
            self.log("[plan] " + " | ".join(m.title for m in run.milestones))

            # 5. act
            browser.navigate(self.ctx.base_url + "/")
            obs = rt.observe()
            hints: list[str] = []
            last_results: list[str] = []
            deadline = time.time() + 60 * float(limits.get("max_minutes", 20))
            for i in range(1, int(limits.get("max_steps", 60)) + 1):
                if time.time() > deadline:
                    run.final_summary = "time limit reached"
                    status = "gave_up"
                    break
                state = BrainState(run=run, context=self.ctx, memory=self.memory, observation=obs, skills=skills,
                                   hints=list(hints), last_results=last_results[-6:],
                                   documents=dict(rt.documents), sessions=sorted(rt.sessions))
                calls_before = self.brain.usage()["llm_calls"]
                t0 = time.time()
                thought, action = self.brain.decide(state)
                result = rt.execute(action, i)
                if result.image is not None and hasattr(self.brain, "note_image"):
                    self.brain.note_image(result.image)
                if action.tool in BROWSER_TOOLS or action.tool == "back":
                    obs = rt.observe()
                step = Step(index=i, url=obs.url, thought=thought, action=action, result=result.text, policy=result.policy,
                            screenshot=_relative(browser.screenshot(f"{i:03d}"), run_dir), llm_calls=self.brain.usage()["llm_calls"] - calls_before,
                            duration_ms=int((time.time() - t0) * 1000))
                run.steps.append(step)
                with (run_dir / "trajectory.jsonl").open("a") as fh:
                    fh.write(step.model_dump_json() + "\n")
                last_results.append(f"step {i}: {action.tool} {action.args if action.tool != 'done' else ''} -> {result.text[:4500]}")
                self.log(f"[{i}] {action.tool} {str(action.args)[:120]} -> {result.text[:140]}")
                hints = self._detect(run, obs, result.text)
                if result.stop:
                    status = result.status
                    break
            else:
                status = "gave_up"
                run.final_summary = run.final_summary or "step limit reached"

            # 6. verify: only the verifier decides
            if status == "claimed_done":
                run.verification = self.verifier.verify(run)
                run.final_status = run.verification.status
            elif status == "needs_clarification":
                run.final_status = "needs_clarification"
            else:
                run.final_status = "gave_up"
                denied = [a for a in run.approvals if not a.granted]
                if denied:
                    run.final_status = "blocked"
            run.usage.browser_actions = browser.actions
            run.model = self.brain.model          # may differ from the start after a budget failover
            u = self.brain.usage()
            run.usage.llm_calls, run.usage.input_tokens = u["llm_calls"], u["input_tokens"]
            run.usage.output_tokens, run.usage.cost_usd = u["output_tokens"], round(u["cost_usd"], 5)

            # 7. learn
            if self.learn and self.memory.enabled:
                self._learn(run)
            return self._finish(run, run_dir, browser)
        finally:
            browser.close()

    def _detect(self, run: RunRecord, obs, last_result: str) -> list[str]:
        hints = []
        steps = run.steps
        if len(steps) >= 2 and len({s.action.signature() for s in steps[-2:]}) == 1:
            hints.append(f"You just repeated the exact same call and it returned: '{steps[-1].result[:160]}'. Do not send it again: "
                         "fix the arguments to match the tool's expected shape, use a different element or path, or ask for help.")
        if len(steps) >= 4:
            sig = [s.action.signature() for s in steps[-4:]]
            if sig[0] == sig[2] and sig[1] == sig[3] and sig[0] != sig[1]:
                hints.append("You are alternating between two pages without acting on either. Navigation links (marked nav) "
                             "only move between pages: on a form, act on the form controls (select/textbox ids), e.g. with fill_form.")
        if obs.is_login_page:
            hints.append("The page is a sign-in form: your session expired. Sign in again with the credentials from the company context, then continue where you left off.")
        if obs.http_error and obs.http_error >= 500:
            hints.append(f"The server returned HTTP {obs.http_error}. Do not repeat a submit blindly; navigate to the list page and check what exists.")
        if "no element with id" in last_result:
            hints.append("Element ids are re-numbered after every action: use ids from the CURRENT observation only.")
        return hints

    def _learn(self, run: RunRecord):
        # 7a. skills: only from verified, completed runs
        if run.final_status == "completed":
            for sid in run.skills_used:
                self.memory.record_use(sid, True)
            skill = self.brain.distill_skill(run, self.ctx)
            if skill:
                skill.source_run = run.run_id
                self.memory.add_skill(skill)
                run.learned.append(skill.id)
                self.log(f"[learn] skill {skill.id}: {skill.name}")
        elif run.final_status == "failed":
            for sid in run.skills_used:
                self.memory.record_use(sid, False)
        # 7b. rules: from what people said during the run
        feedback = [(c.answer, "clarification") for c in run.clarifications if c.answer]
        feedback += [(a.note, a.approver or "approver") for a in run.approvals if a.note]
        for text, who in feedback:
            for rule in self.brain.extract_rules(text, who, run, self.ctx):
                rule.source = {"run_id": run.run_id, "who": who, "ts": time.time(), "quote": text}
                self.memory.add_rule(rule)
                run.learned.append(rule.id)
                self.log(f"[learn] rule {rule.id}: {rule.text}")

    def _finish(self, run: RunRecord, run_dir: Path, browser: Browser) -> RunRecord:
        run.finished_at = time.time()
        write_report(run, run_dir)
        return run

    def feedback(self, text: str, who: str = "manager", run: RunRecord | None = None) -> list:
        """Teach the worker outside a run: 'from now on, bills over 50,000 need my approval'."""
        rules = self.brain.extract_rules(text, who, run, self.ctx)
        for rule in rules:
            rule.source = {"run_id": run.run_id if run else "", "who": who, "ts": time.time(), "quote": text}
            self.memory.add_rule(rule)
        return rules
