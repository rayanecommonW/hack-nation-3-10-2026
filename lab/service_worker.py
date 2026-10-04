"""Isolated screen runner.

The RDKit manylinux wheel segfaults on some serverless Python runtimes. Running
it in-process takes the whole worker down with no traceback and no chance to
fall back. So it runs here, in a child process, under a hard timeout: a
segfault becomes a non-zero return code and a silent process, which the parent
treats as "unavailable" and answers from the committed verified run instead.

    python -m lab.service_worker   ->  prints one JSON object on stdout
"""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    from lab import screening

    loop_spec = [
        ("H1", "systemic"),
        ("H2", "systemic"),
        ("H3", "systemic"),
        ("H3", "surface_agent"),
    ]
    t0 = time.perf_counter()
    experiments = []
    for hypothesis, gate in loop_spec:
        result = screening.run_screen(hypothesis, gate=gate)
        cp = result["control_performance"]
        experiments.append({
            "hypothesis": hypothesis,
            "gate": gate,
            "gate_label": result["gate_label"],
            "hypothesis_text": result["hypothesis_text"],
            "scoring_weights": result["scoring_weights"],
            "verdict": cp["verdict"],
            "recall": cp["positive_controls"]["recall"],
            "specificity": cp["negative_controls"]["specificity"],
            "auc_positive_vs_negative": cp["auc_positive_vs_negative"],
            "positives_in_top10": cp["positive_controls"]["in_top10"],
            "positives_missed": cp["positive_controls"]["missed"],
            "false_positives_in_top10": cp["negative_controls"]["false_positives_in_top10"],
            "n_input": result["n_input"],
            "n_valid": result["n_valid"],
            "n_excluded": result["n_excluded"],
            "n_retained": result["n_retained"],
            "n_priority": len([c for c in result["full_ranking"] if c["tier"] == "priority"]),
            "shortlist": [c["name"] for c in result["shortlist"][:8]],
        })

    accepted = max(experiments, key=lambda e: (e["recall"], e["auc_positive_vs_negative"] or 0.0))
    final = screening.run_screen(accepted["hypothesis"], gate=accepted["gate"])
    elapsed = time.perf_counter() - t0

    cascade = {
        "n_input": final["n_input"],
        "n_valid": final["n_valid"],
        "n_excluded": final["n_excluded"],
        "n_retained": final["n_retained"],
        "n_priority": len([c for c in final["full_ranking"] if c["tier"] == "priority"]),
        "n_shortlist": min(8, len(final["shortlist"])),
    }

    payload = {
        "source": "live",
        "cascade": cascade,
        "ran_on": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_clock_s": round(elapsed, 3),
        "compounds_screened": final["n_input"],
        "compounds_per_hour": round(final["n_input"] / (elapsed / 3600.0), 1),
        "discovery_loop": experiments,
        "accepted": {
            "hypothesis": accepted["hypothesis"],
            "gate": accepted["gate"],
            "recall": accepted["recall"],
            "specificity": accepted["specificity"],
            "auc_positive_vs_negative": accepted["auc_positive_vs_negative"],
            "shortlist": accepted["shortlist"],
        },
        "ranking": [
            {"name": c["name"], "drug_class": c["drug_class"],
             "net_charge_class": c["net_charge_class"], "logp": c["logp"],
             "tpsa": c["tpsa"], "amphiphilicity": c["amphiphilicity"],
             "score": c["h3_score"], "similarity": c["similarity"],
             "pains": c["pains"], "lipinski_ok": c["lipinski_ok"], "mw": c["mw"]}
            for c in final["full_ranking"][:15]
        ],
    }
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
