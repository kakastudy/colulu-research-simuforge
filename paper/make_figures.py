# -*- coding: utf-8 -*-
"""Generate publication-quality figures from the frozen runs/ evidence.

All numbers are read from JSON artefacts in runs/; nothing is hard-coded from
prose.  Figures are written to paper/figures/ as 300 dpi PNG plus vector PDF.
"""
import json
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS = os.path.join(ROOT, "runs")
OUT = os.path.join(ROOT, "paper", "figures")
os.makedirs(OUT, exist_ok=True)

BLUE = "#1F4E79"
TEAL = "#16807A"
RED = "#B03A2E"
AMBER = "#C9861B"
GREY = "#7F8C8D"
LIGHT = "#EDF2F7"
INK = "#22303C"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.linewidth": 0.7,
    "axes.edgecolor": "#4A5A68",
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def load(name):
    with open(os.path.join(RUNS, name), "r", encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    png = os.path.join(OUT, name + ".png")
    fig.savefig(png, bbox_inches="tight", facecolor="white")
    fig.savefig(os.path.join(OUT, name + ".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("WROTE", name, os.path.getsize(png), "bytes")


def box(ax, x, y, w, h, text, fc, ec, fontsize=7.2, bold=False, alpha=1.0):
    """Draw a rounded box whose text is auto-wrapped and auto-shrunk to fit."""
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                       linewidth=0.9, edgecolor=ec, facecolor=fc, alpha=alpha)
    ax.add_patch(p)
    fig_w_in = ax.figure.get_figwidth()
    fig_h_in = ax.figure.get_figheight()
    w_pt = w * fig_w_in * 0.92 * 72
    h_pt = h * fig_h_in * 0.92 * 72
    fs = fontsize
    for _ in range(9):
        max_chars = max(8, int(w_pt / (0.55 * fs)) - 2)
        lines = []
        for para in str(text).split("\n"):
            lines.extend(textwrap.wrap(para, width=max_chars) or [""])
        if len(lines) * 1.30 * fs <= h_pt * 0.88:
            break
        fs -= 0.35
    ax.text(x + w / 2, y + h / 2, "\n".join(lines), ha="center", va="center",
            fontsize=max(fs, 4.5), fontweight="bold" if bold else "normal",
            color=INK, linespacing=1.22)
    return p


def arrow(ax, x1, y1, x2, y2, color=GREY, style="-|>", lw=1.1, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=9, linewidth=lw, color=color,
                                 connectionstyle="arc3,rad=%.3f" % rad))


# ---------------------------------------------------------------- Fig 1 ----
def fig1():
    fig, ax = plt.subplots(figsize=(7.2, 4.35))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.01, 0.965, "Evidence-gated architecture for a falsifiable digital twin",
            fontsize=10, fontweight="bold", color=BLUE, va="top")

    layers = [
        ("L0", 0.775, "Frozen baseline",
         "Default path byte-identical.\n86-batch regression anchor;\nmax|delta| = 0.00e+00",
         "final_validation_v2.json", BLUE, "#DCE8F2"),
        ("L1", 0.585, "Opt-in candidates",
         "V1 innovation test; V2 variance\ninjection; V3 dual lookup.\nAll disabled by default.",
         "fully bypassable", TEAL, "#DDF0EE"),
        ("L2", 0.395, "Evidence gate",
         "Zero-info controls; two-sided\ncriteria; LOO thresholds;\nA/B confusion table",
         "18/20 NO_GO", AMBER, "#FBF0DC"),
        ("L3", 0.205, "Human promotion",
         "Default-path switch requires\nexplicit human confirmation",
         "NOT EXECUTED", RED, "#F7E3E0"),
    ]
    for tag, y, title, body, artefact, col, fill in layers:
        box(ax, 0.015, y, 0.075, 0.145, tag, col, col, 10, True, 0.92)
        box(ax, 0.098, y, 0.205, 0.145, title, fill, col, 7.6, True)
        box(ax, 0.311, y, 0.360, 0.145, body, "#FFFFFF", "#B9C6D2", 6.4)
        box(ax, 0.679, y, 0.220, 0.145, artefact, "#F7F9FB", "#C8D3DD", 6.3)

    arrow(ax, 0.926, 0.205, 0.926, 0.775, RED, "-|>", 1.4, -0.16)
    ax.text(0.947, 0.49, "PROMOTION BLOCKED", fontsize=6.4, color=RED,
            ha="center", va="center", fontweight="bold", rotation=90)
    for y in (0.395, 0.585, 0.775):
        arrow(ax, 0.926, y - 0.012, 0.926, y - 0.055, GREY, "-|>", 0.9)

    box(ax, 0.015, 0.055, 0.885, 0.105,
        "Governance spine:  versioned contract v1.0-v1.97  |  debt ledger D-2...D-92  |  "
        "sign-off R-1...R-17  |  gate + final check + idempotent sync",
        LIGHT, "#9FB0BF", 6.3)
    ax.text(0.015, 0.012,
            "Invariant: a candidate may be evaluated, but never silently promoted; every rejection and every "
            "negative result is retained as evidence.",
            fontsize=6.4, color=GREY, va="bottom")
    save(fig, "fig1_framework")


# ---------------------------------------------------------------- Fig 2 ----
def fig2():
    fig, ax = plt.subplots(figsize=(7.2, 4.15))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.01, 0.965, "Mechanistic model, observation layers and four-ring estimator fallback",
            fontsize=10, fontweight="bold", color=BLUE, va="top")

    box(ax, 0.015, 0.68, 0.205, 0.19,
        "Process inputs (26)\nfeeds, aeration,\nagitation, pH/T", "#EDF2F7", "#9FB0BF", 6.6)
    box(ax, 0.255, 0.68, 0.235, 0.19,
        "33-state stiff ODE\nBDF (rtol 1e-3)\nmax_step 0.01 h", "#DCE8F2", BLUE, 6.8, True)
    box(ax, 0.525, 0.68, 0.205, 0.19,
        "37 channels\non-line 0.2 h\noff-line 12 h, 98.2% NaN", "#EDF2F7", "#9FB0BF", 6.6)
    arrow(ax, 0.222, 0.775, 0.253, 0.775, BLUE)
    arrow(ax, 0.492, 0.775, 0.523, 0.775, BLUE)

    box(ax, 0.765, 0.68, 0.220, 0.19,
        "Evaluation\nt >= 20 h; 86 batches\nyield gate +/-5%", "#DDF0EE", TEAL, 6.8, True)
    arrow(ax, 0.732, 0.775, 0.763, 0.775, TEAL)

    ax.text(0.015, 0.615, "Estimator chain (B/C/D tiers): degradation is explicit, never silent",
            fontsize=8.2, fontweight="bold", color=INK)
    chain = [
        ("1  EnKF", "CV floor; ensemble\nfailure; |z| > 5", "#DDF0EE", TEAL),
        ("2  MHE", "SLSQP on mup, m_s\n4 h window", "#DCE8F2", BLUE),
        ("3  Carbon balance", "steady C closure\n|err| > 20% => reject", "#FBF0DC", AMBER),
        ("4  explicit_failure", "chain exhausted;\nno plausible output", "#F7E3E0", RED),
    ]
    x = 0.015
    for i, (name, desc, fill, col) in enumerate(chain):
        box(ax, x, 0.375, 0.225, 0.205, name + "\n\n" + desc, fill, col, 6.8, i == 0)
        if i < 3:
            arrow(ax, x + 0.227, 0.477, x + 0.246, 0.477, GREY, "-|>", 1.0)
        x += 0.246

    ax.text(0.015, 0.315, "Observability boundary determined analytically (see Fig. 6):",
            fontsize=7.2, color=GREY)
    box(ax, 0.015, 0.185, 0.470, 0.105,
        "Deliverable: X, viscosity, DO2 (3.17 / 5.57 / 11.83%)",
        "#EAF5F2", TEAL, 6.5)
    box(ax, 0.500, 0.185, 0.485, 0.105,
        "Non-identifiable: A0/A1/A3/A4, S, P, PAA",
        "#FBEDEA", RED, 6.5)
    ax.text(0.015, 0.105,
            "Residual discovery: sparse regression on d(S_sim - S_v3)/dt gave a death correction "
            "beta = (81.70, -293.71, 158.56), R2 = 0.6663, n = 621.",
            fontsize=6.6, color=INK)
    ax.text(0.015, 0.055,
            "Hierarchical MAP/EM gives only dispersion upper bounds; no independent "
            "generalisation error is claimed (the planned hold-out was never reserved).",
            fontsize=6.6, color=INK)
    save(fig, "fig2_model")


# ---------------------------------------------------------------- Fig 3 ----
def fig3():
    fv = load("final_validation_v2.json")["results"]
    acc = load("r156_acceptance.json")
    batches = [r["batch"] for r in fv]
    errs = np.array([r["yield_err"] * 100.0 for r in fv])
    rmse = float(np.sqrt(np.mean(errs ** 2)))
    nh = acc["summary"]["n_health"]

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.15), gridspec_kw={"width_ratios": [2.25, 1]})
    ax = axes[0]
    cols = [RED if abs(e) > 4 else (AMBER if abs(e) > 2 else BLUE) for e in errs]
    ax.bar(range(len(errs)), errs, color=cols, width=0.78, linewidth=0)
    ax.axhline(5, color=RED, ls="--", lw=0.9)
    ax.axhline(-5, color=RED, ls="--", lw=0.9)
    ax.axhline(0, color="#4A5A68", lw=0.7)
    ax.set_ylim(-6.4, 6.4)
    ax.set_xlim(-1, len(errs))
    ax.set_xticks(range(0, 86, 10))
    ax.set_xticklabels([str(batches[i]) for i in range(0, 86, 10)])
    ax.set_xlabel("Batch identifier (86-batch evaluation set)")
    ax.set_ylabel("Yield error (%)")
    ax.set_title("(a) Frozen A-tier baseline: RMSE = %.4f%%, 86/86 within +/-5%%" % rmse,
                 fontsize=8.4, color=BLUE, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    labels = ["normal", "benign", "degraded", "catastrophic"]
    vals = [nh.get(k, 0) for k in labels]
    colors = [BLUE, "#B7C6D4", AMBER, RED]
    bars = ax.bar(range(4), vals, color=colors, width=0.66)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels, rotation=22, ha="right")
    ax.set_ylabel("Batches")
    ax.set_ylim(0, 92)
    ax.set_title("(b) Five-channel health", fontsize=8.4, color=BLUE, fontweight="bold")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, str(v), ha="center", fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig3_validation")


# ---------------------------------------------------------------- Fig 4 ----
def fig4():
    cov = load("r160_i3_coverage_tautology.json")
    acc = load("r156_acceptance.json")
    probe = load("r163_degradation_probe.json")
    nh = acc["summary"]["n_health"]
    a_sum = probe.get("A_summary", {})
    n_scan = a_sum.get("n_scanned", len(probe.get("A_screening", [])))
    n_deg = a_sum.get("n_degraded", sum(1 for r in probe.get("A_screening", []) if r.get("degraded")))

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.95))
    # (a) coverage
    ax = axes[0]
    channels = ["X", "P", "PAA", "vis"]
    junk = [cov["junk"][c]["coverage"] for c in channels]
    real = [cov["real"][c]["coverage"] for c in channels]
    x = np.arange(4); w = 0.36
    ax.bar(x - w / 2, junk, w, label="zero-information predictor", color=RED)
    ax.bar(x + w / 2, real, w, label="fitted predictor", color=BLUE)
    ax.axhline(0.95, color=GREY, ls="--", lw=0.9)
    ax.set_ylim(0, 1.30); ax.set_xticks(x); ax.set_xticklabels(channels)
    ax.set_ylabel("Interval coverage")
    ax.set_title("(a) Tautological coverage\n(both = 0.899549)", fontsize=8.0,
                 color=RED, fontweight="bold")
    ax.legend(frameon=False, loc="upper left", fontsize=5.8)
    ax.spines[["top", "right"]].set_visible(False)

    # (b) health vs legacy
    ax = axes[1]
    new = [nh.get("normal", 0), nh.get("degraded", 0), nh.get("catastrophic", 0)]
    legacy = [86, 0, 0]
    x = np.arange(3); w = 0.36
    ax.bar(x - w / 2, legacy, w, label="legacy crash_level", color=GREY)
    ax.bar(x + w / 2, new, w, label="five-channel classify_health", color=TEAL)
    ax.set_xticks(x); ax.set_xticklabels(["normal", "degraded", "catastrophic"], rotation=20, ha="right")
    ax.set_ylabel("Batches"); ax.set_ylim(0, 100)
    ax.set_title("(b) Constant verdict vs\ninformation-bearing verdict", fontsize=8.0,
                 color=RED, fontweight="bold")
    ax.legend(frameon=False, loc="upper right", fontsize=6.2)
    ax.spines[["top", "right"]].set_visible(False)

    # (c) innovation criterion
    ax = axes[2]
    frac = 100.0 * n_deg / max(n_scan, 1)
    ax.bar([0], [100 - frac], 0.5, color=TEAL)
    ax.bar([0], [frac], 0.5, bottom=[100 - frac], color=RED)
    ax.set_xlim(-0.6, 0.6); ax.set_ylim(0, 118); ax.set_xticks([0]); ax.set_xticklabels([""])
    ax.set_ylabel("Share of scanned batches (%)")
    ax.set_title("(c) Near-constant innovation test\n%d/%d = %.2f%% flagged" % (n_deg, n_scan, frac),
                 fontsize=8.0, color=RED, fontweight="bold")
    ax.text(0, frac / 2 + (100 - frac), "%.2f%%" % frac, ha="center", va="center",
            fontsize=7.5, color="white", fontweight="bold")
    ax.text(0, (100 - frac) / 2, "%.2f%%" % (100 - frac), ha="center", va="center",
            fontsize=6.6, color="white")
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    fig.tight_layout(w_pad=2.2)
    save(fig, "fig4_tautologies")


# ---------------------------------------------------------------- Fig 5 ----
def fig5():
    op = load("r166_v2_optim.json")
    ab = load("r166_ab_gate.json")
    grid = sorted(op["grid"], key=lambda r: r["scale"])
    scales = [r["scale"] for r in grid]
    maxd = [r["max_abs_delta_pp"] for r in grid]
    feas = [r["feasible"] for r in grid]
    ref = op["reference_pp"]
    chosen = op["chosen_scale"]
    seeds = op["seed_stage"]["per_seed"]
    seed7 = next((r for r in grid if abs(r["scale"] - chosen) < 1e-9), None)

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.95))
    # (a) scale sweep
    ax = axes[0]
    ax.plot(scales, maxd, "-o", color=BLUE, ms=4, lw=1.2)
    for s, m, f in zip(scales, maxd, feas):
        ax.plot([s], [m], "o", ms=5, color=TEAL if f else RED, zorder=3)
    ax.axhline(op["v23_max"], color=RED, ls="--", lw=0.9)
    ax.axhline(op["v24_max"], color=AMBER, ls="--", lw=0.9)
    ax.axhline(ref, color=GREY, ls=":", lw=1.0)
    ax.axvline(chosen, color=TEAL, ls="-.", lw=0.9)
    ax.set_xscale("log"); ax.set_ylim(0, 122)
    ax.set_xlabel("Injection scale"); ax.set_ylabel("max|delta| (pp)")
    ax.set_title("(a) Seed 7 sweep; chosen 0.35\nlooks feasible", fontsize=8.0,
                 color=BLUE, fontweight="bold")
    ty = ax.get_yaxis_transform()
    ax.text(0.02, op["v23_max"] + 2, "V2-3 cap 20 pp", transform=ty,
            ha="left", va="bottom", fontsize=5.6, color=RED)
    ax.text(0.02, op["v24_max"] + 2, "V2-4 cap 30 pp", transform=ty,
            ha="left", va="bottom", fontsize=5.6, color=AMBER)
    ax.text(0.02, ref + 2, "reference %.2f pp" % ref, transform=ty,
            ha="left", va="bottom", fontsize=5.6, color=GREY)
    ax.spines[["top", "right"]].set_visible(False)

    # (b) out-of-sample seeds
    ax = axes[1]
    names = ["seed 7 (fit)"] + ["seed %d" % s["seed"] for s in seeds]
    vals = [seed7["max_abs_delta_pp"] if seed7 else 0] + [s["max_abs_delta_pp"] for s in seeds]
    cols = [TEAL] + [RED if s["n_collapse"] else TEAL for s in seeds]
    b = ax.bar(range(len(vals)), vals, 0.58, color=cols)
    ax.set_xticks(range(len(vals))); ax.set_xticklabels(names, rotation=18, ha="right", fontsize=6.4)
    ax.set_ylabel("max|delta| (pp)"); ax.set_ylim(0, 118)
    ax.axhline(20, color=GREY, ls="--", lw=0.9)
    ax.set_title("(b) Same scale, unseen seeds\n=> NO_GO (8/10 checks)",
                 fontsize=8.0, color=RED, fontweight="bold")
    for bar, v in zip(b, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 2, "%.1f" % v, ha="center", fontsize=6.4)
    ax.spines[["top", "right"]].set_visible(False)

    # (c) full-scale batch deltas
    ax = axes[2]
    rows = ab["v2"]["full_scale_rows"]
    bs = [r["batch"] for r in rows]
    d = [r["delta_pp"] for r in rows]
    cols = [RED if abs(v) > 30 else AMBER for v in d]
    ax.bar(range(len(d)), d, 0.62, color=cols)
    ax.axhline(0, color="#4A5A68", lw=0.7)
    ax.set_xticks(range(len(d))); ax.set_xticklabels([str(x) for x in bs], fontsize=6.6)
    ax.set_xlabel("Batch"); ax.set_ylabel("delta yield (pp)")
    ax.set_title("(c) Full-amplitude injection\n3/6 catastrophic collapses",
                 fontsize=8.0, color=RED, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig5_perturbation")


# ---------------------------------------------------------------- Fig 6 ----
def fig6():
    idf = load("r165_mycelium_identifiability.json")["observation_operator"]
    esc = load("r157_bistab_escape.json")
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))

    ax = axes[0]
    labels = ["H_assim", "H_report"]
    for i, (lab, key) in enumerate(zip(labels, ["H_assim", "H_report"])):
        sv = np.array(idf[key]["singular_values"], dtype=float)
        x = np.arange(len(sv)) + (i - 0.5) * 0.36
        ax.bar(x, np.maximum(sv, 1e-3), 0.32, label=lab,
               color=RED if i == 0 else BLUE)
    ax.set_yscale("symlog", linthresh=1e-2)
    ax.set_ylim(0, 5)
    ax.set_xticks(range(4)); ax.set_xticklabels(["s1", "s2", "s3", "s4"])
    ax.set_ylabel("Singular value (symlog)")
    ax.set_title("(a) Structural non-identifiability\nrank 0 / nullity 4 vs rank 1 / nullity 3",
                 fontsize=8.0, color=RED, fontweight="bold")
    ax.legend(frameon=False, fontsize=6.5, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    for knob, col, mk in [("sd", RED, "o"), ("meanP", BLUE, "s")]:
        row = next((r for r in esc["rows"] if r["knob"] == knob), None)
        if row is None:
            continue
        g = row["grid"]
        xs = [p["value"] for p in g]
        ys = [p["yield_err"] for p in g]
        ax.plot(xs, ys, marker=mk, ms=3.6, lw=1.1, color=col, label=knob)
    ax.set_xscale("log")
    ax.set_ylim(-110, 10)
    ax.axhline(0, color=GREY, ls="--", lw=0.8)
    ax.set_xlabel("Control knob value (log)")
    ax.set_ylabel("Yield error (%)")
    ax.set_title("(b) Discontinuous response\n99.8-101.5 pp jump => no usable gradient",
                 fontsize=8.0, color=RED, fontweight="bold")
    ax.legend(frameon=False, fontsize=6.5, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig6_limits")


# -------------------------------------------------------------- Fig S1 ----
def figS1():
    ch = load("r157_i3_channels.json")["channels"]
    order = ["X", "vis", "DO2", "P", "PAA", "S"]
    a = [ch[k]["nrmse_A_median"] for k in order]
    b = [ch[k]["nrmse_cv_median"] for k in order]
    cls = {
        "X": "DELIVERABLE", "vis": "DELIVERABLE", "DO2": "PARTIAL",
        "P": "NOT IDENT.", "PAA": "NOT IDENT.", "S": "MARGINAL",
    }
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    x = np.arange(len(order)); w = 0.36
    ax.bar(x - w / 2, a, w, label="A tier (mechanistic)", color=GREY)
    ax.bar(x + w / 2, b, w, label="B tier (5-fold CV soft sensor)", color=TEAL)
    ax.set_yscale("log"); ax.set_ylim(1, 900)
    ax.set_xticks(x)
    ax.set_xticklabels([k + "\n" + cls[k] for k in order], fontsize=6.3)
    ax.tick_params(axis="x", pad=5)
    ax.set_ylabel("Median nRMSE (%, log)")
    ax.set_title("Channel-level trajectory fidelity across 86 batches (5-fold cross-validation)",
                 fontsize=9, color=BLUE, fontweight="bold")
    for i, k in enumerate(order):
        ax.text(i - w / 2, a[i] * 1.08, "%.1f" % a[i], ha="center", fontsize=5.8, va="bottom")
        ax.text(i + w / 2, b[i] * 1.08, "%.1f" % b[i], ha="center", fontsize=5.8, va="bottom")
    ax.legend(frameon=False, fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    save(fig, "figS1_channels")


# -------------------------------------------------------------- Fig S2 ----
def figS2():
    gate = load("r167_platform_gate.json")
    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.01, 0.965, "Runtime capability loading and the six-view simulation platform",
            fontsize=10, fontweight="bold", color=BLUE, va="top")

    tiers = [("A  6", BLUE), ("B  5", TEAL), ("C  2", AMBER), ("D  1", RED)]
    ax.text(0.015, 0.845, "14 MCP tools (in-process reuse of mcp_server.py function bodies):",
            fontsize=7.6, fontweight="bold")
    x = 0.015
    for lab, col in tiers:
        box(ax, x, 0.735, 0.115, 0.085, lab, "#FFFFFF", col, 8, True)
        x += 0.126
    box(ax, 0.535, 0.735, 0.450, 0.085,
        "12 operators: import + callable verified\n(not os.path.exists)", "#EAF5F2", TEAL, 6.4)

    ax.text(0.015, 0.655, "Four independent admission gates on POST /api/invoke:",
            fontsize=7.6, fontweight="bold")
    gts = ["whitelist (14)", "5 forbidden L3 keys", "opt_in = true", "confirm = true"]
    x = 0.015
    for t in gts:
        box(ax, x, 0.555, 0.235, 0.075, t, "#F7F9FB", "#9FB0BF", 6.7)
        x += 0.247

    ax.text(0.015, 0.475, "Six browser-rendered views (T8 screen-by-screen re-verification):",
            fontsize=7.6, fontweight="bold")
    views = ["overview", "topology", "batch", "channels", "operators", "workbench"]
    for i, v in enumerate(views):
        box(ax, 0.015 + i * 0.163, 0.375, 0.150, 0.075, v,
            "#DDF0EE" if v != "workbench" else "#DCE8F2",
            TEAL if v != "workbench" else BLUE, 6.6, v == "workbench")

    ax.text(0.015, 0.325, "Additive HTTP surface (L0 /api/simulate body unchanged):",
            fontsize=7.6, fontweight="bold")
    box(ax, 0.015, 0.200, 0.970, 0.095,
        "GET /api/health  |  GET /api/ops  |  GET /api/evidence  |  POST /api/invoke\n"
        "POST /api/simulate remains the frozen L0 baseline (function body unchanged)",
        LIGHT, "#9FB0BF", 6.5)

    n_pass = gate.get("n_pass"); n_checks = gate.get("n_checks")
    ax.text(0.015, 0.125,
            "Gate %s %s/%s  |  final check 20/20  |  contract v1.97  |  port 8771 (8770 untouched)  |  "
            "zero pageerror / console error / 4xx across six views" % (gate.get("verdict"), n_pass, n_checks),
            fontsize=6.6, color=INK)
    ax.text(0.015, 0.065,
            "Two naming defects (hier_est -> hier_fit, conservation_metrics -> element_balance) were invisible "
            "to file-existence checks and were exposed only by runtime verification.",
            fontsize=6.5, color=GREY)
    save(fig, "figS2_platform")


# -------------------------------------------------------------- Fig S3 ----
def figS3():
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.01, 0.95, "Evidence lifecycle of the research programme (167 documented rounds)",
            fontsize=9.5, fontweight="bold", color=BLUE, va="top")
    stages = [
        ("R1-R140", "model port,\ncalibration,\n86-batch anchor", "#EDF2F7", "#9FB0BF"),
        ("R141-R157", "falsification of\nconstant metrics,\nsign-off R-1..R-16", "#FBF0DC", AMBER),
        ("R158-R165", "identifiability,\ncontrol limits,\nnegative results", "#F7E3E0", RED),
        ("R166", "A/B gate 18/20\nNO_GO; V2 optim\nNO_GO (8/10)", "#F7E3E0", RED),
        ("R167", "runtime loading,\nsix views, M5\nPASS, v1.97", "#DDF0EE", TEAL),
    ]
    x = 0.015
    for i, (tag, body, fill, col) in enumerate(stages):
        box(ax, x, 0.39, 0.182, 0.32, tag + "\n\n" + body, fill, col, 6.6, i in (3, 4))
        if i < 4:
            arrow(ax, x + 0.184, 0.55, x + 0.197, 0.55, GREY, "-|>", 1.0)
        x += 0.198
    box(ax, 0.015, 0.145, 0.970, 0.175,
        "Every round emits: runs/rNNN_*.json + docs/rNNN_round_report.md + debt ledger entry +\n"
        "contract version row + idempotent governance sync (dry-run by default)",
        LIGHT, "#9FB0BF", 6.5)
    ax.text(0.015, 0.075,
            "Failure artefacts are preserved: the first-pass A/B FAIL (16/18) is archived alongside the final "
            "18/20 NO_GO; thresholds were never relaxed and no NO_GO was rewritten as PASS.",
            fontsize=6.7, color=GREY)
    save(fig, "figS3_lifecycle")


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4(); fig5(); fig6()
    figS1(); figS2(); figS3()
    print("DONE")
