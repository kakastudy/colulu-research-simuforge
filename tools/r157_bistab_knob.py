# -*- coding: utf-8 -*-
"""R157 / D-57（v2）：b22 类**双稳态**的连续旋钮搜索 —— 找能让响应连续下来的旋钮。

v1 的二分器缺陷（已修，见下方「二分判据」）
------------------------------------------
v1 的二分更新规则是

    if abs(ym - ylo) <= abs(yhi - ylo):  lo, ylo = mid, ym
    else:                                hi, yhi = mid, ym

当跳变幅度接近 100 pp（如 `ylo = -100%`、`yhi = 0%`）且中点落在**高端分支**时，
`|ym - ylo| ≈ |yhi - ylo|`，`<=` 的平局判定会把高端中点**错记到低端** ⇒
区间塌陷到单一分支 ⇒ 后续密采样全落在同一侧 ⇒ **假阳性 CONTINUOUS**。
证据：`runs/r157_bistab_knob_v1_bisectbug.json` 的 `sd` 行 —— 二分把区间收敛到
`[0.00149951, 0.0015]`，而该区间 32 个采样点**全部**在高端（−0.151%…−0.148%），
说明跳变根本不在区间内 ⇒ 判定无效。

v2 的二分判据（修正）
--------------------
1. **二分更新**：以**响应区间的中点**为界判定中点在哪一侧（对任意跳变幅度都正确）：
   `if ym < (ylo + yhi) / 2:  lo = mid`  否则 `hi = mid`。
2. **区间收缩诊断**（判定的**主证据**）：
   每步记录区间内的响应跨度 `range_pp = |yhi - ylo|`。
   - **连续函数**：区间收窄时响应跨度**几何收缩**（局部线性 ⇒ 每步约减半）；
   - **不连续函数**：区间始终夹着跳变，响应跨度**恒为满跳变**。
   ⇒ 判据：`range_pp` 在 N 步二分后 **< 5 pp ⇒ CONTINUOUS**，否则 **DISCONTINUOUS**。
   这比"密采样最大相邻跳变"更省算力，且**不依赖采样点落在哪一侧**。
3. **密采样确认**：区间内 16 点密采样，报最大相邻跳变；
   同时校验**区间有效性** —— 若 16 点全在同侧（响应跨度 < 5 pp 但粗扫跨度 > 20 pp），
   判 `BRACKET_INVALID`（区间没夹住跳变），**不得判 CONTINUOUS**。

旋钮（b22 上的有效旋钮；已剔除无效口）
------------------------------------
  sd     `P_std_dev` (par[3]) 门控宽度
  meanP  `mean_P`    (par[4]) 门控中心
  kdeg   `p_deg_rate`         P 水解降解率（默认 0）
  muhs   `mu_h_scale` (par[18]) 衰亡倍率（**注意：par[19] `mu_h` 在 inhib_flag=2 分支被
                                     `k4·par[18]` 覆盖 ⇒ 对 b22 无效，故用 par[18]**）
  Ysp    `Y_sP`      (par[23]) **产素耗糖系数 = 环路增益的直接旋钮**（R154 的环路分析指向它）
  m_s    (par[24])   **对 b22 无效**（b22 有 `m_s_schedule`=[(110,0.01)]，调度优先）⇒ 自动标 N/A

用法
----
    python tools/r157_bistab_knob.py --batches 22 --workers 6
    python tools/r157_bistab_knob.py --batches 22 --knobs sd,meanP,Ysp --refine-n 16
    python tools/r157_bistab_knob.py --batches 22 --ph-fix 1     # 候选基线 v2 口径
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 粗扫网格（绝对值；b22 基准：sd=0.0015 g/L、meanP=0.002 g/L、muhs=3.5、Ysp=0.9）
GRIDS = {
    "sd":    [0.0002, 0.0005, 0.0010, 0.0015, 0.0025, 0.0040, 0.0080, 0.0200, 0.0500],
    "meanP": [0.0010, 0.0014, 0.0017, 0.0019, 0.0020, 0.0021, 0.0024, 0.0030, 0.0050],
    "kdeg":  [0.0, 0.0005, 0.0010, 0.0020, 0.0040, 0.0060, 0.0100, 0.0160, 0.0240],
    "muhs":  [0.5, 1.0, 2.0, 3.5, 5.0, 7.0, 10.0, 15.0, 25.0],
    "Ysp":   [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 1.00],
}
KNOB_LABEL = {
    "sd": "P_std_dev (par[3]) 门控宽度 g/L",
    "meanP": "mean_P (par[4]) 门控中心 g/L",
    "kdeg": "p_deg_rate P 水解 1/h",
    "muhs": "mu_h_scale (par[18]) 衰亡倍率",
    "Ysp": "Y_sP (par[23]) 产素耗糖系数 = 环路增益",
}
KNOB_KEY = {"sd": "P_std_dev", "meanP": "mean_P", "kdeg": "p_deg_rate",
            "muhs": "mu_h_scale", "Ysp": "Y_sP"}

_POOL = None


def _init_pool(workers):
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=workers)
    return _POOL


def _sim_one(job):
    """跑一批一档，返回精简指标。"""
    batch, knob, value, ph_fix, extra = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        p = dict(build_params(COMBINED[batch]))
        if extra:
            p.update(extra)
        if knob is not None:
            p[KNOB_KEY[knob]] = value
        if ph_fix:
            p["ph_fix"] = 1
        sim, v3 = s.simulate_open_loop(int(batch), p)
        ym = s.yield_metrics(sim, v3)
        ph = sim["pH"].to_numpy(float)
        P = sim["P"].to_numpy(float)
        out = {
            "knob": knob, "value": float(value),
            "yield_err": float(ym["rel_err_total"]),
            "p_max": float(np.nanmax(P)),
            "p_end": float(P[-1]),
            "ph_max": float(np.nanmax(ph)),
            "ph_end": float(ph[-1]),
        }
        try:
            va = s.validity(sim)
            out["valid"] = bool(va["valid"])
            out["ph_max_pre"] = float(va.get("ph_max_pre", float("nan")))
        except Exception:  # noqa: BLE001
            out["valid"] = None
        return out
    except Exception as e:  # noqa: BLE001
        return {"knob": knob, "value": float(value),
                "error": f"{type(e).__name__}: {e}"}


def _run(jobs, workers):
    """统一走**同一个**进程池（v1 每步新建池，Windows spawn 下开销大）。"""
    if not jobs:
        return []
    ex = _init_pool(workers)
    jobs = [j if len(j) == 5 else (j[0], j[1], j[2], j[3], None) for j in jobs]
    return list(ex.map(_sim_one, jobs))


def _bisect(batch, knob, a, bnd, ya, yb, n, ph_fix, workers, mode="anchor", extra=None):
    """跳变夹逼二分。

    返回 (lo, hi, ylo, yhi, 跨度序列)。

    两种更新规则
    ------------
    **`anchor`（v3，现行默认）—— 跳变夹逼**
        锚点取**粗扫两端的响应** `yA = f(a)`、`yB = f(b)`（不随迭代移动）。
        每步用**最近锚点**给中点分类：`dA = |ym - yA|`、`dB = |ym - yB|`，
        `dA < dB` ⇒ 中点属低端分支 ⇒ `lo = mid`；否则 ⇒ `hi = mid`。
        **不变量：区间始终同时含跳变两侧** ⇒ 步数增加时区间收敛到**跳变位置本身**。

    **`midpoint`（v2，已弃用）**
        以**响应区间中点** `(ylo+yhi)/2` 为界分类。
        ✗ 对**单调光滑**函数它收敛到「响应取中值的那一点」而不是跳变处 ——
        区间里根本没有跳变 ⇒ 跨度照样几何收缩（假 CONTINUOUS），
        且密采样全落在同一侧（`BRACKET_INVALID`）。

    判据
    ----
    跨度 `span = |f(hi) - f(lo)|`：
      连续函数 ⇒ 区间收窄时跨度**几何收缩**；不连续函数 ⇒ 跨度**恒为满跳变**。
    """
    lo, hi = a, bnd
    ylo, yhi = ya, yb
    yA, yB = ya, yb          # 锚点：粗扫两端的响应（固定，不随迭代移动）
    spans = [abs(yhi - ylo)]
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        r = _run([(batch, knob, mid, ph_fix, extra)], workers)[0]
        if "error" in r:
            break
        ym = r["yield_err"] * 100
        if mode == "anchor":
            dA = abs(ym - yA)
            dB = abs(ym - yB)
            if dA < dB:
                lo, ylo = mid, ym
            else:
                hi, yhi = mid, ym
        else:  # midpoint（v2，已弃用）
            if ym < 0.5 * (ylo + yhi):
                lo, ylo = mid, ym
            else:
                hi, yhi = mid, ym
        spans.append(abs(yhi - ylo))
    return lo, hi, ylo, yhi, spans



def analyse(knob, grid_rows, refine_rows, bisect_info):
    """连续性判定（v2）。"""
    rows = [r for r in grid_rows if "error" not in r]
    vals = [r["value"] for r in rows]
    ys = [r["yield_err"] * 100 for r in rows]
    coarse_max = 0.0
    coarse_jump = None
    for i in range(1, len(rows)):
        d = ys[i] - ys[i - 1]
        if abs(d) > abs(coarse_max):
            coarse_max = d
            coarse_jump = (vals[i - 1], vals[i], d)
    res = {
        "knob": knob,
        "label": KNOB_LABEL.get(knob, knob),
        "n_grid": len(rows),
        "grid": [{"value": r["value"], "yield_err": r["yield_err"] * 100,
                  "valid": r.get("valid"), "ph_max": r.get("ph_max"),
                  "p_max": r.get("p_max")} for r in rows],
        "coarse_max_adj_jump_pp": coarse_max,
        "coarse_jump_at": coarse_jump,
    }
    # 找相邻 >20pp 的区间做细化
    bracket = None
    for i in range(1, len(rows)):
        if abs(ys[i] - ys[i - 1]) > 20.0:
            bracket = (vals[i - 1], vals[i], ys[i - 1], ys[i])
            break
    if bracket is None:
        res["transition"] = None
        res["verdict"] = ("CONTINUOUS" if abs(coarse_max) < 5.0
                          else ("MARGINAL" if abs(coarse_max) < 20.0 else "DISCONTINUOUS"))
        res["reason"] = ("粗扫 9 档内无 >20 pp 跳变；最大相邻跳变 %.2f pp" % coarse_max)
        return res

    a, b, ya, yb = bracket
    total_jump = yb - ya
    res["transition"] = {"bracket": [a, b], "jump_pp": total_jump,
                         "y_lo": ya, "y_hi": yb}
    if not bisect_info:
        res["verdict"] = "DISCONTINUOUS"
        res["reason"] = "存在 %.1f pp 跳变（二分未执行）" % total_jump
        return res

    lo, hi, ylo, yhi, spans = bisect_info
    res["bisect"] = {
        "bracket_lo": lo, "bracket_hi": hi,
        "y_lo": ylo, "y_hi": yhi,
        "final_range_pp": abs(yhi - ylo),
        "range_trace_pp": spans,
        "shrink_ratio": (spans[-1] / spans[0]) if spans and spans[0] else float("nan"),
    }

    fr = [r for r in refine_rows if "error" not in r]
    fr.sort(key=lambda r: r["value"])
    fy = [r["yield_err"] * 100 for r in fr]
    m = 0.0
    for i in range(1, len(fr)):
        m = max(m, abs(fy[i] - fy[i - 1]))
    sample_range = (max(fy) - min(fy)) if fy else float("nan")
    # **震荡检测**：相邻差分的变号次数（≥3 ⇒ 非单调震荡 ⇒ 混沌窗，不是"陡但连续"）
    diffs = [fy[i] - fy[i - 1] for i in range(1, len(fy))]
    n_sign = sum(1 for i in range(1, len(diffs))
                 if diffs[i] * diffs[i - 1] < 0 and abs(diffs[i]) > 1e-9
                 and abs(diffs[i - 1]) > 1e-9)
    res["refine"] = {"n": len(fr), "max_adj_jump_pp": m,
                     "sample_range_pp": sample_range,
                     "n_sign_changes": n_sign,
                     "bracket_lo": fr[0]["value"] if fr else None,
                     "bracket_hi": fr[-1]["value"] if fr else None,
                     "samples": [{"value": r["value"], "yield_err": r["yield_err"] * 100,
                                  "valid": r.get("valid")} for r in fr]}

    # ---- 判定 ----
    final_range = abs(yhi - ylo)
    # **混沌优先**：密采样出现非单调震荡 ⇒ 区间内是**混沌窗**，不是可走的连续段
    if m >= 5.0 and n_sign >= 3:
        res["verdict"] = "ERRATIC"
        res["reason"] = ("密采样 %d 点的相邻差分**变号 %d 次**（最大相邻 %.2f pp）"
                         "⇒ 区间内响应**非单调震荡**（混沌窗）⇒ 既不是阶跃也不是可走的连续段 ⇒ 不可用"
                         % (len(fr), n_sign, m))
        return res
    if final_range >= 5.0:
        res["verdict"] = "DISCONTINUOUS"
        res["reason"] = ("二分 %d 步后区间内响应跨度仍为 %.2f pp（初始 %.2f pp，"
                         "收缩比 %.3g）⇒ 跳变**不随区间收窄而消失** ⇒ **阶跃**"
                         % (len(spans) - 1, final_range, spans[0],
                            res["bisect"]["shrink_ratio"]))
        return res
    # 跨度已收敛 ⇒ 连续；再做**区间有效性**校验
    if abs(total_jump) > 20.0 and sample_range < 5.0 and m < 1.0:
        res["verdict"] = "BRACKET_INVALID"
        res["reason"] = ("粗扫跨度 %.1f pp，但二分区间内 16 点密采样全在同侧"
                         "（采样跨度 %.2f pp、最大相邻 %.2f pp）⇒ 区间没夹住跳变 ⇒ 判定无效"
                         % (total_jump, sample_range, m))
        return res
    res["verdict"] = "CONTINUOUS"
    res["reason"] = ("二分 %d 步后区间内响应跨度 %.3f pp（初始 %.2f pp，收缩比 %.3g）；"
                     "密采样 %d 点最大相邻 %.3f pp ⇒ 跳变可被小步走完 ⇒ 陡但**连续**"
                     % (len(spans) - 1, final_range, spans[0],
                        res["bisect"]["shrink_ratio"], len(fr), m))
    return res


def _dense_scan(batch, knob, a, b, n, ph_fix, workers, extra=None):
    """**粗区间直接密扫**（`--dense-coarse`）。

    为什么需要它
    ------------
    二分（含锚点夹逼）对**单调光滑**响应会收敛到「响应取中值的那一点」，
    此时区间里**根本没有跳变** ⇒ 跨度收缩到 0 ⇒ 会被误读成「连续」。
    要判定这类旋钮，只能**在粗区间上直接密扫**，看最大相邻跳变：
      若密扫最大相邻 < 5 pp ⇒ 响应能被小步走完 ⇒ **连续**；
      若密扫出现**非单调震荡**（相邻差分多次变号）⇒ **混沌窗**，不可用。
    """
    pts = np.linspace(a, b, n)
    rows = _run([(batch, knob, float(v), ph_fix, extra) for v in pts], workers)
    rows = sorted([r for r in rows if "error" not in r], key=lambda r: r["value"])
    ys = [r["yield_err"] * 100 for r in rows]
    diffs = [ys[i] - ys[i - 1] for i in range(1, len(ys))]
    max_adj = max((abs(d) for d in diffs), default=0.0)
    n_sign = sum(1 for i in range(1, len(diffs))
                 if diffs[i] * diffs[i - 1] < 0 and abs(diffs[i]) > 1e-9
                 and abs(diffs[i - 1]) > 1e-9)
    return rows, ys, max_adj, n_sign


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="22")
    ap.add_argument("--knobs", type=str, default=",".join(GRIDS.keys()))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refine-n", type=int, default=16, help="跳变区间内的密采样点数")
    ap.add_argument("--bisect-n", type=int, default=12, help="二分次数")
    ap.add_argument("--bisect-mode", type=str, default="anchor",
                    choices=["anchor", "midpoint"],
                    help="anchor=跳变夹逼（v3，现行）；midpoint=v2 已弃用（对单调光滑函数会假收缩）")
    ap.add_argument("--base-override", type=str, default="",
                    help="基础参数覆盖，如 'Y_sP=0.85'（崩塌态逃逸实验用）")
    ap.add_argument("--dense-coarse", type=int, default=0,
                    help="1 = 不做二分，直接在**粗扫区间**上密扫 %d 点（判定单调光滑型旋钮用）"
                         % 16)
    ap.add_argument("--ph-fix", type=int, default=0, help="1=用候选基线 v2 的 ph_fix")
    ap.add_argument("--json", type=str, default="runs/r157_bistab_knob.json")
    ap.add_argument("--smoke", action="store_true",
                    help="冒烟：每个旋钮只取 3 档、细化 8 点（验证通路，非结论）")
    args = ap.parse_args()

    if args.smoke:
        for k in GRIDS:
            GRIDS[k] = GRIDS[k][::max(1, len(GRIDS[k]) // 3)]
        args.refine_n = 8
        args.bisect_n = 4

    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    knobs = [k.strip() for k in args.knobs.split(",") if k.strip()]
    ph_fix = int(args.ph_fix)
    extra = {}
    for kv in [x for x in args.base_override.split(",") if x.strip()]:
        k, v = kv.split("=")
        extra[k.strip()] = float(v)
    if extra:
        print("[base-override] %s" % extra)

    all_out = []
    for b in bs:
        print(f"\n{'='*78}\n=== 批次 b{b}   ph_fix={ph_fix} ===\n{'='*78}")
        # ---- 阶段 0：粗扫 ----
        jobs = [(b, k, v, ph_fix, extra) for k in knobs for v in GRIDS[k]]
        grid = _run(jobs, args.workers)
        errs = [r for r in grid if "error" in r]
        if errs:
            print(f"  [ERR] {len(errs)} 个仿真失败，例：{errs[0]['error'][:120]}")
        for k in knobs:
            gk = [r for r in grid if r.get("knob") == k]
            gk_ok = [r for r in gk if "error" not in r]
            if not gk_ok:
                print(f"\n  【{k}】全部失败")
                all_out.append({"batch": b, "knob": k, "verdict": "ERROR",
                                "reason": gk[0].get("error") if gk else "no rows"})
                continue
            gk_ok.sort(key=lambda r: r["value"])
            print(f"\n  【{k}】{KNOB_LABEL[k]}")
            for r in gk_ok:
                print(f"      v={r['value']:<9g} 产量偏差 {r['yield_err']*100:+8.2f}%"
                      f"   pH_max {r.get('ph_max', float('nan')):5.2f}"
                      f"   P_max {r.get('p_max', float('nan')):7.3f}"
                      f"   valid={r.get('valid')}")

            # ---- 模式 B：粗区间直接密扫（判定单调光滑型旋钮）----
            if args.dense_coarse:
                ys0 = [r["yield_err"] * 100 for r in gk_ok]
                pairs = [(gk_ok[i - 1]["value"], gk_ok[i]["value"], ys0[i - 1], ys0[i])
                         for i in range(1, len(gk_ok))]
                worst = max(pairs, key=lambda p: abs(p[3] - p[2]))
                a, bnd = worst[0], worst[1]
                rows_d, ys_d, max_adj, n_sign = _dense_scan(
                    b, k, a, bnd, args.refine_n, ph_fix, args.workers, extra)
                print(f"      ↳ 粗区间密扫 [{a:.8g}, {bnd:.8g}] 共 {len(rows_d)} 点：")
                for r in rows_d:
                    print(f"         v={r['value']:<14.8g} 产量偏差 {r['yield_err']*100:+8.2f}%"
                          f"   valid={r.get('valid')}")
                if n_sign >= 3:
                    verdict = "ERRATIC"
                    reason = ("粗区间密扫 %d 点，相邻差分**变号 %d 次**（最大相邻 %.2f pp）"
                              "⇒ 非单调震荡（混沌窗）⇒ 不可用"
                              % (len(rows_d), n_sign, max_adj))
                elif max_adj < 5.0:
                    verdict = "CONTINUOUS"
                    reason = ("粗区间密扫 %d 点，最大相邻跳变 %.3f pp ⇒ 响应可被小步走完 ⇒ 连续"
                              % (len(rows_d), max_adj))
                else:
                    verdict = "DISCONTINUOUS"
                    reason = ("粗区间密扫 %d 点，最大相邻跳变 %.2f pp（变号 %d 次）⇒ 阶跃"
                              % (len(rows_d), max_adj, n_sign))
                res = {"knob": k, "label": KNOB_LABEL.get(k, k), "batch": b,
                       "mode": "dense_coarse",
                       "coarse_bracket": [a, bnd],
                       "dense": {"n": len(rows_d), "max_adj_jump_pp": max_adj,
                                 "n_sign_changes": n_sign,
                                 "samples": [{"value": r["value"],
                                              "yield_err": r["yield_err"] * 100,
                                              "valid": r.get("valid")} for r in rows_d]},
                       "verdict": verdict, "reason": reason}
                print(f"      ⇒ 判定：**{verdict}** —— {reason}")
                all_out.append(res)
                continue

            # ---- 阶段 1：二分（v3 锚点夹逼）+ 密采样 ----
            refine = []
            ys = [r["yield_err"] * 100 for r in gk_ok]
            bracket = None
            for i in range(1, len(gk_ok)):
                if abs(ys[i] - ys[i - 1]) > 20.0:
                    bracket = (gk_ok[i - 1]["value"], gk_ok[i]["value"], ys[i - 1], ys[i])
                    break
            bisect_info = None
            if bracket is not None:
                a, bnd, ya, yb = bracket
                lo, hi, ylo, yhi, spans = _bisect(
                    b, k, a, bnd, ya, yb, args.bisect_n, ph_fix, args.workers,
                    mode=args.bisect_mode, extra=extra)
                bisect_info = (lo, hi, ylo, yhi, spans)
                print(f"      ↳ 二分 {len(spans)-1} 步 → 区间 [{lo:.8g}, {hi:.8g}]"
                      f"（宽 {(hi-lo):.3g}）")
                print(f"      ↳ 区间内响应跨度序列（pp）："
                      f"{' → '.join('%.2f' % x for x in spans)}")
                pts = np.linspace(lo, hi, args.refine_n)
                refine = _run([(b, k, float(v), ph_fix, extra) for v in pts], args.workers)
                print(f"      ↳ 密采样 {len(refine)} 点：")
                rf = sorted([r for r in refine if "error" not in r],
                            key=lambda r: r["value"])
                for r in rf:
                    print(f"         v={r['value']:<14.8g} 产量偏差 {r['yield_err']*100:+8.2f}%"
                          f"   valid={r.get('valid')}")
            res = analyse(k, gk_ok, refine, bisect_info)
            print(f"      ⇒ 判定：**{res['verdict']}** —— {res['reason']}")
            res["batch"] = b
            all_out.append(res)

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"ph_fix": ph_fix, "bisect_rule": args.bisect_mode,
                       "base_override": (extra or None),
                       "rows": all_out}, f, ensure_ascii=False, indent=1)
        print(f"\nwritten: {args.json}")

    print("\n" + "=" * 78)
    print("【D-57 汇总】b22 类双稳态的连续旋钮搜索")
    print("=" * 78)
    print(f"  {'批':>4} {'旋钮':<7} {'粗扫最大相邻':>14} {'二分后区间跨度':>16} "
          f"{'密采样最大相邻':>16}  判定")
    for r in all_out:
        bi = r.get("bisect") or {}
        print(f"  {r.get('batch','?'):>4} {r.get('knob','?'):<7}"
              f" {r.get('coarse_max_adj_jump_pp', float('nan')):>13.2f}pp"
              f" {bi.get('final_range_pp', float('nan')):>15.3f}pp"
              f" {(r.get('refine') or {}).get('max_adj_jump_pp', float('nan')):>15.3f}pp"
              f"  {r.get('verdict')}")
    cont = [r for r in all_out if r.get("verdict") == "CONTINUOUS"]
    print(f"\n  连续旋钮候选：{[(r['batch'], r['knob']) for r in cont] or '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
