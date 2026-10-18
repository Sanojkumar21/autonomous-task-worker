"""Command line: run a task, teach the worker, inspect memory.

    python -m worker run "Find the latest invoice from Northwind Supplies, enter it into Ledger, and tell me when done"
    python -m worker run "..." --brain scripted           # deterministic SOP controller, no model
    python -m worker feedback "Bills over 50,000 need my approval" --who priya.manager
    python -m worker memory                                # show what the worker has learned
    python -m worker memory --clear
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from worker.context import CompanyContext
from worker.human import CliHuman, NoHuman, ScriptedHuman
from worker.loop import Worker
from worker.memory.store import MemoryStore


def load_env(path=".env"):
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_brain(spec: str | None):
    if spec == "scripted":
        from worker.brains.scripted import ScriptedBrain
        return ScriptedBrain()
    from worker.brains.llm_brain import LLMBrain
    from worker.llm.providers import make_llm
    return LLMBrain(make_llm(None if spec in (None, "llm") else spec))


def main(argv=None):
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(prog="worker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a task")
    r.add_argument("request")
    r.add_argument("--brain", default=os.environ.get("BRAIN", "llm"), help="llm | scripted | gemini:<model> | groq:<model> | anthropic:<model>")
    r.add_argument("--human", default="cli", choices=["cli", "none", "approve-all"], help="who answers questions and approvals")
    r.add_argument("--no-memory", action="store_true", help="ignore and do not update learned memory")
    r.add_argument("--no-learn", action="store_true", help="use memory but do not write to it")
    r.add_argument("--headed", action="store_true", help="show the browser")
    r.add_argument("--base-url", default=os.environ.get("COMPANY_URL"))
    r.add_argument("--memory-dir", default=os.environ.get("MEMORY_DIR"))
    r.add_argument("--quiet", action="store_true")
    f = sub.add_parser("feedback", help="teach the worker a rule or fact")
    f.add_argument("text")
    f.add_argument("--who", default="manager")
    f.add_argument("--brain", default=os.environ.get("BRAIN", "llm"))
    f.add_argument("--memory-dir", default=os.environ.get("MEMORY_DIR"))
    d = sub.add_parser("demonstrate", help="record yourself doing a task once; keep it as a skill")
    d.add_argument("--name", required=True)
    d.add_argument("--intent", default="record_supplier_invoice")
    d.add_argument("--system", default="ledger")
    d.add_argument("--base-url", default=os.environ.get("COMPANY_URL"))
    d.add_argument("--memory-dir", default=os.environ.get("MEMORY_DIR"))
    m = sub.add_parser("memory", help="show or clear learned memory")
    m.add_argument("--clear", action="store_true")
    m.add_argument("--memory-dir", default=os.environ.get("MEMORY_DIR"))
    args = ap.parse_args(argv)

    if args.cmd == "memory":
        store = MemoryStore(args.memory_dir)
        if args.clear:
            store.clear()
            print("memory cleared")
            return 0
        print(f"{len(store.skills)} skill(s), {len(store.rules)} rule(s) in {store.dir}")
        for s in store.skills:
            print(f"- skill {s.id}: {s.name} [{s.system}] uses={s.uses} ok={s.successes}")
            for step in s.workflow:
                print(f"    · {step}")
        for r in store.rules:
            print(f"- {r.kind} {r.id}{'' if r.active else ' (inactive)'}: {r.text}  {r.structured or ''}  <- {r.source.get('who', '?')}")
        return 0

    ctx = CompanyContext(base_url=getattr(args, "base_url", None))
    if args.cmd == "demonstrate":
        from worker.demonstrate import record
        store = MemoryStore(args.memory_dir)
        skill = record(ctx, args.intent, args.system, args.name, store)
        print(f"learned skill {skill.id}: {skill.name} ({len(skill.procedure)} steps, params {skill.params})")
        for step in skill.procedure:
            print("  ·", step)
        return 0
    if args.cmd == "feedback":
        store = MemoryStore(args.memory_dir)
        brain = build_brain(args.brain)
        worker = Worker(brain, ctx, store)
        rules = worker.feedback(args.text, args.who)
        for r in rules:
            print(f"learned {r.kind} {r.id}: {r.text} {r.structured or ''}")
        return 0

    store = MemoryStore(args.memory_dir, enabled=not args.no_memory)
    brain = build_brain(args.brain)
    human = {"cli": CliHuman(), "none": NoHuman(),
             "approve-all": ScriptedHuman([{"match": ".*", "approve": True, "approver": "priya.manager", "answer": ""}])}[args.human]
    worker = Worker(brain, ctx, store, human, headless=not args.headed, learn=not args.no_learn, verbose=not args.quiet)
    run = worker.run(args.request)
    print(f"\n== {run.final_status.upper()} ==")
    print(run.final_summary)
    print(f"verifier: {run.verification.status} — {run.verification.summary}")
    print(f"report: runs/{run.run_id}/report.md  replay: runs/{run.run_id}/replay.html")
    return 0 if run.final_status.startswith("completed") else 1


if __name__ == "__main__":
    sys.exit(main())
