# Two-minute demo script

Target: 2:00. The video in `demo/pqs-lab-demo.mp4` is the dashboard walkthrough;
this is the narration to cut against it.

---

**0:00 — Question (8s)**

> This lab has one question: which FDA-approved drugs quench the *P. aeruginosa*
> quorum-sensing signal, PQS? Anti-virulence is the interesting part — an agent
> that blocks the signal without blocking growth isn't expected to select for
> antibiotic resistance. That expectation is a hypothesis, not a fact.

**0:08 — The agents (12s)**

> Ten Omnigent agents. Six own a scientific decision: literature decides what's
> admissible, hypothesis writes falsifiable claims, planner picks the next test
> under budget, screener produces evidence and never interprets it, critic
> attacks the result, decision freezes it. Literature fans out to three API agents
> in parallel. Safety holds a veto.

**0:20 — H1 fails (18s)**

> Experiment one is the obvious screen: rank by 2D similarity to PQS. PQS is a
> twelve-carbon aliphatic lactone. Nothing in the library reaches even 0.20
> similarity. Zero candidates retained. A fingerprint can't express "hydrophobic
> and basic" — which is the property that matters.

**0:38 — The pivot (16s)**

> The critic doesn't call that a null result. AUC is 0.77 — there's signal in the
> ordering, just nothing actionable at the gate. So the assumption reopens: the
> literature says PQS is secreted as a surface-active micellar species. Quenching
> it is a physicochemical problem, not a shape-matching problem.

**0:54 — H2 gets direction, not recall (14s)**

> Hypothesis two uses property space. Chlorhexidine — the strongest documented
> anti-biofilm agent here — goes to rank one. But chloroquine-class distractors
> outrank the macrolides with published QS activity. Recall 0.13. Unusable.

**1:08 — H3, the synthesis (16s)**

> Hypothesis three is two mechanisms. A: surface sequestration. B: direct
> perturbation of QS gene expression — a literature prior over the antibiotic
> classes with published sub-MIC activity. Recall 0.63, specificity 1.00, AUC 1.00.

**1:24 — The gate, not the ranking (14s)**

> And the gate was still the binding constraint. Chlorhexidine is 505 daltons. It
> fails Lipinski. But a topical antiseptic acting on a bacterial surface doesn't
> have to be a systemic drug. Relax the gate: recall 0.75, specificity 1.00.
> Six of eight positives in the top ten, all six negatives rejected.

**1:38 — Acceleration + limits (14s)**

> Seventy thousand compounds an hour against fifty for serial manual triage.
> That's dominated by descriptor compute, not reasoning — I'm saying so because it
> determines where the real 10× is: Spark-scale descriptor batching and a 3D
> docking tier. No docking here, no wet lab, direct quenching unmeasured.

**1:52 — Next experiment + governance (8s)**

> Next: a LasR luciferase quench assay, ± candidate, at sub-MIC, against PAO1 and
> an isogenic *lasI*⁻. Blocked pending human approval — the safety agent won't let
> any agent simulate wet lab. Two of four experiments were refutations and both
> are in the report.

**2:00 — Cut.**