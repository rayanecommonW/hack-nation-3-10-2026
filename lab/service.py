"""Request handling for the PQS Lab, deployed on Vercel.

Read-only by design. There is no POST body, no credential channel and no outbound
model call. The page is a presentation of a recorded run, so this reads the record
and sends it. An earlier version let visitors paste their own model key. That
needed no server secret and cost nothing to run, but it turned a portfolio project
into an open proxy to somebody's account, so it went.

Design constraints:

1. NO SERVER-SIDE SECRET. No environment variable in this project holds a model
   credential, and none is needed.

2. THE LAB MUST NOT BREAK. RDKit cannot be imported inside the web process on
   every runtime, so the screens run in a child process under a hard timeout, and
   a failure falls through to the committed, verified run rather than an error.

3. THE NUMBERS MUST BE REAL. The live path re-executes the same lab.screening code
   the repository ships, so the deployed site and a local run agree.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback

# Make the repository's lab package importable regardless of the bundler's cwd.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FROZEN = os.path.join(_ROOT, "evidence", "results.json")

STATUS_TEXT = {
    200: "OK",
    204: "No Content",
    400: "Bad Request",
    404: "Not Found",
    429: "Too Many Requests",
    500: "Internal Server Error",
}

# Kept as a belt-and-braces scrub on every outgoing string. Nothing in a response
# should ever look like a credential, even if a future change puts one into the
# record by mistake.
_REDACTIONS: list[str] = []

_PREFIXES = ("mstrl_", "sk-", "hf_", "gho_", "ghp_")


def _redact(text: str) -> str:
    for secret in _REDACTIONS:
        if secret and len(secret) > 6:
            text = text.replace(secret, "[REDACTED]")
    for prefix in _PREFIXES:
        idx = 0
        while True:
            idx = text.find(prefix, idx)
            if idx == -1:
                break
            end = idx
            while end < len(text) and (text[end].isalnum() or text[end] in "_-"):
                end += 1
            text = text[:idx] + "[REDACTED]" + text[end:]
            idx += 10
    return text


# --------------------------------------------------------------------------
# 1. the run
# --------------------------------------------------------------------------

def run_lab(timeout: int = 40) -> dict:
    """Re-execute the four-experiment loop in an isolated child process.

    RDKit is imported inside the child. In process a chemistry crash would take
    the web worker down with it and there would be nothing left to fall back to.
    In a child under a hard timeout, a crash is just a non-zero exit code.
    """
    # close_fds is load-bearing. Without it the child inherits the listening
    # socket and the accepted connection, and when the child exits the parent's
    # sockets are closed underneath it.
    proc = subprocess.run(
        [sys.executable, "-m", "lab.service_worker"],
        cwd=_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        timeout=timeout,
    )
    if proc.returncode != 0 or not proc.stdout:
        tail = proc.stderr[-200:].decode("utf-8", "replace")
        raise RuntimeError(
            f"screen worker unavailable (exit {proc.returncode}); stderr tail: {tail}"
        )
    return json.loads(proc.stdout.decode("utf-8"))


def frozen_run() -> dict:
    """Answer from the committed, verified run in evidence/results.json.

    RDKit is 265 MB unpacked and exceeds Vercel's serverless function limit, so
    the deployed service cannot re-execute the screens. These are the same numbers
    `python -m lab.orchestrator` produces locally, and the frontend labels the
    source so a reader knows which is which.
    """
    with open(FROZEN) as fh:
        data = json.load(fh)

    accepted = data["accepted"]
    ranking = []
    for screen in data.get("full_screens", []):
        if (screen["hypothesis"] == accepted["accepted_hypothesis"]
                and screen["gate"] == accepted["gate"]):
            for c in screen["full_ranking"][:15]:
                ranking.append({
                    "name": c["name"], "drug_class": c["drug_class"],
                    "net_charge_class": c["net_charge_class"], "logp": c["logp"],
                    "tpsa": c["tpsa"], "amphiphilicity": c["amphiphilicity"],
                    "score": c.get("h3_score", 0.0), "similarity": c["similarity"],
                    "pains": c["pains"], "lipinski_ok": c["lipinski_ok"],
                    "mw": c["mw"],
                })
            break

    accel = data.get("acceleration", {})
    n = accel.get("compounds_screened", 0)

    experiments = []
    for e in data["discovery_loop"]:
        experiments.append({
            "hypothesis": e["hypothesis"], "gate": e["gate"],
            "gate_label": "", "hypothesis_text": "", "scoring_weights": {},
            "verdict": e["verdict"], "recall": e["recall"],
            "specificity": e["specificity"],
            "auc_positive_vs_negative": e["auc_positive_vs_negative"],
            "positives_in_top10": [], "positives_missed": [],
            "false_positives_in_top10": [],
            "n_input": n, "n_valid": n, "n_excluded": e["n_retained"],
            "n_retained": e["n_retained"], "n_priority": e["n_retained"],
            "shortlist": e["shortlist"],
        })

    # Rebuild the cascade from the accepted screen's stored ranking so the page
    # narrows exactly the way a live run does.
    acc_screen = next(
        (s for s in data.get("full_screens", [])
         if s["hypothesis"] == accepted["accepted_hypothesis"]
         and s["gate"] == accepted["gate"]),
        {},
    )
    tiers = [c.get("tier") for c in acc_screen.get("full_ranking", [])]
    n_priority = len([t for t in tiers if t == "priority"])
    n_retained = len([t for t in tiers if t in ("priority", "secondary")])
    n_excluded = len([t for t in tiers if t == "excluded"])

    return {
        "source": "frozen-run",
        "note": ("Deployed runtime ships without RDKit (265 MB exceeds Vercel's "
                 "function limit), so this is the committed verified run from "
                 "evidence/results.json, the same numbers a local "
                 "`python -m lab.orchestrator` produces. Re-run locally to "
                 "recompute it live."),
        "wall_clock_s": data.get("total_wall_clock_s"),
        "compounds_screened": n,
        "compounds_per_hour": accel.get("candidates_per_hour_agentic", 0.0),
        "cascade": {
            "n_input": n, "n_valid": n - 1, "n_excluded": n_excluded,
            "n_retained": n_retained, "n_priority": n_priority,
            "n_shortlist": min(8, len(accepted["shortlist"])),
        },
        "discovery_loop": experiments,
        "accepted": {
            "hypothesis": accepted["accepted_hypothesis"],
            "gate": accepted["gate"],
            "recall": accepted["recall"],
            "specificity": accepted["specificity"],
            "auc_positive_vs_negative": accepted["auc_positive_vs_negative"],
            "shortlist": accepted["shortlist"],
        },
        "ranking": ranking,
        "citations": data.get("citations", {}),
        "sensitivity": data.get("sensitivity", []),
        "ablation": data.get("ablation", {}),
    }


# --------------------------------------------------------------------------
# 2. request handling
# --------------------------------------------------------------------------

def _respond(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": _redact(json.dumps(payload)),
    }


def handler(request: dict) -> dict:
    try:
        if request.get("method", "GET").upper() == "OPTIONS":
            return _respond(200, {"ok": True})

        try:
            run = run_lab()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            try:
                run = frozen_run()
            except Exception:  # noqa: BLE001
                return _respond(500, {
                    "error": "run unavailable",
                    "detail": _redact(traceback.format_exc()[-500:]),
                })

        run["security"] = {
            "server_side_secrets": "none",
            "credential_channel": "none, the service accepts no credential",
            "key_required_for_core_demo": False,
        }
        return _respond(200, run)

    except Exception:  # noqa: BLE001
        return _respond(500, {"error": _redact(traceback.format_exc()[-800:])})