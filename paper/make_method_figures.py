# -*- coding: utf-8 -*-
"""Figures for the counterfactual-validation (methods-oriented) manuscript.

Every value is read from paper/methods_experiments.json and
paper/extended_stats.json.  Missing experimental blocks (e.g. while the
fresh ODE integrations are still running) are skipped with a warning so
the script can be re-run incrementally.

Output: 300 dpi PNG plus vector PDF in paper/figures/.
"""
from __future__ import annotations

import json
import math
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PAPER = os.path.join(ROOT, "paper")
FIG = os.path.join(PAPER, "figures")
os.makedirs(FIG, exist_ok=True)

with open(os.path.join(PAPER, "methods_experiments.json"), encoding="utf-8") as f:
    M = json.load(f)
with open(os.path.join(PAPER, "extended_stats.json"), encoding="utf-8") as f:
    E = json.load(f)

BLUE = "#1F4E79"
TEAL = "#16807A"
RED = "#B03A2E"
AMBER = "#C9861B"
GREY = "#7F8C8D"
LIGHT = "#EDF2F7"
INK = "#22303C"
PURPLE = "#6B4C9A"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.4,
    "axes.titlesize": 9.4, "axes.labelsize": 8.4,
    "xtick.labelsize": 7.6, "ytick.labelsize": 7.6,
    "legend.fontsize": 7.4, "figure.dpi": 300, "savefig.dpi": 300,
    "axes.linewidth": 0.7, "pdf.fonttype": 42,
})


def save(fig, name):
    fig.subplots_adjust(top=min(fig.subplotpars.top, 0.87))
    for ext, kw in (("png", {"dpi": 300}), ("pdf", {})):
        fig.savefig(os.path.join(FIG, "%s.%s" % (name, ext)),
                    bbox_inches="tight", facecolor="white", **kw)
    plt.close(fig)
    print("  ->", name)


def label(ax, s, fs=9.6):
    ax.set_title(s, loc="left", fontsize=fs, fontweight="bold", color=BLUE, pad=9)


def despine(ax, sides=("top", "right")):
    for s in sides:
        ax.spines[s].set_visible(False)


def wrap(s, n=26):
    return "\n".join(textwrap.wrap(s, n))


def have(key):
    if key not in M:
        print("  !! skip (missing %s)" % key)
        return False
    return True


# ------------------------------------------------------------ M8 overview --
def fig_overview():
    """Simulation pipeline and counterfactual validation protocol (new Fig. 1)."""
    fig, ax = plt.subplots(figsize=(11.6, 6.3))
    ax.set_xlim(0, 100); ax.set_ylim(0, 56); ax.axis("off")

    def box(x, y, w, h, title, body, fc, ec, fs=8.0):
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.0",
                           facecolor=fc, edgecolor=ec, linewidth=1.1)
        ax.add_patch(p)
        ax.text(x + w / 2, y + h - 2.1, title, ha="center", va="center",
                fontsize=fs + 0.5, fontweight="bold", color=ec)
        ax.text(x + w / 2, y + h / 2 - 1.7, body, ha="center", va="center",
                fontsize=fs - 0.7, color=INK, linespacing=1.32)

    def arrow(x1, y1, x2, y2, color=GREY, style="-|>", lw=1.15, rad=0.0):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                     mutation_scale=9, color=color, linewidth=lw,
                                     connectionstyle="arc3,rad=%s" % rad))

    ax.text(50, 53.5, "Counterfactual validation protocol for process simulation models",
            ha="center", fontsize=11.6, fontweight="bold", color=BLUE)
    ax.text(50, 50.4, "IndPenSim penicillin fed-batch benchmark: industrial-scale demonstration, not the contribution",
            ha="center", fontsize=8.2, color=GREY, style="italic")

    # top row: pipeline
    box(2, 38.5, 21, 9.2, "1  BENCHMARK", "100 fed-batch records\n100,000 L, ~230 h\n26 on-line + 11 assay channels",
        "#F2F7FC", BLUE)
    box(27.5, 38.5, 21, 9.2, "2  MODEL", "33-state stiff ODE\n105 parameters\nBDF, rtol 1e-3, max step 0.01 h",
        "#F2F7FC", BLUE)
    box(53, 38.5, 21, 9.2, "3  FROZEN BASELINE", "86 calibrated batches\nyield RMSE 2.3448%\nreconstruction, not prediction",
        "#EAF5F2", TEAL)
    box(78.5, 38.5, 19.5, 9.2, "4  CLAIMS", "accuracy, health,\nidentifiability, transfer,\nsensitivity, deployment",
        "#FDF6EA", AMBER)
    for a, b in ((23, 27.5), (48.5, 53), (74, 78.5)):
        arrow(a, 43.1, b, 43.1, GREY)

    ax.text(95.0, 36.3, "every claim must be able to fail", fontsize=7.6,
            color=RED, ha="right", style="italic")

    # middle row: five diagnostic modules (a single bus, no crossing diagonals)
    ax.text(50, 34.9, "COUNTERFACTUAL DIAGNOSTIC BATTERY", ha="center",
            fontsize=9.2, fontweight="bold", color=PURPLE)
    mods = [
        ("E1  Solver\nsensitivity", "BDF / Radau / LSODA /\nRK45 at tighter tolerances", "#F2F7FC", BLUE),
        ("E5  Criterion\ndiscriminative validity", "zero-information control,\nconstant detector, trigger rate,\nobservation rank", "#F6F1FB", PURPLE),
        ("E4  Observation\noperator rank", "rank / nullity / condition\nnumber; new rows vs more rows", "#F6F1FB", PURPLE),
        ("E2  Leave-batch-out\nparameter transfer", "held-out batches never supply\ntheir own calibration vector", "#EAF5F2", TEAL),
        ("E3  Discontinuity-\naware sensitivity", "finite-difference step sweep\nand gradient-optimiser audit", "#FDF1EF", RED),
    ]
    xs = [1.5, 21.2, 40.9, 60.6, 80.3]
    ax.plot([10, 98], [32.6, 32.6], color=PURPLE, lw=1.0, alpha=0.75)
    arrow(98, 38.5, 98, 32.7, RED, lw=1.0)
    for (t, b, fc, ec), x in zip(mods, xs):
        box(x, 19.6, 18.2, 10.6, t, b, fc, ec, fs=7.7)
        arrow(x + 9.1, 32.6, x + 9.1, 30.3, ec, lw=0.9)

    # bottom row: three axes + filter
    box(4, 6.0, 27, 9.4, "THREE SEPARATE AXES",
        "control separation, output entropy,\ndetection power\n"
        "reported separately, never collapsed", "#F6F1FB", PURPLE, fs=7.7)
    box(36.5, 6.0, 27, 9.4, "ADMISSION FILTER",
        "reject tautological, constant,\nsaturated, degenerate and\ncollinear criteria first",
        "#FDF6EA", AMBER, fs=7.6)
    box(69, 6.0, 27, 9.4, "SURVIVING EVIDENCE",
        "4 of 10 criteria admitted; negative results\nretained as methodological evidence",
        "#EAF5F2", TEAL, fs=8.0)
    for a, b in ((31, 36.5), (63.5, 69)):
        arrow(a, 10.7, b, 10.7, GREY)
    arrow(50, 19.6, 17.5, 15.5, PURPLE, rad=-0.16, lw=0.85)
    ax.text(50, 2.4, "All experiments are in silico; no wet-laboratory or prospective plant data are introduced.",
            ha="center", fontsize=7.6, color=GREY, style="italic")
    save(fig, "figM8_overview")


# ------------------------------------------------------------- M1 solver ---
def fig_solver():
    if not have("E1_solver_sensitivity"):
        return
    d = M["E1_solver_sensitivity"]
    solvers = [c["id"] for c in d["configurations"]]
    batches = d["batches"]
    rows = d["rows"]
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.7))
    colors = [TEAL, BLUE, PURPLE, AMBER]

    ax = axes[0]
    label(ax, "(a) End-product deviation", fs=8.7)
    for j, s in enumerate(solvers):
        vals = []
        for b in batches:
            r = next((x for x in rows if x["solver"] == s and x["batch"] == b and x["ok"]), None)
            vals.append(abs(r["end_product_deviation_pct"]) if r else np.nan)
        ax.scatter([b for b in batches], vals, s=34, color=colors[j], label=s,
                   edgecolor="white", linewidth=0.6, zorder=3)
    ax.axhline(0.5, color=RED, ls="--", lw=0.9)
    ax.text(92, 0.62, "0.5% reference", fontsize=7, color=RED, ha="right")
    ax.set_yscale("symlog", linthresh=1e-4)
    ax.set_xlabel("batch"); ax.set_ylabel("|deviation| (%)")
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)
    ax.legend(frameon=False, ncol=2, loc="upper left", fontsize=6.9)

    ax = axes[1]
    label(ax, "(b) Batch-dependent solver spread")
    spread = []
    for b in batches:
        vals = [abs(r["end_product_deviation_pct"]) for r in rows
                if r["batch"] == b and r["ok"]]
        spread.append(max(vals) if vals else np.nan)
    bars = ax.bar(range(len(batches)), spread, width=0.62,
                  color=[RED if (v == v and v > 1.0) else TEAL for v in spread],
                  alpha=0.85)
    for bar, v in zip(bars, spread):
        if v == v:
            ax.text(bar.get_x() + bar.get_width() / 2, v, "%.1f" % v,
                    ha="center", va="bottom", fontsize=6.8)
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set_xticks(range(len(batches))); ax.set_xticklabels(batches)
    ax.set_xlabel("batch"); ax.set_ylabel("max |deviation| across solvers (%)")
    ax.axhline(1.0, color=GREY, ls="--", lw=0.9)
    ax.set_ylim(0, max([v for v in spread if v == v] + [1]) * 3)
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[2]
    label(ax, "(c) Computational cost")
    means = []
    for s in solvers:
        v = [r["cpu_s"] for r in rows if r["solver"] == s and r["ok"]]
        means.append(np.mean(v) if v else 0)
    bars = ax.bar(range(len(solvers)), means, color=colors, alpha=0.82, width=0.62)
    for b, v in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, v, "%.1f" % v,
                ha="center", va="bottom", fontsize=7.4)
    ax.set_xticks(range(len(solvers)))
    ax.set_xticklabels([s.replace("_", "\n") for s in solvers])
    ax.set_ylabel("mean CPU time (s) / batch")
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)
    fig.suptitle("E1 | Solver sensitivity of the frozen 33-state ODE (6 representative batches)",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.subplots_adjust(wspace=0.42)
    save(fig, "figM1_solver")


# ----------------------------------------------------------- M2 criteria ---
def fig_criteria():
    if not have("E5_discriminative_validity"):
        return
    d = M["E5_discriminative_validity"]
    rows = d["rows"]
    ids = [r["id"] for r in rows]
    names = [wrap(r["instrument"], 30) for r in rows]
    axes_names = ["control\nseparation", "output\nentropy", "detection\npower"]
    mat = np.array([[r["control_separation"], r["output_entropy"], r["detection_power"]]
                    for r in rows])
    fig = plt.figure(figsize=(11.2, 6.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1.0], wspace=0.34)

    ax = fig.add_subplot(gs[0])
    label(ax, "(a) Discriminative-validity matrix")
    im = ax.imshow(mat, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
    for i in range(len(rows)):
        for j in range(3):
            v = mat[i, j]
            ax.text(j, i, "%.2f" % v, ha="center", va="center",
                    fontsize=7.4, color="white" if v > 0.55 else INK,
                    fontweight="bold" if v == 0 else "normal")
            if v == 0:
                ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                       edgecolor=RED, linewidth=1.5))
    ax.set_xticks(range(3)); ax.set_xticklabels(axes_names, fontsize=7.8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(["%s  %s" % (i, n.replace("\n", " ")) for i, n in zip(ids, names)],
                       fontsize=7.0)
    for i, r in enumerate(rows):
        if not r["admissible_for_synthesis"]:
            ax.text(-0.62, i, "x", color=RED, fontsize=11, fontweight="bold",
                    ha="center", va="center")
        else:
            ax.text(-0.62, i, "+", color=TEAL, fontsize=11, fontweight="bold",
                    ha="center", va="center")
    ax.set_xlim(-0.95, 2.5)
    cb = fig.colorbar(im, ax=ax, fraction=0.032, pad=0.02)
    cb.ax.tick_params(labelsize=7)
    cb.set_label("axis value (0 = non-discriminating)", fontsize=7.4)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)

    ax2 = fig.add_subplot(gs[1], projection="polar")
    label(ax2, "(b) Axis fingerprints", fs=8.8)
    th = np.linspace(0, 2 * np.pi, 3, endpoint=False).tolist()
    th += th[:1]
    picks = [("M1 TAUTOLOGICAL", RED), ("M2 CONSTANT", AMBER),
             ("M3 SATURATED", PURPLE), ("M8 CERTIFIED", TEAL)]
    for mid, c in picks:
        r = next(x for x in rows if x["id"] == mid.split()[0])
        v = [r["control_separation"], r["output_entropy"], r["detection_power"]]
        v += v[:1]
        ax2.plot(th, v, color=c, lw=1.7, label=mid.split()[1], marker="o", ms=3)
        ax2.fill(th, v, color=c, alpha=0.10)
    ax2.set_xticks(th[:-1]); ax2.set_xticklabels(["control\nseparation", "output\nentropy",
                                                  "detection\npower"], fontsize=7.0)
    ax2.tick_params(axis="x", pad=11)
    ax2.set_ylim(0, 1.05); ax2.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax2.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=6.6)
    ax2.set_rlabel_position(62)
    ax2.grid(alpha=0.4, lw=0.7)
    ax2.legend(frameon=False, fontsize=6.6, loc="upper center",
               bbox_to_anchor=(0.5, -0.10), ncol=2)
    fig.suptitle("E5 | %d criteria: %d rejected, %d admitted to synthesis" %
                 (d["n_criteria"], d["n_rejected"], d["n_retained"]),
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    save(fig, "figM2_criteria")


# --------------------------------------------------------------- M3 rank ---
def fig_rank():
    if not have("E4_identifiability"):
        return
    d = M["E4_identifiability"]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.6))
    ax = axes[0]
    label(ax, "(a) Singular values (column-normalised)")
    for name, c in (("H_assim", RED), ("H_report", BLUE)):
        s = d["baseline"][name]["singular_values"]
        ax.bar(np.arange(4) + (-0.19 if name == "H_assim" else 0.19),
               [max(v, 1e-3) for v in s], width=0.36, color=c, alpha=0.85,
               label="%s (rank %d, nullity %d)" %
                     (name, d["baseline"][name]["rank"], d["baseline"][name]["nullity"]))
    ax.set_yscale("symlog", linthresh=1e-2)
    ax.axhline(1e-3, color=GREY, ls=":", lw=0.9)
    ax.text(1.5, 1.4e-3, "zeros plotted at 1e-3", fontsize=6.8, color=GREY, ha="center")
    ax.set_xticks(range(4)); ax.set_xticklabels(["A0", "A1", "A3", "A4"])
    ax.set_ylabel("singular value (symlog)")
    ax.legend(frameon=False, fontsize=6.8, loc="upper right")
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[1]
    label(ax, "(b) Rank restoration by new measurement types")
    ks = [r["n_independent_compartment_rows"] for r in d["rank_restoration"]]
    ranks = [r["rank"] for r in d["rank_restoration"]]
    nulls = [r["nullity"] for r in d["rank_restoration"]]
    ax.plot(ks, ranks, "o-", color=TEAL, lw=2, label="rank", ms=6)
    ax.plot(ks, nulls, "s--", color=RED, lw=1.7, label="nullity", ms=5)
    ax.set_xlabel("independent compartment-resolved rows added")
    ax.set_ylabel("dimension"); ax.set_ylim(-0.2, 4.4); ax.set_xticks(ks)
    ax.legend(frameon=False, fontsize=7.2); ax.grid(alpha=0.3, lw=0.6); despine(ax)

    ax = axes[2]
    label(ax, "(c) More rows of the same type do not help")
    cats = ["H_assim\n(50 x 4)", "H_report\n(60 x 4)", "H_report\n+ 50 repeated\nrows"]
    vals = [d["baseline"]["H_assim"]["rank"], d["baseline"]["H_report"]["rank"],
            d["repeated_rows"]["rank"]]
    bars = ax.bar(range(3), vals, color=[RED, AMBER, GREY], alpha=0.85, width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.07, "rank %d" % v,
                ha="center", fontsize=7.6)
    ax.set_xticks(range(3)); ax.set_xticklabels(cats, fontsize=7.2)
    ax.set_ylabel("rank"); ax.set_ylim(0, 2.0)
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)
    fig.suptitle("E4 | Observation-operator rank diagnostic on the four mycelial compartments",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "figM3_rank")


# ----------------------------------------------------------- M4 gradient ---
def fig_gradient():
    if not have("E3_discontinuity"):
        return
    d = M["E3_discontinuity"]
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.7))
    ax = axes[0]
    label(ax, "(a) Apparent gradient diverges as h -> 0")
    for br, c in zip(d["bisection_brackets"], [RED, PURPLE]):
        hs = [s["h"] for s in br["sweep"]]
        gs = [s["apparent_gradient_pp_per_unit"] for s in br["sweep"]]
        ax.loglog(hs, gs, "o-", color=c, lw=1.8, ms=5,
                  label="%s ($\Delta y$=%.1f pp)" % (br["knob"], br["jump_pp"]))
    ax.set_xlabel("finite-difference step h"); ax.set_ylabel("|apparent gradient| (pp / unit)")
    ax.grid(alpha=0.3, lw=0.6, which="both"); despine(ax)
    ax.legend(frameon=False, fontsize=7.0)
    ax.text(0.03, 0.08, "slope $\\propto 1/h$", transform=ax.transAxes,
            fontsize=7.6, color=INK, style="italic")

    ax = axes[1]
    label(ax, "(b) Adjacent-grid gradients", fs=8.7)
    adj = M.get("E3_discontinuity", {}).get("adjacent_grid_gradients", {})
    # reconstruct a compact display from the summary plus the frozen surface
    surf = E.get("kla_grid", {})
    grads = []
    for row in surf.get("yield_err_pct", []):
        for i in range(len(row) - 1):
            grads.append((row[i + 1] - row[i]) / 10.0)
    ax.hist(np.clip(grads, -12, 12), bins=36, color=BLUE, alpha=0.82, edgecolor="white", lw=0.4)
    ax.axvline(0, color=GREY, ls="--", lw=0.9)
    ax.set_xlabel("d(yield error)/d(alpha_kLa), clipped to +/-12 pp per unit")
    ax.set_ylabel("number of grid intervals")
    ax.text(0.97, 0.88, "n = %d\n|g|>1: %d\nsign flips: %d" %
            (adj.get("n_intervals", len(grads)), adj.get("n_abs_gt_1pp_per_unit", 0),
             adj.get("n_sign_flips", 0)),
            transform=ax.transAxes, ha="right", va="top", fontsize=7.2,
            bbox=dict(boxstyle="round,pad=0.35", fc="#F7FAFC", ec=LIGHT))
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[2]
    label(ax, "(c) Gradient optimiser outcomes", fs=8.7)
    opt = d["offline_optimisation"]
    methods = ["SLSQP", "trust-constr"]
    stalled, moved = [], []
    for m in methods:
        rr = [r for r in opt["rows"] if r.get("method") == m]
        stalled.append(sum(1 for r in rr if r.get("stalled_at_start")))
        moved.append(sum(1 for r in rr if not r.get("stalled_at_start") and "error" not in r))
    x = np.arange(2); w = 0.36
    ax.bar(x - w / 2, moved, w, color=TEAL, alpha=0.85, label="moved > 1 unit")
    ax.bar(x + w / 2, stalled, w, color=RED, alpha=0.85, label="stalled at start")
    ax.set_xticks(x); ax.set_xticklabels(methods)
    ax.set_ylabel("optimiser runs (n = 5 starts each)"); ax.set_ylim(0, 5.8)
    ax.legend(frameon=False, fontsize=7.0); ax.grid(axis="y", alpha=0.3, lw=0.6)
    despine(ax)
    fig.suptitle("E3 | Discontinuous parameter response invalidates finite-difference gradients",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.subplots_adjust(wspace=0.38)
    save(fig, "figM4_gradient")


# ----------------------------------------------------------- M5 transfer ---
def fig_transfer():
    if not have("E2_leave_batch_out"):
        return
    d = M["E2_leave_batch_out"]
    rec = E["error_distribution"]
    rec_err = E["parity"]["difference_pct"]
    med = [r["yield_err_pct"] for r in d["rows"]
           if r["ok"] and r["strategy"] == "median_prior"]
    draw = [r["yield_err_pct"] for r in d["rows"]
            if r["ok"] and r["strategy"] == "drawn_prior"]
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.7))

    ax = axes[0]
    label(ax, "(a) Reconstruction vs leave-batch-out transfer")
    parts = [np.clip(rec_err, -100, 100), np.clip(med, -100, 100), np.clip(draw, -100, 100)]
    bp = ax.boxplot(parts, labels=["per-batch\ncalibrated", "LBO median\nprior", "LBO drawn\nprior"],
                    patch_artist=True, widths=0.58, showfliers=True,
                    flierprops=dict(marker="o", ms=2.4, alpha=0.45))
    for p, c in zip(bp["boxes"], [TEAL, AMBER, RED]):
        p.set_facecolor(c); p.set_alpha(0.4); p.set_edgecolor(c)
    for m in bp["medians"]:
        m.set_color(INK); m.set_linewidth(1.3)
    ax.axhspan(-5, 5, color=TEAL, alpha=0.09)
    ax.axhline(0, color=GREY, ls="--", lw=0.8)
    ax.set_ylabel("end-of-batch yield error (%)")
    ax.text(0.5, 0.95, "shaded: +/-5% acceptance band", transform=ax.transAxes,
            ha="center", va="top", fontsize=7.0, color=TEAL)
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[1]
    label(ax, "(b) Empirical CDF of absolute error")
    for v, c, lab in ((np.abs(rec_err), TEAL, "per-batch calibrated"),
                      (np.abs(med), AMBER, "LBO median prior"),
                      (np.abs(draw), RED, "LBO drawn prior")):
        v = np.sort(v)
        ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=c, lw=1.7, label=lab)
    ax.axvline(5, color=GREY, ls="--", lw=0.9)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("|yield error| (%)"); ax.set_ylabel("cumulative fraction")
    ax.legend(frameon=False, fontsize=6.9, loc="lower right")
    ax.grid(alpha=0.3, lw=0.6); despine(ax)

    ax = axes[2]
    label(ax, "(c) RMSE comparison and interval coverage")
    vals = [2.3448, d["median_prior"]["rmse_pct"] or 0, d["drawn_prior"]["rmse_pct"] or 0]
    names = ["reconstruction\n(per-batch)", "LBO median\nprior", "LBO drawn\nprior"]
    bars = ax.bar(range(3), np.clip(vals, 0, 200), color=[TEAL, AMBER, RED],
                  alpha=0.85, width=0.58)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, min(v, 200),
                "%.1f%%" % v, ha="center", va="bottom", fontsize=7.8)
    ax.set_xticks(range(3)); ax.set_xticklabels(names, fontsize=7.4)
    ax.set_ylabel("yield RMSE (%)")
    cov = d["drawn_prior"].get("p05_p95_interval_coverage")
    ax.text(0.02, 0.60, "P5/P95 coverage: %s" % ("%.2f" % cov if cov is not None else "n/a"),
            transform=ax.transAxes, ha="left", va="top", fontsize=7.4,
            bbox=dict(boxstyle="round,pad=0.3", fc="#F7FAFC", ec=LIGHT))
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)
    fig.suptitle("E2 | Leave-batch-out parameter transfer separates reconstruction from prediction",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "figM5_transfer")


# ------------------------------------------------------- M6 uncertainty ----
def fig_uncertainty():
    if not have("E6_uncertainty_propagation"):
        return
    d = M["E6_uncertainty_propagation"]
    bb = d["by_batch"]
    keys = list(bb.keys())
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.7),
                             gridspec_kw={"width_ratios": [1.35, 1.0, 1.0]})
    ax = axes[0]
    label(ax, "(a) Monte Carlo yield deviation by batch")
    for i, k in enumerate(keys):
        v = bb[k]
        if not v.get("n"):
            continue
        ax.plot([v["p05_pct"], v["p95_pct"]], [i, i], color=BLUE, lw=2.2,
                solid_capstyle="round")
        ax.plot([v["p50_pct"]], [i], "o", color=RED, ms=5.5)
        ax.plot([v["p05_pct"], v["p95_pct"]], [i, i], "|", color=BLUE, ms=9)
    ax.axvline(0, color=GREY, ls="--", lw=0.9)
    ax.set_yticks(range(len(keys))); ax.set_yticklabels(["batch %s" % k for k in keys])
    ax.set_xlabel("yield deviation from the frozen baseline (%)")
    ax.text(0.98, 0.05, "bar: P5-P95, dot: median", transform=ax.transAxes,
            ha="right", fontsize=7.0, color=GREY)
    ax.grid(axis="x", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[1]
    label(ax, "(b) Pooled deviation distribution")
    pooled = [r["deviation_from_baseline_pct"] for r in d["rows"] if r["ok"]]
    ax.hist(pooled, bins=22, color=TEAL, alpha=0.8, edgecolor="white", lw=0.4)
    ax.axvline(0, color=GREY, ls="--", lw=0.9)
    ax.axvspan(-2.3448, 2.3448, color=AMBER, alpha=0.16)
    ax.text(0.97, 0.92, "n = %d\nRMSE %.2f%%" % (len(pooled), d["pooled"]["rmse_pct"] or 0),
            transform=ax.transAxes, ha="right", va="top", fontsize=7.2,
            bbox=dict(boxstyle="round,pad=0.3", fc="#F7FAFC", ec=LIGHT))
    ax.set_xlabel("yield deviation (%)"); ax.set_ylabel("replicates")
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[2]
    label(ax, "(c) Sensitivity proxy by parameter")
    sens = d["sensitivity_correlation"]
    ks = list(sens.keys()); vs = [abs(sens[k] or 0) for k in ks]
    bars = ax.bar(range(len(ks)), vs, color=[BLUE, PURPLE, AMBER], alpha=0.85, width=0.58)
    for b, v in zip(bars, vs):
        ax.text(b.get_x() + b.get_width() / 2, v, "%.2f" % v,
                ha="center", va="bottom", fontsize=7.6)
    ax.set_xticks(range(len(ks)))
    ax.set_xticklabels([k.replace("alpha_kla", "alpha_kLa") for k in ks], fontsize=7.4)
    ax.set_ylabel("|correlation with |yield deviation||"); ax.set_ylim(0, max(vs + [0.4]) * 1.35)
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)
    fig.suptitle("E6 | Propagation of nominal batch-level random effects through the frozen ODE",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "figM6_uncertainty")


# ------------------------------------------------------------ M7 filter ----
def fig_filter():
    if not have("E8_admission_filter") or not have("E5_discriminative_validity"):
        return
    e8 = M["E8_admission_filter"]
    e5 = M["E5_discriminative_validity"]
    fig, ax = plt.subplots(figsize=(11.2, 4.4))
    ax.set_xlim(0, 100); ax.set_ylim(0, 42); ax.axis("off")

    def node(x, y, w, h, title, sub, fc, ec, fs=8.0):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.5,rounding_size=0.9",
                                    facecolor=fc, edgecolor=ec, lw=1.1))
        ax.text(x + w / 2, y + h - 2.3, title, ha="center", va="center",
                fontsize=fs + 0.4, fontweight="bold", color=ec)
        ax.text(x + w / 2, y + h / 2 - 1.4, sub, ha="center", va="center",
                fontsize=fs - 0.9, color=INK, linespacing=1.35)

    def arrow(x1, y1, x2, y2, c=GREY, lw=1.3):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=11, color=c, lw=lw))

    ax.text(50, 39.6, "E8 | Admission filter: remove degenerate criteria before any multi-criteria synthesis",
            ha="center", fontsize=10.2, fontweight="bold", color=BLUE)
    node(1.5, 24, 20, 11, "EVIDENCE POOL",
         "%d acceptance criteria\n%d gate checks in %d families" %
         (e8["before"]["n_instruments"], e8["before"]["n_gate_checks"],
          e8["before"]["n_gate_families"]), "#F2F7FC", BLUE)
    node(26, 24, 22, 11, "COUNTERFACTUAL AUDITS",
         "zero-information control\nconstant-detector / trigger-rate\nobservation-rank / collinearity",
         "#F6F1FB", PURPLE)
    node(53, 27.5, 20, 8.5, "REJECT",
         "%d criteria\n%s" % (e8["after"]["n_instruments"] and e5["n_rejected"],
                              ", ".join(e8["after"]["rejected_ids"])), "#FDF1EF", RED)
    node(53, 16.5, 20, 8.5, "ADMIT",
         "%d criteria\n%s" % (e5["n_retained"], ", ".join(e5["retained_ids"])),
         "#EAF5F2", TEAL)
    node(79, 21.5, 19.5, 11, "SYNTHESIS",
         "report surviving evidence\nand the negative results\nas methodological findings",
         "#FDF6EA", AMBER)
    arrow(21.5, 29.5, 26, 29.5)
    arrow(48, 29.5, 53, 31.7, RED)
    arrow(48, 29.5, 53, 20.7, TEAL)
    arrow(73, 20.7, 79, 25.5, TEAL)
    arrow(73, 31.7, 79, 29.0, RED, lw=1.0)
    ax.text(76, 34.2, "archived, not deleted", fontsize=7.4, color=RED,
            ha="center", style="italic")

    # lower strip: verdict breakdown
    counts = {}
    for r in e5["rows"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    x0 = 3.0
    ax.text(3.0, 10.8, "Verdict distribution across the diagnostic matrix",
            fontsize=8.4, fontweight="bold", color=BLUE)
    palette = {"TAUTOLOGICAL": RED, "CONSTANT": AMBER, "SATURATED": PURPLE,
               "CERTIFIED": TEAL, "CERTIFIED (opt-in)": "#57A99A",
               "CERTIFIED (width only)": "#7FC3B7", "DEGENERATE": "#C97B6E",
               "COLLINEAR": "#9B8AA5"}
    total = sum(counts.values())
    for name, n in counts.items():
        w = 94.0 * n / total
        ax.add_patch(Rectangle((x0, 4.0), w - 0.5, 4.4,
                               facecolor=palette.get(name, GREY), alpha=0.85,
                               edgecolor="white", lw=1.0))
        ax.text(x0 + (w - 0.5) / 2, 6.2, "%s\n%d" % (name.replace(" (", "\n("), n),
                ha="center", va="center", fontsize=6.8, color="white", fontweight="bold")
        x0 += w
    save(fig, "figM7_filter")


# ------------------------------------------------------------ M9 balance ---
def fig_balance():
    if not have("E7_physical_consistency"):
        return
    d = M["E7_physical_consistency"]
    cb = d["carbon_balance"]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
    ax = axes[0]
    label(ax, "(a) Carbon-balance error by batch")
    vals = cb["per_batch_pct"]; bs = cb["batches"]
    cols = [TEAL if abs(v) <= 20 else RED for v in vals]
    ax.bar(range(len(vals)), vals, color=cols, alpha=0.85, width=0.68)
    ax.axhspan(-20, 20, color=TEAL, alpha=0.09)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xticks(range(len(bs))); ax.set_xticklabels(bs, rotation=45, ha="right", fontsize=6.9)
    ax.set_ylabel("carbon-balance error (%)")
    ax.text(0.98, 0.92, "%d/%d within +/-20%%\nmedian %.2f%%" %
            (cb["n_within_budget"], cb["n_batches"], cb["median_pct"]),
            transform=ax.transAxes, ha="right", va="top", fontsize=7.2,
            bbox=dict(boxstyle="round,pad=0.3", fc="#F7FAFC", ec=LIGHT))
    ax.grid(axis="y", alpha=0.3, lw=0.6); despine(ax)

    ax = axes[1]
    label(ax, "(b) Declared closure boundaries")
    items = [
        ("Carbon", cb["median_pct"], 20.0),
        ("Nitrogen (model conv.)", 9.9, 35.0),
        ("Nitrogen (metering conv.)", -58.1, 35.0),
    ]
    ys = np.arange(len(items))
    for i, (name, v, budget) in enumerate(items):
        ok = abs(v) <= budget
        ax.barh(i, v, color=TEAL if ok else RED, alpha=0.82, height=0.5)
        ax.plot([-budget, budget], [i, i], color=BLUE, lw=1.2, ls="--", alpha=0.7)
        ax.text(v + (1.5 if v >= 0 else -1.5), i, "%.1f%%" % v,
                va="center", ha="left" if v >= 0 else "right", fontsize=7.4)
    ax.set_yticks(ys); ax.set_yticklabels([n for n, _, _ in items], fontsize=7.4)
    ax.axvline(0, color=GREY, lw=0.8)
    ax.set_xlabel("balance error (%)   |   dashed: declared budget")
    ax.grid(axis="x", alpha=0.3, lw=0.6); despine(ax)
    fig.suptitle("E7 | Physical-consistency checks on the steady-state census",
                 fontsize=9.8, color=BLUE, fontweight="bold", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "figM9_balance")


if __name__ == "__main__":
    print("generating methodological figures ...")
    fig_overview()
    fig_criteria()
    fig_rank()
    fig_gradient()
    fig_filter()
    fig_balance()
    fig_solver()
    fig_transfer()
    fig_uncertainty()
    print("done.")
