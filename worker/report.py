"""Evidence report: what happened, what was checked, what a person decided.

Writes three files into the run directory:
- run.json     the full RunRecord (machine-readable)
- report.md    a human-readable summary with the verifier's findings
- replay.html  a step-by-step replay with screenshots, for demos and review
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from worker.types import RunRecord


def rupees(paise) -> str:
    try:
        return f"{int(paise) / 100:,.2f}"
    except (TypeError, ValueError):
        return str(paise)


def write_report(run: RunRecord, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(run.model_dump_json(indent=1))
    md = render_markdown(run)
    (run_dir / "report.md").write_text(md)
    (run_dir / "replay.html").write_text(render_replay(run, run_dir))
    return run_dir / "report.md"


def render_markdown(run: RunRecord) -> str:
    v = run.verification
    lines = [f"# Run {run.run_id}: {run.final_status}", "",
             f"**Request:** {run.request}", "",
             f"**Outcome:** {run.final_summary or '(no summary)'}", "",
             f"**Verifier:** `{v.status}` — {v.summary}", ""]
    if run.contract:
        c = run.contract
        lines += ["## Understanding", f"- Intent: `{c.intent}` on `{c.target_system or '?'}`", f"- {c.summary}"]
        if c.params:
            lines.append(f"- Parameters: `{json.dumps(c.params)}`")
        if c.questions:
            lines.append(f"- Ambiguities raised: {'; '.join(c.questions)}")
        lines.append("")
    if run.milestones:
        lines += ["## Plan"] + [f"- [{'x' if m.status == 'done' else ' '}] **{m.title}** — done when: {m.done_when}"
                               + (" (write)" if m.writes else "") for m in run.milestones] + [""]
    if run.skills_used or run.rules_applied:
        lines += ["## Memory used"]
        for s in run.skills_used:
            lines.append(f"- skill `{s}`")
        for r in run.rules_applied:
            lines.append(f"- rule `{r}`")
        lines.append("")
    if run.facts:
        lines += ["## Facts gathered (with provenance)", "| step | fact | value | source |", "|---|---|---|---|"]
        for f in run.facts:
            lines.append(f"| {f.step} | `{f.key}` | {f.value} | {f.source} |")
        lines.append("")
    if run.clarifications:
        lines += ["## Questions asked"]
        for q in run.clarifications:
            lines.append(f"- step {q.step}: {q.question} → **{q.answer or '(no answer)'}**")
        lines.append("")
    if run.approvals:
        lines += ["## Approvals"]
        for a in run.approvals:
            lines.append(f"- step {a.step}: {'GRANTED' if a.granted else 'DENIED'} by {a.approver or '-'} — {a.reason}"
                         + (f" (note: {a.note})" if a.note else ""))
        lines.append("")
    gated = [s for s in run.steps if s.policy]
    if gated:
        lines += ["## Policy decisions"]
        for s in gated:
            p = s.policy
            lines.append(f"- step {s.index}: {'allowed' if p.allowed else ('needs approval' if p.needs_approval else 'blocked')}"
                         f" — {'; '.join(p.reasons)} [{', '.join(p.rule_ids) or '-'}]")
        lines.append("")
    if v.checks:
        lines += ["## Verification (independent, via the admin API)", "| ok | assertion | detail |", "|---|---|---|"]
        for c in v.checks:
            a = c["assertion"]
            lines.append(f"| {'✅' if c['ok'] else '❌'} | {a['kind']} {a['system']}/{a['entity']} {json.dumps(a['match'])} "
                         f"{json.dumps(a['expect']) if a['expect'] else ''} | {c['detail']} |")
        if v.unexplained_changes:
            lines.append("")
            lines.append("Undeclared writes: " + json.dumps(v.unexplained_changes))
        lines.append("")
    lines += ["## Timeline"]
    for s in run.steps:
        res = s.result.replace("\n", " ")
        lines.append(f"{s.index}. `{s.action.tool}` {json.dumps(s.action.args)[:160]} → {res[:200]}")
    u = run.usage
    lines += ["", "## Cost",
              f"- steps: {len(run.steps)}, browser actions: {u.browser_actions}, human interventions: {u.human_interventions}",
              f"- LLM calls: {u.llm_calls}, tokens in/out: {u.input_tokens}/{u.output_tokens}, est. cost: ${u.cost_usd:.4f}",
              f"- wall time: {run.elapsed():.0f}s, brain: {run.brain} {run.model}, memory: {run.memory_mode}"]
    if run.learned:
        lines += ["", "## Learned from this run"] + [f"- `{x}`" for x in run.learned]
    return "\n".join(lines) + "\n"


def render_replay(run: RunRecord, run_dir: Path) -> str:
    cards = []
    for s in run.steps:
        shot = Path(s.screenshot).name if s.screenshot else ""
        img = f'<img src="screens/{html.escape(shot)}" loading="lazy">' if shot else ""
        policy = ""
        if s.policy:
            cls = "ok" if s.policy.allowed else "warn"
            policy = f'<div class="policy {cls}">policy: {html.escape("; ".join(s.policy.reasons))}</div>'
        cards.append(f"""<section class="step"><h3>Step {s.index} · <code>{html.escape(s.action.tool)}</code>
        <span class="muted">{html.escape(s.url)}</span></h3>
        <p class="thought">{html.escape(s.thought)}</p>
        <pre>{html.escape(json.dumps(s.action.args, ensure_ascii=False)[:600])}</pre>
        <p class="result">→ {html.escape(s.result[:600])}</p>{policy}{img}</section>""")
    v = run.verification
    checks = "".join(f"<li>{'✅' if c['ok'] else '❌'} {html.escape(c['detail'])}</li>" for c in v.checks)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Replay {html.escape(run.run_id)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:24px auto;color:#1d2330}}
.step{{border:1px solid #e3e6ec;border-radius:8px;padding:12px 16px;margin:14px 0}} img{{max-width:100%;border:1px solid #ddd;margin-top:8px}}
.muted{{color:#777;font-size:12px;font-weight:400}} .thought{{color:#444}} .result{{color:#0b5}} pre{{background:#f6f7f9;padding:8px;overflow:auto}}
.policy{{padding:6px 10px;border-radius:4px;font-size:13px}} .policy.ok{{background:#e6f6ea}} .policy.warn{{background:#fff6e0}}
.status{{padding:10px 14px;border-radius:6px;background:#eef1f6}}</style></head><body>
<h1>{html.escape(run.request)}</h1>
<div class="status"><b>Status: {html.escape(run.final_status)}</b> · verifier: {html.escape(v.status)} — {html.escape(v.summary)}<br>
{html.escape(run.final_summary)}</div>
<h2>Verification</h2><ul>{checks or '<li>(none)</li>'}</ul>
<h2>Steps</h2>{''.join(cards)}
</body></html>"""
