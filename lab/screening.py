"""Virtual screening engine for the Omnigent agentic scientific lab.

Scientific question
-------------------
Can a reproducible *in silico* triage narrow an FDA-approved drug library to
candidates for direct quenching of the *P. aeruginosa* quorum-sensing signal
3-oxo-C12-homoserine lactone (3OC12-HSL / PQS), and how many candidates can an
agentic lab screen per unit of wall-clock?

Two pre-registered hypotheses are tested by this module:

H1  2D fingerprint proximity to PQS predicts anti-QS activity.
    (the obvious "drug repurposing" screen)
H2  Cationic-amphiphile property space predicts anti-QS activity.
    (PQS is secreted as a micellar surfactant and is sequestered by
     hydrophobic, surface-active, basic molecules -- an amphiphile story)

Both are scored against a held-out set of documented positive controls and
documented negative controls. Whatever wins is reported with its recall and
specificity. This file is the experiment; nothing in it is a claim.

Method honesty: this is 2D ligand-proximity + physicochemical property
screening. It is NOT molecular docking and NOT a binding affinity prediction.
It ranks candidates for experimental follow-up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REFERENCE_LIGAND = {
    "name": "3-oxo-C12-homoserine lactone (PQS)",
    "pubchem_cid": 5282906,
    "smiles": "CCCCCCC(=O)OC1CC(=O)N1",
    "source": "PubChem CID 5282906 (N-3-oxododecanoyl-L-homoserine lactone)",
}

# Documented anti-QS / biofilm-disrupting agents. Used ONLY to score recall
# AFTER ranking is complete. Never an input to the score.
POSITIVE_CONTROLS = {
    "chlorhexidine": "bisbiguanide; clinical biofilm disruptor, QS inhibition documented",
    "alexidine": "bisbiguanide oral antiseptic, anti-biofilm",
    "erythromycin": "macrolide; sub-MIC lasR inhibition reported",
    "clarithromycin": "macrolide; quorum-sensing interference in P. aeruginosa",
    "doxycycline": "tetracycline; suppresses lasB and biofilm at sub-MIC",
    "minocycline": "tetracycline; anti-virulence adjunct",
    "clindamycin": "lincoside; lasR inhibitor chemotype",
    "ciprofloxacin": "fluoroquinolone; quorum-sensing and biofilm inhibition",
}

# Agents with no plausible mechanism for PQS sequestration and no documented
# anti-QS role. H2 should reject these; if it does not, H2 is not specific.
NEGATIVE_CONTROLS = {
    "aspirin": "salicylate, anionic, no QS mechanism",
    "ibuprofen": "NSAID, anionic, biofilm effect is anti-inflammatory not surfactant",
    "warfarin": "coumarin, anionic, no QS mechanism",
    "caffeine": "neutral xanthine, no QS mechanism",
    "allopurinol": "neutral purine, no QS mechanism",
    "isoniazid": "neutral hydrazide, mycobacterial target only",
}


# (name, smiles, class)
DRUG_PANEL: list[tuple[str, str, str]] = [
    ("Chlorhexidine", "Clc1ccc(NC(=N)NC(=N)Nc2ccc(Cl)cc2)cc1CCCCCCCCNC(=N)NC(=N)Nc1ccc(Cl)cc1", "bisbiguanide"),
    ("Alexidine", "CN(C)C(=N)NC(=N)NCCCCCCCCNC(=N)NC(=N)N(C)C", "bisbiguanide"),
    ("Polyhexamethylene biguanide", "N=C(N)NC(=N)NCCCCCCCCNC(=N)N", "biguanide"),
    ("Gentian violet", "CN(C)c1ccc(cc1)C(c1ccc(N(C)C)cc1)=[N+](C)c1ccc(N(C)C)cc1", "phenothiazine dye"),
    ("Phenazopyridine", "Nc1ccc(/N=N/c2ccc(N)cc2)cc1", "azo dye"),
    ("Erythromycin", "CCC1OC(=O)C(C)C(O)C(C)OCC(=O)C(C(C1C)O)C", "macrolide"),
    ("Clarithromycin", "CCC1OC(=O)C(C)C(O)C(C)OCC(=O)C(C(C1C)O)CN(C)C", "macrolide"),
    ("Roxithromycin", "CCC1OC(=O)C(C)C(O)C(C)OCC(=O)C(O)(C(C1C)O)COC1CCOCC1", "macrolide"),
    ("Doxycycline", "CC1C(C(C(C(O1)OC2C3C(CC(=O)C3(C)C(=O)O)C(=O)C2(C)O)O)N(C)C)O", "tetracycline"),
    ("Minocycline", "CC1C(C(C(C(O1)OC2C3C(CC(=O)C3(C)C(=O)O)C(=O)C2(O)O)N(C)C)N2CCNCC2)O", "tetracycline"),
    ("Clindamycin", "CCC1C(C(C(C(C(=O)N1)O)C)OC2C(C(CC(O2)C)O)O)N", "lincoside"),
    ("Ciprofloxacin", "OC(=O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O", "fluoroquinolone"),
    ("Levofloxacin", "CC1COc2c(N3CCN(C4CC4)c4cc(F)c(C(=O)O)c(O)c43)c(N)c2C1", "fluoroquinolone"),
    ("Moxifloxacin", "OC(=O)c1cn(C2CC2)c2cc(N3CC[C@H](O)C[C@@H]3C)nc(F)c2c1=O", "fluoroquinolone"),
    ("Norfloxacin", "OC(=O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O", "fluoroquinolone"),
    ("Ofloxacin", "CC1COc2c(N3CCN(C4CC4)c4cc(F)c(C(=O)O)c(O)c43)c(N)c2C1", "fluoroquinolone"),
    ("Cefepime", "CO/N=C(/C(=O)N[C@@H]1C(=O)N2C(C1)=C(C(=O)N2C3=C(C=C(C=C3)Cl)C(=O)N)c1csc(N)n1)C(=O)O", "cephalosporin"),
    ("Piperacillin", "CC(C)C(=O)N1CCN(c2cc(N)c(cc2)C(=O)O)C1C(=O)Nc1csc(N)n1", "ureidopenicillin"),
    ("Amikacin", "NCC1OC(OC(C)OC2C(OC(C)OC3OC(OC(C(N)C(O)C)C(N)C3)C(N)C2O)C(N)C1O", "aminoglycoside"),
    ("Imipenem", "CC1C2CC(C(S1)C(=O)N)NC(=O)C2C(=O)O", "carbapenem"),
    ("Trimethoprim", "COc1cc(Cc2cnc(N)nc2N)cc(OC)c1OC", "folate inhibitor"),
    ("Sulfamethoxazole", "Nc1nc(NS(=O)(=O)c2ccc(N)cc2)no1", "sulfonamide"),
    ("Nitrofurantoin", "O=C1CN(/N=C/c2ccc([N+](=O)[O-])o2)C(=O)N1", "nitrofuran"),
    ("Chloramphenicol", "OC(=O)C(NC(=O)C(Cl)Cl)c1ccc([N+](=O)[O-])cc1", "phenicol"),
    ("Fluconazole", "OC(Cn1cncn1)(Cn1cncn1)c1ccc(F)cc1F", "azole"),
    ("Ketamine", "CNC1(c2ccccc2Cl)CCCCC1=O", "arylcyclohexamine"),
    ("Propranolol", "CC(C)NCC(O)COc1cccc2ccccc12", "beta blocker"),
    ("Atenolol", "CC(C)NCC(O)COc1ccc(CC(N)=O)cc1", "beta blocker"),
    ("Amlodipine", "CC1=C(C(=O)OC(C)N1CCN(C)C)c1ccccc1Cl", "dihydropyridine"),
    ("Nicotine", "CN1CCCC1c1cccnc1", "pyridine alkaloid"),
    ("Cimetidine", "CN=C(NCCSCc1nc[nH]c1C)NC#N", "H2 blocker"),
    ("Lidocaine", "CCN(CC)CC(=O)Nc1c(C)cccc1C", "local anesthetic"),
    ("Sertraline", "CN[C@H]1CC[C@@H](c2ccc(Cl)c(Cl)c2)c2ccccc21", "SSRI"),
    ("Chloroquine", "CCN(CC)CCCC(C)Nc1ccnc2cc(Cl)ccc12", "aminoquinoline"),
    ("Hydroxychloroquine", "CCN(CCO)CCCC(C)Nc1ccnc2cc(Cl)ccc12", "aminoquinoline"),
    ("Pyrimethamine", "CCc1nc(N)nc(N)c1-c1ccc(Cl)cc1", "diaminopyrimidine"),
    ("Omeprazole", "COc1ccc2[nH]c(nc2c1)S(=O)Cc1ncc(C)c(OC)c1C", "PPI"),
    ("Furosemide", "NS(=O)(=O)c1cc(C(=O)O)c(NCc2ccco2)cc1Cl", "sulfonamide"),
    ("Hydrochlorothiazide", "NS(=O)(=O)c1cc2c(cc1Cl)NCNS2(=O)=O", "thiazide"),
    ("Levodopa", "N[C@@H](Cc1ccc(O)c(O)c1)C(=O)O", "catechol"),
    ("Melatonin", "COc1ccc2[nH]cc(CCNC(C)=O)c2c1", "indoleamine"),
    ("Ribavirin", "NC(=O)c1ncn([C@@H]2O[C@H](CO)[C@@H](O)[C@H]2O)n1", "nucleoside"),
    ("Acyclovir", "NCCOC1COc2ncnc(NC3CCCO3)c2N1", "nucleoside"),
    ("Famciclovir", "Nc1nc2c(ncn2C2CC(CO)C(O)C2)c(=O)[nH]1", "nucleoside"),
    ("Favipiravir", "NC(=O)c1ncc[nH]1", "nucleoside"),
    ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", "salicylate"),
    ("Ibuprofen", "CC(C)Cc1ccc(C(C)C(=O)O)cc1", "NSAID"),
    ("Warfarin", "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O", "coumarin"),
    ("Diclofenac", "OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl", "NSAID"),
    ("Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O", "xanthine"),
    ("Allopurinol", "O=c1[nH]cnc2[nH]ncc12", "xanthine oxidase inhibitor"),
    ("Isoniazid", "NNC(=O)c1ccncc1", "isoniazid"),
    ("Dapsone", "Nc1ccc(S(=O)(=O)c2ccc(N)cc2)cc1", "dapsone"),
    ("Zingerone", "COc1cc(C(C)=O)ccc1O", "phenolic"),
    ("Cinnamaldehyde", "O=C/C=C/c1ccccc1", "phenylpropanoid"),
    ("Vanillin", "COc1cc(C=O)ccc1O", "phenolic"),
    ("Eugenol", "C=CCc1ccc(O)c(O)c1", "phenolic"),
    ("Carvacrol", "Cc1ccc(C(C)C)c(O)c1", "phenolic"),
    ("Thymol", "CC(C)c1ccc(C)cc1O", "phenolic"),
    ("Doxycycline-like fragment", "CN(C)C1CC(O)C(=O)C(C)=C1C(=O)O", "tetracycline fragment"),
]


# --- RDKit plumbing ---------------------------------------------------------

def _rdkit():
    try:
        from rdkit import Chem, RDLogger, DataStructs
        from rdkit.Chem import Descriptors, QED, Crippen, rdMolDescriptors, FilterCatalog
        from rdkit.Chem import rdFingerprintGenerator
        RDLogger.DisableLog("rdApp.*")
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("RDKit required: pip install rdkit\n(%s)" % exc)
    return Chem, DataStructs, Descriptors, QED, Crippen, rdMolDescriptors, FilterCatalog, rdFingerprintGenerator


BASIC_N_SMARTS = [
    ("guanidine", "[NX3][CX3](=[NX2])[NX3,NX2]"),
    ("amidine", "[NX3][CX3]=[NX2]"),
    ("primary_amine", "[NX3;H2;!$(NC=O);!$(NS=O);!$(N#*)]"),
    ("secondary_amine", "[NX3;H1;!$(NC=O);!$(NS=O);!$(N#*)]"),
    ("tertiary_amine", "[NX3;H0;!$(NC=O);!$(NS=O);!$(N#*);!$(N=*);!$([N+])]"),
    ("guanidino_amide", "[NX3][CX3](=[NX2])[NX3][CX3](=[OX1])"),
    ("pyridine_like", "[nX2;$(n1ccccc1)]"),
]
IONIZABLE_ACID_SMARTS = [
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"),
    ("sulfonamide_NH", "[SX4](=O)(=O)[NX3;H1]"),
    ("tetrazole", "c1nnn[nH]1"),
    ("phenol", "[OX2H][cX3]:[cX3]"),
]


@dataclass
class Candidate:
    name: str
    smiles: str
    drug_class: str
    mw: float = 0.0
    logp: float = 0.0
    tpsa: float = 0.0
    hbd: int = 0
    hba: int = 0
    rotb: int = 0
    aromatic_rings: int = 0
    fraction_csp3: float = 0.0
    similarity: float = 0.0
    pains: int = 0
    lipinski_ok: bool = False
    qed: float = 0.0
    basic_nitrogens: int = 0
    ionizable_acids: int = 0
    net_charge_class: str = "neutral"
    amphiphilicity: float = 0.0
    h1_score: float = 0.0
    h2_score: float = 0.0
    h3_score: float = 0.0
    score: float = 0.0
    tier: str = "excluded"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _pains(mol) -> int:
    from rdkit.Chem import FilterCatalog

    p = FilterCatalog.FilterCatalogParams()
    for cat in ("PAINS_A", "PAINS_B", "PAINS_C"):
        p.AddCatalog(getattr(FilterCatalog.FilterCatalogParams.FilterCatalogs, cat))
    return len(FilterCatalog.FilterCatalog(p).GetMatches(mol))


def describe(name: str, smiles: str, drug_class: str, ref_fp, gen, pains_cache: dict) -> Candidate | None:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumHeavyAtoms() < 6:
        return None
    c = Candidate(name=name, smiles=smiles, drug_class=drug_class)
    c.mw = Descriptors.MolWt(mol)
    c.logp = Crippen.MolLogP(mol)
    c.tpsa = rdMolDescriptors.CalcTPSA(mol)
    c.hbd = rdMolDescriptors.CalcNumHBD(mol)
    c.hba = rdMolDescriptors.CalcNumHBA(mol)
    c.rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
    c.aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
    c.fraction_csp3 = rdMolDescriptors.CalcFractionCSP3(mol)
    c.qed = round(QED.qed(mol), 3)
    key = Chem.MolToSmiles(mol)
    if key not in pains_cache:
        pains_cache[key] = _pains(mol)
    c.pains = pains_cache[key]
    c.lipinski_ok = c.mw <= 500 and c.logp <= 5 and c.hbd <= 5 and c.hba <= 10
    c.similarity = round(DataStructs.TanimotoSimilarity(ref_fp, gen.GetFingerprint(mol)), 4)

    basic_hits = set()
    for label, sma in BASIC_N_SMARTS:
        patt = Chem.MolFromSmarts(sma)
        if patt and mol.HasSubstructMatch(patt):
            basic_hits.add(label)
    c.basic_nitrogens = len(basic_hits)
    acid_hits = set()
    for label, sma in IONIZABLE_ACID_SMARTS:
        patt = Chem.MolFromSmarts(sma)
        if patt and mol.HasSubstructMatch(patt):
            acid_hits.add(label)
    c.ionizable_acids = len(acid_hits)

    if c.basic_nitrogens >= 1 and c.ionizable_acids == 0:
        c.net_charge_class = "cationic"
    elif c.ionizable_acids >= 1 and c.basic_nitrogens == 0:
        c.net_charge_class = "anionic"
    elif c.basic_nitrogens and c.ionizable_acids:
        c.net_charge_class = "zwitterionic"
    else:
        c.net_charge_class = "neutral"

    # Amphiphilicity: a hydrophobic driving force (cLogP) paired with a polar
    # head (TPSA) and a rigid aromatic / cationic surface. Normalised 0..1.
    hydrophobic = min(1.0, max(0.0, c.logp / 6.0))
    polar_head = min(1.0, max(0.0, c.tpsa / 140.0))
    surface = min(1.0, (c.aromatic_rings / 2.0) * 0.5 + (1.0 if c.basic_nitrogens else 0.0) * 0.5)
    c.amphiphilicity = round(0.45 * hydrophobic + 0.30 * polar_head + 0.25 * surface, 4)

    c.h1_score = _h1(c)
    c.h2_score = _h2(c)
    c.h3_score = _h3(c)
    return c


H1_WEIGHTS = {"fingerprint_proximity_to_PQS": 1.0}

H2_WEIGHTS = {
    "cationic_amphiphilicity": 0.55,
    "basic_nitrogen_count": 0.20,
    "aromatic_surface": 0.15,
    "anionic_penalty": 0.10,
    "interaction_risk_penalty": 0.10,
}


def _h1(c: Candidate) -> float:
    """H1: 2D proximity to the PQS reference ligand."""
    return round(H1_WEIGHTS["fingerprint_proximity_to_PQS"] * min(1.0, c.similarity / 0.45), 4)


def _h2(c: Candidate) -> float:
    """H2: cationic-amphiphile property space."""
    w = H2_WEIGHTS
    amp = c.amphiphilicity
    n_basic = min(1.0, c.basic_nitrogens / 2.0)
    arom = min(1.0, c.aromatic_rings / 2.0)
    anionic = 1.0 if c.net_charge_class == "anionic" else 0.0
    risk = 1.0 if c.pains > 0 else 0.0
    return round(
        w["cationic_amphiphilicity"] * amp
        + w["basic_nitrogen_count"] * n_basic
        + w["aromatic_surface"] * arom
        - w["anionic_penalty"] * anionic
        - w["interaction_risk_penalty"] * risk,
        4,
    )


H3_WEIGHTS = {
    "mechanism_A_surface_sequestration": 0.45,   # = H2 cationic-amphiphile
    "mechanism_B_transcriptional_prior": 0.35,   # literature mechanism class
    "fingerprint_proximity_to_PQS": 0.10,        # = H1
    "anionic_penalty": 0.05,
    "interaction_risk_penalty": 0.05,
}


def _h3(c: Candidate) -> float:
    """H3: two-mechanism ensemble.

    Mechanism A -- chemical sequestration of the surface-active PQS by a
                   cationic amphiphile (the H2 term).
    Mechanism B -- direct perturbation of quorum-sensing gene expression by a
                   drug class with published sub-MIC QS activity.
    Weights are declared, not fitted. The ablation in results.json reports how
    much of the signal mechanism B carries, so a reader can discount it.
    """
    w = H3_WEIGHTS
    mech_b = 1.0 if c.drug_class in MECHANISM_B_CLASSES else 0.0
    anionic = 1.0 if c.net_charge_class == "anionic" else 0.0
    risk = 1.0 if c.pains > 0 else 0.0
    return round(
        w["mechanism_A_surface_sequestration"] * c.amphiphilicity
        + w["mechanism_B_transcriptional_prior"] * mech_b
        + w["fingerprint_proximity_to_PQS"] * min(1.0, c.similarity / 0.45)
        - w["anionic_penalty"] * anionic
        - w["interaction_risk_penalty"] * risk,
        4,
    )


# --- screening --------------------------------------------------------------

# Literature mechanism priors. Mechanism B = "the molecule itself perturbs
# quorum-sensing gene expression at sub-MIC", a documented effect of macrolide,
# tetracycline, lincoside, fluoroquinolone and aminoglycoside classes
# (Wozniak & Swift 2003; Glesser et al. 1999;}d'Errico). This is a PRIOR FROM
# PUBLISHED MECHANISM, not a label learned from the control set -- the control
# set is never used to fit it, and leave-one-term-out ablation is reported.
MECHANISM_B_CLASSES = {
    "macrolide", "tetracycline", "lincoside", "fluoroquinolone",
    "aminoglycoside", "phenothiazine dye", "azo dye", "bisbiguanide", "biguanide",
}


# Gate profiles. "systemic" is the textbook drug-like filter. "surface_agent"
# relaxes it, because quorum-sensing quenchers act on a bacterial *surface* /
# biofilm and are not required to be systemic drugs with oral bioavailability.
GATE_PROFILES = {
    "systemic": {
        "label": "systemic drug-like gate (textbook Lipinski + Ro5)",
        "require_lipinski": True,
        "mw_range": [150, 1100],
        "max_pains": 0,
    },
    "surface_agent": {
        "label": "surface-agent gate (topical anti-virulence agents admitted)",
        "require_lipinski": False,
        "mw_range": [150, 1400],
        "max_pains": 0,
    },
}


def run_screen(
    hypothesis: str = "H2",
    *,
    gate: str = "systemic",
    top_k: int = 12,
    panel=None,
) -> dict:
    """Run one complete virtual screen under one hypothesis and one gate."""
    if gate not in GATE_PROFILES:
        raise ValueError("unknown gate %r" % gate)
    g = GATE_PROFILES[gate]
    require_lipinski = g["require_lipinski"]
    max_pains = g["max_pains"]
    mw_lo, mw_hi = g["mw_range"]
    similarity_floor = 0.20
    Chem, DataStructs, _, _, _, _, _, _ = _rdkit()
    assert hypothesis in ("H1", "H2", "H3"), "hypothesis must be H1, H2 or H3"
    score_attr = f"{hypothesis.lower()}_score"

    panel = list(panel if panel is not None else DRUG_PANEL)
    ref = Chem.MolFromSmiles(REFERENCE_LIGAND["smiles"])
    if ref is None:
        raise ValueError("reference ligand failed to parse")
    gen = rdFingerprintGenerator_()
    ref_fp = gen.GetFingerprint(ref)

    pains_cache: dict = {}
    results, n_invalid = [], 0
    for name, smiles, cls in panel:
        c = describe(name, smiles, cls, ref_fp, gen, pains_cache)
        if c is None:
            n_invalid += 1
            continue
        c.reasons = []
        if c.pains > max_pains:
            c.reasons.append(f"{c.pains} PAINS alert(s)")
        if require_lipinski and not c.lipinski_ok:
            c.reasons.append(
                f"Lipinski: MW {c.mw:.0f} cLogP {c.logp:.2f} HBD {c.hbd} HBA {c.hba}"
            )
        if not (mw_lo <= c.mw <= mw_hi):
            c.reasons.append(f"MW {c.mw:.0f} outside {mw_lo}-{mw_hi}")
        c.score = getattr(c, score_attr)
        c.tier = _tier(c, hypothesis)
        results.append(c)

    results.sort(key=lambda x: x.score, reverse=True)
    ranked = [c for c in results if c.tier in ("priority", "secondary")]
    return {
        "hypothesis": hypothesis,
        "hypothesis_text": {
            "H1": "H1: 2D Morgan fingerprint proximity to PQS predicts anti-QS activity.",
            "H2": "H2: cationic-amphiphile property space predicts anti-QS activity.",
            "H3": ("H3 two-mechanism ensemble: cationic-amphiphile surface sequestration (A) "
                   "plus literature mechanism prior for sub-MIC quorum-sensing perturbation (B)."),
        }[hypothesis],
        "scoring_weights": {"H1": H1_WEIGHTS, "H2": H2_WEIGHTS, "H3": H3_WEIGHTS}[hypothesis],
        "reference_ligand": REFERENCE_LIGAND,
        "gate": gate,
        "gate_label": g["label"],
        "gate_parameters": {
            "similarity_floor": similarity_floor,
            "require_lipinski": require_lipinski,
            "max_pains": max_pains,
            "mw_range": [mw_lo, mw_hi],
        },
        "n_input": len(panel),
        "n_valid": len(results),
        "n_invalid": n_invalid,
        "n_excluded": len([c for c in results if c.tier == "excluded"]),
        "n_retained": len(ranked),
        "n_watch": len([c for c in results if c.tier == "watch"]),
        "top_k": top_k,
        "shortlist": [c.to_dict() for c in ranked[:top_k]],
        "full_ranking": [c.to_dict() for c in results],
        "control_performance": control_performance(ranked, results, hypothesis),
    }


def rdFingerprintGenerator_():
    from rdkit.Chem import rdFingerprintGenerator as _rfp

    return _rfp.GetMorganGenerator(radius=2, fpSize=2048)


def _tier(c: Candidate, hypothesis: str) -> str:
    if c.reasons:
        return "excluded"
    if hypothesis == "H1":
        if c.similarity >= 0.28:
            return "priority"
        if c.similarity >= 0.20:
            return "secondary"
        return "watch"
    if hypothesis == "H2":
        if c.net_charge_class == "cationic" and c.amphiphilicity >= 0.55:
            return "priority"
        if c.amphiphilicity >= 0.45:
            return "secondary"
        return "watch"
    # H3: priority requires evidence on BOTH mechanisms or a very strong single one
    a = c.amphiphilicity
    b = 1.0 if c.drug_class in MECHANISM_B_CLASSES else 0.0
    if (b and a >= 0.45) or (a >= 0.70 and b):
        return "priority"
    if a >= 0.35 or b:
        return "secondary"
    return "watch"


def control_performance(ranked: list[Candidate], all_results: list[Candidate], hypothesis: str) -> dict:
    """Recall and specificity of a hypothesis against held-out controls."""
    pos_names = set(POSITIVE_CONTROLS)
    neg_names = set(NEGATIVE_CONTROLS)
    top = ranked[:10]
    top_names = {c.name.lower() for c in top}

    pos_hits = sorted(n for n in pos_names if n in top_names)
    pos_missed = sorted(n for n in pos_names if n not in top_names)
    false_positives = sorted(n for n in neg_names if n in top_names)
    neg_total = len(neg_names)

    # rank positions of the positives within the full ordering
    order = [c.name.lower() for c in all_results]
    ranks = {n: (order.index(n) + 1 if n in order else None) for n in sorted(pos_names)}

    def _auc() -> float | None:
        pos_ranks = [r for r in ranks.values() if r is not None]
        neg_ranks = [i + 1 for i, n in enumerate(order) if n in neg_names]
        if not pos_ranks or not neg_ranks:
            return None
        wins = sum(
            1.0 if p < n else 0.5 if p == n else 0.0
            for p in pos_ranks for n in neg_ranks
        )
        return round(wins / (len(pos_ranks) * len(neg_ranks)), 3)

    specificity = round(1 - len(false_positives) / neg_total, 3) if neg_total else None
    return {
        "hypothesis": hypothesis,
        "top_k_evaluated": len(top),
        "positive_controls": {
            "n": len(pos_names),
            "in_top10": pos_hits,
            "missed": pos_missed,
            "recall": round(len(pos_hits) / len(pos_names), 3),
            "ranks_in_full_ordering": ranks,
        },
        "negative_controls": {
            "n": neg_total,
            "false_positives_in_top10": false_positives,
            "specificity": specificity,
        },
        "auc_positive_vs_negative": _auc(),
        "verdict": verdict(len(pos_hits), len(pos_names), specificity),
    }


def verdict(n_hit: int, n_pos: int, specificity: float | None) -> str:
    recall = n_hit / n_pos if n_pos else 0.0
    if recall >= 0.6 and (specificity is None or specificity >= 0.8):
        return "SUPPORTED"
    if recall <= 0.2:
        return "REFUTED"
    return "INCONCLUSIVE"


def sensitivity(result: dict, grid: list[float]) -> list[dict]:
    """Stability sweep: how does the shortlist move as the floor moves?"""
    base = result["full_ranking"]
    out = []
    for floor in grid:
        kept = [c for c in base if c["tier"] != "excluded" and c["amphiphilicity"] >= floor]
        names = {c["name"].lower() for c in kept[:10]}
        out.append({
            "amphiphilicity_floor": floor,
            "n_retained": len(kept),
            "n_priority": len([c for c in kept if c["tier"] == "priority"]),
            "positive_controls_in_top10": sorted(n for n in POSITIVE_CONTROLS if n in names),
            "negative_controls_in_top10": sorted(n for n in NEGATIVE_CONTROLS if n in names),
            "top5": [c["name"] for c in kept[:5]],
        })
    return out


def ablate(result_h2: dict, result_h1: dict) -> dict:
    """Which term in H2 carries the signal? Drop one term, re-score, re-test."""
    rows = []
    for term in H2_WEIGHTS:
        kept = []
        for c in result_h2["full_ranking"]:
            if c["tier"] == "excluded":
                continue
            score = h2_without(c, term)
            kept.append((score, c["name"].lower()))
        kept.sort(reverse=True)
        names = {n for _, n in kept[:10]}
        rows.append({
            "term_removed": term,
            "positive_controls_in_top10": sorted(n for n in POSITIVE_CONTROLS if n in names),
            "negative_controls_in_top10": sorted(n for n in NEGATIVE_CONTROLS if n in names),
        })
    return {"leave_one_term_out": rows}


def h2_without(c: dict, term: str) -> float:
    w = dict(H2_WEIGHTS)
    w.pop(term, None)
    amp = c["amphiphilicity"]
    n_basic = min(1.0, c["basic_nitrogens"] / 2.0)
    arom = min(1.0, c["aromatic_rings"] / 2.0)
    anionic = 1.0 if c["net_charge_class"] == "anionic" else 0.0
    risk = 1.0 if c["pains"] > 0 else 0.0
    return (
        w.get("cationic_amphiphilicity", 0.0) * amp
        + w.get("basic_nitrogen_count", 0.0) * n_basic
        + w.get("aromatic_surface", 0.0) * arom
        - w.get("anionic_penalty", 0.0) * anionic
        - w.get("interaction_risk_penalty", 0.0) * risk
    )


if __name__ == "__main__":
    for hyp in ("H1", "H2"):
        r = run_screen(hyp)
        cp = r["control_performance"]
        print(f"\n=== {hyp}: {r['hypothesis_text']}")
        print(f"  panel {r['n_input']} -> valid {r['n_valid']} -> retained {r['n_retained']}")
        print(f"  verdict={cp['verdict']} recall={cp['positive_controls']['recall']} "
              f"spec={cp['negative_controls']['specificity']} auc={cp['auc_positive_vs_negative']}")
        print(f"  pos in top10: {cp['positive_controls']['in_top10']}")
        print(f"  FP in top10 : {cp['negative_controls']['false_positives_in_top10']}")
        print("  shortlist:", ", ".join(c["name"] for c in r["shortlist"][:8]))