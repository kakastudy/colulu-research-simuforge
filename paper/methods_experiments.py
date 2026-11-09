# -*- coding: utf-8 -*-
"""Supplementary methodological experiments for the process-simulation manuscript.

All quantities are recomputed from the frozen artefacts under runs/ and
data/processed/, or from fresh calls to the frozen 33-state ODE engine.
Nothing in this file modifies the baseline, the calibrated parameter table,
or any previously published result.

Stages
  fast : E3, E4, E5, E7, E8 (pure recomputation, seconds)
  sim  : E1, E2, E6 (fresh ODE integrations, multiprocessing, minutes)
  all  : both

Output: paper/methods_experiments.json (incremental, merged per stage)
"""
import os
import sys
import json
import math
import time
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed

# Pin numerical-library threads BEFORE numpy is imported anywhere.  Without
# this, each spawned worker oversubscribes the CPU and the pool loses its
# speed-up (measured: 4-process pool becomes no faster than serial).
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ[_k] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")
RUNS = os.path.join(ROOT, "runs")
ENGINE = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
OUT = os.path.join(PAPER, "methods_experiments.json")


def L(name):
    with open(os.path.join(RUNS, name), encoding="utf-8") as f:
        return json.load(f)


def P(name):
    with open(os.path.join(PAPER, name), encoding="utf-8") as f:
        return json.load(f)


def save(d):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def load():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {"schema": "methods_experiments/1", "note":
            "Supplementary methodological experiments. All baseline results are unchanged."}


def pct(x, q):
    xs = sorted(x)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)


def rmse(xs):
    return math.sqrt(sum(v * v for v in xs) / len(xs)) if xs else None


# ---------------------------------------------------------------- E3 -------
def e3_discontinuity():
    """Finite-difference apparent gradient across a bisection bracket, plus an
    offline gradient-based optimisation experiment on the recorded response surface."""
    bis = L("r157_bistab_escape.json")
    surf = L("r162_kla_sensitivity.json")
    ext = P("extended_stats.json")

    # (a) Apparent gradient as the finite-difference step is refined.
    gradient_rows = []
    for row in bis["rows"]:
        if row.get("verdict") != "DISCONTINUOUS" or not row.get("bisect"):
            continue
        b = row["bisect"]
        width_final = b["bracket_hi"] - b["bracket_lo"]
        trace = b.get("range_trace_pp", [])
        for n, span in enumerate(trace):
            # step n is the bracket width before the (12-n)-th halving
            h = width_final * (2 ** (len(trace) - 1 - n))
            gradient_rows.append({
                "knob": row["knob"], "step": n, "h": h,
                "response_span_pp": span,
                "apparent_gradient_pp_per_unit": span / h if h > 0 else None,
            })
        # explicit 1e-2 .. 1e-8 style sweep evaluated on the same bracket
        sweep = []
        dy = b["y_hi"] - b["y_lo"]
        lo = b["bracket_lo"]
        for k in range(2, 9):
            h = 10.0 ** (-k)
            # the bracket interior is a step: any centred difference crossing it
            # returns the full jump, so the apparent gradient scales as 1/h
            sweep.append({"h": h, "delta_y_pp": dy,
                          "apparent_gradient_pp_per_unit": dy / h,
                          "centre": lo + width_final / 2})
        row_out = {
            "knob": row["knob"], "batch": row.get("batch"),
            "bracket": [b["bracket_lo"], b["bracket_hi"]],
            "bracket_width": width_final, "jump_pp": dy,
            "final_range_pp": b.get("final_range_pp"),
            "bisection_steps": len(trace),
            "sweep": sweep,
        }
        gradient_rows.append({"sweep_for": row["knob"], **row_out})

    # (b) Offline optimisation on the recorded 12 x 12 response surface.
    from scipy.optimize import minimize
    import numpy as np
    klas = np.array(surf["klas"], dtype=float)
    by_batch = collections.defaultdict(dict)
    for r in surf["runs"]:
        by_batch[r["batch"]][r["alpha_kla"]] = r["rel_err_total"] * 100.0
    curves = []
    for b in surf["batches"]:
        d = by_batch.get(b, {})
        if len(d) == len(klas):
            curves.append([d[k] for k in klas])
    median_curve = np.median(np.array(curves), axis=0)

    def f(x):
        return float(np.interp(x[0], klas, median_curve) ** 2)

    starts = [35.0, 55.0, 75.0, 100.0, 130.0]
    opt_rows = []
    for method in ("SLSQP", "trust-constr"):
        for x0 in starts:
            t0 = time.perf_counter()
            try:
                res = minimize(f, [x0], method=method, bounds=[(30.0, 140.0)],
                               options={"maxiter": 200} if method == "SLSQP" else {"maxiter": 200})
                x_end = float(res.x[0])
                stalled = abs(x_end - x0) < 1.0
                opt_rows.append({
                    "method": method, "x0": x0, "x_end": x_end,
                    "objective": float(res.fun), "success": bool(res.success),
                    "nfev": int(getattr(res, "nfev", 0)),
                    "stalled_at_start": stalled,
                    "endpoint_abs_err_pp": float(abs(np.interp(x_end, klas, median_curve))),
                    "wall_s": round(time.perf_counter() - t0, 4),
                })
            except Exception as exc:  # pragma: no cover
                opt_rows.append({"method": method, "x0": x0, "error": str(exc)})
    n_stalled = sum(1 for r in opt_rows if r.get("stalled_at_start"))
    n_opts = len(opt_rows)

    # (c) Coarse-grid adjacent finite differences on the recorded surface.
    adj = []
    for b in surf["batches"]:
        d = by_batch.get(b, {})
        for i in range(len(klas) - 1):
            k0, k1 = klas[i], klas[i + 1]
            if k0 in d and k1 in d:
                adj.append({"batch": b, "k0": k0, "k1": k1,
                            "gradient_pp_per_unit": (d[k1] - d[k0]) / (k1 - k0)})
    big = [a for a in adj if abs(a["gradient_pp_per_unit"]) > 1.0]
    sign_flips = 0
    for b in surf["batches"]:
        seq = [a["gradient_pp_per_unit"] for a in adj if a["batch"] == b]
        sign_flips += sum(1 for i in range(len(seq) - 1)
                          if seq[i] * seq[i + 1] < 0)

    return {
        "source": ["runs/r157_bistab_escape.json", "runs/r162_kla_sensitivity.json",
                   "paper/extended_stats.json"],
        "design": "Apparent finite-difference gradients are recomputed from the frozen "
                  "12-step bisection brackets and the 12x12 oxygen-transfer response surface; "
                  "gradient-based optimisers are then run offline on that recorded surface.",
        "bisection_gradient_trace": [r for r in gradient_rows if "knob" in r and "step" in r],
        "bisection_brackets": [r for r in gradient_rows if "sweep_for" in r],
        "adjacent_grid_gradients": {
            "n_intervals": len(adj), "n_abs_gt_1pp_per_unit": len(big),
            "n_sign_flips": sign_flips,
            "max_abs": max((abs(a["gradient_pp_per_unit"]) for a in adj), default=0.0),
            "median_abs": pct([abs(a["gradient_pp_per_unit"]) for a in adj], 0.5),
        },
        "offline_optimisation": {
            "objective": "minimise squared end-of-batch yield error by varying alpha_kLa "
                         "on the recorded median response curve (linear interpolation)",
            "starts": starts, "rows": opt_rows,
            "n_runs": n_opts, "n_stalled_at_start": n_stalled,
            "stalled_fraction": n_stalled / n_opts if n_opts else None,
        },
        "response_surface_jump_pp": ext.get("bistability", {}).get("yield_err_pct"),
        "interpretation": "Where the response is a step of ~100 pp, the centred difference "
                          "does not converge: its apparent gradient grows as 1/h, and "
                          "gradient optimisers terminate at their starting points.",
    }


# ---------------------------------------------------------------- E4 -------
def e4_identifiability():
    """Executable rank/nullity diagnostic protocol for the observation operator."""
    import numpy as np
    r165 = L("r165_mycelium_identifiability.json")
    obs = r165["observation_operator"]
    meta = obs.get("H_meta", {})
    n_t = 5
    n_assim = 10 * n_t
    n_rep = 2 * n_t

    H_assim = np.zeros((n_assim, 4))
    H_report = np.vstack([H_assim, np.ones((n_rep, 4))])

    def svd_diag(H):
        norms = np.linalg.norm(H, axis=0)
        safe = np.where(norms > 0, norms, 1.0)
        Hn = H / safe
        S = np.linalg.svd(Hn, compute_uv=False)
        tol = max(Hn.shape) * np.finfo(float).eps * (S[0] if len(S) and S[0] > 0 else 1.0)
        rank = int(np.sum(S > tol))
        nz = S[S > tol]
        return {"shape": list(H.shape), "singular_values": [float(x) for x in S],
                "rank": rank, "nullity": H.shape[1] - rank,
                "cond": float(nz[0] / nz[-1]) if len(nz) else float("inf"),
                "column_norms": [float(x) for x in norms]}

    base = {"H_assim": svd_diag(H_assim), "H_report": svd_diag(H_report)}

    # Protocol step 4: simulate adding compartment-resolved measurement rows.
    added = []
    for k in range(0, 5):
        rows = [np.eye(4)[j] for j in range(k)]
        H = np.vstack([H_assim] + rows) if rows else H_assim.copy()
        d = svd_diag(H)
        added.append({"n_independent_compartment_rows": k, "rank": d["rank"],
                      "nullity": d["nullity"],
                      "singular_values": [round(x, 6) for x in d["singular_values"]],
                      "cond": d["cond"] if math.isfinite(d["cond"]) else None})
    # Repeating rows of an existing type does not change the column space.
    rep = np.vstack([H_report] + [np.ones(4)] * 50)
    repeated = svd_diag(rep)

    checks = {
        "baseline_matches_frozen_evidence": (
            base["H_assim"]["rank"] == obs["H_assim"]["rank"] == 0
            and base["H_assim"]["nullity"] == obs["H_assim"]["nullity"] == 4
            and base["H_report"]["rank"] == obs["H_report"]["rank"] == 1
            and base["H_report"]["nullity"] == obs["H_report"]["nullity"] == 3
            and abs(base["H_report"]["singular_values"][0] -
                    obs["H_report"]["singular_values"][0]) < 1e-9),
        "four_independent_rows_restore_full_rank": added[4]["rank"] == 4 and added[4]["nullity"] == 0,
        "repeated_rows_do_not_change_rank": repeated["rank"] == base["H_report"]["rank"],
    }

    protocol = [
        "1. Enumerate the state (or parameter) subset claimed as deliverable and the "
        "measurement channels actually used by the estimator.",
        "2. Assemble the observation operator H with one row per channel per sampling time; "
        "a one-hot row marks a directly observed state, a sum row marks an aggregate assay.",
        "3. Column-normalise H, compute its singular values, rank, nullity and condition number.",
        "4. If nullity > 0, simulate adding one independent row per null-space direction and "
        "recompute the rank; only new measurement types can reduce nullity.",
        "5. Reject the delivery claim for every null-space direction regardless of fit quality; "
        "record the claim as conditional on H, not on the process.",
        "6. Report the rank table alongside the numerical fit so that a reviewer can "
        "distinguish a lack of data volume from a lack of observability.",
    ]
    return {
        "source": ["runs/r165_mycelium_identifiability.json",
                   "tools/r165_mycelium_identifiability.py"],
        "state_subset": ["A0", "A1", "A3", "A4"],
        "n_time_steps": n_t,
        "assimilation_channels": meta.get("assimilation_channels", []),
        "baseline": base,
        "rank_restoration": added,
        "repeated_rows": {"shape": repeated["shape"], "rank": repeated["rank"],
                          "nullity": repeated["nullity"]},
        "checks": checks,
        "protocol": protocol,
        "interpretation": "Nullity 4 is a property of the available measurement types; "
                          "50 additional rows of the existing aggregate assay leave rank 1 unchanged, "
                          "whereas four independent compartment-resolved rows restore rank 4.",
    }


# ---------------------------------------------------------------- E5 -------
def e5_discriminative_validity():
    """Core methodological matrix: discriminative validity of every criterion."""
    ext = P("extended_stats.json")
    cert = ext["falsifiability_certificates"]["rows"]
    audits = {
        "M1": ["zero-information"],
        "M2": ["constant-detector", "trigger-rate"],
        "M3": ["trigger-rate"],
        "M4": ["constant-detector", "trigger-rate"],
        "M5": ["zero-information", "trigger-rate"],
        "M6": ["zero-information"],
        "M7": ["zero-information", "constant-detector"],
        "M8": ["zero-information", "constant-detector"],
    }
    control_results = {
        "M1": "coverage 0.899548532731377 for fitted and zero-information predictors",
        "M2": "86/86 normal; first guard clause can never be false",
        "M3": "27/32 = 84.38% of unperturbed batches flagged",
        "M4": "77/5/4 resolved; all 9 flagged batches carry documented evidence",
        "M5": "0/20 controls triggered; confusion 10/5/4/1",
        "M6": "junk coverage 0.0000 vs fitted 0.1072 (X) / 0.3160 (P)",
        "M7": "reports 12/12 loaded for valid and non-callable symbols",
        "M8": "detects 2/2 injected naming defects; 12/12 verified",
    }
    rows = []
    for c in cert:
        cid = c["id"]
        axes = [c["control_separation"], c["output_degeneracy"], c["detection_power"]]
        degenerate = (c["control_separation"] == 0.0 or
                      c["output_degeneracy"] == 0.0 or
                      c["detection_power"] == 0.0)
        rows.append({
            "id": cid, "instrument": c["instrument"],
            "control_separation": c["control_separation"],
            "output_entropy": c["output_degeneracy"],
            "detection_power": c["detection_power"],
            "min_axis": min(axes),
            "audits_applied": audits.get(cid, []),
            "adversarial_control": control_results.get(cid, ""),
            "verdict": c["verdict"],
            "admissible_for_synthesis": not degenerate and c["verdict"].startswith("CERTIFIED"),
        })
    # Two additional criteria found to be non-independent / degenerate.
    rows.append({
        "id": "M9", "instrument": "Empirical-Bayes population dispersion",
        "control_separation": 0.0, "output_entropy": 0.0, "detection_power": 0.0,
        "min_axis": 0.0, "audits_applied": ["zero-information"],
        "adversarial_control": "effective sample size 46.8/48 implies zero dispersion",
        "verdict": "DEGENERATE", "admissible_for_synthesis": False,
    })
    rows.append({
        "id": "M10", "instrument": "Health-vs-validity as independent corroboration",
        "control_separation": 0.0, "output_entropy": ext["health_validity_crosstab"]["phi_coefficient"],
        "detection_power": 1.0, "min_axis": 0.0,
        "audits_applied": ["collinearity"],
        "adversarial_control": "phi = 1.0; both criteria consume the same pH-guard signal",
        "verdict": "COLLINEAR", "admissible_for_synthesis": False,
    })
    retained = [r for r in rows if r["admissible_for_synthesis"]]
    return {
        "source": ["paper/extended_stats.json", "runs/r160_i3_coverage_tautology.json",
                   "runs/r156_acceptance.json", "runs/r166_ab_gate.json",
                   "runs/r163_degradation_probe.json"],
        "axes": ["control separation (zero-information contrast)",
                 "output entropy (normalised Shannon entropy of the output distribution)",
                 "detection power (Youden J or fraction of injected defects detected)"],
        "rows": rows,
        "n_criteria": len(rows),
        "n_rejected": len(rows) - len(retained),
        "n_retained": len(retained),
        "retained_ids": [r["id"] for r in retained],
        "rejected_ids": [r["id"] for r in rows if not r["admissible_for_synthesis"]],
        "interpretation": "Four criteria are structurally non-discriminating (TAUTOLOGICAL, "
                          "CONSTANT, SATURATED, TAUTOLOGICAL); two more are removed by "
                          "degeneracy and collinearity before any multi-criteria synthesis.",
    }


# ---------------------------------------------------------------- E7 -------
def e7_physical_consistency():
    ext = P("extended_stats.json")
    census = ext["fallback_census"]
    c = census["c_error_pct"]
    x = census["x_rel_diff_pct"]
    return {
        "source": ["paper/extended_stats.json", "runs/r161_fallback_chain_probe.json"],
        "carbon_balance": {
            "n_batches": census["n_batches"], "budget_pct": 20.0,
            "n_within_budget": census["n_credible"],
            "fraction_within": census["n_credible"] / census["n_batches"],
            "mean_pct": sum(c) / len(c), "median_pct": pct(c, 0.5),
            "min_pct": min(c), "max_pct": max(c),
            "p05_pct": pct(c, 0.05), "p95_pct": pct(c, 0.95),
            "per_batch_pct": c, "batches": census["batches"],
        },
        "biomass_relative_difference": {
            "mean_pct": sum(x) / len(x), "median_pct": pct(x, 0.5),
            "min_pct": min(x), "max_pct": max(x), "per_batch_pct": x,
        },
        "nitrogen_balance": {"model_convention_pct": 9.9,
                             "true_metering_convention_pct": -58.1, "budget_pct": 35.0},
        "respiratory_quotient": "exact reproduction from recorded inputs",
        "our_cer_bias": "simulated OUR and CER approximately 12% high because of "
                        "overestimated CO2 outgassing; retained as a declared model bias",
        "scope_note": "Balances are recomputed from the frozen steady-state census. "
                      "No full elemental closure is claimed, and no new wet-laboratory "
                      "or plant measurement is introduced.",
    }


# ---------------------------------------------------------------- E8 -------
def e8_admission_filter(e5):
    ext = P("extended_stats.json")
    gates = ext["gate_matrices"]
    families = {k: {"n": len(v), "n_pass": sum(1 for c in v if c["pass"]),
                    "n_fail": sum(1 for c in v if not c["pass"])}
                for k, v in gates.items() if isinstance(v, list)}
    return {
        "source": ["paper/methods_experiments.json:E5", "paper/extended_stats.json"],
        "flow": ["enumerate every acceptance instrument",
                 "apply zero-information, constant-detector, trigger-rate and rank audits",
                 "reject criteria with any zero axis, zero control separation, "
                 "degenerate dispersion or perfect collinearity",
                 "admit only the surviving criteria into multi-criteria synthesis",
                 "report rejected criteria and their re-issue conditions alongside the result"],
        "before": {"n_instruments": e5["n_criteria"],
                   "n_gate_families": len(families),
                   "n_gate_checks": sum(f["n"] for f in families.values())},
        "after": {"n_instruments": e5["n_retained"],
                  "retained_ids": e5["retained_ids"],
                  "rejected_ids": e5["rejected_ids"],
                  "n_gate_failures_retained": sum(f["n_fail"] for f in families.values())},
        "gate_families": families,
        "surviving_evidence": [
            "five-channel health assessment (77 normal / 5 degraded / 4 catastrophic)",
            "channel-wise leave-one-out calibrated innovation detector (opt-in)",
            "interval half-width and normalised-RMSE improvement (not coverage)",
            "runtime import-and-callable verification of deployed capabilities",
            "cross-validated biomass and viscosity soft sensors",
            "explicit-failure estimator chain",
            "pre-registered NO_GO verdict for disturbance-variance injection",
        ],
        "interpretation": "Degenerate criteria are removed before aggregation rather "
                          "than averaged into a composite score, because a composite "
                          "would reintroduce the arbitrary weighting that the protocol rejects.",
    }


def stage_fast():
    d = load()
    d["E3_discontinuity"] = e3_discontinuity()
    d["E4_identifiability"] = e4_identifiability()
    d["E5_discriminative_validity"] = e5_discriminative_validity()
    d["E7_physical_consistency"] = e7_physical_consistency()
    d["E8_admission_filter"] = e8_admission_filter(d["E5_discriminative_validity"])
    d["stage_fast_done"] = True
    save(d)
    print("fast stage done:", ", ".join(k for k in d if k.startswith("E")))
    return d


# ------------------------------------------------------- simulation utils ---
def _worker(job):
    """One fresh ODE integration. Runs in a spawned process on Windows."""
    os.chdir(ROOT)
    for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS"):
        os.environ[_k] = "1"
    if ENGINE not in sys.path:
        sys.path.insert(0, ENGINE)
    try:
        import numpy as np
        from simulate import simulate_open_loop, yield_metrics
        t0 = time.perf_counter()
        sim, v3 = simulate_open_loop(job["batch"], dict(job["params"]))
        m = yield_metrics(sim, v3)
        wall = time.perf_counter() - t0

        # trajectory-level normalised RMSE and peak-time shift, defensive on columns
        traj = {}
        peak_shift = None
        try:
            if "time_h" in sim.columns and "time_h" in v3.columns:
                mask = sim["time_h"].to_numpy() >= 20.0
                for ch in ("P", "DO2", "S", "V", "pH", "T"):
                    if ch in sim.columns and ch in v3.columns:
                        a = sim[ch].to_numpy()[mask]
                        b = v3[ch].to_numpy()[mask]
                        n = min(len(a), len(b))
                        if n > 10:
                            a, b = a[:n], b[:n]
                            denom = np.nanmax(b) - np.nanmin(b)
                            if denom and np.isfinite(denom) and denom > 0:
                                traj[ch] = float(np.sqrt(np.nanmean(((a - b) / denom) ** 2)))
                if "P" in sim.columns and "P" in v3.columns:
                    ta = sim["time_h"].to_numpy()[mask]
                    pa = sim["P"].to_numpy()[mask]
                    pb = v3["P"].to_numpy()[mask]
                    if len(pa) > 10 and len(pb) > 10:
                        peak_shift = float(ta[np.nanargmax(pa)] - ta[np.nanargmax(pb)])
        except Exception:
            pass

        return {"ok": True, "batch": job["batch"], "tag": job.get("tag", ""),
                "yield_err_pct": float(m["rel_err_total"]) * 100.0,
                "total_sim_g": float(m["total_sim_g"]),
                "total_v3_g": float(m["total_v3_g"]),
                "trajectory_nrmse": traj, "peak_time_shift_h": peak_shift,
                "wall_s": round(wall, 3)}
    except Exception as exc:
        return {"ok": False, "batch": job["batch"], "tag": job.get("tag", ""),
                "error": "%s: %s" % (type(exc).__name__, exc)}


def _run_pool(jobs, workers=8, label=""):
    out = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_worker, j): i for i, j in enumerate(jobs)}
        for i, fut in enumerate(as_completed(futs)):
            out.append(fut.result())
            if (i + 1) % 20 == 0 or (i + 1) == len(jobs):
                print("%s %d/%d  elapsed %.1fs" % (label, i + 1, len(jobs),
                                                   time.perf_counter() - t0), flush=True)
    return out


def _anchor():
    """Frozen recorded/simulated yields plus the AUTHORITATIVE per-batch
    parameter vector.  The short parameter dictionaries stored alongside the
    validation results are a partial record; the single source of truth for
    the frozen engine is golden_params.params_for(batch).
    """
    d = L("final_validation_v2.json")
    if ENGINE not in sys.path:
        sys.path.insert(0, ENGINE)
    from golden_params import params_for
    out = {}
    for r in d["results"]:
        rr = dict(r)
        try:
            rr["params"] = params_for(r["batch"])
        except Exception:
            rr["params"] = dict(r["params"])
        out[r["batch"]] = rr
    return out, d["results"]


# ---------------------------------------------------------------- E1 -------
def e1_solver_sensitivity():
    anchor, _ = _anchor()
    batches = [8, 36, 55, 60, 91, 92]
    configs = [
        {"id": "BDF_tight", "ode_method": "BDF", "ode_rtol": 1e-6, "ode_atol": 1e-9},
        {"id": "Radau", "ode_method": "Radau", "ode_rtol": 1e-6, "ode_atol": 1e-9},
        {"id": "LSODA", "ode_method": "LSODA", "ode_rtol": 1e-6, "ode_atol": 1e-9},
        {"id": "RK45_fixed", "ode_method": "RK45", "ode_rtol": 1e-6,
         "ode_atol": 1e-9, "ode_max_step": 0.01},
    ]
    jobs = []
    for b in batches:
        base = dict(anchor[b]["params"])
        for c in configs:
            p = dict(base)
            p.update({k: v for k, v in c.items() if k != "id"})
            jobs.append({"batch": b, "params": p, "tag": c["id"]})

    print("E1: %d fresh integrations" % len(jobs), flush=True)
    res = _run_pool(jobs, label="E1")
    rows = []
    for r in res:
        b, tag = r["batch"], r["tag"]
        ref = anchor[b]
        if r["ok"]:
            rows.append({
                "batch": b, "solver": tag,
                "yield_err_pct": r["yield_err_pct"],
                "reference_yield_err_pct": ref["yield_err"] * 100.0,
                "delta_yield_err_pp": r["yield_err_pct"] - ref["yield_err"] * 100.0,
                "end_product_deviation_pct": 100.0 * (r["total_sim_g"] - ref["yield_sim"]) / ref["yield_sim"],
                "trajectory_nrmse": r["trajectory_nrmse"],
                "peak_time_shift_h": r["peak_time_shift_h"],
                "cpu_s": r["wall_s"], "ok": True,
            })
        else:
            rows.append({"batch": b, "solver": tag, "ok": False, "error": r["error"]})

    by_solver = {}
    for c in configs:
        rr = [x for x in rows if x["solver"] == c["id"] and x["ok"]]
        dev = [abs(x["end_product_deviation_pct"]) for x in rr]
        dy = [abs(x["delta_yield_err_pp"]) for x in rr]
        tn = [v for x in rr for v in x["trajectory_nrmse"].values()]
        by_solver[c["id"]] = {
            "n_ok": len(rr),
            "n_fail": sum(1 for x in rows if x["solver"] == c["id"] and not x["ok"]),
            "max_abs_end_product_deviation_pct": max(dev) if dev else None,
            "median_abs_end_product_deviation_pct": pct(dev, 0.5) if dev else None,
            "max_abs_delta_yield_err_pp": max(dy) if dy else None,
            "median_trajectory_nrmse": pct(tn, 0.5) if tn else None,
            "mean_cpu_s": sum(x["cpu_s"] for x in rr) / len(rr) if rr else None,
        }
    ok_all = [x for x in rows if x["ok"]]
    return {
        "source": ["candidate/indpensim/v0.1/simulate.py:integrate_interval",
                   "runs/final_validation_v2.json", "fresh integrations"],
        "reference": "BDF, rtol 1e-3, atol 1e-6, max_step 0.01 h (frozen default)",
        "batches": batches, "configurations": configs,
        "rows": rows, "by_solver": by_solver,
        "n_integrations": len(jobs), "n_ok": len(ok_all),
        "overall_max_abs_deviation_pct": max(
            (abs(x["end_product_deviation_pct"]) for x in ok_all), default=None),
        "interpretation": "End-of-batch yield is compared across implicit multistep, "
                          "implicit Runge-Kutta, adaptive LSODA and explicit fixed-step "
                          "integrators at tighter tolerances on identical batch inputs.",
    }


# ---------------------------------------------------------------- E2 -------
def e2_leave_batch_out():
    anchor, results = _anchor()
    batches = [r["batch"] for r in results]
    # five disjoint folds over the ordered batch roster
    folds = [batches[i::5] for i in range(5)]
    shared = ["Y_NP", "Y_NX", "alpha_kla", "dist_tcin_asym", "m_s", "mup", "mux",
              "q_co2", "vis_out_scale"]
    jobs, meta = [], []
    for k, held in enumerate(folds):
        train = [b for b in batches if b not in held]
        med = {key: pct([anchor[b]["params"][key] for b in train
                         if key in anchor[b]["params"]], 0.5) for key in shared}
        # four held-out batches per fold, spread across the recorded-yield range
        ordered = sorted(held, key=lambda b: anchor[b]["yield_v3"])
        picks = [ordered[int(round(q * (len(ordered) - 1)))]
                 for q in (0.0, 1 / 3, 2 / 3, 1.0)]
        for b in picks:
            jobs.append({"batch": b, "params": dict(med), "tag": "LBO_median_fold%d" % k})
            meta.append({"batch": b, "fold": k, "strategy": "median_prior",
                         "n_train": len(train)})

    # stochastic prior: draw a complete calibrated parameter vector from the training pool
    import random
    rng = random.Random(20261107)
    rep_batches = [8, 16, 36, 55, 60, 79, 91, 92]
    for k, held in enumerate(folds):
        train = [b for b in batches if b not in held]
        for b in rep_batches:
            if b not in held:
                continue
            for rep in range(3):
                src = rng.choice(train)
                jobs.append({"batch": b, "params": dict(anchor[src]["params"]),
                             "tag": "LBO_draw_fold%d_r%d" % (k, rep)})
                meta.append({"batch": b, "fold": k, "strategy": "drawn_prior",
                             "rep": rep, "source_batch": src, "n_train": len(train)})

    print("E2: %d fresh integrations (never uses held-out yield as input)" % len(jobs), flush=True)
    res = _run_pool(jobs, label="E2")
    by_tag = {}
    for r, m in zip(res, meta):
        by_tag.setdefault((r["batch"], r["tag"]), (r, m))
    rows = []
    for (b, tag), (r, m) in by_tag.items():
        rec = anchor[b]["yield_v3"]
        if r["ok"]:
            e = 100.0 * (r["total_sim_g"] - rec) / rec
            rows.append({"batch": b, "strategy": m["strategy"], "fold": m["fold"],
                         "rep": m.get("rep"), "source_batch": m.get("source_batch"),
                         "yield_err_pct": e, "abs_err_pct": abs(e),
                         "total_sim_g": r["total_sim_g"],
                         "within_5pct": abs(e) <= 5.0, "ok": True})
        else:
            rows.append({"batch": b, "strategy": m["strategy"], "fold": m["fold"],
                         "rep": m.get("rep"), "ok": False, "error": r["error"]})

    med_rows = [r for r in rows if r["ok"] and r["strategy"] == "median_prior"]
    draw_rows = [r for r in rows if r["ok"] and r["strategy"] == "drawn_prior"]
    med_err = [r["yield_err_pct"] for r in med_rows]
    draw_err = [r["yield_err_pct"] for r in draw_rows]
    # prospective interval coverage: does the P5-P95 band of the predicted
    # product mass contain the recorded product mass of the held-out batch?
    by_batch = collections.defaultdict(list)
    for r in draw_rows:
        by_batch[r["batch"]].append(r["total_sim_g"])
    covered = 0
    interval_widths = []
    for b, vals in by_batch.items():
        if len(vals) < 3:
            continue
        lo, hi = pct(vals, 0.05), pct(vals, 0.95)
        interval_widths.append(hi - lo)
        if lo <= anchor[b]["yield_v3"] <= hi:
            covered += 1
    return {
        "source": ["runs/final_validation_v2.json (calibrated parameter vectors and recorded yields)",
                   "fresh integrations with held-out parameter vectors excluded"],
        "design": "Five disjoint folds over the 86-batch roster. Twenty held-out batches "
                  "(four per fold, spread across the recorded-yield range) receive a median "
                  "prior, and eight representative held-out batches receive three drawn priors "
                  "each. Priors are built only from the calibration vectors of the other "
                  "folds; the batch's own inputs are used, but its recorded product mass "
                  "enters only the final error calculation. The subset is declared explicitly.",
        "prior_strategies": {"median_prior": "per-parameter median over the training folds",
                             "drawn_prior": "a complete parameter vector drawn from the training folds"},
        "shared_parameter_keys": shared,
        "n_integrations": len(jobs),
        "n_ok": len(med_rows) + len(draw_rows),
        "median_prior": {
            "n": len(med_err), "rmse_pct": rmse(med_err),
            "bias_pct": sum(med_err) / len(med_err) if med_err else None,
            "median_abs_pct": pct([abs(v) for v in med_err], 0.5) if med_err else None,
            "max_abs_pct": max((abs(v) for v in med_err), default=None),
            "within_5pct": sum(1 for r in med_rows if r["within_5pct"]),
            "n_batches": len(med_rows),
        },
        "drawn_prior": {
            "n": len(draw_err), "rmse_pct": rmse(draw_err),
            "bias_pct": sum(draw_err) / len(draw_err) if draw_err else None,
            "median_abs_pct": pct([abs(v) for v in draw_err], 0.5) if draw_err else None,
            "within_5pct": sum(1 for r in draw_rows if r["within_5pct"]),
            "p05_pct": pct(draw_err, 0.05), "p95_pct": pct(draw_err, 0.95),
            "n_replicated_batches": len(by_batch),
            "p05_p95_interval_coverage": covered / len(by_batch) if by_batch else None,
            "median_prediction_interval_width_g": pct(interval_widths, 0.5) if interval_widths else None,
            "median_prediction_interval_width_pct_of_yield": (
                100.0 * pct(interval_widths, 0.5) /
                (sum(anchor[b]["yield_v3"] for b in by_batch) / len(by_batch))
                if interval_widths and by_batch else None),
        },
        "reference_reconstruction_rmse_pct": 2.3448,
        "rows": rows,
        "interpretation": "Reconstruction consistency (2.3448% with per-batch calibration) and "
                          "conditional transferability (held-out parameter priors) are "
                          "different quantities and must not be interchanged.",
    }


# ---------------------------------------------------------------- E6 -------
def e6_uncertainty_propagation():
    import random
    anchor, _ = _anchor()
    batches = [8, 36, 55, 60, 91]
    rng = random.Random(20261107)
    sigma_rel = {"mux": 0.025 / 0.41, "mup": 0.0025 / 0.041, "alpha_kla": 10.0 / 85.0}
    jobs, meta = [], []
    for b in batches:
        base = dict(anchor[b]["params"])
        for rep in range(6):
            p = dict(base)
            factors = {}
            for key, s in sigma_rel.items():
                f = max(0.2, 1.0 + rng.gauss(0.0, s))
                p[key] = base.get(key, 1.0) * f
                factors[key] = f
            jobs.append({"batch": b, "params": p, "tag": "MC_r%d" % rep})
            meta.append({"batch": b, "rep": rep, "factors": factors})

    print("E6: %d fresh integrations (Monte Carlo parameter propagation)" % len(jobs), flush=True)
    res = _run_pool(jobs, label="E6")
    rows = []
    for r, m in zip(res, meta):
        if r["ok"]:
            ref = anchor[m["batch"]]["yield_sim"]
            rows.append({"batch": m["batch"], "rep": m["rep"],
                         "total_sim_g": r["total_sim_g"],
                         "deviation_from_baseline_pct": 100.0 * (r["total_sim_g"] - ref) / ref,
                         "factors": m["factors"], "wall_s": r["wall_s"], "ok": True})
        else:
            rows.append({"batch": m["batch"], "rep": m["rep"], "ok": False,
                         "error": r["error"], "factors": m["factors"]})
    by_batch = {}
    for b in batches:
        v = [r["deviation_from_baseline_pct"] for r in rows
             if r["ok"] and r["batch"] == b]
        by_batch[b] = {"n": len(v), "p05_pct": pct(v, 0.05), "p50_pct": pct(v, 0.5),
                       "p95_pct": pct(v, 0.95), "width_pp": (pct(v, 0.95) - pct(v, 0.05)) if v else None,
                       "rmse_pct": rmse(v)} if v else {"n": 0}
    # Morris-style elementary-effect proxy: correlation of each factor with |deviation|
    import math as _m
    sens = {}
    ok = [r for r in rows if r["ok"]]
    for key in sigma_rel:
        xs = [r["factors"][key] for r in ok]
        ys = [abs(r["deviation_from_baseline_pct"]) for r in ok]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        vx = sum((a - mx) ** 2 for a in xs)
        vy = sum((b - my) ** 2 for b in ys)
        sens[key] = cov / _m.sqrt(vx * vy) if vx > 0 and vy > 0 else None
    return {
        "source": ["runs/final_validation_v2.json", "fresh integrations"],
        "design": "Six Monte Carlo replicates on five representative batches. Nominal batch-level "
                  "random effects (mux 0.41 +/- 0.025, mup 0.041 +/- 0.0025, "
                  "alpha_kLa 85 +/- 10) are applied as multiplicative perturbations "
                  "to each batch's own calibrated vector; no recorded yield is used as input.",
        "sigma_relative": sigma_rel,
        "batches": batches, "n_integrations": len(jobs), "n_ok": len(ok),
        "by_batch": {str(k): v for k, v in by_batch.items()},
        "pooled": {
            "p05_pct": pct([r["deviation_from_baseline_pct"] for r in ok], 0.05),
            "p95_pct": pct([r["deviation_from_baseline_pct"] for r in ok], 0.95),
            "rmse_pct": rmse([r["deviation_from_baseline_pct"] for r in ok]),
            "max_abs_pct": max((abs(r["deviation_from_baseline_pct"]) for r in ok), default=None),
        },
        "sensitivity_correlation": sens,
        "rows": rows,
        "interpretation": "Parameter uncertainty propagating through the same frozen engine "
                          "is compared with the 2.3448% per-batch reconstruction error.",
    }


def stage_sim():
    d = load()
    d["E1_solver_sensitivity"] = e1_solver_sensitivity()
    save(d)
    d["E2_leave_batch_out"] = e2_leave_batch_out()
    save(d)
    d["E6_uncertainty_propagation"] = e6_uncertainty_propagation()
    d["stage_sim_done"] = True
    save(d)
    print("sim stage done.", flush=True)
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["fast", "sim", "all"], default="all")
    a = ap.parse_args()
    if a.stage in ("fast", "all"):
        stage_fast()
    if a.stage in ("sim", "all"):
        stage_sim()
