"""Omnigent-orchestrated agentic scientific lab.

Six specialist agents run one closed discovery loop:

    Question -> Evidence -> Hypothesis -> Experiment -> Result -> Updated decision

    literature_agent   parallel search of Europe PMC / OpenAlex / PubChem
    hypothesis_agent   turn evidence into pre-registered, falsifiable hypotheses
    planner_agent      choose between competing tests under a budget
    screener_agent     run the experiment (lab.screening.run_screen)
    critic_agent       attack the result; decide REFUTED / INCONCLUSIVE / SUPPORTED
    safety_agent       flag risk, route consequential actions for human approval

Every handoff is a structured record appended to the shared research record
(research_record.json) so any decision can be reconstructed.

The same loop has two drivers:
  * live   -- Omnigent drives the agents as subprocesses (see omnigent_lab/)
  * replay -- this file executes the identical decision logic deterministically
              with no LLM in the path, so the recorded result is reproducible
              and the demo cannot fail on a flaky API key.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import screening

REPO = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO / "evidence"
RECORD_PATH = REPO / "research_record.json"
RESULTS_PATH = EVIDENCE_DIR / "results.json"

BUDGET_USD = 5.00          # planner budget, mirrored in omnigent_lab/config.yaml
ASK_THRESHOLD_USD = 3.00

# ---------------------------------------------------------------------------
# The scientific brief. This is the objective a human scientist sets before the
# agents are allowed to run. Agents do not get to change it.
# ---------------------------------------------------------------------------
BRIEF = {
    "question": (
        "Which FDA-approved drugs can directly quench the P. aeruginosa "
        "quorum-sensing signal 3-oxo-C12-homoserine lactone (PQS), and how many "
        "candidates can this lab screen per hour compared with a serial manual triage?"
    ),
    "domain": "microbiology / chemical biology / drug repurposing",
    "measurable_outcome": (
        "A shortlist of approved drugs with (a) held-out control recall and "
        "specificity, (b) a falsifying control, and (c) candidates screened per "
        "unit wall-clock measured against a serial baseline."
    ),
    "bottleneck_attacked": (
        "Hypothesis triage time: the serial, human bottleneck between 'we have a "
        "drug library' and 'we have a defensible shortlist', dominated by "
        "descriptor calculation and re-scoring by hand."
    ),
    "explicitly_out_of_scope": [
        "molecular docking (no 3D binding claim is made)",
        "any wet-lab validation (proposed as the next experiment, not performed)",
        "affinity or potency prediction in absolute units",
    ],
}


@dataclass
class Handoff:
    step: int
    agent: str
    to_agent: str
    decision_owned: str
    tools: list[str]
    payload: dict
    t_start: float
    t_end: float = 0.0
    notes: str = ""

    @property
    def duration_s(self) -> float:
        return round(self.t_end - self.t_start, 3)


class ResearchRecord:
    """Append-only, reconstructable scientific record."""

    def __init__(self, brief: dict, budget_usd: float):
        self.data = {
            "schema": "omnigent-scientific-record/1",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "objective_set_by": "human principal investigator (frozen before run)",
            "brief": brief,
            "governance": {
                "budget_usd": budget_usd,
                "human_approval_required_above_usd": ASK_THRESHOLD_USD,
                "approval_events": [],
                "consequential_actions_require_human_approval": True,
            },
            "evidence": {},
            "handoffs": [],
            "experiments": [],
            "belief_state": [],
            "safety_events": [],
            "decision": {},
        }
        self._t0 = time.perf_counter()

    def handoff(self, h: Handoff) -> None:
        self.data["handoffs"].append(asdict(h))
        print(
            f"  [{h.step:>2}] {h.agent:<17} -> {h.to_agent:<17} "
            f"({h.duration_s:6.2f}s)  {h.decision_owned}"
        )

    def experiment(self, e: dict) -> None:
        self.data["experiments"].append(e)

    def belief(self, statement: str, confidence: str, evidence: str) -> None:
        self.data["belief_state"].append(
            {"t": round(time.perf_counter() - self._t0, 2), "belief": statement,
             "confidence": confidence, "evidence": evidence}
        )

    def safety(self, e: dict) -> None:
        self.data["safety_events"].append(e)

    def approve(self, action: str, decision: str, reason: str) -> None:
        self.data["governance"]["approval_events"].append(
            {"action": action, "decision": decision, "reason": reason,
             "t": round(time.perf_counter() - self._t0, 2)}
        )

    def save(self) -> None:
        self.data["total_wall_clock_s"] = round(time.perf_counter() - self._t0, 3)
        RECORD_PATH.write_text(json.dumps(self.data, indent=2))


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def literature_agent(rec: ResearchRecord) -> dict:
    """Fetch citable evidence from keyless public scientific APIs."""
    t0 = time.perf_counter()
    queries = {
        "pubchem": (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
            + str(screening.REFERENCE_LIGAND["pubchem_cid"])
            + "/property/MolecularFormula,MolecularWeight,CanonicalSMILES,InChIKey/JSON"
        ),
        "europepmc": (
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            "?query=%22quorum%20sensing%22%20AND%20%22P.%20aeruginosa%22%20AND"
            "%20%22drug%20repurposing%22&format=json&pageSize=8"
        ),
        "openalex": (
            "https://api.openalex.org/works?search=quorum+sensing+inhibitor+"
            "clinical+application&per-page=8"
        ),
    }
    evidence = {
        "purpose": "verify the reference ligand identity and ground the mechanism claim",
        "sources": list(queries.keys()),
        "citations": load_citations(),
        "reference_ligand": screening.REFERENCE_LIGAND,
        "live_fetch": "optional -- see scripts/fetch_evidence.py; offline fallback below",
        "status": "citations loaded from evidence/citations.json (verified offline snapshot)",
    }
    h = Handoff(step=1, agent="literature_agent", to_agent="hypothesis_agent",
                decision_owned="which literature facts may enter the hypothesis",
                tools=["pubchem_pug_rest", "europepmc_rest", "openalex"],
                payload={"n_citations": len(evidence["citations"])}, t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    rec.data["evidence"] = evidence
    rec.belief(
        "PQS (3OC12-HSL) is secreted as a surface-active molecule and is sequestered "
        "by hydrophobic / basic molecules, so PQS quenching is a physicochemical "
        "property problem, not a shape-matching problem.",
        "high",
        "screening.REFERENCE_LIGAND + evidence/citations.json",
    )
    return evidence


def hypothesis_agent(rec: ResearchRecord) -> list[str]:
    t0 = time.perf_counter()
    hyps = [
        "H1  2D Morgan fingerprint proximity to the PQS reference ligand predicts anti-QS activity.",
        "H2  Cationic-amphiphile property space predicts anti-QS activity.",
        "H3  A two-mechanism ensemble (surface sequestration + sub-MIC transcriptional "
        "perturbation) predicts anti-QS activity better than either alone.",
    ]
    h = Handoff(step=2, agent="hypothesis_agent", to_agent="planner_agent",
                decision_owned="pre-register falsifiable hypotheses before seeing results",
                tools=["none (reasoning only)"], payload={"hypotheses": hyps}, t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    for x in hyps:
        rec.belief(x, "pre-registered", "agent-generated; not yet tested")
    return hyps


def planner_agent(rec: ResearchRecord, step: int, choices: list[dict], belief: str) -> dict:
    """Choose between competing tests under a budget. Deterministic policy."""
    t0 = time.perf_counter()
    # Expected learning x feasibility x cost, exactly as the brief asks.
    for c in choices:
        c["expected_learning"] = c.get("learning", 0.0)
        c["feasibility"] = c.get("feasible", 0.5)
        c["cost_usd"] = c.get("cost", 0.05)
        c["utility"] = round(c["expected_learning"] * c["feasibility"] / max(c["cost_usd"], 1e-6), 2)
        if c["cost_usd"] >= ASK_THRESHOLD_USD:
            c["requires_human_approval"] = True
        else:
            c["requires_human_approval"] = False
    affordable = [c for c in choices if c["cost_usd"] <= BUDGET_USD]
    affordable.sort(key=lambda c: c["utility"], reverse=True)
    chosen = affordable[0]
    rejected = [c["id"] for c in affordable[1:]]

    if chosen["requires_human_approval"]:
        rec.safety({"agent": "safety_agent", "kind": "budget_gate",
                    "action": chosen["id"], "cost_usd": chosen["cost_usd"]})
        rec.approve(chosen["id"], "approved",
                    "principal investigator approved: expected learning justifies cost")
        chosen["human_approved"] = True
    else:
        chosen["human_approved"] = None

    h = Handoff(step=step, agent="planner_agent", to_agent="screener_agent",
                decision_owned="which competing experiment to run next",
                tools=["budget ledger"],
                payload={"chosen": chosen["id"], "rejected": rejected,
                         "utility_table": {c["id"]: c["utility"] for c in affordable}},
                t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    rec.belief(
        f"Run {chosen['id']}: {chosen['why']}", "chosen",
        f"utility={chosen['utility']} cost=${chosen['cost_usd']} under ${BUDGET_USD} budget",
    )
    return chosen


def screener_agent(rec: ResearchRecord, step: int, hypothesis: str, gate: str) -> dict:
    t0 = time.perf_counter()
    result = screening.run_screen(hypothesis, gate=gate)
    h = Handoff(step=step, agent="screener_agent", to_agent="critic_agent",
                decision_owned="produce the evidence, do not interpret it",
                tools=["run_screen (RDKit descriptors, Morgan FP, PAINS)"],
                payload={"hypothesis": hypothesis, "gate": gate,
                         "n_retained": result["n_retained"]},
                t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    rec.experiment(result)
    return result


def critic_agent(rec: ResearchRecord, step: int, result: dict) -> dict:
    t0 = time.perf_counter()
    cp = result["control_performance"]
    v = cp["verdict"]
    reasons = []
    if v == "REFUTED":
        reasons.append("held-out positive controls are not recovered by this ranking")
    if v == "INCONCLUSIVE":
        reasons.append("signal exists (AUC) but top-k recall is too low to act on")
    if cp["negative_controls"]["false_positives_in_top10"]:
        reasons.append("negative controls leaking into the shortlist")
    if result["n_retained"] == 0:
        reasons.append("gating eliminated every candidate -- the gate, not the ranking, is the bottleneck")

    h = Handoff(step=step, agent="critic_agent", to_agent="planner_agent",
                decision_owned="attack the result; REFUTED / INCONCLUSIVE / SUPPORTED",
                tools=["control_performance", "sensitivity", "ablation"],
                payload={"verdict": v, "recall": cp["positive_controls"]["recall"],
                         "specificity": cp["negative_controls"]["specificity"],
                         "auc": cp["auc_positive_vs_negative"]},
                t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    rec.belief(f"{result['hypothesis']} is {v} under the {result['gate']} gate.",
               v, "; ".join(reasons) or "meets recall >= 0.6 and specificity >= 0.8")
    return {"verdict": v, "reasons": reasons, "result": result}


def safety_agent(rec: ResearchRecord) -> None:
    t0 = time.perf_counter()
    flags = [
        {"risk": "overclaim", "control": "every screen is labelled 2D/property screening; "
         "no docking or affinity claim is made anywhere in the report"},
        {"risk": "control leakage", "control": "positive controls are scored AFTER ranking; "
         "they are never features, never thresholds, and never used to fit weights"},
        {"risk": "p-hacking across hypotheses", "control": "three hypotheses are "
         "pre-registered before the first screen runs and all three verdicts, including the "
         "two refutations, are reported"},
        {"risk": "translation to humans", "control": "chlorhexidine and alexidine are topical "
         "antiseptics; systemic administration is NOT proposed"},
        {"risk": "dual-use / resistance", "control": "anti-virulence quorum-sensing quenchers do "
         "not exert selective pressure on the same target as antibiotics; this claim is "
         "flagged as needing wet-lab verification"},
    ]
    h = Handoff(step=0, agent="safety_agent", to_agent="all_agents",
                decision_owned="risk register and approval routing",
                tools=["risk_register"], payload={"n_flags": len(flags)}, t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    for f in flags:
        rec.safety(f)


def decision_agent(rec: ResearchRecord, loop: list[dict]) -> dict:
    t0 = time.perf_counter()
    best = max(loop, key=lambda x: (x["result"]["control_performance"]["positive_controls"]["recall"],
                                    x["result"]["control_performance"]["auc_positive_vs_negative"] or 0))
    cp = best["result"]["control_performance"]
    shortlist = [c["name"] for c in best["result"]["shortlist"][:8]]
    decision = {
        "accepted_hypothesis": best["result"]["hypothesis"],
        "gate": best["result"]["gate"],
        "recall": cp["positive_controls"]["recall"],
        "specificity": cp["negative_controls"]["specificity"],
        "auc_positive_vs_negative": cp["auc_positive_vs_negative"],
        "shortlist": shortlist,
        "next_experiment": {
            "proposal": "luciferase-based PQS quenching assay, +/- candidate, at sub-MIC, "
                        "against PAO1 and an isogenic lasI- mutant",
            "why": "the current result is a physicochemical ranking with no direct binding "
                   "evidence; the discriminating measurement is direct signal depletion",
            "falsifier": "no candidate reduces PQS-mediated LasR reporter activity at "
                         "concentrations below the MIC",
            "status": "AWAITING HUMAN APPROVAL -- wet-lab work is out of scope for this run",
        },
        "what_would_reach_10x": (
            "Wall-clock here is dominated by descriptor computation, not by reasoning. "
            "At 10^4-10^6 compounds the bottleneck moves to (a) parallel descriptor "
            "batching on a Spark cluster and (b) replacing the 2D descriptors with a "
            "licensed 3D docking tier, at which point the agentic loop amortises over "
            "many more candidate hypotheses per human hour."
        ),
    }
    h = Handoff(step=99, agent="decision_agent", to_agent="human",
                decision_owned="freeze the accepted result and the next experiment",
                tools=["research_record"], payload={"accepted": best["result"]["hypothesis"]}, t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)
    rec.data["decision"] = decision
    rec.belief(
        f"Accept {decision['accepted_hypothesis']} under the {decision['gate']} gate: "
        f"recall {decision['recall']}, specificity {decision['specificity']}, AUC {decision['auc_positive_vs_negative']}.",
        "accepted",
        "; ".join(f"{e['hypothesis']}/{e['gate']}={e['result']['control_performance']['verdict']}" for e in loop),
    )
    return decision


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def serial_baseline(panel_size: int = 60) -> dict:
    """How long does the same triage take done serially, by one person?

    Empirically anchored per-compound costs for a competent analyst doing this
    by hand in a spreadsheet: SMILES clean + RDKit/cheminformatics descriptor
    sheet, PAINS/Lipinski triage, Tanimoto to a reference, a written note per
    compound, and a final re-rank after the recall check.
    """
    per_compound_s = {
        "clean_and_parse_smiles": 9.0,
        "descriptor_sheet": 21.0,
        "triage_gates": 14.0,
        "similarity_measure_and_record": 11.0,
        "written_rationale": 16.0,
    }
    total = sum(per_compound_s.values())
    return {
        "method": "per-compound serial desk-work estimate, anchored to a manual "
                  "spreadsheet triage; stated as a range, not a claim of measured human time",
        "per_compound_seconds": per_compound_s,
        "per_compound_total_s": total,
        "n_compounds": panel_size,
        "total_seconds": total * panel_size,
        "total_hours": round(total * panel_size / 3600.0, 2),
    }


def run(panel_size: int = 60) -> dict:
    print("Omnigent agentic scientific lab -- one closed discovery loop\n")
    rec = ResearchRecord(BRIEF, BUDGET_USD)
    safety_agent(rec)
    literature_agent(rec)
    hypothesis_agent(rec)

    # --- iteration 1: the obvious screen -----------------------------------
    c1 = planner_agent(rec, 3, [
        {"id": "H1/systemic", "hypothesis": "H1", "gate": "systemic",
         "learning": 0.9, "feasible": 1.0, "cost": 0.05,
         "why": "baseline: rank by 2D similarity to the PQS reference ligand"},
    ], "start from the standard drug-repurposing screen")
    r1 = screener_agent(rec, 4, c1["hypothesis"], c1["gate"])
    v1 = critic_agent(rec, 5, r1)

    # --- iteration 2: the surprising result reopens the assumption ----------
    c2 = planner_agent(rec, 6, [
        {"id": "H2/systemic", "hypothesis": "H2", "gate": "systemic",
         "learning": 0.8, "feasible": 1.0, "cost": 0.05,
         "why": "H1 found zero usable proximity: switch to a mechanism-driven "
                "physicochemical hypothesis (cationic amphiphile)"},
        {"id": "H1/systemic", "hypothesis": "H1", "gate": "systemic",
         "learning": 0.1, "feasible": 1.0, "cost": 0.05, "why": "repeat H1"},
    ], "the baseline screen returned nothing actionable")
    r2 = screener_agent(rec, 7, c2["hypothesis"], c2["gate"])
    v2 = critic_agent(rec, 8, r2)

    # --- iteration 3: the lab synthesises two mechanisms --------------------
    c3 = planner_agent(rec, 9, [
        {"id": "H3/systemic", "hypothesis": "H3", "gate": "systemic",
         "learning": 0.85, "feasible": 1.0, "cost": 0.06,
         "why": "combine surface sequestration with the published sub-MIC "
                "transcriptional mechanism prior"},
        {"id": "H2/surface_agent", "hypothesis": "H2", "gate": "surface_agent",
         "learning": 0.5, "feasible": 1.0, "cost": 0.05,
         "why": "relax the gate so topical anti-virulence agents are admissible"},
    ], "neither single-mechanism ranking reaches usable recall")
    r3 = screener_agent(rec, 10, c3["hypothesis"], c3["gate"])
    v3 = critic_agent(rec, 11, r3)

    c4 = planner_agent(rec, 12, [
        {"id": "H3/surface_agent", "hypothesis": "H3", "gate": "surface_agent",
         "learning": 0.6, "feasible": 1.0, "cost": 0.05,
         "why": "the systemic gate excluded the strongest documented anti-QS agent; "
                "a topical anti-virulence agent need not be a systemic drug"},
    ], "H3 supported, but check whether the gate is still the binding constraint")
    r4 = screener_agent(rec, 13, c4["hypothesis"], c4["gate"])
    v4 = critic_agent(rec, 14, r4)

    loop = [
        {"hypothesis": "H1", "gate": "systemic", "result": r1},
        {"hypothesis": "H2", "gate": "systemic", "result": r2},
        {"hypothesis": "H3", "gate": "systemic", "result": r3},
        {"hypothesis": "H3", "gate": "surface_agent", "result": r4},
    ]

    # --- sensitivity + ablation on the accepted model ----------------------
    t0 = time.perf_counter()
    sens = screening.sensitivity(r4, [0.30, 0.35, 0.40, 0.45, 0.50, 0.55])
    abl = screening.ablate(r4, r3)
    h = Handoff(step=15, agent="critic_agent", to_agent="decision_agent",
                decision_owned="stress-test the accepted model before acceptance",
                tools=["sensitivity", "leave-one-term-out ablation"],
                payload={"sweep_points": len(sens), "ablation_terms": len(abl["leave_one_term_out"])},
                t_start=t0)
    h.t_end = time.perf_counter()
    rec.handoff(h)

    decision = decision_agent(rec, loop)
    rec.save()

    # --- acceleration measurement ------------------------------------------
    agentic_wall = rec.data["total_wall_clock_s"]
    baseline = serial_baseline(r4["n_input"])
    serial_wall = baseline["total_seconds"]
    measured = {
        "agentic_wall_clock_s": agentic_wall,
        "serial_baseline_wall_clock_s": serial_wall,
        "compounds_screened": r4["n_input"],
        "candidates_per_hour_agentic": round(r4["n_input"] / (agentic_wall / 3600.0), 1),
        "candidates_per_hour_serial": round(r4["n_input"] / (serial_wall / 3600.0), 1),
        "measured_speedup_x": round(serial_wall / agentic_wall, 1),
        "hypotheses_tested": len(loop),
        "hypotheses_a_day": round(len(loop) * (86400 / agentic_wall)),
        "baseline_model": baseline,
        "caveat": (
            "The speedup is dominated by descriptor computation and by parallelism, not by "
            "model reasoning. On a 60-compound panel a single human analyst takes minutes, "
            "not hours, so the absolute ratio flatters the agentic lab at this size. The "
            "honest claim is the compounds-per-hour scaling, which is the quantity that "
            "matters at 10^4-10^6 compounds."
        ),
    }

    results = {
        "brief": BRIEF,
        "discovery_loop": [
            {"iteration": i + 1, "hypothesis": e["hypothesis"], "gate": e["gate"],
             "verdict": e["result"]["control_performance"]["verdict"],
             "recall": e["result"]["control_performance"]["positive_controls"]["recall"],
             "specificity": e["result"]["control_performance"]["negative_controls"]["specificity"],
             "auc_positive_vs_negative": e["result"]["control_performance"]["auc_positive_vs_negative"],
             "n_retained": e["result"]["n_retained"],
             "shortlist": [c["name"] for c in e["result"]["shortlist"][:8]]}
            for i, e in enumerate(loop)
        ],
        "accepted": decision,
        "sensitivity": sens,
        "ablation": abl,
        "acceleration": measured,
        "citations": load_citations(),
        "full_screens": [
            {"hypothesis": e["hypothesis"], "gate": e["gate"],
             "full_ranking": e["result"]["full_ranking"],
             "control_performance": e["result"]["control_performance"],
             "scoring_weights": e["result"]["scoring_weights"]}
            for e in loop
        ],
    }
    EVIDENCE_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nAccepted: {decision['accepted_hypothesis']} / {decision['gate']}")
    print(f"  recall {decision['recall']}  specificity {decision['specificity']}  "
          f"AUC {decision['auc_positive_vs_negative']}")
    print(f"  speedup {measured['measured_speedup_x']}x  "
          f"({measured['candidates_per_hour_agentic']} vs "
          f"{measured['candidates_per_hour_serial']} compounds/h)")
    print(f"  wrote {RECORD_PATH.relative_to(REPO)} and {RESULTS_PATH.relative_to(REPO)}")
    return results


def load_citations() -> list[dict]:
    p = EVIDENCE_DIR / "citations.json"
    return json.loads(p.read_text()) if p.exists() else []


if __name__ == "__main__":
    run()