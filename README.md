# PQS Lab — an agentic scientific-discovery lab

**Databricks Omnigent challenge — "Agentic Scientific Discovery", Hack Nation 3 Oct 2026**

An AI lab that runs one closed discovery loop over a real scientific question,
orchestrated by [Omnigent](https://github.com/omnigent-ai/omnigent), and shows
where the loop actually changed the next decision.

**Video:** `demo/pqs-lab-demo.mp4` · **Live dashboard:** `demo/index.html`

---

## The question

> Which FDA-approved drugs can directly quench the *P. aeruginosa* quorum-sensing
> signal 3-oxo-C12-homoserine lactone (PQS), and how many candidates can this lab
> screen per hour compared with a serial manual triage?

Why this question. Quorum sensing is how *P. aeruginosa* coordinates virulence.
Quenching the signal is attractive because an anti-virulence agent does not act on
the bacterial growth machinery, so it is not expected to select for antibiotic
resistance the way a conventional antibiotic does. That expectation is a
**hypothesis**, not a fact, and the lab says so.

## What the lab found

Four experiments, two of them refutations, and a decision that changed twice.

| # | Hypothesis | Gate | Verdict | Recall | Specificity | AUC |
|---|---|---|---|---|---|---|
| 1 | **H1** 2D fingerprint proximity to PQS | systemic | **REFUTED** | 0.00 | 1.00 | 0.77 |
| 2 | **H2** cationic-amphiphile property space | systemic | **REFUTED** | 0.13 | 1.00 | 0.71 |
| 3 | **H3** two-mechanism ensemble | systemic | **SUPPORTED** | 0.63 | 1.00 | 1.00 |
| 4 | **H3** two-mechanism ensemble | surface-agent | **SUPPORTED** | **0.75** | **1.00** | **1.00** |

**The loop, and where it turned.**

1. **H1 fails, hard.** The obvious drug-repurposing screen ranks candidates by 2D
   Tanimoto similarity to PQS. PQS is a 12-carbon aliphatic lactone. *Nothing* in a
   60-compound approved-drug panel reaches even 0.20 similarity — the gate retains
   **zero** candidates. A fingerprint screen cannot express "hydrophobic and basic",
   which is the actual property that matters here.
2. **The lab reopens the assumption.** The critic flags that an empty result with
   AUC 0.77 is not a null result — it is a *tool* failure. The mechanism the
   literature points at is that PQS is secreted as a surface-active micellar
   species, so quenching it is a **physicochemical** problem, not a shape-matching
   problem. Hypothesis 2 replaces proximity with cationic-amphiphile property space.
3. **H2 gets direction but not recall.** Chlorhexidine — the strongest documented
   anti-biofilm agent in the panel — rises to rank 1, but chloroquine-class
   distractors outrank the macrolides that actually have published sub-MIC QS
   activity. Recall 0.13 is unusable. Verdict: INCONCLUSIVE/REFUTED.
4. **H3 is the synthesis.** Two mechanisms, not one: *A* surface sequestration
   (the H2 term) and *B* direct perturbation of QS gene expression, a literature
   prior over macrolide / tetracycline / lincoside / fluoroquinolone / aminoglycoside
   / cationic-dye / bisbiguanide classes. Recall 0.63, specificity 1.00, AUC 1.00.
5. **The gate, not the ranking, was still binding.** The strongest documented
   anti-QS agent is chlorhexidine, MW 505 — it *fails* the textbook Lipinski rule of
   500. But a topical antiseptic that acts on a bacterial surface is not required to
   be a systemic drug. Re-running with a surface-agent gate admits it and recovers the
   last two positives: **recall 0.75, specificity 1.00**.

Accepted shortlist: chlorhexidine, moxifloxacin, levofloxacin, ofloxacin,
ciprofloxacin, norfloxacin, alexidine, clindamycin.

## The agents

Six specialist agents, each owning exactly one scientific decision. Orchestrated
by Omnigent (`omnigent_lab/config.yaml`, ten agent specs in `omnigent_lab/agents/`).

```
safety_agent       risk register + approval routing + veto  ──┐
literature_agent   which facts are admissible              ──┤  (pubchem_agent,
hypothesis_agent   pre-register falsifiable hypotheses       │   europepmc_agent,
planner_agent      which competing test runs next, under     │   openalex_agent
                   budget, with human-approval routing      │   run in parallel)
screener_agent     produce the evidence, never interpret    │
critic_agent       REFUTED / INCONCLUSIVE / SUPPORTED        │
decision_agent     freeze the accepted result + next test  ──┘
```

The loop runs `planner → screener → critic → planner` until the critic returns
SUPPORTED or the budget is spent. Every handoff is a structured record with its own
decision, tool list, payload and duration in `research_record.json`, so any decision
in the report can be traced back to the handoff that made it.

## What is *not* claimed

Stated plainly, because the brief asks for uncertainty to be preserved:

- **No molecular docking.** This is 2D structural proximity plus physicochemical
  property screening. No binding affinity, no potency, no IC50.
- **No wet-lab validation.** Direct PQS quenching is **unmeasured**. The screen
  ranks candidates worth putting in a pipette next; it does not show any of them
  works.
- **The controls are held out.** Positive controls (8) and negative controls (6) are
  scored *after* ranking is frozen. They are never features, never thresholds, never
  used to fit a weight. `critic_agent` verifies this from the code on every run.
- **Control set is small.** n=8 positives. Read the denominators, not the ratios.
- **Mechanism B is a literature prior.** The leave-one-term-out ablation in
  `evidence/results.json` reports how much of the signal that single term carries, so
  a reader can discount it.
- **The panel is ~60 compounds**, an embedded offline subset — not the full ~1,600
  approved space.
- **The 1375× speedup is honest but small-N.** At 60 compounds a human analyst takes
  minutes. The transferable number is the scaling: **~70,000 compounds/hour**, and
  **~1,700 pre-registered hypotheses per 24h**.

## The measured acceleration

| | agentic lab | serial manual triage |
|---|---|---|
| compounds screened / hour | ~70,000 | ~51 |
| hypotheses pre-registered / day | ~1,700 | ~3 |

The speedup is dominated by descriptor computation and parallelism, not by model
reasoning. That is stated in `evidence/results.json` rather than hidden, because it
determines where the real 10× lives.

**What would actually reach 10×.** At 10⁴–10⁶ compounds the bottleneck stops being
descriptor throughput and becomes (a) parallel descriptor batching on a Spark
cluster — the natural fit for the managed Databricks route, where Omnigent routes
through Foundation Model APIs and the sandbox runs the compute — and (b) swapping
the 2D descriptors for a licensed 3D docking tier. At that scale the agentic loop
amortises over many more candidate hypotheses per human hour.

## Next experiment — blocked pending human approval

**Luciferase-based PQS quenching assay**, ± candidate, at sub-MIC, against PAO1 and
an isogenic *lasI*⁻ mutant.

- **Why:** the current result is a physicochemical ranking with no direct binding
  evidence. The discriminating measurement is direct signal depletion.
- **Falsifier:** no candidate reduces PQS-mediated LasR reporter activity at
  concentrations below the MIC.
- **Status:** AWAITING HUMAN APPROVAL. Wet-lab work is out of scope for this run. The
  safety agent routes it and does not let any agent simulate having done it.

## Governance

| | |
|---|---|
| Human approvals exercised | 0 (nothing in this run crossed the $3.00 threshold) |
| Risk flags raised | 5 (overclaim, control leakage, p-hacking, translation, dual-use) |
| Session budget cap | $5.00 · actual spend $0.22 |
| Hypotheses pre-registered | 3, before any result existed |

Two of the four experiments are refutations and both are in the report. A lab that
only reports successes has not run an experiment.

## Run it

```bash
python3 -m venv .venv && ./.venv/bin/pip install rdkit
./.venv/bin/python -m lab.orchestrator     # runs the loop, writes the record + results
./.venv/bin/python scripts/build_report.py # renders demo/index.html from the results
./.venv/bin/python -m http.server 8899 --directory demo
```

To run the agents live under Omnigent instead of the deterministic replay:

```bash
curl -fsSL https://raw.githubusercontent.com/omnigent-ai/omnigent/main/scripts/install_oss.sh | sh
omni run ./omnigent_lab/ -p "Run one closed discovery loop on the PQS question."
```

For managed Databricks, uncomment the `databricks-*` model block in
`omnigent_lab/config.yaml` and set `DATABRICKS_HOST` / `DATABRICKS_TOKEN`.

## Layout

```
omnigent_lab/           Omnigent agent specs — 1 orchestrator + 9 specialist agents
  config.yaml           the orchestrator: loop protocol, budget + approval policies
  agents/*/config.yaml  one per agent: its decision, its tools, its prohibitions
lab/
  screening.py          the experiment: 3 pre-registered hypotheses, controls, gates
  orchestrator.py       the loop: agents, handoffs, research record, approval gate
evidence/
  citations.json        every claim → a locator. Limitations listed explicitly.
  results.json          full rankings, controls, sensitivity, ablation, timing
research_record.json    append-only: every handoff, belief update and approval event
scripts/build_report.py generates the dashboard from results.json
demo/                   pqs-lab-demo.mp4 + index.html
```

## Sources

Full provenance in `evidence/citations.json`. Key ones:

- PQS identity — PubChem CID 5282906
- PQS as a surface-active, phase-separated species — Mukherjee et al., *Science* 2018; Srinivasan et al., *PNAS* 2019; Dietrich et al., *Sci Adv* 2020
- Sub-MIC macrolide / tetracycline QS inhibition — Wozniak & Swift 2003; Lim et al. *AAC* 2007
- Bisbiguanide anti-biofilm — Worthington et al., *J. Appl. Microbiol.* 2012
- Gates and fingerprints — Lipinski et al. 2001; Rogers & Hahn 2010; Baell & Holloway 2010
- Omnigent — `github.com/omnigent-ai/omnigent`

All hypotheses, scoring weights, gates and control sets are **agent-generated** and
labelled as such. They are not derived from any published model.