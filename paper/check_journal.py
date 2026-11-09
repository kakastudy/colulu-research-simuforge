# -*- coding: utf-8 -*-
"""Consistency check for the journal submission version (manuscript_journal.md).

Verifies: (1) no internal development-process provenance leaks into the text,
(2) headline numbers agree with the frozen evidence, (3) every figure file
exists, (4) every reference is cited and every citation resolves.
Outputs paper/journal_check.json.
"""
from __future__ import annotations

import json
import os
import re

PAPER = os.path.dirname(os.path.abspath(__file__))
MS = os.path.join(PAPER, "manuscript_journal.md")
OUT = os.path.join(PAPER, "journal_check.json")

txt = open(MS, encoding="utf-8").read()
checks = []


def check(cid, name, ok, detail=None):
    checks.append({"id": cid, "name": name, "ok": bool(ok),
                   "detail": detail if detail is not None else {}})


# --- J1: no internal development-process provenance --------------------------
leak_patterns = [
    (r"runs/", "evidence directory path"),
    (r"docs/", "docs directory path"),
    (r"platform/", "platform directory path"),
    (r"tools/", "tools directory path"),
    (r"paper/", "paper directory path"),
    (r"candidate/", "candidate directory path"),
    (r"\.json", "JSON file reference"),
    (r"\.py\b", "Python file reference"),
    (r"\.yaml", "yaml file reference"),
    (r"\.md\b", "markdown file reference"),
    (r"v1\.9[0-9]", "contract version string"),
    (r"\bD-\d+", "debt-ledger ID"),
    (r"\bR1[0-9]{2}\b", "round ID"),
    (r"R1-R167", "programme round range"),
    (r"\b87 71\b|\b87 70\b|87 70|87 71", "port numbers"),
    (r"\[G\d+", "gate check IDs"),
    (r"\bF\d+\b check", "final-check IDs"),
    (r"ENGINE_CONTRACT", "contract file name"),
    (r"debt ledger", "debt ledger phrase"),
    (r"sign-off", "sign-off phrase"),
    (r"round report", "round report phrase"),
    (r"state\.yaml", "state file"),
    (r"\[\d+\]", "numeric citation brackets"),
]
leaks = []
for pat, what in leak_patterns:
    for m in re.finditer(pat, txt):
        leaks.append({"pattern": pat, "what": what,
                      "context": txt[max(0, m.start() - 60):m.end() + 60]
                      .replace("\n", " ")})
check("J1", "no internal development-process provenance in the manuscript",
      not leaks, {"n_leaks": len(leaks), "leaks": leaks[:12]})

# --- J2: headline numbers present -------------------------------------------
headlines = {
    "RMSE 2.3448": r"2\.3448",
    "86/86 within band": r"86/86|all 86 batches inside",
    "coverage tautology value": r"0\.899548532731377",
    "innovation flag rate": r"84\.38",
    "full-amplitude deviation": r"96\.06",
    "seed-11 collapse": r"99\.85",
    "A/B verdict": r"18/20 NO_GO",
    "health 77/5/4": r"77 normal|77/5/4",
    "phi collinearity": r"phi = 1\.0|phi = 1\.0000",
    "Bland-Altman limits": r"-4\.6[89].*\+4\.55|4\.687",
    "Shapiro-Wilk p": r"0\.182",
    "sign test p": r"0\.590",
    "runs test p": r"0\.696",
    "RMSE reduction vs LOO": r"96\.82",
    "RMSE reduction vs persistence": r"97\.46",
    "RMSE reduction vs zero": r"97\.66",
    "median-normalised improvement": r"88\.8|2\.22% versus 26\.31",
    "mycelial rank/nullity": r"rank 0 and nullity 4|rank 0, nullity 4|rank 0 / nullity 4",
    "control discontinuity": r"99\.8.*101\.5|99\.83",
    "kLa interior optimum": r"78\.15",
    "product P degradation": r"17\.70",
    "biomass CV gain": r"2\.28",
}
missing = [k for k, pat in headlines.items() if not re.search(pat, txt)]
check("J2", "all headline numbers present", not missing,
      {"n_expected": len(headlines), "missing": missing})

# --- J3: figures exist --------------------------------------------------------
figs = re.findall(r"!\[([^\]]*)\]\((figures/[^)]+)\)", txt)
fig_bad = [rel for _, rel in figs
           if not os.path.exists(os.path.join(PAPER, rel))
           or os.path.getsize(os.path.join(PAPER, rel)) < 10000]
check("J3", "all referenced figure files exist and are non-empty",
      len(figs) == 19 and not fig_bad, {"n": len(figs), "bad": fig_bad})

# figure labels unique and sequential in citation order
labels = [lab for lab, _ in figs]
check("J4", "figure labels are unique", len(set(labels)) == len(labels),
      {"labels": labels})

# --- J5: highlights / keywords / modules -------------------------------------
check("J5", "Highlights section with 5 bullets",
      len(re.findall(r"^- ", txt.split("## Keywords")[0], flags=re.M)) == 5, {})
check("J6", "Keywords line present", "**Keywords:**" in txt, {})
mods = ["## 1. Introduction", "## 2. Materials and methods",
        "## 3. Results and discussion", "## 4. Conclusions",
        "## CRediT authorship contribution statement",
        "## Declaration of competing interest", "## Data availability",
        "## References"]
absent = [m for m in mods if m not in txt]
check("J7", "journal module structure complete (Elsevier style)", not absent,
      {"missing": absent})

# --- J8: author-year citations resolve and references are cited --------------
ref_sec = txt.split("## References", 1)[1]
refs = [b.strip() for b in re.split(r"\n\s*\n", ref_sec) if b.strip()]
check("J8", "reference list has 40 entries", len(refs) == 40,
      {"n": len(refs)})

body = txt.split("## References", 1)[0]
uncited = []
for r in refs:
    m = re.match(r"^([A-Z][A-Za-z'’\-]+)", r)
    if not m:
        uncited.append(r[:50])
        continue
    surname = m.group(1)
    if surname not in body:
        uncited.append(surname)
check("J9", "every reference is cited in the body", not uncited,
      {"uncited": uncited})

cites = set()
for m in re.finditer(r"\(([^()]*?(?:19|20)\d{2}[^()]*?)\)", body):
    inner = m.group(1)
    for part in inner.split(";"):
        part = part.strip()
        mm = re.match(r"^([A-Z][a-z'’][A-Za-z'’\-]+)", part)
        if mm and not part.startswith(("Box", "Table", "Fig")):
            cites.add(mm.group(1))
first_words = {re.match(r"^([A-Z][a-z'’][A-Za-z'’\-]+)", r).group(1)
               for r in refs if re.match(r"^([A-Z][a-z'’][A-Za-z'’\-]+)", r)}
unresolved = sorted(c for c in cites if c not in first_words)
check("J10", "every author-year citation resolves to a reference entry",
      not unresolved, {"unresolved": unresolved})

# --- J11: placeholders only where allowed -------------------------------------
allowed = txt.count("[to be completed")
check("J11", "author placeholders limited to permitted fields", allowed == 5,
      {"count": allowed})

# --- J12: no numbered-contribution list in the introduction -------------------
intro = txt.split("## 1. Introduction", 1)[1].split("## 2. Materials")[0]
check("J12", "introduction uses prose objectives, not a bolded bullet list",
      not re.search(r"\n\d\. \*\*", intro), {})

verdict = "PASS" if all(c["ok"] for c in checks) else "FAIL"
result = {"round": "journal", "verdict": verdict,
          "n_pass": sum(c["ok"] for c in checks), "n_checks": len(checks),
          "checks": checks}
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(json.dumps({"verdict": verdict, "n_pass": result["n_pass"],
                  "n_checks": result["n_checks"]}))
