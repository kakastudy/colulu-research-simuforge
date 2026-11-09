# -*- coding: utf-8 -*-
"""Extended publication figures for the revised manuscript.

Every value is read from paper/extended_stats.json (itself derived from runs/).
Figures are 300 dpi PNG plus vector PDF.  Figure types deliberately go beyond
time-series/trend plots: parity, Bland-Altman, violin, ECDF, Q-Q, ACF, radar,
heatmap, forest, parallel coordinates, alluvial/Sankey and mosaic plots.
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
from scipy import stats as sps
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch, Polygon, PathPatch
from matplotlib.path import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIG = os.path.join(ROOT, "paper", "figures")
os.makedirs(FIG, exist_ok=True)
with open(os.path.join(ROOT, "paper", "extended_stats.json"), "r", encoding="utf-8") as f:
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
    "pdf.fonttype": 42,
})

DIV = LinearSegmentedColormap.from_list(
    "div", ["#B03A2E", "#E8C9C3", "#FFFFFF", "#B7DAD6", "#16807A"])
SEQ = LinearSegmentedColormap.from_list(
    "seq", ["#F4F7FA", "#CFDEEC", "#7FA9CD", "#1F4E79"])


def save(fig, name):
    fig.subplots_adjust(top=min(fig.subplotpars.top, 0.865))
    for ext, kw in (("png", {"dpi": 300}), ("pdf", {})):
        p = os.path.join(FIG, "%s.%s" % (name, ext))
        fig.savefig(p, bbox_inches="tight", facecolor="white", **kw)
    plt.close(fig)
    print("  ->", name)


def label(ax, s):
    ax.set_title(s, loc="left", fontsize=9.2, fontweight="bold",
                 color=BLUE, pad=9)


def despine(ax, sides=("top", "right")):
    for s in sides:
        ax.spines[s].set_visible(False)


def heat(ax, mat, xticks, yticks, cmap=SEQ, vmin=None, vmax=None,
         fmt="{:.2f}", cbar_label="", fontsize=6.2, cbar=True):
    m = np.asarray(mat, dtype=float)
    if vmin is None:
        vmin = float(np.nanmin(m))
    if vmax is None:
        vmax = float(np.nanmax(m))
    masked = np.ma.masked_invalid(m)
    im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    ax.set_xticks(range(len(xticks)))
    ax.set_xticklabels(xticks)
    ax.set_yticks(range(len(yticks)))
    ax.set_yticklabels(yticks)
    ax.tick_params(length=0)
    ax.set_xticks(np.arange(-0.5, len(xticks), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(yticks), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.55, alpha=0.85)
    ax.tick_params(which="minor", length=0)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if not np.isnan(m[i, j]):
                ax.text(j, i, fmt.format(m[i, j]), ha="center", va="center",
                        fontsize=fontsize,
                        color="white" if (m[i, j] - vmin) / max(1e-12, vmax - vmin) > 0.62 else INK)
    for sp in ax.spines.values():
        sp.set_visible(False)
    if cbar:
        cb = plt.colorbar(im, ax=ax, fraction=0.026, pad=0.015)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=6)
        if cbar_label:
            cb.set_label(cbar_label, fontsize=6.5)
    return im


# ======================================================================
# Fig. 7 - baseline ladder, naive competitors, parity, Bland-Altman
# ======================================================================
def fig7():
    fig, axs = plt.subplots(2, 2, figsize=(11.6, 8.2))
    fig.subplots_adjust(hspace=0.46, wspace=0.30)

    # (a) calibration ladder
    ax = axs[0, 0]
    steps = E["calibration_ladder"]["steps"]
    zh2en = {
        "名义参数": "Nominal parameters",
        "3D 校准 (mux/mup/dTcin)": "3-param calib. (mux/mup/dTcin)",
        "m_s × mux": "m_s x mux grid",
        "组合 (3D + m_s)": "3-param + m_s",
        "m_s × mup × dTcin (3D)": "m_s x mup x dTcin",
        "改进 (constant m_s)": "constant m_s",
        "时变 m_s (最终)": "time-varying m_s (final)",
    }
    names = [textwrap.fill(zh2en.get(s["method"], s["method"]), 16) for s in steps]
    vals = [s["rmse_pct"] for s in steps]
    xs = np.arange(len(vals))
    ax.bar(xs - 0.18, vals, 0.52, color="#AFC6DC", edgecolor=BLUE, linewidth=0.7)
    ax.plot(xs, vals, "o-", color=BLUE, lw=1.2, ms=3.5)
    for i, v in enumerate(vals):
        ax.text(i, v + 1.6, "%.2f" % v, ha="center", fontsize=6.3, color=INK)
    ax.axvline(len(vals) - 0.45, color=GREY, ls="--", lw=1.0)
    ax.bar([len(vals) + 0.35], [E["calibration_ladder"]["final_86_batch_rmse_pct"]],
           0.52, color=TEAL, edgecolor=INK, linewidth=0.7)
    ax.text(len(vals) + 0.35, E["calibration_ladder"]["final_86_batch_rmse_pct"] + 1.6,
            "2.34", ha="center", fontsize=6.3, color=TEAL, fontweight="bold")
    ax.text(len(vals) - 0.45, 62, " protocol changes:\n 12 -> 86 batches", fontsize=6.0,
            color=GREY, ha="right", va="top")
    allnames = names + ["Final 86-batch\nfrozen anchor"]
    ax.set_xticks(list(xs) + [len(vals) + 0.35])
    ax.set_xticklabels(allnames, fontsize=5.7, rotation=32, ha="right")
    ax.set_ylabel("Yield RMSE (%)")
    ax.set_ylim(0, 82)
    label(ax, "(a) Calibration ladder (different protocols)")
    despine(ax)

    # (b) naive baselines, two normalisations
    ax = axs[0, 1]
    rows = E["baseline_ladder"]["rows"]
    ys = np.arange(len(rows))[::-1]
    rel = [r["rmse_pct"] for r in rows]
    med = [r["rmse_pct_of_median_yield"] for r in rows]
    ax.barh(ys + 0.19, rel, 0.36, color=BLUE, label="relative yield error RMSE")
    ax.barh(ys - 0.19, med, 0.36, color=TEAL, label="absolute error / median yield")
    for y, a, b in zip(ys, rel, med):
        ax.text(a + 1.5, y + 0.19, "%.2f" % a, va="center", fontsize=6.2)
        ax.text(b + 1.5, y - 0.19, "%.2f" % b, va="center", fontsize=6.2, color=TEAL)
    ax.set_yticks(ys)
    ax.set_yticklabels([textwrap.fill(r["name"], 30) for r in rows], fontsize=6.3)
    ax.set_xlabel("RMSE (%)")
    ax.set_xlim(0, 118)
    ax.legend(frameon=False, loc="upper right", fontsize=6.2)
    label(ax, "(b) Frozen twin vs. uninformed competitors")
    despine(ax)

    # (c) parity
    ax = axs[1, 0]
    p = E["parity"]
    yt = np.asarray(p["recorded_yield_g"]) / 1e6
    ys_ = np.asarray(p["simulated_yield_g"]) / 1e6
    ax.scatter(yt, ys_, s=16, color=BLUE, alpha=0.72, edgecolor="white", linewidth=0.4)
    lo, hi = 0.4, 4.8
    ax.plot([lo, hi], [lo, hi], color=INK, lw=1.0, label="identity")
    ax.fill_between([lo, hi], [lo * 0.95, hi * 0.95], [lo * 1.05, hi * 1.05],
                    color=TEAL, alpha=0.13, label="+/-5% band")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Recorded product mass (10$^6$ g)")
    ax.set_ylabel("Simulated product mass (10$^6$ g)")
    ax.text(0.03, 0.94, "r = %.4f   R$^2$ = %.4f\n86/86 inside +/-5%%" %
            (p["pearson_r"], p["r2"]), transform=ax.transAxes,
            fontsize=6.6, va="top", color=INK,
            bbox=dict(fc="white", ec="#C8D3DD", lw=0.6, pad=3))
    ax.legend(frameon=False, loc="lower right", fontsize=6.3)
    label(ax, "(c) Parity of recorded and simulated yield")
    despine(ax)

    # (d) Bland-Altman
    ax = axs[1, 1]
    mx = np.asarray(p["mean_yield_g"]) / 1e6
    dd = np.asarray(p["difference_pct"])
    colors = [RED if abs(v) > 4 else (AMBER if abs(v) > 2 else BLUE) for v in dd]
    ax.scatter(mx, dd, s=15, c=colors, alpha=0.72, edgecolor="white", linewidth=0.4)
    for v, c, ls in ((p["ba_mean_pct"], INK, "-"), (p["ba_lo_pct"], RED, "--"),
                     (p["ba_hi_pct"], RED, "--")):
        ax.axhline(v, color=c, ls=ls, lw=0.9)
    ax.text(0.98, 0.95, "bias %.3f%%\nlimits %.2f / +%.2f%%" %
            (p["ba_mean_pct"], p["ba_lo_pct"], p["ba_hi_pct"]),
            transform=ax.transAxes, fontsize=6.5, va="top", ha="right",
            bbox=dict(fc="white", ec="#C8D3DD", lw=0.6, pad=3))
    ax.axhline(5, color=TEAL, ls=":", lw=0.8)
    ax.axhline(-5, color=TEAL, ls=":", lw=0.8)
    ax.set_xlabel("Mean of recorded and simulated yield (10$^6$ g)")
    ax.set_ylabel("Difference (%)")
    ax.set_ylim(-7, 7)
    label(ax, "(d) Bland-Altman difference plot")
    despine(ax)

    fig.suptitle("Fig. 7 | Extended baseline validation: calibration history, uninformed "
                 "competitors, parity and agreement", fontsize=9.5, color=BLUE,
                 fontweight="bold", y=0.995)
    save(fig, "fig7_baselines")


# ======================================================================
# Fig. 8 - distributional diagnostics
# ======================================================================
def fig8():
    fig, axs = plt.subplots(2, 2, figsize=(11.6, 8.0))
    fig.subplots_adjust(hspace=0.48, wspace=0.28)
    d = E["error_distribution"]
    fv = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"),
                        encoding="utf-8"))["results"]
    e_all = np.asarray([100.0 * r["yield_err"] for r in fv])

    # (a) violin / box by health class
    ax = axs[0, 0]
    groups = [(k, np.asarray(v)) for k, v in E["error_by_health"].items()
              if len(v) >= 3]
    order = ["normal", "degraded", "catastrophic"]
    groups.sort(key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
    data = [g[1] for g in groups]
    vp = ax.violinplot(data, positions=range(1, len(data) + 1), widths=0.72,
                       showextrema=False, bw_method=0.4)
    for i, body in enumerate(vp["bodies"]):
        body.set_facecolor([BLUE, AMBER, RED][i % 3])
        body.set_alpha(0.35)
        body.set_edgecolor([BLUE, AMBER, RED][i % 3])
        body.set_linewidth(0.9)
    ax.boxplot(data, positions=range(1, len(data) + 1), widths=0.16,
               showfliers=False, patch_artist=True,
               boxprops=dict(facecolor="white", lw=0.8),
               medianprops=dict(color=INK, lw=1.1),
               whiskerprops=dict(lw=0.7), capprops=dict(lw=0.7))
    for i, (k, v) in enumerate(groups, start=1):
        ax.text(i, 5.6, "n=%d" % len(v), ha="center", fontsize=6.2, color=GREY)
    ax.axhline(5, color=GREY, ls=":", lw=0.8)
    ax.axhline(-5, color=GREY, ls=":", lw=0.8)
    ax.set_xticks(range(1, len(groups) + 1))
    ax.set_xticklabels([g[0] for g in groups])
    ax.set_ylabel("Yield error (%)")
    ax.set_ylim(-7, 7)
    label(ax, "(a) Error distribution by health class")
    despine(ax)

    # (b) ECDF + histogram
    ax = axs[0, 1]
    xs = np.sort(e_all)
    ys = np.arange(1, len(xs) + 1) / len(xs)
    ax.step(xs, ys, where="post", color=BLUE, lw=1.4, label="ECDF of signed error")
    ax.fill_between(xs, ys, step="post", color=BLUE, alpha=0.09)
    ax2 = ax.twinx()
    ax2.hist(e_all, bins=18, color=GREY, alpha=0.30, edgecolor="white", linewidth=0.4)
    ax2.set_ylabel("count", fontsize=7, color=GREY)
    ax2.tick_params(axis="y", labelsize=6, colors=GREY)
    ax2.spines["top"].set_visible(False)
    ax.axvline(-5, color=TEAL, ls=":", lw=0.9)
    ax.axvline(5, color=TEAL, ls=":", lw=0.9)
    ax.text(0.02, 0.06, "SD %.3f%%  IQR %.3f pp\nWilson 95%% CI for 86/86: [%.3f, %.3f]" %
            (d["sd_pct"], d["iqr_pct"], d["wilson95_within5"][0], d["wilson95_within5"][1]),
            transform=ax.transAxes, fontsize=6.3, va="bottom",
            bbox=dict(fc="white", ec="#C8D3DD", lw=0.6, pad=3))
    ax.set_xlabel("Signed yield error (%)")
    ax.set_ylabel("Cumulative probability")
    ax.set_ylim(0, 1.04)
    ax.legend(frameon=False, loc="lower right", fontsize=6.2)
    label(ax, "(b) Empirical CDF and histogram")
    despine(ax)

    # (c) Q-Q plot
    ax = axs[1, 0]
    (osm, osr), (slope, intercept, r) = sps.probplot(e_all, dist="norm")
    ax.scatter(osm, osr, s=14, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.4)
    ax.plot(osm, slope * osm + intercept, color=RED, lw=1.1)
    lim = [float(min(osm)), float(max(osm))]
    ax.plot(lim, [slope * v + intercept for v in lim], color=RED, lw=1.1)
    ax.text(0.03, 0.94, "Shapiro-Wilk W = %.4f, p = %.4f\nQ-Q correlation r = %.4f\nskew %.3f, excess kurtosis %.3f" %
            (d["shapiro_W"], d["shapiro_p"], r, d["skewness"], d["excess_kurtosis"]),
            transform=ax.transAxes, fontsize=6.3, va="top",
            bbox=dict(fc="white", ec="#C8D3DD", lw=0.6, pad=3))
    ax.set_xlabel("Theoretical normal quantile")
    ax.set_ylabel("Observed error quantile (%)")
    label(ax, "(c) Normality assessment")
    despine(ax)

    # (d) ACF
    ax = axs[1, 1]
    lags = np.arange(1, 11)
    x = e_all - e_all.mean()
    den = float(np.dot(x, x))
    acf = np.asarray([float(np.dot(x[:-k], x[k:])) / den for k in lags])
    cols = [RED if abs(v) > 1.96 / math.sqrt(len(e_all)) else BLUE for v in acf]
    ax.bar(lags, acf, 0.62, color=cols, alpha=0.85)
    b = 1.96 / math.sqrt(len(e_all))
    ax.axhline(b, color=GREY, ls="--", lw=0.8)
    ax.axhline(-b, color=GREY, ls="--", lw=0.8)
    ax.axhline(0, color=INK, lw=0.7)
    ax.set_xticks(lags)
    ax.set_xlabel("Lag (batch order)")
    ax.set_ylabel("Autocorrelation")
    ax.set_ylim(-0.35, 0.35)
    ax.text(0.03, 0.94, "lag-1 %.4f   Wald-Wolfowitz runs %d (p = %.3f)\nsign test %d+/ %d- (p = %.3f)" %
            (d["lag1_autocorr"], d["runs"], d["runs_p"], d["n_positive"],
             d["n_negative"], d["sign_test_p"]),
            transform=ax.transAxes, fontsize=6.3, va="top",
            bbox=dict(fc="white", ec="#C8D3DD", lw=0.6, pad=3))
    label(ax, "(d) Serial-dependence check")
    despine(ax)

    fig.suptitle("Fig. 8 | Distributional diagnostics of the frozen-baseline error "
                 "(n = 86)", fontsize=9.5, color=BLUE, fontweight="bold", y=0.995)
    save(fig, "fig8_distribution")


# ======================================================================
# Fig. 9 - falsifiability certificates
# ======================================================================
def fig9():
    fig = plt.figure(figsize=(11.6, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.42, 0.95, 0.95], wspace=0.42)
    axs = [fig.add_subplot(gs[0, i]) for i in range(3)]
    certs = E["falsifiability_certificates"]["rows"]
    short = {
        "M1": "resid.-quantile coverage", "M2": "legacy crash classifier",
        "M3": "global innovation test", "M4": "five-channel health",
        "M5": "channel-wise LOO (V1)", "M6": "mu +/- 1.96 sigma",
        "M7": "file-existence load", "M8": "import + callable",
    }

    # (a) heatmap
    ax = axs[0]
    mat = np.asarray([[c["control_separation"], c["output_degeneracy"],
                       c["detection_power"]] for c in certs], dtype=float)
    mat = np.clip(mat, 0, 1)
    heat(ax, mat, ["Control\nseparation", "Output\nnon-degeneracy",
                   "Detection\npower"],
         ["%s  %s" % (c["id"], short[c["id"]]) for c in certs],
         cmap=SEQ, vmin=0, vmax=1, fmt="{:.2f}", fontsize=6.4,
         cbar_label="certificate axis (0-1)")
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=6.2)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=6.0)
    label(ax, "(a) Machine-checkable falsifiability certificates")

    # (b) radar
    ax = fig.add_subplot(gs[0, 1], projection="polar")
    axes = E["falsifiability_certificates"]["schema"][:3]
    pick = ["M1", "M2", "M3", "M8"]
    cols = {"M1": RED, "M2": AMBER, "M3": PURPLE, "M8": TEAL}
    ang = np.linspace(0, 2 * np.pi, len(axes), endpoint=False).tolist()
    ang += ang[:1]
    for cid in pick:
        c = next(c for c in certs if c["id"] == cid)
        v = [min(1.0, c[k]) for k in axes]
        v += v[:1]
        ax.plot(ang, v, lw=1.3, color=cols[cid], label=cid)
        ax.fill(ang, v, color=cols[cid], alpha=0.07)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels(["control\nseparation", "output\nentropy", "detection\npower"],
                       fontsize=6.0)
    ax.tick_params(axis="x", pad=9)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["", "0.5", "", "1.0"], fontsize=5.8)
    ax.tick_params(axis="y", colors=GREY)
    ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.28, 1.14), fontsize=6.0)
    ax.set_title("(b) Instrument fingerprints", fontsize=9, color=BLUE,
                 fontweight="bold", pad=18, loc="left")

    # (c) V1 confusion matrix + metrics
    ax = axs[2]
    cf = E["falsifiability_certificates"]["v1_confusion"]
    m = np.asarray([[cf["TP"], cf["FN"]], [cf["FP"], cf["TN"]]], dtype=float)
    heat(ax, m, ["injected", "control"], ["flagged", "not flagged"],
         cmap=SEQ, vmin=0, vmax=10, fmt="{:.0f}", fontsize=10, cbar=False)
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", pad=4)
    ax.set_title("(c) V1 channel-wise detector", fontsize=9, color=BLUE,
                 fontweight="bold", loc="left")
    ax.text(0.5, -0.13,
            "TPR %.3f   FPR %.3f   Youden J = %.3f   accuracy %.2f\n"
            "0/20 controls triggered; 11/20 injections detected; LOO 5/5." %
            (cf["TPR"], cf["FPR"], cf["Youden_J"], cf["accuracy"]),
            transform=ax.transAxes, ha="center", va="top", fontsize=6.2, color=INK,
            bbox=dict(fc=LIGHT, ec="#C8D3DD", lw=0.6, pad=4))

    fig.suptitle("Fig. 9 | Auditing the auditors: eight acceptance instruments scored on "
                 "three discriminability axes", fontsize=9.5, color=BLUE,
                 fontweight="bold", y=0.99)
    save(fig, "fig9_certificates")


# ======================================================================
# Fig. 10 - evidence matrix, forests, inventory
# ======================================================================
def fig10():
    fig, axs = plt.subplots(2, 2, figsize=(11.6, 8.0))
    fig.subplots_adjust(hspace=0.55, wspace=0.30)
    gm = E["gate_matrices"]

    # (a) gate matrix
    ax = axs[0, 0]
    keys = ["G", "F", "AB", "V2O", "R166F"]
    maxlen = max(len(gm[k]) for k in keys)
    mat = np.full((len(keys), maxlen), 0.5)  # grey = no such check
    for i, k in enumerate(keys):
        for j, c in enumerate(gm[k]):
            mat[i, j] = 1.0 if c["pass"] else 0.0
    cmap = LinearSegmentedColormap.from_list(
        "bwg", ["#B03A2E", "#E9EDF1", "#16807A"])
    heat(ax, mat, ["" if j % 5 else str(j + 1) for j in range(maxlen)],
         ["%s (n=%d)" % (k, len(gm[k])) for k in keys],
         cmap=cmap, vmin=0, vmax=1, fmt="{:.0f}", fontsize=0.0, cbar=False)
    ax.set_xlabel("check index")
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=5.4)
    fail_ids = []
    for k in ("AB", "V2O"):
        fail_ids += ["%s:%s" % (k, c["id"]) for c in gm[k] if not c["pass"]]
    ax.text(0.02, -0.28, "PASS = teal, FAIL = red.  Retained failures: %s.\n"
            "First-pass A/B evidence (16/18) is archived alongside the final 18/20 NO_GO." %
            ", ".join(fail_ids), transform=ax.transAxes, fontsize=6.1,
            color=INK, va="top")
    label(ax, "(a) Executable evidence-gate matrix")

    # (b) channel forest
    ax = axs[0, 1]
    ch = E["channel_cv"]
    order = ["X", "vis", "DO2", "PAA", "P", "S"]
    ys = np.arange(len(order))[::-1]
    for y, k in zip(ys, order):
        c = ch[k]
        gain = c["gain_median_pp"]
        col = TEAL if gain > 1 else RED
        ax.plot([c["nrmse_cv_median"], c["nrmse_A_median"]], [y, y],
                color=GREY, lw=1.0, zorder=1)
        ax.scatter([c["nrmse_A_median"]], [y], s=26, color=GREY, zorder=2)
        ax.scatter([c["nrmse_cv_median"]], [y], s=30, color=col, zorder=3)
        ax.text(c["nrmse_cv_median"], y - 0.27, "%+.2f pp" % gain,
                ha="center", fontsize=6.0, color=col)
    ax.set_ylim(-0.65, 5.75)
    ax.set_xscale("log")
    ax.set_yticks(ys)
    ax.set_yticklabels(order)
    ax.set_xlabel("Median nRMSE (%) - log scale")
    ax.scatter([], [], s=26, color=GREY, label="mechanistic A tier")
    ax.scatter([], [], s=30, color=TEAL, label="5-fold CV soft sensor")
    ax.legend(frameon=False, fontsize=6.0, loc="lower left")
    label(ax, "(b) Channel-level paired effect sizes")

    # (c) seed-transfer forest
    ax = axs[1, 0]
    inj = E["injection"]
    optim = json.load(open(os.path.join(ROOT, "runs", "r166_v2_optim.json"),
                           encoding="utf-8"))
    abgate = json.load(open(os.path.join(ROOT, "runs", "r166_ab_gate.json"),
                            encoding="utf-8"))
    labels = ["tuning seed 7\nscale 0.35", "unseen seed 11\nscale 0.35",
              "unseen seed 23\nscale 0.35", "full amplitude\nscale 1.0"]
    vals = [
        next(g["max_abs_delta_pp"] for g in optim["grid"]
             if abs(g["scale"] - inj["chosen_scale"]) < 1e-9),
        inj["seed_transfer"][0]["max_abs_delta_pp"],
        inj["seed_transfer"][1]["max_abs_delta_pp"],
        max(abs(r["delta_pp"]) for r in abgate["v2"]["full_scale_rows"]),
    ]
    xs = np.arange(4)
    cols = [TEAL, RED, TEAL, RED]
    for x, v, c in zip(xs, vals, cols):
        ax.bar(x, v, 0.55, color=c, alpha=0.82)
        ax.text(x, v + 2.0, "%.2f" % v, ha="center", fontsize=6.4, color=c)
    ax.axhline(inj["caps"]["V2-3"], color=AMBER, ls="--", lw=0.9)
    ax.axhline(inj["caps"]["V2-4"], color=GREY, ls="--", lw=0.9)
    ax.text(0.02, 0.20, "V2-3 cap 20 pp", transform=ax.transAxes,
            fontsize=5.9, color=AMBER, va="bottom")
    ax.text(0.02, 0.29, "V2-4 cap 30 pp", transform=ax.transAxes,
            fontsize=5.9, color=GREY, va="bottom")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=6.0)
    ax.set_ylabel("max |delta| from frozen baseline (pp)")
    ax.set_ylim(0, 112)
    label(ax, "(c) Realisation-path invariance test")

    # (d) inventory
    ax = axs[1, 1]
    inv = E["evidence_inventory"]
    items = [("evidence JSON", inv["n_evidence_json"]),
             ("v1.x contract rows", inv["n_v1_contract_versions"]),
             ("debt-ledger IDs", inv["n_debt_ids"]),
             ("round reports", inv["n_round_reports"]),
             ("sign-off records", inv["n_signoff_ids"]),
             ("browser screenshots", inv["n_screenshots"])]
    ys = np.arange(len(items))[::-1]
    vals = [v for _, v in items]
    ax.barh(ys, vals, 0.60, color=BLUE, alpha=0.85)
    for y, v in zip(ys, vals):
        ax.text(v + 2, y, str(v), va="center", fontsize=6.4)
    ax.set_yticks(ys)
    ax.set_yticklabels([k for k, _ in items], fontsize=6.5)
    ax.set_xscale("log")
    ax.set_xlim(1, 400)
    ax.set_xlabel("count (log scale)")
    label(ax, "(d) Durable evidence inventory")
    despine(ax)

    fig.suptitle("Fig. 10 | Executable evidence: gate matrix, effect-size forests and "
                 "programme inventory", fontsize=9.5, color=BLUE,
                 fontweight="bold", y=0.995)
    save(fig, "fig10_evidence_matrix")


# ======================================================================
# Fig. 11 - parallel coordinates, radar, kLa heatmap
# ======================================================================
def fig11():
    fig = plt.figure(figsize=(11.6, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 0.95, 1.15], wspace=0.44)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1], projection="polar")
    ax2 = fig.add_subplot(gs[0, 2])
    rows = E["baseline_ladder"]["rows"]
    names = ["L0 frozen", "LOO mean", "Global mean", "Persistence", "Zero"]
    cols = [TEAL, BLUE, "#7FA9CD", AMBER, RED]

    # (a) parallel coordinates - all axes are "higher is better"
    metrics = np.asarray([
        [1 - r["rmse_pct"] / 100.0,
         1 - r["median_abs_pct"] / 100.0,
         r["within5"] / r["n"],
         1 - r["rmse_pct_of_median_yield"] / 100.0]
        for r in rows], dtype=float)
    metrics = np.clip(metrics, 0, 1)
    xax = np.arange(4)
    for i in range(len(rows)):
        ax0.plot(xax, metrics[i], "o-", color=cols[i], lw=1.5, ms=3.5,
                 alpha=0.85, label=names[i])
    ax0.set_xticks(xax)
    ax0.set_xticklabels(["1 - RMSE", "1 - median\n|error|", "within\n+/-5% rate",
                         "1 - scaled\nRMSE"], fontsize=6.3)
    ax0.set_ylabel("normalised capability (higher = better)")
    ax0.set_ylim(-0.03, 1.05)
    ax0.legend(frameon=False, fontsize=5.9, loc="upper center",
               bbox_to_anchor=(0.5, -0.20), ncol=3)
    label(ax0, "(a) Parallel coordinates of five baselines")
    despine(ax0)

    # (b) radar
    ang = np.linspace(0, 2 * np.pi, 4, endpoint=False).tolist()
    ang += ang[:1]
    for i in (0, 1, 3, 4):
        v = metrics[i].tolist()
        v += v[:1]
        ax1.plot(ang, v, lw=1.4, color=cols[i], label=names[i])
        ax1.fill(ang, v, color=cols[i], alpha=0.06)
    ax1.set_xticks(ang[:-1])
    ax1.set_xticklabels(["RMSE", "median error", "within band", "scaled RMSE"],
                        fontsize=5.9)
    ax1.tick_params(axis="x", pad=9)
    ax1.set_ylim(0, 1.02)
    ax1.set_yticks([0.5, 1.0])
    ax1.set_yticklabels(["0.5", "1.0"], fontsize=5.8)
    ax1.legend(frameon=False, fontsize=5.9, loc="upper right",
               bbox_to_anchor=(1.34, 1.12))
    ax1.set_title("(b) Capability fingerprints", fontsize=9, color=BLUE,
                  fontweight="bold", loc="left", pad=18)

    # (c) kLa sensitivity heatmap
    kl = E["kla_grid"]
    mat = np.asarray([[np.nan if v is None else v for v in row]
                      for row in kl["yield_err_pct"]], dtype=float)
    norm = TwoSlopeNorm(vmin=-100, vcenter=0, vmax=20)
    im = ax2.imshow(np.ma.masked_invalid(mat), cmap=DIV, norm=norm, aspect="auto",
                    interpolation="nearest")
    ax2.set_xticks(range(len(kl["alpha_kla"])))
    ax2.set_xticklabels([str(int(v)) for v in kl["alpha_kla"]], fontsize=5.8)
    ax2.set_yticks(range(len(kl["batches"])))
    ax2.set_yticklabels([str(b) for b in kl["batches"]], fontsize=6.0)
    ax2.set_xlabel("alpha_kLa")
    ax2.set_ylabel("batch")
    ax2.tick_params(length=0)
    for sp in ax2.spines.values():
        sp.set_visible(False)
    cb = plt.colorbar(im, ax=ax2, fraction=0.032, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=6)
    cb.set_label("yield error (%)", fontsize=6.4)
    ax2.set_title("(c) 12 x 12 alpha_kLa response surface", fontsize=9,
                  color=BLUE, fontweight="bold", loc="left")
    ax2.text(0.5, -0.15, "k* mean %.2f +/- %.2f (interior); full 12 x 12 grid (%d cells)." %
             (kl["kstar"]["mean_interior"], kl["kstar"]["std_interior"],
              kl["n_filled"]), transform=ax2.transAxes,
             ha="center", fontsize=6.1, color=GREY)

    fig.suptitle("Fig. 11 | Multi-baseline comparison and parameter-response surface",
                 fontsize=9.5, color=BLUE, fontweight="bold", y=0.99)
    save(fig, "fig11_multibaseline")


# ======================================================================
# Fig. S4 - channel-level detail
# ======================================================================
def figS4():
    fig, axs = plt.subplots(1, 3, figsize=(11.6, 4.2))
    fig.subplots_adjust(wspace=0.42)
    ch = E["channel_cv"]
    order = ["X", "vis", "DO2", "PAA", "P", "S"]

    ax = axs[0]
    keys = ["nrmse_A_median", "nrmse_cv_median", "nrmse_cv_p90",
            "nrmse_cv_max", "gain_median_pp", "ci_half_width_pct"]
    mat = np.asarray([[ch[k][kk] for kk in keys] for k in order], dtype=float)
    logm = np.log10(np.maximum(mat, 0.01) + 1)
    heat(ax, logm, ["A median", "CV median", "CV p90", "CV max", "gain pp",
                    "CI half-w"],
         order, cmap=SEQ, vmin=0, vmax=float(logm.max()),
         fmt="", fontsize=0, cbar_label="log10(1 + value)")
    for i, k in enumerate(order):
        for j, kk in enumerate(keys):
            ax.text(j, i, ("%.1f" % mat[i, j]), ha="center", va="center",
                    fontsize=5.7,
                    color="white" if logm[i, j] > 0.62 * logm.max() else INK)
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=5.9, rotation=28, ha="right")
    label(ax, "(a) Channel metric matrix")

    ax = axs[1]
    xs = np.arange(len(order))
    a = [ch[k]["nrmse_A_median"] for k in order]
    b = [ch[k]["nrmse_cv_median"] for k in order]
    ax.bar(xs - 0.19, a, 0.36, color=GREY, label="A tier")
    ax.bar(xs + 0.19, b, 0.36, color=TEAL, label="5-fold CV")
    ax.set_yscale("log")
    ax.set_ylim(0.5, 500)
    ax.set_xticks(xs)
    ax.set_xticklabels(order)
    ax.set_ylabel("median nRMSE (%)")
    ax.legend(frameon=False, fontsize=6.2)
    label(ax, "(b) Mechanistic vs. cross-validated")
    despine(ax)

    ax = axs[2]
    gains = [ch[k]["gain_median_pp"] for k in order]
    cum = 0.0
    for i, g in enumerate(gains):
        ax.bar(i, g, 0.60, color=TEAL if g > 0 else RED,
               bottom=0 if g > 0 else 0, alpha=0.85)
        ax.text(i, g + (1.0 if g >= 0 else -2.5), "%+.2f" % g,
                ha="center", fontsize=6.2,
                color=TEAL if g > 0 else RED)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(order)
    ax.set_ylabel("median nRMSE improvement (pp)")
    ax.text(0.02, 0.96, "S is a circular comparison; a large\ngain there is not evidence.",
            transform=ax.transAxes, va="top", fontsize=5.9, color=GREY)
    label(ax, "(c) Per-channel effect sizes")
    despine(ax)

    fig.suptitle("Fig. S4 | Channel-level fidelity detail (supplementary)",
                 fontsize=9.5, color=BLUE, fontweight="bold", y=0.99)
    save(fig, "figS4_channel_heatmap")


# ======================================================================
# Fig. S5 - injection heatmaps
# ======================================================================
def figS5():
    fig, axs = plt.subplots(1, 3, figsize=(11.6, 4.2))
    fig.subplots_adjust(wspace=0.44)
    inj = E["injection"]

    ax = axs[0]
    mat = np.asarray([[np.nan if v is None else v for v in row]
                      for row in inj["delta_pp"]], dtype=float)
    lim = float(np.nanmax(np.abs(mat)))
    heat(ax, mat, [str(b) for b in inj["batches"]],
         ["scale %.2f" % s for s in inj["scales"]],
         cmap=DIV, vmin=-lim, vmax=lim, fmt="{:.1f}", fontsize=5.7,
         cbar_label="delta (pp)")
    ax.set_xlabel("batch")
    label(ax, "(a) Amplitude x batch (tuning seed 7)")

    ax = axs[1]
    seeds = inj["seed_transfer"]
    srows = [[r["delta_pp"] for r in s["rows"]] for s in seeds]
    mat2 = np.asarray(srows, dtype=float)
    lim2 = float(np.nanmax(np.abs(mat2)))
    heat(ax, mat2, [str(r["batch"]) for r in seeds[0]["rows"]],
         ["seed %d" % s["seed"] for s in seeds],
         cmap=DIV, vmin=-lim2, vmax=lim2, fmt="{:.1f}", fontsize=6.2,
         cbar_label="delta (pp)")
    ax.set_xlabel("batch")
    ax.text(0.5, -0.19, "same scale %.2f: seed 11 collapses on batches 22 and 27" %
            inj["chosen_scale"], transform=ax.transAxes, ha="center",
            fontsize=6.0, color=INK)
    label(ax, "(b) Unseen seeds at scale 0.35")

    ax = axs[2]
    optim = json.load(open(os.path.join(ROOT, "runs", "r166_v2_optim.json"),
                           encoding="utf-8"))
    grid = optim["grid"]
    scales = [g["scale"] for g in grid]
    feasible = np.asarray([[1.0 if g["feasible"] else 0.0] for g in grid])
    cmap = LinearSegmentedColormap.from_list("bw", ["#B03A2E", "#16807A"])
    heat(ax, feasible, ["feasible?"], ["%.2f" % s for s in scales],
         cmap=cmap, vmin=0, vmax=1, fmt="{:.0f}", fontsize=7.5, cbar=False)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=6.3)
    ax.set_xticklabels(["1 = pass\n0 = fail"], fontsize=6.2)
    ax.text(0.5, -0.32, "5/7 feasible on seed 7; LOO chose 0.35 in 6/6 folds.\n"
            "Feasibility on the tuning seed is not transferable.",
            transform=ax.transAxes, ha="center", fontsize=6.1, color=INK)
    label(ax, "(c) Frozen-cap feasibility matrix")

    fig.suptitle("Fig. S5 | Disturbance-variance injection: amplitude x batch response "
                 "and seed transfer (supplementary)",
                 fontsize=9.5, color=BLUE, fontweight="bold", y=0.99)
    save(fig, "figS5_injection_heatmap")


# ======================================================================
# Fig. S6 - epistemic boundary certificate (alluvial + boundary matrix)
# ======================================================================
def figS6():
    fig = plt.figure(figsize=(11.6, 5.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1.0], wspace=0.28)
    ax = fig.add_subplot(gs[0, 0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # three columns: claims -> audit -> status
    claims = [
        ("Biomass X", 6, TEAL), ("Viscosity", 6, TEAL), ("DO2", 6, TEAL),
        ("Product P", 4, AMBER), ("PAA", 4, AMBER), ("Substrate S", 4, AMBER),
        ("Mycelial A0-A4", 3, RED), ("Continuous control", 3, RED),
        ("Raman -> PAA", 3, RED), ("Runtime loading", 2, TEAL),
    ]
    audits = [("5-fold CV", 0.36, TEAL), ("rank / nullity", 0.30, PURPLE),
              ("zero-info control", 0.20, BLUE), ("seed transfer", 0.14, AMBER)]
    statuses = [("DELIVERABLE", 0.40, TEAL), ("PARTIAL / circular", 0.28, AMBER),
                ("WITHDRAWN", 0.32, RED)]
    total = sum(c[1] for c in claims)

    def column(x, items, title, w=0.012):
        y = 0.90
        boxes = []
        for name, weight, col in items:
            h = 0.78 * weight / total if x < 0.5 else 0.78 * weight / sum(i[1] for i in items)
            y -= h
            patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.002,rounding_size=0.004",
                                   linewidth=0.7, edgecolor=col, facecolor=col, alpha=0.82)
            ax.add_patch(patch)
            ax.text(x - 0.012, y + h / 2, name, ha="right", va="center",
                    fontsize=6.1, color=INK)
            boxes.append((name, y, h, col))
            y -= 0.012
        ax.text(x + w / 2, 0.94, title, ha="center", fontsize=7.2,
                color=BLUE, fontweight="bold")
        return boxes

    c1 = column(0.24, claims, "claims")
    c2 = column(0.55, audits, "adversarial audit")
    c3 = column(0.84, statuses, "certified status")

    # flow ribbons: deterministic mapping claim -> audit -> status
    mapping = {
        "Biomass X": ("5-fold CV", "DELIVERABLE"),
        "Viscosity": ("5-fold CV", "DELIVERABLE"),
        "DO2": ("5-fold CV", "DELIVERABLE"),
        "Product P": ("5-fold CV", "WITHDRAWN"),
        "PAA": ("5-fold CV", "WITHDRAWN"),
        "Substrate S": ("zero-info control", "PARTIAL / circular"),
        "Mycelial A0-A4": ("rank / nullity", "WITHDRAWN"),
        "Continuous control": ("rank / nullity", "WITHDRAWN"),
        "Raman -> PAA": ("zero-info control", "WITHDRAWN"),
        "Runtime loading": ("zero-info control", "DELIVERABLE"),
    }
    b1 = {n: (y, h) for n, y, h, _ in c1}
    b2 = {n: (y, h) for n, y, h, _ in c2}
    b3 = {n: (y, h) for n, y, h, _ in c3}
    off2 = {k: 0.0 for k in b2}
    off3 = {k: 0.0 for k in b3}
    for name, weight, col in claims:
        y1, h1 = b1[name]
        a, s = mapping[name]
        w = 0.78 * weight / total * 0.85
        y2 = b2[a][0] + b2[a][1] - off2[a] - w
        off2[a] += w
        y3 = b3[s][0] + b3[s][1] - off3[s] - w
        off3[s] += w
        for x0, ya, x1, yb in ((0.252, y1, 0.55, y2), (0.562, y2, 0.84, y3)):
            verts = [(x0, ya), (x0 + 0.09, ya), (x1 - 0.09, yb), (x1, yb),
                     (x1, yb + w), (x1 - 0.09, yb + w), (x0 + 0.09, ya + w), (x0, ya + w),
                     (x0, ya)]
            codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                     Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                     Path.CLOSEPOLY]
            ax.add_patch(PathPatch(Path(verts, codes), facecolor=col,
                                   edgecolor="none", alpha=0.20, lw=0))
    ax.set_title("(a) Epistemic boundary certificate: claim -> audit -> status",
                 fontsize=9, color=BLUE, fontweight="bold", loc="left")

    # boundary matrix
    ax2 = fig.add_subplot(gs[0, 1])
    items = ["X", "vis", "DO2", "P", "PAA", "S", "A0-A4", "control", "Raman", "loading"]
    crit = ["CV hold-out", "rank(H)", "zero-info", "seed", "runtime"]
    code = np.asarray([
        [2, 2, 2, 1, 2], [2, 2, 2, 1, 2], [2, 2, 2, 1, 2],
        [0, 1, 1, 0, 2], [0, 0, 1, 0, 2], [1, 0, 0, 0, 2],
        [0, 0, 2, 0, 2], [0, 0, 1, 0, 2], [0, 1, 0, 0, 2],
        [1, 1, 0, 1, 2],
    ], dtype=float)
    cmap = LinearSegmentedColormap.from_list(
        "status", ["#B03A2E", "#E8C9A6", "#16807A"])
    im = ax2.imshow(code, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    ax2.set_xticks(range(len(crit)))
    ax2.set_xticklabels(crit, fontsize=6.2, rotation=20, ha="right")
    ax2.set_yticks(range(len(items)))
    ax2.set_yticklabels(items, fontsize=6.3)
    for i in range(len(items)):
        for j in range(len(crit)):
            ax2.text(j, i, ["F", "P", "C"][int(code[i, j])], ha="center",
                     va="center", fontsize=6.3, color="white", fontweight="bold")
    for sp in ax2.spines.values():
        sp.set_visible(False)
    ax2.tick_params(length=0)
    ax2.set_title("(b) Boundary matrix (C / P / F)", fontsize=9,
                  color=BLUE, fontweight="bold", loc="left")
    ax2.text(0.5, -0.16, "C = certified, P = partial, F = withdrawn.\n"
             "Nullity(H) > 0 forces WITHDRAWN regardless of fit quality.",
             transform=ax2.transAxes, ha="center", fontsize=6.2, color=GREY)

    fig.suptitle("Fig. S6 | Negative results as first-class typed outputs (supplementary)",
                 fontsize=9.5, color=BLUE, fontweight="bold", y=0.98)
    save(fig, "figS6_epistemic_sankey")


# ======================================================================
# Fig. S7 - bistability, fallback census, mosaic
# ======================================================================
def figS7():
    fig, axs = plt.subplots(1, 3, figsize=(11.6, 4.2))
    fig.subplots_adjust(wspace=0.44)

    ax = axs[0]
    bs = E["bistability"]
    mat = np.asarray(bs["yield_err_pct"], dtype=float)
    heat(ax, mat, ["%.2f" % s for s in bs["scales"]],
         ["batch %d" % b for b in bs["batches"]],
         cmap=DIV, vmin=-100, vmax=20, fmt="{:.0f}", fontsize=5.6,
         cbar_label="yield error (%)")
    ax.set_xlabel("mup0 scale")
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=5.8, rotation=30, ha="right")
    label(ax, "(a) Bistable response surface")

    ax = axs[1]
    fc = E["fallback_census"]
    xs = np.arange(len(fc["batches"]))
    err = np.asarray(fc["c_error_pct"])
    ax.bar(xs, err, 0.65, color=[TEAL if abs(v) <= 20 else RED for v in err])
    ax.axhline(20, color=AMBER, ls="--", lw=0.9)
    ax.axhline(-20, color=AMBER, ls="--", lw=0.9)
    ax.set_xticks(xs)
    ax.set_xticklabels([str(b) for b in fc["batches"]], fontsize=5.9, rotation=35)
    ax.set_ylabel("carbon-balance error (%)")
    ax.set_xlabel("batch")
    ax.text(0.02, 0.94, "%d/%d credible; budget +/-20%%" %
            (fc["n_credible"], fc["n_batches"]),
            transform=ax.transAxes, fontsize=6.3, va="top")
    label(ax, "(b) Third-ring steady-state census")
    despine(ax)

    ax = axs[2]
    ct = E["health_validity_crosstab"]["binary_table"]
    m = np.asarray([[ct["normal_valid"], ct["normal_invalid"]],
                    [ct["flagged_valid"], ct["flagged_invalid"]]], dtype=float)
    heat(ax, m, ["valid", "invalid"], ["normal", "flagged"],
         cmap=SEQ, vmin=0, vmax=77, fmt="{:.0f}", fontsize=9.5, cbar=False)
    ax.set_title("(c) Health vs. validity mosaic", fontsize=9, color=BLUE,
                 fontweight="bold", loc="left")
    ax.text(0.5, -0.19, "phi = %.1f : perfectly collinear (shared pH-guard signal).\n"
            "Two criteria, one piece of evidence - not independent corroboration." %
            E["health_validity_crosstab"]["phi_coefficient"],
            transform=ax.transAxes, ha="center", fontsize=6.2, color=RED,
            bbox=dict(fc="#FBEDEA", ec=RED, lw=0.6, pad=4))

    fig.suptitle("Fig. S7 | Structural boundaries and criterion independence "
                 "(supplementary)", fontsize=9.5, color=BLUE,
                 fontweight="bold", y=0.99)
    save(fig, "figS7_governance")


def main():
    fig7()
    fig8()
    fig9()
    fig10()
    fig11()
    figS4()
    figS5()
    figS6()
    figS7()
    print("DONE 9 extended figures")


if __name__ == "__main__":
    main()
