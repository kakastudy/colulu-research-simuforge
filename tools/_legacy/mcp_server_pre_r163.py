# -*- coding: utf-8 -*-
# R163 零回归夹具：mcp_server.py 在 D-80 接入回退链**之前**的逐字副本。
# 仅 _ROOT 的路径推导改为项目根硬编码（因文件被移到 tools/_legacy/），其余不变。
# 用途：tools/r163_mcp_integration_probe.py 的 Z1 零回归基线。
# -*- coding: utf-8 -*-
"""MCP 组件服务层：把青霉素发酵仿真求解器（A/B/C 三档算子）暴露为 Agent 可调用工具。

协议：Model Context Protocol (MCP) 2.x，基于 fastmcp 实现。
传输：默认 stdio（Agent 子进程标准接法）；`--transport http --port 8931` 可起 HTTP。

工具（Agent-facing tools）：
  solver_info          — 求解器能力清单（版本、档位、黄金集、参数键）
  simulate_batch       — A 档：给定批号+参数 → 全状态轨迹摘要（降采样）
  evaluate_batch       — A 档：产量指标 + 证据化崩溃分级
  golden_set_validate  — A 档：12 批黄金集复验（RMSE / within5% / crash 分级）
  estimate_batch       — B 档：从在线量测网格估计批次级参数（软测量）
  optimize_feed        — C 档：反设计 — 产量目标下 MV 倍率寻优
   advise_control       — C 档：PH4 时间窗 MV 反事实咨询（+T1 校验）

运行：项目根目录下 `python candidate/indpensim/v0.1/mcp_server.py [--transport http]`
Agent 侧注册：{"command": "python", "args": ["<abs path to mcp_server.py>"]}
"""
import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(_ROOT)  # 数据路径以项目根为基准（data/processed/batches/...）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

from fastmcp import FastMCP

from simulate import simulate_open_loop, yield_metrics, classify_crash
from params import make_params
from calibration import calib_params, GOLDEN_NORMAL, GOLDEN_FAULT, GOLDEN
from trajectory_metrics import trajectory_metrics as _traj_metrics_fn
from conservation_metrics import element_balance as _element_balance_fn
from knowledge_constraints import validate_t1

VERSION = "v0.1.0-c5"
PARAM_KEYS_INFO = {
    "mux": "比生长速率基准 0.41（批次随机 ±0.025）",
    "mup": "比产素速率基准 0.041",
    "alpha_kla": "气液传氧系数 85",
    "Tcin": "夹套入口温度 K（默认 285）",
    "m_s": "维持系数 0.029（校准键）",
    "m_s_schedule": "时变维持系数 [(t_switch, m_s_late), ...]",
    "dist_tcin_asym": "夹套温度扰动渐近值 (+K)",
    "mv_scales": "C 档 MV 倍率 {Fs, Foil, Fpaa, Fg, RPM}",
}

mcp = FastMCP("indpensim-solver")


def _default_params(b: int) -> dict:
    """黄金集批次 → 校准参数；非黄金集 → 标称基线。调用方键优先覆盖。"""
    try:
        return calib_params(b)
    except KeyError:
        return {"alpha_kla": 85.0}


def _downsample(sim, stride=30):
    """轨迹摘要：每 stride 个样本取 1（0.2h 步长 → 6h 粒度）。"""
    cols = ["time_h", "S", "DO2", "P", "V", "pH", "T", "CO2d", "OUR", "CER"]
    d = sim[cols].iloc[::stride].copy()
    return d.round(4).to_dict(orient="records")


@mcp.tool
def solver_info() -> dict:
    """求解器能力清单：版本、三档算子、黄金集批号、可调参数键。"""
    return {
        "name": "indpensim-solver", "version": VERSION,
        "tiers": {
            "A": "机理引擎（33 维 ODE，开环回放 V3 被控量）",
            "B": "软测量估计（网格法，在线量测 → 批次级参数）",
            "C": "反设计寻优（MV 倍率 Nelder-Mead，无灾难崩溃约束）",
        },
        "golden_set": {"normal": GOLDEN_NORMAL, "fault": GOLDEN_FAULT},
        "evaluation_set_all86": "golden_params.GOLDEN_ALL（86 批，golden_set_validate 默认成员）",
        "param_keys": PARAM_KEYS_INFO,
        "validation_state": "86 批 RMSE 2.345% ≤ 3.5%，86/86 在 ±5%，catastrophic 0（ENGINE_CONTRACT v1.61/v1.62）",
        "capability_level": "L1 prototype（M4 有条件通过，见 docs/m4_review_signoff.md）",
    }


@mcp.tool
def simulate_batch(batch_no: int, params: dict | None = None) -> dict:
    """A 档：开环回放仿真一个批次。默认用黄金集校准参数；params 的键覆盖之
    （可含 mux/mup/m_s/m_s_schedule/dist_*/mv_scales/Tcin/x0_biomass 等）。
    返回轨迹摘要（6h 粒度）、批末状态与崩溃分级。batch_no ∈ [1,100]。"""
    merged = {**_default_params(int(batch_no)), **(params or {})}
    sim, v3 = simulate_open_loop(int(batch_no), merged)
    ym = yield_metrics(sim, v3)
    level, reasons = classify_crash(sim, yield_err=ym["rel_err_total"])
    return {
        "batch": batch_no,
        "yield": {"sim_g": float(ym["total_sim_g"]), "v3_g": float(ym["total_v3_g"]),
                   "rel_err": float(ym["rel_err_total"])},
        "end_state": {"P": float(sim["P"].iloc[-1]), "pH": float(sim["pH"].iloc[-1]),
                       "CO2d": float(sim["CO2d"].max()), "V": float(sim["V"].iloc[-1])},
        "crash": {"level": level, "reasons": reasons},
        "trajectory": _downsample(sim),
    }


@mcp.tool
def evaluate_batch(batch_no: int, params: dict | None = None) -> dict:
    """A 档：评估批次 — 产量指标 + 证据化崩溃分级（normal/benign/catastrophic + 证据链）。
    默认用黄金集校准参数；params 的键覆盖之。"""
    merged = {**_default_params(int(batch_no)), **(params or {})}
    sim, v3 = simulate_open_loop(int(batch_no), merged)
    ym = yield_metrics(sim, v3)
    level, reasons = classify_crash(sim, yield_err=ym["rel_err_total"])
    return {"batch": batch_no, "yield": ym.__dict__ if hasattr(ym, "__dict__") else dict(ym),
            "crash": {"level": level, "reasons": reasons}}


@mcp.tool
def golden_set_validate(dw: bool = True, full: bool = True, n_jobs: int = 6) -> dict:
    """A 档：复验 V3 黄金集。返回每批 err/CO2d/pH/crash 分级与 RMSE。

    full=True（默认，R135 T7 起）：评估集 = **86 批**（golden_params.GOLDEN_ALL），
      与引擎黄金回归同一成员表；并行执行，8 核约 4–6 min。
    full=False：退回 13 批（calibration.GOLDEN，11 正常 + 2 故障），串行，用于快速冒烟。
    """
    from validate import golden_all_rows, summarize_rows

    if full:
        from golden_params import GOLDEN_ALL
        rows = golden_all_rows(batches=list(GOLDEN_ALL), n_jobs=int(n_jobs))
        members = set(GOLDEN_ALL)
        rmse, within5, catastrophic = summarize_rows(rows)
    else:
        rows = golden_all_rows(batches=GOLDEN_NORMAL + GOLDEN_FAULT, n_jobs=1)
        members = set(GOLDEN_NORMAL + GOLDEN_FAULT)
        rmse, within5, catastrophic = summarize_rows(rows)

    for r in rows:
        r["type"] = "normal" if r["batch"] not in GOLDEN_FAULT else "fault"
    return {
        "evaluation_set": {"n": len(rows), "members": sorted(members),
                           "source": "golden_params.GOLDEN_ALL" if full else "calibration.GOLDEN"},
        "rmse": rmse,
        "within5": within5,
        "catastrophic": catastrophic,
        "batches": rows,
    }


@mcp.tool
def estimate_batch(batch_no: int, quick: bool = True) -> dict:
    """B 档：软测量 — 从在线量测（DO2/CO2d/pH/T/NH3/OUR/CER）网格估计批次级参数，给产率估值与在线 RMSE。"""
    from soft_sensing import estimate_batch as _est
    r = _est(int(batch_no), verbose=False)
    return {"batch": batch_no, "params": r["params"], "yield_err": r["yield_err"],
             "online_rmse": r["online_rmse"], "crashed": bool(r["crashed"]),
             "top5": r.get("top5", [])[:5] if "top5" in r else None}


@mcp.tool
def estimate_batch_stage2(batch_no: int) -> dict:
    """B 档两阶段版：先在线网格（54 组合），再 mup 锚定 P_offline 化验（§14.3，5/5 崩塌批救回）。
    返回 stage1/stage2 参数对比、P_offline RMSE 与独立评估的产率偏差。**约 10 分钟**。"""
    from soft_sensing import estimate_batch as _est
    from stage2_estimator import estimate_stage2, load_v3
    r1 = _est(int(batch_no), verbose=False)
    r2 = estimate_stage2(int(batch_no), r1["params"], v3=load_v3(int(batch_no)))
    return {"batch": batch_no, "stage1": {k: r1[k] for k in ("params", "yield_err", "online_rmse")},
             "stage2_mup": r2["stage2_mup"], "p_offline_rmse": r2["p_offline_rmse"],
             "yield_err": r2["yield_err"], "co2d_max": r2["co2d_max"]}


@mcp.tool
def reconstruct_batch(batch_no: int, n_ens: int = 50) -> dict:
    """内部观测体系（回溯型，PH3-m1）：集合平滑器 — θ_b 后验采样 → 引擎重放 →
    状态轨迹均值 ±1.96σ + I3 覆盖率（P/PAA/X 对 V3 化验真值）。
    批号未入快校准日志时自动先做 18 组合快校准（~2.5 分钟）再重放（~n_ens×8 秒）。"""
    from observe import ensemble_smooth
    from knowledge_constraints import paa_pat_trigger
    r = ensemble_smooth(int(batch_no), n_ens=min(int(n_ens), 120), out_path=None)
    sampled = r["mean"].iloc[::100].round(3).to_dict("records")  # 6h 粒度轨迹抽样
    _cal = calib_params(int(batch_no))
    trig, trig_reason = paa_pat_trigger(_cal.get("mup"))
    return {"batch": r["batch"], "n_ens_eff": r["n_ens_eff"],
             "n_fail": r.get("n_fail", 0), "coverage": r["coverage"],
             "mean_sample": sampled,
             "paa_pat_advisory": {"trigger": bool(trig), "reason": trig_reason,
              "note": "μp>0.055 → 建议锚定修正层接入（docsraman_pat_integration_spec.md §1）"}}


@mcp.tool
def optimize_feed(batch_no: int, vars: list[str] | None = None, maxiter: int = 25,
                  objective: str = "max_yield") -> dict:
    """C 档：反设计寻优 — 在 MV 倍率（Fs/Foil/Fpaa/Fg/RPM 子集）上按目标寻优。
    objective="max_yield"（最大化产量）或 "track_target"（对准 V3 批次目标产量）。
    vars 形如 ["Fs","Foil"]；返回基线产量、最优倍率、改进幅度、崩溃分级。"""
    from optimize import optimize_feed as _opt
    r = _opt(int(batch_no), var_names=vars or ["Fs"], maxiter=int(maxiter),
             objective=objective, verbose=False)
    return r


@mcp.tool
def advise_control(batch_no: int, t_window_start: float, t_window_end: float,
                   candidates: list[dict] | None = None) -> dict:
    """PH4 滚动控制咨询：在 [t0,t1) 时间窗内对 MV 倍率做反事实重放评分，
    输出最优建议（gap %）+ 崩溃分级 + T1 操作窗校验（物理/化学/物理约束）。
    candidates 形如 [{"Fs":1.03,"Foil":1.0}, ...]（缺省 6 组典型组合）。"""
    base = calib_params(int(batch_no)) if int(batch_no) in GOLDEN else {"alpha_kla": 85.0}
    cands = candidates or [{"Fs": 1.00, "Foil": 1.00}, {"Fs": 1.03, "Foil": 1.00},
                            {"Fs": 1.06, "Foil": 1.00}, {"Fs": 1.00, "Foil": 0.95},
                            {"Fs": 1.03, "Foil": 0.95}, {"Fs": 0.97, "Foil": 1.00}]
    v3 = pd.read_csv(f"data/processed/batches/batch_{int(batch_no):02d}.csv")
    rows = []
    sims = []  # 与 rows 一一对应（T1 包络用 best 候选自身轨迹）
    for cand in cands:
        params = dict(base, mv_window_scales=[{"t0": float(t_window_start),
                                               "t1": float(t_window_end), "scales": cand}])
        try:
            sim, _ = simulate_open_loop(int(batch_no), params)
            ym = yield_metrics(sim, v3)
            lvl, reasons = classify_crash(sim, yield_err=float(ym["rel_err_total"]))
            rows.append({"scales": cand, "yield_g": float(ym["total_sim_g"]),
                         "err_vs_v3": float(ym["rel_err_total"]), "crash": lvl})
            sims.append(sim)
        except Exception as e:
            rows.append({"scales": cand, "error": f"{type(e).__name__}: {e}", "crash": "DIVERGED"})
            sims.append(None)
    ok_rows = [r for r in rows if "err_vs_v3" in r and r["crash"] != "catastrophic"]
    target_g = 0.0
    if ok_rows:
        # V3 目标产量（与 yield_metrics 同口径）
        sim_ref, _ = simulate_open_loop(int(batch_no), base)
        ym_ref = yield_metrics(sim_ref, v3)
        target_g = float(ym_ref["total_v3_g"])
        best = min(ok_rows, key=lambda r: abs(r["yield_g"] - target_g))
        # T1 窗口包络（best 候选自身，窗内片面瞬时值 → 最违反包络；窗口包络约束证据 R48）
        sim_b = sims[rows.index(best)]
        sb = sim_b[(sim_b["time_h"] >= float(t_window_start))
                   & (sim_b["time_h"] < float(t_window_end))]
        src = sb if len(sb) else sim_b.tail(1)
        ph_lo, ph_hi = float(src["pH"].min()), float(src["pH"].max())
        ph_v = ph_lo if (ph_lo < 5.2 or ph_hi <= 6.9) else ph_hi
        sample = {"T": float(src["T"].max()), "pH": ph_v,
                  "CO2d": float(src["CO2d"].max()), "DO2": float(src["DO2"].min()),
                  "mv_scales": best["scales"]}
        t1_ok, t1_reasons = validate_t1(sample)
    else:
        best = None; t1_ok = True; t1_reasons = []
    return {"batch": int(batch_no), "window": [t_window_start, t_window_end],
            "target_g": target_g, "cands": rows, "best": best,
            "t1_sample": sample if ok_rows else None,
            "t1_validation": {"ok": bool(t1_ok), "reasons": t1_reasons}}


@mcp.tool
def trajectory_check(batch_no: int) -> dict:
    """A 档验收算子（GOAL §4.2）：S/X/P/DO/T/pH/V/Wt/OUR/CER 逐点对照 V3
    （X 对照含 4h 化验滞后对齐）。返回每通道 RMSE/bias/nRMSE(均值与最大口径)/相关系数。"""
    params = calib_params(int(batch_no)) if int(batch_no) in GOLDEN else {"alpha_kla": 85.0}
    sim, v3 = simulate_open_loop(int(batch_no), params)
    return {"batch": int(batch_no), "metrics": _traj_metrics_fn(sim, v3)}


@mcp.tool
def element_balance_check(batch_no: int) -> dict:
    """A 档验收算子（GOAL §4.3）：批级 C/N 平衡闭合（V3 进料/排放/产品 + 引擎常数 T7）
    与 RQ 系比。R134 T2 起 CER 项按体积速率 ×V(t) 并 ×12/44 折碳，C 中位 −64.5%→−1.5%
    （见 runs/element_balance_v2.json）；旧口径 element_balance.json 仅留对照。"""
    v3 = pd.read_csv(f"data/processed/batches/batch_{int(batch_no):02d}.csv")
    r = _element_balance_fn(v3)
    r["batch"] = int(batch_no)
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--port", type=int, default=8931)
    a = ap.parse_args()
    if a.transport == "http":
        mcp.run(transport="http", port=a.port, host="127.0.0.1")
    else:
        mcp.run()
