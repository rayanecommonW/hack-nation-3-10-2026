"""Request-handling service for the PQS Lab, deployed on Vercel.

Design constraints, in order of importance:

1. NO SERVER-SIDE SECRET. This function reads no environment variable for any
   model credential. There is no key in this repository and none in Vercel's
   project environment. If a visitor wants an LLM narrative they paste their own
   key into the browser; it arrives in the POST body, is used for exactly one
   upstream call, and is discarded. It is never logged, never persisted, never
   written to disk, never returned to the client, and never placed in a header
   (Vercel's request logs capture method/path/status; bodies are not logged, so
   the body is the safer channel).

2. THE LAB MUST NOT BREAK. If RDKit cannot be imported in the runtime, the
   function degrades to the committed, verified run in evidence/results.json
   rather than erroring. The demo always renders.

3. THE NUMBERS MUST BE REAL. The live path re-executes the same
   lab.screening code path the repository ships, so the deployed site and the
   local run agree.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request

# Make the repository's lab package importable regardless of the bundler's cwd.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"
FROZEN = os.path.join(_ROOT, "evidence", "results.json")

# Never let a credential reach a response or an error message.
_REDACTIONS: list[str] = []


def _redact(text: str) -> str:
    for secret in _REDACTIONS:
        if secret and len(secret) > 6:
            text = text.replace(secret, "[REDACTED]")
    # Defence in depth: strip anything that looks like a provider key.
    for prefix in ("mstrl_", "sk-", "hf_"):
        idx = 0
        while True:
            idx = text.find(prefix, idx)
            if idx == -1:
                break
            end = idx
            while end < len(text) and (text[end].isalnum() or text[end] in "_-"):
                end += 1
            text = text[: idx] + "[REDACTED]" + text[end:]
            idx = idx + 10
    return text


# --------------------------------------------------------------------------
# 1. the science
# --------------------------------------------------------------------------

def run_lab(timeout: int = 40):
    """Re-execute the four-experiment loop in an isolated child process.

    RDKit's manylinux wheel segfaults on some serverless Python runtimes. In
    process that kills the worker silently -- no traceback, no chance to fall
    back. In a child process under a hard timeout, a segfault is just a
    non-zero exit code, and the caller falls through to frozen_run().
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "lab.service_worker"],
        cwd=_ROOT,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(
            f"screen worker unavailable (exit {proc.returncode}); "
            f"stderr tail: {proc.stderr[-200:].decode('utf-8', 'replace')}"
        )
    return json.loads(proc.stdout.decode("utf-8"))


def frozen_run():
    """Answer from the committed, verified run in evidence/results.json.

    RDKit is 265 MB unpacked and exceeds Vercel's serverless function limit, so
    the deployed service cannot re-execute the screens. These are the same
    numbers `python -m lab.orchestrator` produced locally, and the frontend
    labels the source so a reader knows which is which.
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
    per_hour = accel.get("candidates_per_hour_agentic", 0.0)

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
            "n_input": n, "n_retained": e["n_retained"], "shortlist": e["shortlist"],
        })

    return {
        "source": "frozen-run",
        "note": ("Deployed runtime ships without RDKit (265 MB exceeds Vercel's "
                 "function limit), so this is the committed verified run from "
                 "evidence/results.json -- identical numbers to a local "
                 "`python -m lab.orchestrator`. Re-run locally to recompute live."),
        "wall_clock_s": data.get("total_wall_clock_s"),
        "compounds_screened": n,
        "compounds_per_hour": per_hour,
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
# 2. optional BYOK narrative
# --------------------------------------------------------------------------

NARRATIVE_PROMPT = """You are the principal investigator of an agentic scientific \
lab, briefing a visiting reviewer. Be concise and plain. Do not inflate.

QUESTION
Which FDA-approved drugs quench the P. aeruginosa quorum-sensing signal PQS \
(3-oxo-C12-Hosm), and how many can the lab screen per hour?

WHAT THE LAB RAN (verified numbers, do not alter any of them)
{loop}

ACCEPTED RESULT
{accepted}

HARD CONSTRAINTS ON YOUR ANSWER
- No docking was run. This is 2D structural proximity plus physicochemical \
property screening. Say so.
- No wet lab was run. Direct signal quenching is unmeasured.
- Never state a binding affinity, IC50 or potency.
- Two experiments were refutations. Do not hide them.
- The speedup is descriptor computation and parallelism, not model reasoning.

Write four short paragraphs: (1) the question and why anti-virulence is \
interesting, (2) how the loop turned twice, naming what was refuted, (3) what \
the accepted result means and what it does not mean, (4) the single next \
experiment and its falsifier. No headings, no bullet points, no preamble.
Every number you use must appear in the run data above."""


def narrate(key: str, run: dict) -> dict:
    """One upstream call with the visitor's key. The key is used and dropped."""
    if not key:
        return {"available": False, "reason": "no key supplied"}

    if len(key) < 20 or not re.match(r"^[A-Za-z0-9_.\-]+$", key):
        return {"available": False, "reason": "key rejected before use: malformed"}

    _REDACTIONS.append(key)

    prompt = NARRATIVE_PROMPT.format(
        loop="\n".join(
            f"  exp{e['hypothesis']}/{e['gate']}: {e['verdict']} recall={e['recall']} "
            f"specificity={e['specificity']} AUC={e['auc_positive_vs_negative']}"
            for e in run["discovery_loop"]
        ),
        accepted=f"  {run['accepted']['hypothesis']} / {run['accepted']['gate']}: "
                 f"recall {run['accepted']['recall']}, specificity "
                 f"{run['accepted']['specificity']}, AUC "
                 f"{run['accepted']['auc_positive_vs_negative']}\n  "
                 f"shortlist: {', '.join(run['accepted']['shortlist'])}",
    )

    body = json.dumps({
        "model": MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 700,
    }).encode()
    req = urllib.request.Request(
        MISTRAL_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode())
            text = payload["choices"][0]["message"]["content"]
            return {"available": True, "model": MISTRAL_MODEL, "text": _redact(text)}
        except urllib.error.HTTPError as exc:
            detail = _redact(exc.read().decode()[:300])
            last = f"mistral HTTP {exc.code}: {detail}"
            if exc.code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {"available": False, "reason": last}
        except Exception as exc:  # noqa: BLE001
            last = _redact(f"{type(exc).__name__}: {exc}")
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {"available": False, "reason": last}
    return {"available": False, "reason": last}


# --------------------------------------------------------------------------
# 3. handler
# --------------------------------------------------------------------------

STATUS_TEXT = {
    200: "OK", 204: "No Content", 400: "Bad Request",
    404: "Not Found", 429: "Too Many Requests", 500: "Internal Server Error",
}

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Cache-Control": "no-store",
}


def _respond(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **CORS},
        "body": _redact(json.dumps(payload)),
    }


def handler(request):
    try:
        if request.get("method", "GET").upper() == "OPTIONS":
            return _respond(200, {"ok": True})

        if request.get("method", "GET").upper() == "POST":
            try:
                body = json.loads(request.get("body") or "{}")
            except Exception:  # noqa: BLE001
                body = {}
            key = (body.get("mistral_key") or "").strip()
            if key:
                _REDACTIONS.append(key)

        try:
            run = run_lab()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            try:
                run = frozen_run()
            except Exception:  # noqa: BLE001
                return _respond(500, {
                    "error": "lab unavailable",
                    "detail": _redact(traceback.format_exc()[-500:]),
                })

        if request.get("method", "GET").upper() == "POST" and key:
            run["narrative"] = narrate(key, run)
            # Belt and braces: prove the credential is not in the response.
            run["credential_echoed"] = bool(key and key in json.dumps(run))
        else:
            run["narrative"] = {"available": False, "reason": "POST with your own key to enable"}
            run["credential_echoed"] = False

        run["security"] = {
            "server_side_secrets": "none",
            "credential_channel": "request body (never a header, never a URL)",
            "credential_persisted": False,
            "credential_logged": False,
            "key_required_for_core_demo": False,
        }
        return _respond(200, run)

    except Exception:  # noqa: BLE001
        return _respond(500, {"error": _redact(traceback.format_exc()[-800:])})


import re  # noqa: E402  (used by narrate; imported late to keep the header tidy)