# -*- coding: utf-8 -*-
"""报告图件生成（SCI 风格）。产出 runs/report_assets/fig_*.png。"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
ASSETS = "runs/report_assets"
os.makedirs(ASSETS, exist_ok=True)

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 10.5,
    "axes.titlesize": 11.5,
    "axes.labelsize": 10.5,
    "figure.dpi": 100,
    "savefig.dpi": 220,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "legend.frameon": False,
})
C = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#7f7f7f"]


def load(j):
    with open(j, encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    p = os.path.join(ASSETS, name)
    fig.tight_layout()
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("fig ->", p)


# ---------- 图 1：RMSE 演进 ----------
stages = ["名义参数", "3D 校准\n(mux/mup/ΔTcin)", "m_s 校准", "m_s+mup+dTcin\n3D", "常数 m_s\n改进", "时变 m_s\n(最终)"]
rmse = [70.95, 37.40, 32.57, 16.18, 7.28, 4.48]
within5 = [1, 2, 2, 2, 6, 8]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.bar(range(len(stages)), rmse, color=C[0], alpha=0.85, label="RMSE (%)")
ax.axhline(5, color=C[1], ls="--", lw=1.4, label="验收阈值 5%")
for i, v in enumerate(rmse):
    ax.text(i, v + 1.2, f"{v:.2f}", ha="center", fontsize=9)
ax2 = ax.twinx()
ax2.plot(range(len(stages)), within5, "o-", color=C[2], lw=1.6, ms=5, label="±5% 内批数")
ax2.set_ylabel("±5% 内批数（/12）", color=C[2])
ax2.tick_params(axis="y", colors=C[2])
ax2.set_ylim(0, 13); ax2.grid(False)
ax.set_xticks(range(len(stages))); ax.set_xticklabels(stages, fontsize=8.6)
ax.set_ylabel("黄金集产量 RMSE (%)")
ax.set_ylim(0, 80)
ax.set_title("图 1  A 档黄金集产量 RMSE 演进（逐层校准）")
ax.legend(loc="upper right"); ax2.legend(loc="right")
save(fig, "fig1_rmse_evolution.png")

# ---------- 图 2：12 批终验产率偏差 ----------
val = load("runs/final_validation_v2.json")
b = [r["batch"] for r in val]; err = [100 * r["yield_err"] for r in val]
co2d = [r.get("co2d_max", 0) for r in val]
lvl = [r.get("crash_level", "normal") for r in val]
colors = [C[1] if l == "catastrophic" else (C[4] if l == "benign" else C[0]) for l in lvl]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.bar(range(12), err, color=colors, alpha=0.88)
ax.axhspan(-5, 5, color=C[2], alpha=0.12, label="±5% 达标区")
for i, e in enumerate(err):
    ax.text(i, e + (0.6 if e >= 0 else -1.4), f"{e:+.1f}", ha="center", fontsize=8.6)
ax.set_xticks(range(12)); ax.set_xticklabels([f"{x}\n{'故障' if x in (91,92) else '正常'}" for x in b], fontsize=9)
ax.set_ylabel("产量偏差 (%)"); ax.set_title("图 2  时变 m_s 校准时基线终验产率偏差（蓝=正常批穿越 benign；红=灾难）")
ax.legend()
save(fig, "fig2_batch_errors.png")

# ---------- 图 3：轨迹指标热图 ----------
tm = load("runs/trajectory_metrics.json")
channels = ["S", "P", "DO2", "T", "pH", "V", "Wt", "OUR", "CER", "X_offline"]
M = np.full((len(tm), len(channels)), np.nan)
for i, row in enumerate(tm):
    for j, ch in enumerate(channels):
        v = row["metrics"].get(ch, {})
        M[i, j] = v.get("nrmse_max_pct", np.nan)
fig, ax = plt.subplots(figsize=(7.2, 4.6))
im = ax.imshow(np.clip(M, 0, 35), cmap="YlOrRd", aspect="auto", vmin=0, vmax=35)
ax.set_xticks(range(len(channels))); ax.set_xticklabels(channels, fontsize=9)
ax.set_yticks(range(len(tm))); ax.set_yticklabels([f"批{r['batch']}" for r in tm], fontsize=9)
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        v = M[i, j]
        if np.isfinite(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                    color="black" if v < 22 else "white")
plt.colorbar(im, ax=ax, label="max 口径 nRMSE (%) [截断 35]")
ax.set_title("图 3  轨迹级逐点偏差（max 口径 nRMSE，%）；T/V/Wt 优、X 中期偏高为已知差距")
save(fig, "fig3_trajectory_heatmap.png")

# ---------- 图 4：批 23/92 轨迹证据（需实跑） ----------
def run_batch(b):
    sys.path.insert(0, "candidate/indpensim/v0.1")
    from simulate import simulate_open_loop
    from calibration import calib_params
    sim, v3 = simulate_open_loop(b, calib_params(b))
    return sim, v3

fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.2))
for col, (batch, tag) in enumerate([(23, "批 23（benign 判据案例）"), (8, "批 8（正常对照）")]):
    sim, v3 = run_batch(batch)
    t_sim = sim["time_h"].to_numpy(float)  # sim 行丢首行，时间轴对齐
    ax = axes[0, col]
    ax.plot(t_sim, sim["CO2d"], color=C[0], lw=1.2, label="Sim CO2d")
    ax.axhline(7.57, color=C[1], ls="--", lw=1.2, label="X_crit_CO2 = 7.57")
    crossing = sim[sim["CO2d"] > 7.57]
    if len(crossing):
        ax.axvline(crossing["time_h"].iloc[0], color=C[4], ls=":", lw=1.4,
                   label=f"穿越 t={crossing['time_h'].iloc[0]:.0f} h")
        ax.axvspan(crossing["time_h"].iloc[0], v3['time_h'].iloc[-1], color=C[4], alpha=0.08)
    ax.set_ylabel("CO2d (g/L)")
    ax.set_title(tag)
    ax.legend(fontsize=8)
    ax = axes[1, col]
    ax.plot(t_sim, sim["P"], color=C[2], lw=1.2, label="Sim P")
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").dropna()
    xl = v3["time_h"][xo.index]
    ax.plot(xl, xo, "o", ms=4, color=C[3], label="V3 X_offline")
    ax2b = ax.twinx()
    ax2b.plot(t_sim, sim["X"], color=C[5], lw=1.0, alpha=0.8, label="Sim X")
    ax2b.set_ylabel("Sim X (g/L)", color=C[5]); ax2b.grid(False)
    ax2b.tick_params(axis="y", colors=C[5])
    ax.set_ylabel("P (g/L)"); ax.set_xlabel("时间 (h)")
    ax.legend(fontsize=8, loc="upper left")
fig.suptitle("图 4  批 23 良性穿越 vs 批 8 正常对照（CO2d / P / X 轨迹）", y=1.0)
save(fig, "fig4_batch23_evidence.png")

# ---------- 图 5：B 档两阶段救回 ----------
batches = ["批16", "批36", "批55", "批80", "批92"]
stage1 = [-92.5, -95.8, -92.1, -95.2, -95.8]
stage2 = [12.5, 12.2, 4.4, 4.1, 0.17]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
xpos = np.arange(5)
ax.bar(xpos - 0.18, stage1, 0.35, color=C[1], alpha=0.8, label="stage-1 纯在线网格")
ax.bar(xpos + 0.18, stage2, 0.35, color=C[2], alpha=0.85, label="stage-2 P_offline 锚定")
ax.axhspan(-5, 5, color=C[2], alpha=0.10, label="±5% 达标区")
ax.axhline(0, color="black", lw=0.8)
ax.set_xticks(xpos); ax.set_xticklabels(batches)
ax.set_ylabel("产量偏差 (%)")
ax.set_title("图 5  B 档两阶段估计器：5/5 崩塌批救回（μp 锚定 P_offline 化验）")
ax.legend()
save(fig, "fig5_b_rescue.png")

# ---------- 图 6：批 92 μp 扫描趋势（穿越定位） ----------
rows = load("runs/b92_crossing_scan.json")
rows += load("runs/b92_crossing_fine.json")
pp = load("runs/b92_pinpoint.json")
scan = [(r["mup"], r["yield_err"], r["p_rmse"]) for r in rows if r["mux"] in (0.41, 0.47)]
fine = [(float(k), v[1]) for k, v in pp.items()]
fig, ax = plt.subplots(figsize=(7.2, 4.2))
for mux in (0.41, 0.47):
    xs = sorted([s for s in scan if abs(s[0] % 1 - mux) < 1e-6], key=lambda t: t[0])
    ax.plot([t[0] for t in xs], [t[1] * 100 for t in xs], "o-", lw=1.4, ms=4,
            label=f"mux={mux:.2f}")
for mv, (prm, ye, _c) in [(k, v) for k, v in pp.items()]:
    ax.plot(float(mv), ye * 100, "^", ms=9, color=C[1],
            label="最终定位 0.0322" if abs(float(mv) - 0.0322) < 1e-6 else None)
ax.axhspan(-5, 5, color=C[2], alpha=0.12, label="±5% 达标区")
ax.axhline(0, color="black", lw=0.8)
ax.set_xlabel("μp (1/h)"); ax.set_ylabel("产量偏差 (%)")
ax.set_title("图 6  批 92 μp 敏感度：0.001 步距 ≈ 60% 产量摆动；mup=0.0322 → +0.17%")
ax.legend(fontsize=8)
save(fig, "fig6_b92_mup_scan.png")

# ---------- 图 7：C 档收敛曲线（新带 history 的轨迹） ----------
p = "runs/opt_batch_60_track_v2.json"
if os.path.exists(p):
    r7 = load(p)
    hist = pd.DataFrame(r7["history"])
    hist = hist.dropna(subset=["yield_g"]).set_index("eval")
    best = hist["yield_g"].cummin()
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.plot(hist.index, hist["yield_g"] / 1e6, "o-", ms=4, color=C[0], label="每次评估产量")
    ax.plot(best.index, best / 1e6, "-", color=C[2], lw=2.0, label="累计最优")
    v3_target = 2.379
    ax.axhline(v3_target, color=C[1], ls="--", lw=1.4, label="V3 目标 2.379 Mg")
    ax.set_xlabel("评估序号"); ax.set_ylabel("产量 (Mg)")
    ax.set_title(f"图 7  C 档收敛曲线（批 60，FS/Foil，track_target；最优 {r7['opt_err_vs_v3']*100:+.1f}%）")
    ax.legend()
    save(fig, "fig7_c_convergence.png")
else:
    print("skip fig7 (no history file yet)")

# ---------- 图 8：元素平衡（N/C 呼吸归认） ----------
eb = load("runs/element_balance.json")
bb = [r["batch"] for r in eb]
n_err = [r["err_N_pct"] for r in eb]
resp = load("runs/mechanism_c_closure.json")
resp_share = [r["resp_share_pct"] for r in resp]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.bar(np.arange(12) - 0.18, n_err, 0.35, color=C[0], alpha=0.85, label="N 平衡误差 (%)")
ax.bar(np.arange(12) + 0.18, resp_share, 0.35, color=C[3], alpha=0.85,
       label="C 呼吸归认份额 (%)")
ax.set_xticks(np.arange(12)); ax.set_xticklabels(bb)
ax.set_ylabel("%")
ax.set_title("图 8  元素平衡核验：N 闭合通过（-8%~-17%）；V3 尾气 C 份额与液相账差 30×")
ax.legend()
save(fig, "fig8_element_balance.png")

# ---------- 图 9：RQ 签名（故障 vs 正常） ----------
rq = load("runs/rq_signature_check.json")
labels = [f"批{r['batch']}" + ("（故障）" if r["batch"] in (91, 92) else "") for r in rq]
v3m = [r["v3_rq_med"] for r in rq]; simm = [r["sim_rq_med"] for r in rq]
xpos = np.arange(len(rq))
fig, ax = plt.subplots(figsize=(8.0, 4.0))
ax.bar(xpos - 0.2, v3m, 0.4, color=C[0], label="V3")
ax.bar(xpos + 0.2, simm, 0.4, color=C[2], label="Sim")
ax.set_xticks(xpos); ax.set_xticklabels(labels, fontsize=8, rotation=30)
ax.set_ylabel("RQ 中位数")
ax.set_title("图 9  故障特征级验证：批 91 的 RQ 异常被机理回放定性复现（2.22 → 1.62）")
ax.legend()
ax.axhline(1.16, color=C[1], ls="--", lw=1.2, label="正常批上界 1.16")
save(fig, "fig9_rq_signature.png")

# ---------- 图 10：算子库与服务架构 ----------
fig, ax = plt.subplots(figsize=(8.6, 6.2))
ax.axis("off")
def box(x, y, w, h, text, fc, fs=9.5):
    ax.add_patch(plt.Rectangle((x, y), w, h, fc=fc, ec="#333333", lw=1.0, alpha=0.92))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)
box(0.02, 0.80, 0.96, 0.16,
    "数据层：V3 数据集（2.5 GB, 100 批）· 黄金集（10 正常 + 2 故障）· 化验滞后 4h 对齐 · glossary.yaml 计量口径", "#eef3fa")
box(0.02, 0.56, 0.30, 0.16, "A 档 机理引擎\n33 维 ODE 开环回放\nclassify_crash 证据链", "#dff0d8")
box(0.35, 0.56, 0.30, 0.16, "B 档 软测量\n在线 54 网格 →\nμp 锚定 P_offline (stage-2)", "#fcf8e3")
box(0.68, 0.56, 0.30, 0.16, "C 档 反设计\nMV 倍率 Nelder-Mead\nmax_yield / track_target", "#fdecea")
box(0.02, 0.34, 0.96, 0.12,
    "算子库共享层：calibration.py（校准 SSOT）· mv_scales（有效域告警）· runstore（记录持久化）· trajectory/element/mc 评估算子",
    "#e8eaf6")
box(0.02, 0.10, 0.44, 0.16, "MCP 服务层\nstdio + HTTP 双传输\n9 工具（solve/estimate/optimize/validate…）", "#ede7f6")
box(0.52, 0.10, 0.46, 0.16, "M5 看板（双工作台）\n🚀 运行面板：A/B/C + 趋势图\n📚 运行记录：持久化 & 秒开", "#e0f2f1")
for x0 in (0.17, 0.5, 0.83):
    ax.annotate("", xy=(x0, 0.56), xytext=(x0, 0.46+0.005), arrowprops=dict(arrowstyle="-|>", color="#555555"))
ax.annotate("", xy=(0.24, 0.26), xytext=(0.24, 0.33), arrowprops=dict(arrowstyle="-|>", color="#555555"))
ax.annotate("", xy=(0.75, 0.26), xytext=(0.75, 0.33), arrowprops=dict(arrowstyle="-|>", color="#555555"))
ax.set_title("图 10  仿真算子库与服务架构（数据层 / 三档算子 / 共享层 / Agent 服务）", fontsize=12)
save(fig, "fig10_architecture.png")

# ---------- 图 11：崩溃判据决策流 ----------
fig, ax = plt.subplots(figsize=(8.6, 3.6))
ax.axis("off")
box(0.01, 0.35, 0.20, 0.30, "CO2d > 7.57 ?\n（阈值穿越）", "#eef3fa")
box(0.27, 0.62, 0.24, 0.26, "pH ∈ [5.0, 8.0] ?", "#eef3fa")
box(0.27, 0.06, 0.24, 0.26, "P 末值 ≥ 0.5×峰值 ?", "#eef3fa")
box(0.58, 0.62, 0.22, 0.26, "|产率偏差| ≤ 5% ?", "#eef3fa")
box(0.86, 0.62, 0.13, 0.26, "benign\n🟡", "#fdecea")
box(0.58, 0.06, 0.22, 0.26, "catastrophic\n🔴（含证据链）", "#fdecea")
box(0.86, 0.06, 0.13, 0.26, "normal ✅\n（未穿越）", "#eef3fa")
for a, b2 in [((0.21, 0.50), (0.27, 0.75)), ((0.21, 0.50) if False else (0.21, 0.46), (0.27, 0.19)),
              ((0.51, 0.75), (0.57, 0.75)), ((0.80, 0.75), (0.86, 0.75)),
              ((0.80, 0.19) if False else (0.51, 0.19), (0.57, 0.19))]:
    ax.annotate("", xy=b2, xytext=a, arrowprops=dict(arrowstyle="-|>", color="#555555"))
ax.set_title("图 11  崩溃证据化判据：病理三分级决策流（时间分数仅记录不作硬闸）", fontsize=12)
save(fig, "fig11_crash_decision.png")

print("ALL FIGURES DONE")
