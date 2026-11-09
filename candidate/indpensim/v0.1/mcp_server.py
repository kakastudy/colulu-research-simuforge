# -*- coding: utf-8 -*-
"""MCP 组件服务层：把青霉素发酵仿真求解器（A/B/C 三档算子）暴露为 Agent 可调用工具。

协议：Model Context Protocol (MCP) 2.x，基于 FastMCP 实现。
     R166 / D-85：优先第三方 `fastmcp` 包；未安装时回退官方 SDK 内置
     `mcp.server.fastmcp.FastMCP`（锁 mcp==1.12.0）⇒ 本机可直接启动。
传输：默认 stdio（Agent 子进程标准接法）；`--transport http --port 8931` 可起 HTTP。

工具（Agent-facing tools）：
  solver_info          — 求解器能力清单（版本、档位、黄金集、参数键）
  simulate_batch       — A 档：给定批号+参数 → 全状态轨迹摘要（降采样）
  evaluate_batch       — A 档：产量指标 + 证据化崩溃分级
  golden_set_validate  — A 档：12 批黄金集复验（RMSE / within5% / crash 分级）
  estimate_batch       — B 档：从在线量测网格估计批次级参数（软测量）
  optimize_feed        — C 档：反设计 — 产量目标下 MV 倍率寻优
   advise_control       — C 档：PH4 时间窗 MV 反事实咨询（+T1 校验）
  reconstruct_batch    — 回溯型重构（集合平滑）；**fallback_chain=True** 接入 D 档回退链（R163/D-80）
  batch_fallback_tier  — D 档：只读判定某批的回退链层级（enkf/mhe/steady_state/explicit_failure）
  trajectory_check     — A 档验收算子：逐点轨迹对照 V3（GOAL §4.2）
  element_balance_check— A 档验收算子：批级 C/N 元素平衡（GOAL §4.3）
  observe_online       — PH5 / B 档在线 EnKF 同化（只读）；返回体恒含降级 / 不可辨识标记（R164-1）
  discover_residual    — PH5 / PH2 结构残差发现（SINDy 稀疏辨识，只读）；返回体恒含不可辨识 / 降级标记（R164-1）

工具总数：**14**（R164-1 由 12 补齐 `observe_online` + `discover_residual`；两者均为纯新增，
既有 12 个工具的函数体与返回体逐位不变 ⇒ 默认路径 `max|Δ| = 0.00e+00`）。

运行：项目根目录下 `python candidate/indpensim/v0.1/mcp_server.py [--transport http]`
Agent 侧注册：{"command": "python", "args": ["<abs path to mcp_server.py>"]}
"""
import argparse
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.chdir(_ROOT)  # 数据路径以项目根为基准（data/processed/batches/...）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

# R166 / D-85：优先第三方 fastmcp；未安装时回退 MCP 官方 SDK 内置的
# mcp.server.fastmcp.FastMCP（本机锁版本 mcp==1.12.0 已提供同构 tool/run/list_tools API）。
# 不引入第三方 fastmcp 发行版的依据：2.x 全系要求 rich>=13.9.4 / pydantic>=2.11 /
# 更高 mcp / anyio 4.x，实测 pip dry-run 会连带升级 11–30 个包并破坏 requirements.txt
# 的 numpy/scipy/pandas 复现锁 ⇒ 用官方 SDK 兼容层，零依赖污染且服务本机可启动。
try:
    from fastmcp import FastMCP as _FastMCP
    _FASTMCP_BACKEND = "fastmcp"
except ImportError:
    from mcp.server.fastmcp import FastMCP as _FastMCP
    _FASTMCP_BACKEND = "mcp.server.fastmcp"


if _FASTMCP_BACKEND == "mcp.server.fastmcp":
    class _OfficialSDKFastMCP(_FastMCP):
        """官方 SDK 兼容层：抹平两处 API 差异，使 14 个 `@mcp.tool` 装饰行逐字不变。

        ① 官方 SDK 的 `tool` 只接受 `@tool()`；第三方 fastmcp 允许 `@tool`（无括号）。
        ② 官方 SDK 的 `run` 用 `transport="streamable-http"` 且不接 `port`/`host`。
        stdio 是本项目受支持的路径；HTTP 仅做参数归一化，不监听任何端口。
        """
        def tool(self, *args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return super().tool()(args[0])
            return super().tool(*args, **kwargs)

        def run(self, transport="stdio", **kwargs):
            if transport == "http":
                transport = "streamable-http"
            return super().run(transport=transport)

    FastMCP = _OfficialSDKFastMCP
else:
    FastMCP = _FastMCP

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
            "D": "B 档方法族回退链（EnKF 健康 → MHE + 稳态碳平衡 → 稳态基线 → 显式失败；"
                 "R163/D-80，**opt-in**：reconstruct_batch(fallback_chain=True) 或 batch_fallback_tier）",
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
def reconstruct_batch(batch_no: int, n_ens: int = 50, fallback_chain: bool = False) -> dict:
    """内部观测体系（回溯型，PH3-m1）：集合平滑器 — θ_b 后验采样 → 引擎重放 →
    状态轨迹均值 ±1.96σ + I3 覆盖率（P/PAA/X 对 V3 化验真值）。
    批号未入快校准日志时自动先做 18 组合快校准（~2.5 分钟）再重放（~n_ens×8 秒）。

    **fallback_chain**（R163 / D-80）：默认 **False** ⇒ 返回体与接入前**逐位一致**
    （零回归保证，见 `tools/r163_mcp_integration_probe.py`）。
    置 True 时启用 **B 档方法族回退链**（EnKF 健康 → MHE → 稳态碳平衡 → 显式失败），
    并在返回体**追加** `fallback_chain` 块，其中**必含**：
      - `tier`：`enkf` / `mhe` / `steady_state` / `explicit_failure`
      - `degraded`：是否已降级
      - `reconstruction_valid`：**主结果（集合平滑）当前是否可信**
      - `reasons` / `trace`：降级原因与逐环判定链（不得静默，§3.3）
      - `fallback`：降级后的可用估计（无则 None）
    ⚠ `tier != 'enkf'` 时**主结果可能不可信**，应改用 `fallback` 字段；
      `tier == 'explicit_failure'` 表示**无可用估计**（不得当作貌似合理的数使用）。
    """
    from observe import ensemble_smooth
    from knowledge_constraints import paa_pat_trigger
    r = ensemble_smooth(int(batch_no), n_ens=min(int(n_ens), 120), out_path=None)
    sampled = r["mean"].iloc[::100].round(3).to_dict("records")  # 6h 粒度轨迹抽样
    _cal = calib_params(int(batch_no))
    trig, trig_reason = paa_pat_trigger(_cal.get("mup"))
    out = {"batch": r["batch"], "n_ens_eff": r["n_ens_eff"],
           "n_fail": r.get("n_fail", 0), "coverage": r["coverage"],
           "mean_sample": sampled,
           "paa_pat_advisory": {"trigger": bool(trig), "reason": trig_reason,
            "note": "μp>0.055 → 建议锚定修正层接入（docsraman_pat_integration_spec.md §1）"}}
    if fallback_chain:
        # 只**追加**键，不改动任何既有键 ⇒ fallback_chain=False 时返回体逐位不变
        out["fallback_chain"] = _fallback_chain_block(int(batch_no))
    return out


def _fallback_chain_block(batch_no, n_ens=20, seed=7):
    """回退链判定块（**降级标记必须出现在返回体** —— §3.3 禁止静默输出貌似合理的数）。

    本函数是**只读旁路**：不改变 `reconstruct_batch` 的任何数值路径。
    """
    import solver_chain as sc
    chain = sc.evaluate_batch_fallback(int(batch_no), n_ens=int(n_ens), seed=int(seed))
    tier = chain["tier"]
    valid = bool(tier == sc.TIER_ENKF)
    return {
        "tier": tier,
        "degraded": bool(chain["degraded"]),
        "reconstruction_valid": valid,
        "reasons": chain["reasons"],
        "trace": chain["trace"],
        "fallback": chain["fallback"],
        "evidence": chain["evidence"],
        "note": ("tier='enkf' ⇒ 集合估计有效，主结果可直接采用；"
                 "tier!='enkf' ⇒ 已降级，**主结果（集合平滑）可能不可信**，"
                 "请改用 fallback 字段；"
                 "tier='explicit_failure' ⇒ 无可用估计（不得当作貌似合理的数使用）。"),
    }


@mcp.tool
def batch_fallback_tier(batch_no: int, n_ens: int = 20, seed: int = 7) -> dict:
    """只读：判定某批的 B 档方法族**回退链层级**（不跑集合平滑，比 reconstruct_batch 快）。

    链序：EnKF 健康 →（不健康）MHE + 稳态碳平衡约束 →（不可解）稳态基线 →（闭合失败）显式失败。
    返回 `tier` / `degraded` / `reasons` / `trace` / `evidence` / `fallback`。
    `tier='enkf'` 表示集合估计健康；`explicit_failure` 表示**无可用估计**。
    """
    import solver_chain as sc
    chain = sc.evaluate_batch_fallback(int(batch_no), n_ens=int(n_ens), seed=int(seed))
    return {"batch": int(batch_no), "tier": chain["tier"],
            "degraded": chain["degraded"], "reasons": chain["reasons"],
            "trace": chain["trace"], "evidence": chain["evidence"],
            "fallback": chain["fallback"]}


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


# ---------------------------------------------------------------------------
# R164-1（PH5 服务化补齐）：两个**纯新增**只读工具。
# 纪律：① 不改任何既有工具 / 不改引擎数值 ⇒ 默认路径逐位零回归；
#       ② 返回体**恒含** `identifiable` / `degraded` / `degradation_reasons`
#          （§3.3 禁止静默输出貌似合理的数；「不可辨识」与「降级」都不得省略）；
#       ③ 降级判定是数据驱动的（阈值写进返回体 `criteria`，非恒真）。
# ---------------------------------------------------------------------------

# 菌丝分室状态的观测结构结论（R164-7 / D-88）：在现有观测算子下**结构性不可辨识**。
# 该块对两个工具都返回，作为「不可辨识」标记的权威口径（须先证明再登记，见
# docs/r165_mycelium_identifiability.md）。
_MYCELIUM_UNIDENTIFIABLE = {
    "identifiable": False,
    "exposed": ["X_sum", "X_sd", "vis"],
    "not_exposed": ["A0", "A1", "A3", "A4"],
    "reason": ("观测算子只暴露 X_sum / X_sd / vis 三个标量；X_offline 在 observe.py 的 "
               "ident_map 中为 None 且被 continue 排除同化；EnKF 的 ALLOWED 表不含任何 A 组索引 "
               "⇒ 观测矩阵对 A 组子空间的限制秩为 0（至多 1），零空间 ≥3 维 ⇒ 分室不可分离。"),
    "scope": ("在**现有观测设计**下不可辨识（增加同类批次不改变列空间）；换用含菌丝形态测量的"
              "新观测通道可解，属 R164-V5(b) / 数据资产级「不可验证」的范畴。"),
    "code_refs": ["observe.py:31-32", "observe.py:68-74", "observe.py:251-256",
                  "observe.py:276-279", "model.py:670", "simulate.py:90-93"],
}


@mcp.tool
def discover_residual(batch_no: int, max_terms: int = 3,
                      theta_source: str = "log") -> dict:
    """PH5 / PH2：**结构残差发现**（SINDy 式稀疏辨识）的只读服务化封装（R164-1）。

    对已入库 θ_b 的批次：以 θ_b 重跑引擎 → S/P 通道残差通量 → 9 项候选库全子集
    最小二乘 + BIC 排序 → 最优稀疏结构（`residual_discovery.py`）。

    **返回体恒含**：`identifiable`（结构是否可辨识）、`degraded`（是否降级）、
    `degradation_reasons`（降级原因，不得静默）。不可辨识判据是数据驱动的三条
    （样本数 / 设计矩阵条件数 / 最优与次优结构的 ΔBIC），阈值随返回体 `criteria` 报出，
    便于复核且避免恒真判据（承 D-78）。

    **只读**：不写引擎、不写 data/、不进入任何默认路径；`theta_source="log"`
    从 `runs/hier_est/train_theta_v2.jsonl`（v1 兜底）取 θ_b，缺 θ 时显式降级返回。
    """
    import numpy as np
    from residual_discovery import load_theta, _aligned_residuals, _features, sparse_fit

    b = int(batch_no)
    mt = max(1, min(int(max_terms), 3))
    criteria = {"min_samples_per_term": 3, "max_design_cond": 1e8,
                "min_delta_bic": 2.0, "max_terms": mt}
    out = {
        "batch": b, "tool": "discover_residual", "mode": "read_only",
        "theta_source": theta_source, "theta_available": False,
        "identifiable": False, "degraded": True, "degradation_reasons": [],
        "criteria": criteria, "structures": {},
        "mycelium_compartments": dict(_MYCELIUM_UNIDENTIFIABLE),
        "note": ("`identifiable` / `degraded` 恒返回；degraded=True 时 structures 为空或部分，"
                 "**不得**把貌似合理的稀疏结构当作已辨识结论使用。菌丝分室状态在任何情况下"
                 "都不可辨识（见 mycelium_compartments），本工具只做 S/P 通量的结构发现。"),
    }
    try:
        thetas = load_theta() if theta_source == "log" else {}
    except Exception as e:
        out["degradation_reasons"].append(
            f"theta_log_unreadable: {type(e).__name__}: {str(e)[:160]}")
        return out
    theta = thetas.get(b)
    if theta is None or not theta.get("theta_post"):
        out["degradation_reasons"].append(
            f"theta_not_available: batch {b} 不在 {theta_source} θ_b 日志中 ⇒ 无法做残差重放，"
            "结构发现不可辨识（显式降级，不猜测 θ）")
        return out
    out["theta_available"] = True
    try:
        sim, v3, res = _aligned_residuals(b, theta)
    except Exception as e:
        out["degradation_reasons"].append(
            f"replay_failed: {type(e).__name__}: {str(e)[:160]}")
        return out

    ch_ok = {}
    reasons = []
    for ch in ("S", "P"):
        t = res[ch]["t"]
        dres = np.gradient(res[ch]["resid"], t)
        cols = _features(sim, v3, t)
        best, top5 = sparse_fit(t, dres, cols, max_terms=mt)
        phi = np.column_stack([cols[c] for c in cols])
        try:
            cond = float(np.linalg.cond(phi))
        except Exception:
            cond = float("inf")
        delta_bic = float(top5[1]["bic"] - top5[0]["bic"]) if len(top5) >= 2 else float("inf")
        n = int(len(t))
        k = int(len(best["terms"]))
        ok_n = n >= criteria["min_samples_per_term"] * (k + 1)
        ok_cond = cond < criteria["max_design_cond"]
        ok_bic = delta_bic >= criteria["min_delta_bic"]
        ch_ok[ch] = bool(ok_n and ok_cond and ok_bic)
        out["structures"][ch] = {
            "best": best, "top5": top5, "n_samples": n, "n_terms": k,
            "design_cond": cond, "delta_bic": delta_bic,
            "checks": {"enough_samples": ok_n, "design_well_conditioned": ok_cond,
                       "bic_separation": ok_bic},
        }
        if not ok_n:
            reasons.append(f"{ch}: n_samples={n} < {criteria['min_samples_per_term']}*(k+1)={3*(k+1)}")
        if not ok_cond:
            reasons.append(f"{ch}: design_cond={cond:.3e} ≥ {criteria['max_design_cond']:.0e}（候选库近共线）")
        if not ok_bic:
            reasons.append(f"{ch}: delta_bic={delta_bic:.3f} < {criteria['min_delta_bic']}（最优与次优结构不可分辨）")

    out["identifiable"] = bool(all(ch_ok.values())) if ch_ok else False
    out["degraded"] = not out["identifiable"]
    out["degradation_reasons"] = reasons if reasons else []
    if not reasons:
        out["note"] += " 本批 S/P 结构辨识通过三条判据；菌丝分室状态仍不可辨识（见上）。"
    return out


@mcp.tool
def observe_online(batch_no: int, n_ens: int = 20, seed: int = 7,
                   stride: int = 50, health_probe: bool = False) -> dict:
    """PH5 / B 档：**在线 EnKF 同化**的只读服务化封装（R164-1）。

    包装 `observe.enkf_observe(...)`：在线 5 通道 + 4 个延迟化验点同化，逐样本输出
    状态均值 ± 标准差（P/S/X_sum/PAA/mup/m_s）。`stride` 控制返回记录的降采样步长
    （默认 50 ⇒ 10 h 粒度），`health_probe=True` 追加集合健康度旁路证据（opt-in，
    不影响数值）。

    **返回体恒含**：`degraded` / `reconstruction_valid` / `identifiable` /
    `degradation_reasons` / `mycelium_compartments`。降级分两级：
      - **硬失败**（异常 / 空记录 / 非有限）⇒ `reconstruction_valid=False`；
      - **软告警**（成员积分失败、n_ens<8 低置信）⇒ 仍 `degraded=True` 但标注为低置信。
    **菌丝分室 A0/A1/A3/A4 在任何情况下都 `identifiable=False`**（观测算子结构秩亏，
    D-88 / R164-7）——本工具只上报 `X_sum` / `X_sd`，不提供分室估计。

    **只读**：不写引擎、不写 data/、`out_path=None`、不进入任何默认路径。
    """
    import math
    from observe import enkf_observe

    b = int(batch_no)
    ne = max(2, min(int(n_ens), 120))
    st = max(1, int(stride))
    out = {
        "batch": b, "tool": "observe_online", "mode": "read_only",
        "n_ens": ne, "seed": int(seed), "stride": st,
        "health_probe": bool(health_probe),
        "degraded": False, "reconstruction_valid": True,
        "identifiable": False, "degradation_reasons": [],
        "mycelium_compartments": dict(_MYCELIUM_UNIDENTIFIABLE),
        "criteria": {"min_n_ens_full_confidence": 8,
                     "hard_failures": ["enkf_exception", "empty_records", "non_finite"]},
        "n_records": 0, "integration_failures": None,
        "records_sample": [], "end_state": None, "health_sample": None,
        "note": ("`degraded` / `reconstruction_valid` / `identifiable` 恒返回。"
                 "degraded=True 时先看 degradation_reasons 再决定是否采用 records_sample；"
                 "reconstruction_valid=False ⇒ 无可用估计，不得当作貌似合理的数使用。"
                 "本工具不输出 A0/A1/A3/A4 分室估计（结构性不可辨识）。"),
    }
    if ne < out["criteria"]["min_n_ens_full_confidence"]:
        out["degraded"] = True
        out["degradation_reasons"].append(
            f"ensemble_too_small: n_ens={ne} < {out['criteria']['min_n_ens_full_confidence']} ⇒ 低置信（软告警）")
    try:
        r = enkf_observe(b, n_ens=ne, seed=int(seed), verbose=False,
                         out_path=None, health_probe=bool(health_probe))
    except Exception as e:
        out["degraded"] = True
        out["reconstruction_valid"] = False
        out["degradation_reasons"].append(
            f"enkf_exception: {type(e).__name__}: {str(e)[:160]}")
        return out

    recs = r.get("records", []) or []
    out["n_records"] = len(recs)
    out["integration_failures"] = int(r.get("integration_failures", 0))
    if out["integration_failures"] > 0:
        out["degraded"] = True
        out["degradation_reasons"].append(
            f"member_integration_failures: {out['integration_failures']} 次（软告警；成员已重采样回均值邻域）")
    if not recs:
        out["degraded"] = True
        out["reconstruction_valid"] = False
        out["degradation_reasons"].append("empty_records: EnKF 未产出任何记录")
        return out
    nonfinite = []
    for rec in recs:
        for k, v in rec.items():
            if isinstance(v, float) and not math.isfinite(v):
                nonfinite.append(k)
    if nonfinite:
        out["degraded"] = True
        out["reconstruction_valid"] = False
        out["degradation_reasons"].append(
            f"non_finite: 记录含非有限字段 {sorted(set(nonfinite))[:6]}")
        return out

    out["records_sample"] = recs[::st]
    out["end_state"] = recs[-1]
    if bool(health_probe) and r.get("health") is not None:
        h = r["health"]
        out["health_sample"] = {
            "n_health_steps": len(h.get("t", [])),
            "t": h.get("t", [])[::st][:200],
            "cv": h.get("cv", [])[::st][:200],
            "fail_cum": h.get("fail_cum", [])[::st][:200],
        }
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--port", type=int, default=8931)
    a = ap.parse_args()
    if a.transport == "http":
        mcp.run(transport="http", port=a.port, host="127.0.0.1")
    else:
        mcp.run()
