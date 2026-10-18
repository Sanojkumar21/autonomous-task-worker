"""Evaluation harness: cold vs learned vs unseen vs chaos, measured honestly.

For every (condition, task, run):
  1. reset the sandbox and set the chaos configuration,
  2. run the worker with a scripted human,
  3. check the ground truth through the admin API (the worker's own
     verifier is not trusted here), and
  4. record success, steps, LLM calls, tokens, cost, time, interventions.

"Success" means: every ground-truth assertion holds, no undeclared writes
happened (for no-write tasks: no writes at all), and the worker's final
status is honest (a claim of "completed" that the truth contradicts is a
false claim and counts as a failure even if the data happens to be right).

    python -m evals.run_eval --brain scripted --conditions cold chaos --runs 3
    python -m evals.run_eval --brain llm --conditions cold learned unseen --runs 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path

import httpx
import yaml

from worker.context import CompanyContext
from worker.human import ScriptedHuman
from worker.loop import Worker
from worker.memory.store import MemoryStore
from worker.run import build_brain, load_env
from worker.types import Assertion
from worker.verifier import Verifier

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"
WRITE_ACTIONS = {"create_bill", "post_bill", "record_payable"}


def load_suite():
    return yaml.safe_load((ROOT / "evals" / "tasks.yaml").read_text())


class Sandbox:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")

    def reset(self, chaos: dict | None = None, seed: int = 7):
        httpx.post(f"{self.base}/admin/api/reset", timeout=30)
        cfg = {"enabled": False, **(chaos or {})}
        cfg["seed"] = seed
        httpx.post(f"{self.base}/admin/api/chaos", json=cfg, timeout=30)


def effective_threshold(memory: MemoryStore, ctx: CompanyContext) -> int:
    threshold = ctx.approval_threshold_paise()
    for r in memory.active_rules():
        if r.kind == "policy" and "approval_threshold_paise" in r.structured:
            threshold = int(r.structured["approval_threshold_paise"])
    return threshold


def ground_truth(task: dict, verifier: Verifier, started_at: float, run, threshold: int) -> dict:
    snap = verifier.snapshot()
    audit = verifier.audit(started_at)
    checks = []
    for a in task.get("expect", []):
        a = json.loads(json.dumps(a))  # copy
        # approval expectation follows the effective threshold
        if a["kind"] == "exists" and task.get("amount_paise") and "approved_by" not in a.get("expect", {}):
            if int(task["amount_paise"]) >= threshold and task["id"] != "T6_denied":
                a.setdefault("expect", {})["approved_by"] = "priya.manager"
        checks.append(verifier.check_assertion(snap, Assertion(**a)))
    writes = [e for e in audit if e["action"] in WRITE_ACTIONS and e["system"] != "chaos"]
    no_writes_ok = not (task.get("no_writes") and writes)
    data_ok = all(c["ok"] for c in checks) and no_writes_ok
    status_ok = True
    if task.get("expect_status"):
        status_ok = run.final_status in task["expect_status"]
    else:
        status_ok = run.final_status in ("completed", "completed_with_exceptions")
    false_claim = run.final_status.startswith("completed") and not data_ok
    honest = not false_claim
    success = data_ok and status_ok and honest
    return {"success": success, "data_ok": data_ok, "status_ok": status_ok, "honest": honest, "checks": checks,
            "writes": len(writes), "no_writes_ok": no_writes_ok}


def teach(suite, brain, ctx, memory_dir: Path, sandbox: Sandbox, human_default, verbose, runs=None):
    """Build the 'learned' memory: verified runs produce skills; people give feedback."""
    memory = MemoryStore(memory_dir)
    memory.clear()
    tasks = {t["id"]: t for t in suite["tasks"]}
    for tid in (runs or suite["teacher"]["runs"]):
        task = tasks[tid]
        sandbox.reset()
        human = ScriptedHuman(task.get("human", []) + human_default)
        worker = Worker(brain, ctx, memory, human, runs_dir=ROOT / "runs" / "teacher", learn=True, verbose=verbose)
        run = worker.run(task["request"], run_id=f"teach-{tid}-{int(time.time())}")
        print(f"  teacher run {tid}: {run.final_status} ({len(run.steps)} steps)")
    worker = Worker(brain, ctx, memory, runs_dir=ROOT / "runs" / "teacher", learn=True, verbose=False)
    for fb in suite["teacher"]["feedback"]:
        rules = worker.feedback(fb["text"], fb["who"])
        print(f"  feedback from {fb['who']}: learned {[r.kind for r in rules]}")
    memory.load()
    print(f"  memory: {len(memory.skills)} skill(s), {len(memory.active_rules())} active rule(s)")
    return memory


def main(argv=None):
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default=os.environ.get("BRAIN", "scripted"))
    ap.add_argument("--conditions", nargs="+", default=["cold"])
    ap.add_argument("--tasks", nargs="*", help="task ids (default: all for the condition)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--base-url", default=os.environ.get("COMPANY_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--name", default=None, help="results file name")
    ap.add_argument("--teacher-runs", nargs="*", default=None,
                    help="teacher tasks (default from tasks.yaml); fewer saves model quota")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    suite = load_suite()
    ctx = CompanyContext(base_url=args.base_url)
    sandbox = Sandbox(args.base_url)
    verifier = Verifier(args.base_url)
    brain = build_brain(args.brain)
    human_default = [{"match": ".*", "approve": True, "approver": "priya.manager", "answer": ""}]
    tasks_by_id = {t["id"]: t for t in suite["tasks"]}
    results = []
    name = args.name or f"{args.brain.replace(':', '-').replace('/', '-')}-{time.strftime('%Y%m%d-%H%M%S')}"
    RESULTS.mkdir(parents=True, exist_ok=True)

    taught: MemoryStore | None = None       # one teacher phase serves every condition that needs it (memory is frozen)
    teacher_dir = Path(tempfile.mkdtemp(prefix="memory-teacher-"))
    for cond_name in args.conditions:
        cond = suite["conditions"][cond_name]
        allowed = cond.get("tasks") or [t["id"] for t in suite["tasks"] if t["system"] == "ledger"]
        task_ids = [t for t in args.tasks if t in allowed] if args.tasks else allowed
        memory_dir = Path(tempfile.mkdtemp(prefix=f"memory-{cond_name}-"))
        if cond["memory"] == "teacher":
            if taught is None:
                print(f"[{cond_name}] teaching...")
                taught = teach(suite, brain, ctx, teacher_dir, sandbox, human_default, args.verbose, args.teacher_runs)
            else:
                print(f"[{cond_name}] reusing the teacher memory")
            memory = taught
            memory_enabled = True
        else:
            memory = MemoryStore(memory_dir, enabled=False)
            memory_enabled = False
        threshold = effective_threshold(memory, ctx) if memory_enabled else ctx.approval_threshold_paise()
        for tid in task_ids:
            task = tasks_by_id[tid]
            for n in range(1, args.runs + 1):
                chaos = dict(cond.get("chaos", {}))
                sandbox.reset(chaos if chaos.get("enabled") else None, seed=100 + n)
                human = ScriptedHuman(task.get("human", []) + human_default)
                # frozen code, memory read-only during measured runs
                worker = Worker(brain, ctx, memory, human, runs_dir=ROOT / "runs" / "eval" / name, learn=False, verbose=args.verbose)
                run_id = f"{cond_name}-{tid}-{n}"
                t0 = time.time()
                run = worker.run(task["request"], run_id=run_id)
                truth = ground_truth(task, verifier, t0, run, threshold)
                row = {"condition": cond_name, "task": tid, "run": n, "success": truth["success"], "honest": truth["honest"],
                       "final_status": run.final_status, "verifier": run.verification.status, "steps": len(run.steps),
                       "browser_actions": run.usage.browser_actions, "llm_calls": run.usage.llm_calls,
                       "tokens": run.usage.input_tokens + run.usage.output_tokens, "cost_usd": run.usage.cost_usd,
                       "seconds": round(run.elapsed(), 1), "human": run.usage.human_interventions,
                       "policy_blocks": sum(1 for s in run.steps if s.policy and not s.policy.allowed and not s.policy.needs_approval),
                       "approvals": len(run.approvals), "skills_used": run.skills_used, "rules": len(run.rules_applied),
                       "writes": truth["writes"], "checks": truth["checks"], "run_id": run_id, "model": run.model}
                results.append(row)
                (RESULTS / f"{name}.partial.json").write_text(json.dumps(results, indent=1))   # survives an interruption
                mark = "PASS" if row["success"] else "FAIL"
                print(f"[{cond_name}] {tid} run {n}: {mark} status={run.final_status} steps={row['steps']} llm={row['llm_calls']} "
                      f"human={row['human']} t={row['seconds']}s" + ("" if truth["honest"] else "  (FALSE CLAIM)"))
        shutil.rmtree(memory_dir, ignore_errors=True)
    shutil.rmtree(teacher_dir, ignore_errors=True)
    (RESULTS / f"{name}.partial.json").unlink(missing_ok=True)

    out = {"brain": args.brain, "model": brain.model, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": args.runs, "results": results}
    (RESULTS / f"{name}.json").write_text(json.dumps(out, indent=1))
    table = summarize(results)
    (RESULTS / f"{name}.md").write_text(table)
    print("\n" + table)
    print(f"saved evals/results/{name}.json and .md")


def summarize(results: list[dict]) -> str:
    lines = ["| condition | tasks | success | honest | steps (mean) | LLM calls | tokens | human asks | time (s) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for cond in dict.fromkeys(r["condition"] for r in results):
        rs = [r for r in results if r["condition"] == cond]
        n = len(rs)
        lines.append(f"| {cond} | {n} | {sum(r['success'] for r in rs)}/{n} | {sum(r['honest'] for r in rs)}/{n} | "
                     f"{statistics.mean(r['steps'] for r in rs):.1f} | {statistics.mean(r['llm_calls'] for r in rs):.1f} | "
                     f"{statistics.mean(r['tokens'] for r in rs):.0f} | {statistics.mean(r['human'] for r in rs):.1f} | "
                     f"{statistics.mean(r['seconds'] for r in rs):.0f} |")
    lines += ["", "| condition | task | run | result | status | steps | LLM | human | blocks | s |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['condition']} | {r['task']} | {r['run']} | {'PASS' if r['success'] else 'FAIL'}{'' if r['honest'] else ' (false claim)'} | "
                     f"{r['final_status']} | {r['steps']} | {r['llm_calls']} | {r['human']} | {r['policy_blocks']} | {r['seconds']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
