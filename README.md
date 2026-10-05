# truthfully

An agentic AI run for scientific discovery. Six AI agents screened 60 approved drugs against the chemical signal bacteria use
to organise an infection, and narrowed the list to the 7 most worth testing.

Two of the four ideas they tried were wrong, and both are reported here as
failures rather than left out.

**Nothing was tested in a laboratory.** No compound was measured against real
bacteria. Whether any of them actually blocks the signal is unknown. The output
is a shortlist for someone with a lab bench to pick up, not a discovery.

Built for the Databricks Omnigent challenge at Hack Nation, 3 October 2026.
Runs entirely on your own computer. No account, no API key, no cloud.

**Live:** https://hack-nation-3-10-2026.vercel.app

```bash
git clone https://github.com/rayanecommonW/hack-nation-3-10-2026.git
cd hack-nation-3-10-2026
python3 -m venv .venv && ./.venv/bin/pip install rdkit
./.venv/bin/python -m lab.orchestrator      # re-runs the whole discovery loop
./.venv/bin/python scripts/devserver.py 8899  # browse it at localhost:8899
```

No account, no API key, no cloud account. RDKit is the only dependency, and it
runs on your machine.

---

## The question, in plain terms

Bacteria do not attack alone. *Pseudomonas aeruginosa*, which causes lung
infections in people with weakened lungs, releases a chemical signal that tells
its own cells to switch on the genes that cause damage. Biologists call this
process **quorum sensing**. The signal is a molecule called **PQS**.

A drug that blocked PQS would leave the bacteria unable to organise the attack.
This is more interesting than an antibiotic, which kills bacteria and therefore
creates selection pressure for resistance. A drug that only blocks the signal is
expected not to create that pressure.

That expectation is a theory, not an established fact, and testing it needs real
laboratory work this project has not done.

## What happened

Four different ideas about what makes a drug block PQS were tested. The first two
did not survive. "Refuted" below means the idea failed its own stated test.

| # | Hypothesis | Gate | Verdict | Recall | Specificity | AUC |
|---|---|---|---|---|---|---|
| 1 | **H1** fingerprint proximity to PQS | systemic | REFUTED | 0.00 | 1.00 | 0.77 |
| 2 | **H2** cationic-amphiphile property space | systemic | REFUTED | 0.13 | 1.00 | 0.71 |
| 3 | **H3** two-mechanism ensemble | systemic | SUPPORTED | 0.63 | 1.00 | 1.00 |
| 4 | **H3** two-mechanism ensemble | surface agent | **SUPPORTED** | **0.75** | **1.00** | **1.00** |

Accepted shortlist: chlorhexidine, moxifloxacin, levofloxacin, ofloxacin,
ciprofloxacin, norfloxacin, alexidine, clindamycin.

### Where it turned

**Idea 1 returned nothing, and that is not a real answer.** The standard approach
ranks drugs by how closely their chemical shape resembles PQS. PQS is a simple
chain of twelve carbons, and nothing in the panel looks like it. Zero drugs passed.
But the ranking still ordered the known cases better than chance, which is the
signature of the *filter* failing rather than the *idea* failing.

**So the assumption was reopened.** PQS is released as a slippery, fat-loving
molecule that mixes with surfactants. Blocking it is therefore a question about
physical properties, not shape. Idea 2 ranks by physical properties instead.

**Idea 2 found the right drug but the wrong order.** Chlorhexidine, the strongest
documented biofilm drug in the panel, rose to rank one. But drugs that interfere
with the signal for unrelated reasons crowded out the antibiotics with real
published evidence. Recall 0.13.

**Idea 3 combined both.** Physical properties, plus credit for drug families already
reported to disrupt this signalling. Recall 0.63, specificity 1.00.

**Then the filter turned out to be the real constraint.** Chlorhexidine is slightly heavier than the
molecular-weight cutoff normally applied to drugs meant to be swallowed. But a surgical
antiseptic used on skin was never meant to be swallowed, so that limit did not
apply. Removing it recovered the last two drugs.

## What this does not show

Read this before the numbers above, not after.

- **Nothing was measured in a laboratory.** No compound was tested against real
  bacteria. No docking, no binding value, no potency figure. Whether any of them
  blocks the signal is unknown, and that is the only question that matters.
- **The known cases were kept out of the ranking.** Eight drugs whose behaviour is
  documented were scored only after the ranking was frozen. None is a feature, a
  threshold or a weight. The critic agent is required to check this from the source
  code on every run.
- **Eight known cases is a small sample.** Six of eight is a useful sign, far too
  small a number to treat as accuracy.
- **Part of the score comes from published research, not data.** One term rewards
  drug families already reported to interfere with this signal, and it decides most
  of the outcome. Removing it takes the known cases found from six down to two.
- **Sixty drugs, not the full library.** About sixteen hundred are approved. Sixty
  were bundled in so the search runs identically with no internet access.
- **The speed figure is about computing, not thinking.** It measures how fast
  formulas run, not how good the reasoning is. One person could check a list this
  size in an afternoon.
- **The ideas are the system's own.** Nobody published these explanations or these
  weights. They were generated during the run and are labelled as guesses.

**Next step, held for human approval:** measure signal loss in live bacteria, with
and without each candidate drug. That needs laboratory equipment, so no agent here
is permitted to pretend it has been done.

## The agents

Six agents, each owning exactly one scientific decision. Orchestrated by
[Omnigent](https://github.com/omnigent-ai/omnigent).

An agent here is one AI role with a single job and a written rule about what it may
not do. A framework called [Omnigent](https://github.com/omnigent-ai/omnigent) runs
them.

| Agent | Its one job | The rule it cannot break |
|---|---|---|
| `safety_agent` | Keeps the risk list, routes approvals | Can veto, and blocks claims that overstate the evidence |
| `literature_agent` | Decides what counts as evidence | Rejects any claim without a link to its source |
| `hypothesis_agent` | Writes explanations | Must state what would disprove it, before any data exists |
| `planner_agent` | Chooses the next test | Anything over budget waits for a human |
| `screener_agent` | Runs the test | Cannot return an opinion, only numbers |
| `critic_agent` | Tries to prove the result wrong | Must check for leakage in the source before agreeing |
| `decision_agent` | Accepts or rejects | Only accepts results that clear fixed thresholds |

Every handoff is written to `research_record.json` with its own inputs, outputs and
duration, so any figure in the report traces back to the step that produced it.

## How it works

1. **A person writes the question** and what would count as an answer, before
   anything starts. No agent may change it.
2. **Three agents search scientific databases** at once. Anything without a source
   link is rejected, and the agents' own guesses are filed as guesses.
3. **Three explanations are written down in advance,** each with the result that
   would disprove it. Committing to these before data exists is what makes the two
   failures later meaningful.
4. **The planner picks a test** by expected learning over cost, inside budget.
5. **The screener runs it** and returns numbers only, never an opinion.
6. **The critic attacks it** against documented drugs and returns refuted,
   inconclusive or supported. Back to step 4 until something survives.
7. **The decision agent accepts or rejects** and writes the next experiment.

## Where things live

The science and the orchestration are separate on purpose, so the drug search can be
re-run and checked without an AI framework in the loop.

| Path | What it is |
|---|---|
| `lab/screening.py` | The drug search: three ideas, two filters, the known-case tests |
| `lab/orchestrator.py` | The loop: agents, budget, handoffs, approval gate |
| `lab/service.py` | The read-only JSON endpoint the website calls |
| `omnigent_lab/` | Agent definitions, one file per role |
| `index.py` | A small web server: routing, headers, static files |
| `evidence/results.json` | Every number in the report |
| `evidence/citations.json` | Every claim mapped to a DOI or PubChem ID |

## Notes for anyone reading the code

**The orchestrator has two drivers.** The Omnigent specs in `omnigent_lab/` describe
the agents for live use. `lab/orchestrator.py` executes the identical decision logic
deterministically with no model in the path, so the recorded result is reproducible
and the demo cannot fail on a flaky API.

**The screen runs in a child process.** RDKit is imported inside
`lab/service_worker.py` and launched with `close_fds=True`. If the chemistry engine
ever crashes, it takes down a subprocess instead of the web process, and the service
falls back to the committed run.

**RDKit is not deployed.** It is 265 MB unpacked against Vercel's 250 MB serverless
function limit, and when a build overshoots Vercel drops the entire function while
the site still serves, so the failure only shows up when you call the API. The
deployed service therefore answers from `evidence/results.json`. Clone the repo and
`python -m lab.orchestrator` recomputes it, and both paths produce the same figures.

**The WSGI handler sets almost no headers.** An earlier version set
`Content-Length` itself, which the WSGI server also sets, and Chrome rejects a
response carrying that header twice. Let the server own it.

**Fonts are self-hosted.** Latin and Latin Extended subsets only, 440 KB after
collapsing the variable-font duplicates. Self-hosted because the Content Security
Policy has no third-party origins, and a font CDN would have meant either weakening
the policy or leaving readers on a silent fallback face.

**The dev server uses waitress, not wsgiref.** `wsgiref` serialises requests and
mis-frames the response body when the handler forks a subprocess, which presents as
the page receiving headers and then an empty body.

## Sources

Full provenance with limitations in `evidence/citations.json`.

- PQS identity: PubChem CID 5282906
- PQS as a surface-active, phase-separated species: Mukherjee et al., *Science* 2018; Srinivasan et al., *PNAS* 2019; Dietrich et al., *Sci Adv* 2020
- Sub-MIC macrolide and tetracycline quorum-sensing inhibition: Wozniak & Swift 2003; Lim et al., *AAC* 2007
- Bisbiguanide anti-biofilm activity: Worthington et al., *J. Appl. Microbiol.* 2012
- Gates and fingerprints: Lipinski et al. 2001; Rogers & Hahn 2010; Baell & Holloway 2010
- Omnigent: `github.com/omnigent-ai/omnigent`

All hypotheses, weights, gates and control sets are agent-generated and labelled as
hypotheses. They are not derived from any published model.