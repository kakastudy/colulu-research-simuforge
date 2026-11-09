# -*- coding: utf-8 -*-
"""Consistency check for the manuscript against frozen runs/ evidence.

Read-only. Writes paper/manuscript_check.json.
"""
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS = os.path.join(ROOT, "runs")
PAPER = os.path.join(ROOT, "paper")


def load(name):
    with open(os.path.join(RUNS, name), "r", encoding="utf-8") as f:
        return json.load(f)


def txt(name):
    with open(os.path.join(PAPER, name), "r", encoding="utf-8") as f:
        return f.read()

MS = txt("manuscript.md")
checks = []


def check(cid, name, ok, got):
    checks.append({"id": cid, "name": name, "ok": bool(ok), "got": got})


# --- evidence values -------------------------------------------------------
fv = load("final_validation_v2.json")["results"]
errs = [r["yield_err"] * 100 for r in fv]
rmse = round((sum(e * e for e in errs) / len(errs)) ** 0.5, 4)
cov = load("r160_i3_coverage_tautology.json")
probe = load("r163_degradation_probe.json")
ab = load("r166_ab_gate.json")
op = load("r166_v2_optim.json")
acc = load("r156_acceptance.json")
gate = load("r167_platform_gate.json")
fin = load("r167_final_check.json")

check("C1", "86-batch RMSE 2.3448% computed from final_validation_v2.json",
      rmse == 2.3448 and len(errs) == 86, {"rmse": rmse, "n": len(errs)})
check("C2", "86/86 within +/-5%", sum(abs(e) <= 5 for e in errs) == 86,
      sum(abs(e) <= 5 for e in errs))
check("C3", "coverage tautology value matches manuscript",
      abs(cov["junk"]["X"]["coverage"] - 0.899548532731377) < 1e-12
      and all(v == 0.0 for v in cov["coverage_deltas"].values()),
      {"coverage": cov["junk"]["X"]["coverage"], "deltas": cov["coverage_deltas"]})
a = probe.get("A_summary", {})
n_scan = a.get("n_scanned", len(probe.get("A_screening", [])))
n_deg = a.get("n_degraded", sum(1 for r in probe.get("A_screening", []) if r.get("degraded")))
check("C4", "innovation trigger 27/32 = 84.38%",
      n_scan == 32 and n_deg == 27 and round(100 * n_deg / n_scan, 2) == 84.38,
      {"scanned": n_scan, "degraded": n_deg})
rows = ab["v2"]["full_scale_rows"]
mx = max(abs(r["delta_pp"]) for r in rows)
check("C5", "V2 full-amplitude max|delta| = 96.058784 pp, 3/6 collapses",
      abs(mx - 96.058784) < 1e-6 and ab["v2"]["full_scale_n_collapse"] == 3,
      {"max": mx, "collapse": ab["v2"]["full_scale_n_collapse"]})
s11 = op["seed_stage"]["per_seed"][0]
check("C6", "unseen seed 11 = 99.852368 pp / 2 collapses",
      abs(s11["max_abs_delta_pp"] - 99.852368) < 1e-6 and s11["n_collapse"] == 2
      and s11["feasible"] is False,
      {"max": s11["max_abs_delta_pp"], "collapse": s11["n_collapse"], "seed": s11["seed"]})
check("C7", "A/B 18/20 NO_GO and V2 optimisation NO_GO",
      ab["verdict"] == "NO_GO" and ab["n_pass"] == 18 and ab["n_checks"] == 20
      and op["verdict"] == "NO_GO",
      {"ab": [ab["n_pass"], ab["n_checks"]], "optim": [op["n_pass"], op["n_checks"]]})
nh = acc["summary"]["n_health"]
check("C8", "five-channel health 77/0/5/4",
      [nh.get(k) for k in ("normal", "benign", "degraded", "catastrophic")] == [77, 0, 5, 4], nh)
check("C9", "platform gate 25/25 and final check 20/20",
      gate["verdict"] == "PASS" and gate["n_pass"] == 25 and gate["n_checks"] == 25
      and fin["verdict"] == "PASS" and fin["n_pass"] == 20 and fin["n_checks"] == 20,
      {"gate": [gate["n_pass"], gate["n_checks"]], "final": [fin["n_pass"], fin["n_checks"]]})

# --- manuscript contains those values --------------------------------------
must = ["2.3448", "0.899548532731377", "84.38", "96.058784", "99.852368",
        "18/20", "25/25", "20/20", "rank 0 and nullity 4", "77, benign 0, degraded 5",
        "v1.97", "NO_GO"]
missing = [s for s in must if s not in MS]
check("C10", "all headline numbers appear verbatim in the manuscript",
      not missing, {"missing": missing})

# --- figures ---------------------------------------------------------------
figs = re.findall(r"!\[(Fig[^]]*)\]\(([^)]+)\)", MS)
fig_ok, fig_bad = [], []
for label, rel in figs:
    p = os.path.join(PAPER, rel)
    ok = os.path.exists(p) and os.path.getsize(p) > 10000
    (fig_ok if ok else fig_bad).append({"label": label, "path": rel,
                                        "bytes": os.path.getsize(p) if os.path.exists(p) else 0})
check("C11", "19 figure references resolve to non-empty PNG files",
      len(figs) == 19 and not fig_bad, {"n": len(figs), "bad": fig_bad})
captions = re.findall(r"^\*\*Fig\. ", MS, flags=re.M)
check("C12", "every figure has a bold standalone caption", len(captions) >= 19,
      len(captions))
# every figure except the Canvas-exported PFD must have a vector PDF counterpart
stems = {os.path.splitext(os.path.basename(rel))[0] for _, rel in figs}
missing_pdf = sorted(s for s in stems
                     if s != "fig12_pfd" and not os.path.exists(
                         os.path.join(PAPER, "figures", s + ".pdf")))
check("C13", "vector PDF counterparts for all figures except the Canvas PFD",
      not missing_pdf, {"n_pdf": len([f for f in os.listdir(
          os.path.join(PAPER, "figures")) if f.endswith(".pdf")]),
          "missing": missing_pdf})

# --- tables ----------------------------------------------------------------
tables = re.findall(r"\*\*Table \d+\.", MS)
check("C14", "11 main-text tables present", len(tables) == 11, len(tables))
check("C15", "machine-generated supplementary tables present",
      os.path.getsize(os.path.join(PAPER, "supplementary_tables.md")) > 5000,
      os.path.getsize(os.path.join(PAPER, "supplementary_tables.md")))

# --- references ------------------------------------------------------------
bib = txt("references.bib")
n_bib = len(re.findall(r"^@\w+\{", bib, flags=re.M))
ref_section = MS.split("## References", 1)[1]
refs = re.findall(r"^(\d+)\. ", ref_section, flags=re.M)
ref_ids = [int(x) for x in refs]
check("C16", "39 numbered references, contiguous 1..39",
      n_bib == 39 and ref_ids == list(range(1, 40)),
      {"bib_entries": n_bib, "numbered": len(ref_ids), "first_last": [ref_ids[0], ref_ids[-1]]})

# citation tokens: digits/ranges separated by comma without spaces
cites = set()
for token in re.findall(r"\[(\d[\d\u2013,]*(?:\d)?)\]", MS):
    for part in token.replace("\u2013", "-").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                cites.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            cites.add(int(part))
cites = {c for c in cites if 1 <= c <= 33}
not_cited = sorted(set(range(1, 34)) - cites)
check("C17", "every reference 1..33 is cited at least once",
      not not_cited, {"n_cited": len(cites), "not_cited": not_cited})

# --- hygiene ---------------------------------------------------------------
check("C18", "no ${...} template placeholders", not re.search(r"\$\{[A-Za-z_]", MS), None)
auth_placeholders = MS.count("[to be completed") + MS.count("[to be confirmed")
check("C19", "author/funding placeholders are explicit and confined to declarations",
      0 < auth_placeholders <= 8, auth_placeholders)
check("C20", "honesty statements present (in silico, no MATLAB bit-exact, no hold-out, L3 unexecuted)",
      all(s in MS for s in ["in silico", "rng('shuffle')", "never honoured", "not executed"]),
      None)
check("C21", "Data and Code Availability + Limitations + Competing interests sections exist",
      all(s in MS for s in ["## Declarations", "## 6. Limitations",
                            "**Competing interests.**", "**Data and Code Availability.**"]),
      None)
check("C22", "companion deliverables all present",
      all(os.path.exists(os.path.join(PAPER, f)) for f in
          ["supplementary.md", "cover_letter.md", "submission_strategy_zh.md",
           "references.bib", "make_figures.py", "make_supplement.py"]),
      None)

n_pass = sum(1 for c in checks if c["ok"])
result = {
    "tool": "paper/check_manuscript.py",
    "verdict": "PASS" if n_pass == len(checks) else "FAIL",
    "n_pass": n_pass, "n_checks": len(checks),
    "figures": fig_ok,
    "checks": checks,
}
out = os.path.join(PAPER, "manuscript_check.json")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print(json.dumps({"verdict": result["verdict"], "n_pass": n_pass,
                  "n_checks": len(checks)}, ensure_ascii=False))
for c in checks:
    if not c["ok"]:
        print("FAIL", c["id"], c["name"], c["got"])
print("WROTE", out)
