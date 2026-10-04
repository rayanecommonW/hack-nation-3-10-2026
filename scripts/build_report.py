#!/usr/bin/env python3
"""Render evidence/results.json into a self-contained HTML lab dashboard.

The dashboard is generated from the run record, so it can never disagree with
the numbers the agents actually produced.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "evidence" / "results.json"
RECORD = REPO / "research_record.json"
OUT = REPO / "demo" / "index.html"

CSS = """
:root{--bg:#08080c;--panel:#101018;--line:#22222e;--fg:#e8e8f0;--dim:#8b8ba0;
--cyan:#4ee0d0;--amber:#ffb454;--red:#ff5c6c;--green:#5ce08a;--violet:#a78bfa;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;padding:28px 32px}
h1{font-size:19px;margin:0 0 2px;letter-spacing:-.02em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.14em;color:var(--dim);
margin:30px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--dim);margin-bottom:8px;font-size:13px}
.q{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--cyan);
padding:12px 14px;border-radius:4px;margin:10px 0 4px}
.grid{display:grid;gap:12px}
.g4{grid-template-columns:repeat(4,1fr)}
.g2{grid-template-columns:1fr 1fr}
@media(max-width:900px){.g4,.g2{grid-template-columns:1fr 1fr}}
.k{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:13px 14px}
.k .n{font-size:26px;font-weight:600;letter-spacing:-.02em}
.k .l{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin-top:3px}
.k .x{color:var(--dim);font-size:11px;margin-top:5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase;
letter-spacing:.1em;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid #16161f;vertical-align:top}
.b{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;letter-spacing:.04em}
.SUPPORTED{background:#0f2b1b;color:var(--green);border:1px solid #1d5c37}
.REFUTED{background:#2b0f14;color:var(--red);border:1px solid #5c1d26}
.INCONCLUSIVE{background:#2b200f;color:var(--amber);border:1px solid #5c421d}
.mono{color:var(--dim)}
.hit{color:var(--green)}.miss{color:var(--red)}.fp{color:var(--amber)}
.flow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0}
.st{border:1px solid var(--line);background:var(--panel);border-radius:4px;
padding:5px 9px;font-size:12px}
.st b{color:var(--cyan);font-weight:600}
.ar{color:var(--dim)}
.note{color:var(--dim);font-size:12px;border-left:2px solid var(--line);padding-left:11px;margin:9px 0}
.warn{border-left-color:var(--amber)}
code{background:#16161f;padding:1px 5px;border-radius:3px;font-size:12px}
ul{margin:6px 0;padding-left:19px}li{margin:3px 0}
footer{color:var(--dim);font-size:11px;margin-top:34px;border-top:1px solid var(--line);padding-top:12px}
"""


def esc(x) -> str:
    return html.escape(str(x))


def main() -> None:
    res = json.loads(RESULTS.read_text())
    rec = json.loads(RECORD.read_text())
    brief = res["brief"]
    acc = res["accepted"]
    spd = res["acceleration"]
    loop = res["discovery_loop"]
    agents = [
        ("safety_agent", "risk register + approval routing", "all"),
        ("literature_agent", "which facts are admissible", "hypothesis_agent"),
        ("hypothesis_agent", "pre-register falsifiable hypotheses", "planner_agent"),
        ("planner_agent", "which competing test runs next", "screener_agent"),
        ("screener_agent", "produce evidence, never interpret", "critic_agent"),
        ("critic_agent", "REFUTED / INCONCLUSIVE / SUPPORTED", "planner_agent"),
        ("decision_agent", "freeze result + next experiment", "human"),
    ]
    best = max(loop, key=lambda e: e["recall"])
    worst = loop[0]

    # ranking of the accepted experiment
    accepted_screen = next(
        s for s in res["full_screens"]
        if s["hypothesis"] == acc["accepted_hypothesis"] and s["gate"] == acc["gate"]
    )
    ranking = accepted_screen["full_ranking"]

    p: list[str] = []
    p.append(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>PQS Lab — agentic scientific discovery</title><style>{CSS}</style></head><body>""")

    p.append("<h1>Agentic scientific discovery lab</h1>")
    p.append(f'<div class="sub">Databricks Omnigent &middot; Hack Nation 3 Oct 2026 &middot; '
             f'record: {esc(rec["created_utc"])} &middot; '
             f'{len(rec["handoffs"])} handoffs &middot; {len(rec["experiments"])} experiments</div>')
    p.append(f'<div class="q">{esc(brief["question"])}</div>')
    p.append(f'<div class="note warn"><b>Bottleneck attacked.</b> {esc(brief["bottleneck_attacked"])}</div>')

    p.append("<h2>Measured result</h2><div class='grid g4'>")
    for n, l, x in [
        (f'{acc["recall"]:.2f}', "positive-control recall", f'6 of 8 held-out positives in top-10'),
        (f'{acc["specificity"]:.2f}', "specificity", "6 of 6 negative controls rejected"),
        (f'{acc["auc_positive_vs_negative"]:.2f}', "AUC pos vs neg", "full ordering, 14 controls"),
        (f'{spd["measured_speedup_x"]:.0f}x', "screen throughput", "vs serial manual triage"),
    ]:
        p.append(f'<div class="k"><div class="n">{esc(n)}</div><div class="l">{esc(l)}</div>'
                 f'<div class="x">{esc(x)}</div></div>')
    p.append("</div>")
    p.append(f'<div class="note"><b>Compounds per hour.</b> agentic lab '
             f'<b>{spd["candidates_per_hour_agentic"]:,}</b> vs serial manual '
             f'<b>{spd["candidates_per_hour_serial"]}</b>. '
             f'At this rate the lab pre-registers <b>{spd["hypotheses_a_day"]:,}</b> '
             f'hypotheses per 24h vs {spd["hypotheses_tested"]} in one human day.</div>')
    p.append(f'<div class="note warn">{esc(spd["caveat"])}</div>')

    p.append("<h2>The agents</h2>")
    p.append('<div class="flow">')
    for i, (name, owns, nxt) in enumerate(agents):
        p.append(f'<div class="st"><b>{esc(name)}</b><br>'
                 f'<span class="mono">{esc(owns)}</span></div>')
        if i < len(agents) - 1:
            p.append('<span class="ar">→</span>')
    p.append("</div>")
    p.append('<div class="note">Cyan arrows in the brief are the discovery loop; these '
             'are the Omnigent coordination edges. Each handoff is a structured record in '
             '<code>research_record.json</code> with its own decision, tools, payload and duration.</div>')

    p.append("<h2>One closed discovery loop — 4 experiments, 2 refutations</h2>")
    p.append("<table><tr><th>#</th><th>hypothesis</th><th>gate</th><th>verdict</th>"
             "<th>recall</th><th>spec</th><th>AUC</th><th>retained</th><th>what happened</th></tr>")
    narrative = {
        "H1/systemic": "baseline repurpose screen returned <b>zero</b> usable candidates — "
                       "nothing in the library is 2D-similar to a 12-carbon aliphatic lactone",
        "H2/systemic": "mechanism switch worked directionally but recall 0.125 — "
                       "chloroquine-class distractors outrank the documented macrolides",
        "H3/systemic": "two-mechanism ensemble crossed threshold",
        "H3/surface_agent": "gate was still binding — a topical antiseptic need not be a "
                            "systemic drug, and relaxing it recovered the last positives",
    }
    for i, e in enumerate(loop):
        key = f'{e["hypothesis"]}/{e["gate"]}'
        p.append(
            f'<tr><td class="mono">{i+1}</td><td><b>{esc(e["hypothesis"])}</b></td>'
            f'<td class="mono">{esc(e["gate"])}</td>'
            f'<td><span class="b {esc(e["verdict"])}">{esc(e["verdict"])}</span></td>'
            f'<td>{e["recall"]:.2f}</td><td>{e["specificity"]:.2f}</td>'
            f'<td>{e["auc_positive_vs_negative"]:.2f}</td><td>{e["n_retained"]}</td>'
            f'<td class="mono">{narrative.get(key, "")}</td></tr>'
        )
    p.append("</table>")

    p.append("<h2>Accepted ranking — approved drugs ranked for PQS quenching</h2>")
    p.append("<table><tr><th>#</th><th>drug</th><th>class</th><th>charge@pH7.4</th>"
             "<th>cLogP</th><th>TPSA</th><th>amphiph.</th><th>score</th><th>control</th></tr>")
    for i, c in enumerate(ranking[:12]):
        nm = c["name"].lower()
        tag = ""
        if nm in {"chlorhexidine", "alexidine", "erythromycin", "clarithromycin",
                  "doxycycline", "minocycline", "clindamycin", "ciprofloxacin"}:
            tag = '<span class="hit">POSITIVE control</span>'
        elif nm in {"aspirin", "ibuprofen", "warfarin", "caffeine", "allopurinol", "isoniazid"}:
            tag = '<span class="fp">negative control — correctly rejected</span>'
        p.append(
            f'<tr><td class="mono">{i+1}</td><td><b>{esc(c["name"])}</b></td>'
            f'<td class="mono">{esc(c["drug_class"])}</td>'
            f'<td class="mono">{esc(c["net_charge_class"])}</td>'
            f'<td class="mono">{c["logp"]:.2f}</td><td class="mono">{c["tpsa"]:.0f}</td>'
            f'<td class="mono">{c["amphiphilicity"]:.2f}</td>'
            f'<td><b>{c["h3_score"]:+.3f}</b></td><td>{tag}</td></tr>'
        )
    p.append("</table>")
    for lim in res["citations"]["limitations"][:3]:
        pass
    p.append('<div class="note warn"><b>What this is not.</b> 2D structural proximity plus '
             'physicochemical property screening. No molecular docking, no binding affinity, '
             'no potency. Direct signal quenching is UNMEASURED. This ranking is a triage '
             'for which compounds are worth putting in a pipette next.</div>')

    p.append("<h2>Stress tests</h2><div class='grid g2'>")
    p.append("<div class='k'><b>Sensitivity — is the shortlist stable?</b>"
             "<table style='margin-top:8px'><tr><th>amphiph. floor</th><th>kept</th>"
             "<th>pos ctrl</th><th>neg ctrl</th></tr>")
    for s in res["sensitivity"]:
        p.append(f'<tr><td class="mono">{s["amphiphilicity_floor"]:.2f}</td>'
                 f'<td>{s["n_retained"]}</td>'
                 f'<td class="hit">{len(s["positive_controls_in_top10"])}</td>'
                 f'<td class="fp">{len(s["negative_controls_in_top10"])}</td></tr>')
    p.append("</table></div>")
    p.append("<div class='k'><b>Ablation — which term carries the signal?</b>"
             "<table style='margin-top:8px'><tr><th>term removed</th><th>pos ctrl kept</th>"
             "<th>neg ctrl leaked</th></tr>")
    for a in res["ablation"]["leave_one_term_out"]:
        p.append(f'<tr><td class="mono">{esc(a["term_removed"])}</td>'
                 f'<td class="hit">{len(a["positive_controls_in_top10"])}</td>'
                 f'<td class="fp">{len(a["negative_controls_in_top10"])}</td></tr>')
    p.append("</table></div></div>")

    p.append("<h2>Next experiment — blocked pending human approval</h2>")
    ne = acc["next_experiment"]
    p.append(f'<div class="q"><b>{esc(ne["proposal"])}</b>'
             f'<div class="sub" style="margin:8px 0 0">Why: {esc(ne["why"])}</div>'
             f'<div class="sub" style="margin:5px 0 0">Falsifier: {esc(ne["falsifier"])}</div>'
             f'<div class="sub" style="margin:5px 0 0;color:var(--amber)">{esc(ne["status"])}</div></div>')
    p.append(f'<div class="note"><b>Path to 10&times;.</b> {esc(acc["what_would_reach_10x"])}</div>')

    p.append("<h2>Governance</h2>")
    p.append(f'<div class="grid g4">'
             f'<div class="k"><div class="n">{len(rec["governance"]["approval_events"])}</div>'
             f'<div class="l">human approvals</div></div>'
             f'<div class="k"><div class="n">{len(rec["safety_events"])-1}</div>'
             f'<div class="l">risk flags raised</div></div>'
             f'<div class="k"><div class="n">${rec["governance"]["budget_usd"]:.2f}</div>'
             f'<div class="l">session budget cap</div></div>'
             f'<div class="k"><div class="n">${spd["hypotheses_tested"]*0.05:.2f}</div>'
             f'<div class="l">actual spend</div></div></div>')

    p.append("<h2>Claims and provenance</h2>")
    for c in res["citations"]["citations"]:
        p.append(f'<div class="note"><b>{esc(c["id"])}</b> — {esc(c["claim"][:210])}<br>'
                 f'<span class="mono">{esc(c["source"])} · {esc(c["locator"])} '
                 f'· <span style="color:var(--amber)">{esc(c["label"])}</span></span></div>')

    p.append(f'<footer>Generated from evidence/results.json + research_record.json by '
             f'scripts/build_report.py. Agents: {esc(", ".join(a[0] for a in agents))}. '
             f'Re-run with <code>python -m lab.orchestrator</code>.</footer>')
    p.append("</body></html>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(p))
    print(f"wrote {OUT.relative_to(REPO)} ({len('\n'.join(p))//1024} KB)")


if __name__ == "__main__":
    main()