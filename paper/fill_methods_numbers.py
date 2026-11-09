# -*- coding: utf-8 -*-
"""Fill the @@KEY@@ placeholders in manuscript_methods.md from the
machine-readable supplementary experiments.  Refuses to write if any
placeholder is unresolved, so no token can leak into the submission.
"""
from __future__ import annotations

import json
import os
import re

PAPER = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(PAPER, "manuscript_methods.md")
EXPERIMENTS = os.path.join(PAPER, "methods_experiments.json")
LOG = os.path.join(PAPER, "methods_numbers.json")

with open(SRC, encoding="utf-8") as f:
    text = f.read()
with open(EXPERIMENTS, encoding="utf-8") as f:
    M = json.load(f)


def num(v, nd=2):
    if v is None:
        return "n/a"
    try:
        return ("%." + str(nd) + "f") % float(v)
    except (TypeError, ValueError):
        return str(v)


def integer(v):
    if v is None:
        return "n/a"
    return str(int(v))


V = {}
E1 = M["E1_solver_sensitivity"]
E2 = M["E2_leave_batch_out"]
E3 = M["E3_discontinuity"]
E6 = M["E6_uncertainty_propagation"]

V["E1_NTOT"] = integer(E1["n_integrations"])
V["E1_NOK"] = integer(E1["n_ok"])
V["E1_MAXDEV"] = num(E1["overall_max_abs_deviation_pct"], 3)

for key, cid in (("BDF", "BDF_tight"), ("RADAU", "Radau"),
                 ("LSODA", "LSODA"), ("RK45", "RK45_fixed")):
    b = E1["by_solver"][cid]
    V["E1_%sN" % key] = integer(b["n_ok"])
    V["E1_%sMAX" % key] = num(b["max_abs_end_product_deviation_pct"], 3)
    # Table 3 reports the median absolute deviation rather than a trajectory
    # NRMSE (simulation output columns do not share a common channel naming).
    V["E1_%sNRMSE" % key] = num(b["median_abs_end_product_deviation_pct"], 3)
    V["E1_CPU%s" % key] = num(b["mean_cpu_s"], 1)
V["E1_RADAUNFAIL"] = integer(E1["by_solver"]["Radau"]["n_fail"])

mp, dp = E2["median_prior"], E2["drawn_prior"]
V["E2_MEDN"] = integer(mp["n_batches"])
V["E2_MEDRMSE"] = num(mp["rmse_pct"], 2)
V["E2_MEDBIAS"] = num(mp["bias_pct"], 2)
V["E2_MEDWITHIN"] = integer(mp["within_5pct"])
V["E2_DRAWN"] = integer(dp["n"])
V["E2_DRAWRMSE"] = num(dp["rmse_pct"], 2)
V["E2_DRAWBIAS"] = num(dp["bias_pct"], 2)
V["E2_DRAWWITHIN"] = integer(dp["within_5pct"])
_m = dp.get("n_replicated_batches") or 0
_cov = dp.get("p05_p95_interval_coverage")
V["E2_COV"] = ("%d of %d" % (round(_cov * _m), _m)) if _cov is not None and _m else "n/a"
V["E2_WIDTH"] = num(dp.get("median_prediction_interval_width_pct_of_yield"), 1)
V["E2_RATIO"] = num((mp["rmse_pct"] or 0) / 2.3448, 1)

V["E3_STALLED"] = integer(E3["offline_optimisation"]["n_stalled_at_start"])

V["E6_N"] = integer(E6["n_ok"])
V["E6_RMSE"] = num(E6["pooled"]["rmse_pct"], 2)
V["E6_P05"] = num(E6["pooled"]["p05_pct"], 2)
V["E6_P95"] = num(E6["pooled"]["p95_pct"], 2)
V["E6_MAX"] = num(E6["pooled"]["max_abs_pct"], 2)
sens = E6.get("sensitivity_correlation", {})
if sens:
    top = max(sens, key=lambda k: abs(sens[k] or 0))
    V["E6_TOP"] = "alpha_kLa" if top == "alpha_kla" else top
    V["E6_TOPR"] = num(abs(sens[top]), 2)
else:
    V["E6_TOP"], V["E6_TOPR"] = "n/a", "n/a"

found = set(re.findall(r"@@([A-Z0-9_]+)@@", text))
missing = sorted(found - set(V))
extra = sorted(set(V) - found)
if missing:
    raise SystemExit("unresolved placeholders (experiments incomplete?): %s" % missing)

for k, v in V.items():
    text = text.replace("@@%s@@" % k, v)

left = re.findall(r"@@[A-Z0-9_]+@@", text)
if left:
    raise SystemExit("placeholders remain after substitution: %s" % left[:10])

with open(SRC, "w", encoding="utf-8") as f:
    f.write(text)
with open(LOG, "w", encoding="utf-8") as f:
    json.dump({"source": "paper/methods_experiments.json",
               "n_substituted": len(found), "unused_keys": extra,
               "values": V}, f, ensure_ascii=False, indent=2)
print("substituted %d placeholders; unused keys: %s" % (len(found), extra))
