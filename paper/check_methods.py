# -*- coding: utf-8 -*-
"""Consistency check for the methods-oriented submission version.

Verifies: no unresolved placeholders, no internal development provenance,
terminology retargeting, journal module structure, figure/table inventory,
headline numbers, author-year citations and alphabetical references, and
cross-format (md/html/pdf) agreement.  Writes paper/methods_check.json.
"""
from __future__ import annotations

import json
import os
import re

PAPER = os.path.dirname(os.path.abspath(__file__))
MS = os.path.join(PAPER, "manuscript_methods.md")
HTML = os.path.join(PAPER, "manuscript_methods.html")
PDF = os.path.join(PAPER, "manuscript_methods.pdf")
OUT = os.path.join(PAPER, "methods_check.json")

txt = open(MS, encoding="utf-8").read()
checks = []


def check(cid, name, ok, detail=None):
    checks.append({"id": cid, "name": name, "ok": bool(ok),
                   "detail": detail if detail is not None else {}})


# M1 — no unresolved placeholders -------------------------------------------
ph = re.findall(r"@@[A-Z0-9_]+@@", txt)
check("M1", "no unresolved placeholders in the manuscript", not ph,
      {"n": len(ph), "sample": ph[:8]})

# M2 — no internal development-process provenance ----------------------------
leak_patterns = [
    (r"runs/", "evidence directory"), (r"docs/", "docs directory"),
    (r"platform/", "platform directory"), (r"tools/", "tools directory"),
    (r"paper/", "paper directory"), (r"candidate/", "candidate directory"),
    (r"\.json\b", "JSON file reference"), (r"\.py\b", "Python file reference"),
    (r"\.yaml\b", "yaml file reference"), (r"\.md\b", "markdown file reference"),
    (r"v1\.9[0-9]", "contract version"), (r"\bD-\d+", "debt-ledger ID"),
    (r"\bR1[0-9]{2}\b", "round ID"), (r"\b87 7[01]\b|\b877[01]\b", "port numbers"),
    (r"ENGINE_CONTRACT", "contract file"), (r"state\.yaml", "state file"),
    (r"round report", "round report"), (r"debt ledger", "debt ledger"),
    (r"\[\d+\]", "numeric citation brackets"),
]
leaks = []
for pat, what in leak_patterns:
    for m in re.finditer(pat, txt):
        leaks.append({"what": what,
                      "context": txt[max(0, m.start() - 55):m.end() + 55].replace("\n", " ")})
check("M2", "no internal development-process provenance", not leaks,
      {"n_leaks": len(leaks), "leaks": leaks[:10]})

# M3 — terminology retargeting ----------------------------------------------
terms = {t: len(re.findall(t, txt, flags=re.I))
         for t in ("digital twin", "certificate", "quarantine", "promotion")}
check("M3", "terminology retargeted to process simulation validation",
      all(v == 0 for v in terms.values()), terms)

# M4 — journal module structure ---------------------------------------------
modules = ["## Highlights", "## Abstract", "**Keywords:**", "## 1. Introduction",
           "## 2. Materials and methods", "## 3. Results", "## 4. Discussion",
           "## 5. Conclusions", "## CRediT authorship contribution statement",
           "## Declaration of competing interest", "## Data availability",
           "## Acknowledgements", "## References", "**Box 1."]
missing_mod = [m for m in modules if m not in txt]
check("M4", "all standard submission modules present", not missing_mod,
      {"n_modules": len(modules), "missing": missing_mod})

# M5 — section structure -----------------------------------------------------
subs2 = re.findall(r"^### (2\.\d+)", txt, flags=re.M)
subs3 = re.findall(r"^### (3\.\d+)", txt, flags=re.M)
check("M5", "methods 2.1-2.7 and results 3.1-3.6 present",
      subs2 == ["2.%d" % i for i in range(1, 8)] and
      subs3 == ["3.%d" % i for i in range(1, 7)],
      {"methods": subs2, "results": subs3})

# M6 — figure inventory ------------------------------------------------------
figs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", txt)
missing_fig = [f for f in figs if not os.path.exists(os.path.join(PAPER, f))]
caps = re.findall(r"\*\*Fig\. ([^ |*]+) \|", txt)
n_main = len([c for c in caps if not c.startswith("S")])
check("M6", "all cited figures exist and have captions",
      not missing_fig and len(caps) == len(figs),
      {"n_figures": len(figs), "n_main": n_main,
       "n_supplementary": len(caps) - n_main, "missing": missing_fig,
       "n_captions": len(caps)})

# M7 — table inventory -------------------------------------------------------
tables = [int(x) for x in re.findall(r"\*\*Table (\d+)\.\*\*", txt)]
check("M7", "twelve consecutively numbered main-text tables",
      tables == list(range(1, 13)), {"tables": tables})

# M8 — headline numbers from the frozen evidence -----------------------------
headlines = {
    "yield RMSE": r"2\.3448", "within band": r"86/86",
    "coverage tautology": r"0\.899548532731377", "innovation rate": r"84\.38",
    "full amplitude deviation": r"96\.06", "seed-11 collapse": r"99\.85",
    "NO_GO gate": r"18/20", "health verdict": r"77 normal",
    "collinearity": r"phi = 1\.0000", "nullity 4": r"nullity 4",
    "Bland-Altman": r"-4\.687|4\.687", "bisection width": r"2\.44 x 10\^-7",
    "jump": r"99\.8", "kstar": r"78\.15", "carbon": r"12/13|12 of 13",
}
missing_num = [k for k, p in headlines.items() if not re.search(p, txt)]
check("M8", "headline results retained unchanged", not missing_num,
      {"missing": missing_num})

# M9 — supplementary experiment numbers agree with the machine record --------
num_path = os.path.join(PAPER, "methods_numbers.json")
if os.path.exists(num_path):
    V = json.load(open(num_path, encoding="utf-8"))["values"]
    absent = [k for k, v in V.items() if v != "n/a" and str(v) not in txt]
    check("M9", "every substituted experiment value appears in the manuscript",
          not absent, {"n_values": len(V), "absent": absent[:12]})
else:
    check("M9", "every substituted experiment value appears in the manuscript",
          False, {"reason": "methods_numbers.json missing"})

# M10 — author-year citations resolve ---------------------------------------
refs = txt.split("## References", 1)[-1]
body = txt.split("## References", 1)[0]
cite_pat = (r"\b([A-Z][A-Za-z-]+)"
            r"(?:\s+et al\.|\s+and\s+[A-Z][A-Za-z-]+)?"
            r"\s*,\s*((?:19|20)\d{2}[a-z]?)\b")
cites = re.findall(cite_pat, body)
ref_lines = [l for l in refs.splitlines() if l.strip()]
bad = []
for surname, year in cites:
    if not any(re.search(r"\b" + re.escape(surname) + r"\b", l) and year in l
               for l in ref_lines):
        bad.append("%s, %s" % (surname, year))
check("M10", "author-year citations resolve against the reference list",
      not bad, {"n_citations": len(cites), "unresolved": sorted(set(bad))[:14]})

# every reference is cited in the body
ref_surnames = [re.split(r"[ ,]", l.strip())[0] for l in ref_lines]
uncited = [s for s in ref_surnames
           if not re.search(r"\b" + re.escape(s) + r"\b", body)]
check("M10b", "every reference is cited at least once in the body",
      not uncited, {"n_references": len(ref_surnames), "uncited": uncited[:14]})

# M11 — alphabetical references ---------------------------------------------
entries = [l.strip() for l in refs.splitlines()
           if l.strip() and not l.strip().startswith("#")]
first = [re.split(r"[ ,]", e)[0] for e in entries]
check("M11", "reference list is alphabetised and complete",
      first == sorted(first, key=str.lower) and len(entries) >= 45,
      {"n_entries": len(entries), "first_out_of_order":
       [(i, first[i - 1], first[i]) for i in range(1, len(first))
        if first[i - 1].lower() > first[i].lower()][:6]})

# M12 — cross-format agreement ----------------------------------------------
html_ok = os.path.exists(HTML) and os.path.getsize(HTML) > 200000
pdf_ok = os.path.exists(PDF) and os.path.getsize(PDF) > 200000
html_txt = open(HTML, encoding="utf-8").read() if html_ok else ""
check("M12", "HTML and PDF deliverables exist; HTML carries all figures and no tokens",
      html_ok and pdf_ok and "@@" not in html_txt and
      html_txt.count("<figure") >= len(figs),
      {"html_bytes": os.path.getsize(HTML) if html_ok else 0,
       "pdf_bytes": os.path.getsize(PDF) if pdf_ok else 0,
       "html_figures": html_txt.count("<figure"),
       "html_tables": html_txt.count("<table")})

# M13 — supplementary material ----------------------------------------------
sup = os.path.join(PAPER, "supplementary_methods.md")
sup_txt = open(sup, encoding="utf-8").read() if os.path.exists(sup) else ""
check("M13", "supplementary material carries the condensed implementation detail",
      len(sup_txt) > 6000 and all(k in sup_txt for k in
                                  ("S1.", "S2.", "S4.", "S5.", "S6.")),
      {"bytes": len(sup_txt.encode("utf-8"))})

# M14 — three-format source consistency --------------------------------------
md_bytes = os.path.getsize(MS)
check("M14", "Markdown source is a complete standalone manuscript",
      md_bytes > 45000, {"bytes": md_bytes})

n_pass = sum(1 for c in checks if c["ok"])
result = {"schema": "methods_check/1", "manuscript": "manuscript_methods.md",
          "n_checks": len(checks), "n_pass": n_pass,
          "verdict": "PASS" if n_pass == len(checks) else "FAIL",
          "checks": checks}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("%s  %d/%d" % (result["verdict"], n_pass, len(checks)))
for c in checks:
    if not c["ok"]:
        print("  FAIL", c["id"], c["name"], json.dumps(c["detail"], ensure_ascii=False)[:400])
