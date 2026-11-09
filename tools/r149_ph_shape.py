# -*- coding: utf-8 -*-
"""R149 / D-39 第一阶段：pH **振幅**归因，以及 γ1/m_ph 能不能修振幅。

背景（R148 结论）
----------------
R148 §5.5 发现：62/77 valid 批的模型 pH 峰值**超出**本批实测峰值，中位 +0.116。
与 R146"残差均值多为负"合起来，指向的不是"整体偏酸"，而是**振幅过大**（峰更高、谷更低）。
但"指向 γ1 与 m_ph"是从症状反推的推断，**没有测过**。

b22 是最锐利的例子：残差均值只有 −0.007（几乎无偏），
    模型 pH 6.185 … 6.798（振幅 0.613）
    实测 pH 6.436 … 6.589（振幅 0.153）
振幅差 **4.0 倍**，而"偏差"看不见它。

本轮先问一个可证伪的前置问题
--------------------------
    **把 pH 方程的产酸增益（γ1 / m_ph）调小，峰会不会降、谷会不会升？**

如果峰谷同时向中心收（振幅压缩）⇒ 振幅是**增益**问题，γ1 可修，D-39 降级。
如果峰谷同向平移（只是整体抬/降）⇒ 振幅是**形状**问题，γ1 修不动，D-39 升级为结构缺陷。

方法
----
对每批做 4 点扰动（γ1 标度 s ∈ {0.70, 0.85, 1.00, 1.15}），各自独立重跑，
记录 `peak / trough / amp / 分相位残差 / valid / yield_err`。
γ1 在 model.py 中只出现在 dy[6]（R146 已核），所以产量变化只能是 pH 反馈，
这使"调 γ1 会不会弄坏产量"成为可直接测量的问题。

用法
----
    python tools/r149_ph_shape.py --stage jac --batches 22,23,36,55,59,37
    python tools/r149_ph_shape.py --stage base --workers 8        # 全 86 批振幅表

输出：runs/r149_ph_shape_<stage>.json

口径纪律
--------
1. 批集一律取 `runs/final_validation_v2.json` 的 86 批（**不是** sorted(COMBINED)，后者 88 批）。
2. 参数一律走 `golden_params.build_params`，且与冻结基准逐批对账（口径闸门）。
3. `validity()` 在**评估函数内部**调用，不是事后过滤（R146 λ=0.25 事故的教训）。
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

# 分相位边界（h）。IndPenSim 一批约 230–240 h。
PHASE_EDGES = (0.0, 60.0, 120.0, 180.0, 1e9)
PHASE_NAMES = ("0-60", "60-120", "120-180", "180+")


def _aligned_meas(sim, v3, col="pH"):
    """把实测列按 time_h 对齐到仿真网格（不按行号：sim 首行 0.2 是初值不入记录）。"""
    t = sim["time_h"].to_numpy(float)
    _v = {round(float(k), 6): float(v) for k, v in
          zip(v3["time_h"].to_numpy(float), v3[col].to_numpy(float))}
    return t, np.array([_v.get(round(float(x), 6), np.nan) for x in t], dtype=float)


def one(batch, params, tag, scales=None):
    """单批单参数点：返回振幅、分相位残差、有效性、产量误差。"""
    from golden_params import COMBINED, build_params  # noqa: F401
    from simulate import simulate_open_loop, yield_metrics, validity

    sim, v3 = simulate_open_loop(int(batch), dict(params))
    t, ph_o = _aligned_meas(sim, v3, "pH")
    ph_m = sim["pH"].to_numpy(float)
    msk = np.isfinite(ph_m) & np.isfinite(ph_o) & (t > 0)

    tm, pm = t[msk], ph_m[msk]
    to, po = t[msk], ph_o[msk]
    if pm.size < 8:
        raise RuntimeError(f"b{batch}: 有效样点不足（{pm.size}）")

    i_peak_m, i_trough_m = int(np.argmax(pm)), int(np.argmin(pm))
    i_peak_o, i_trough_o = int(np.argmax(po)), int(np.argmin(po))
    amp_m = float(pm[i_peak_m] - pm[i_trough_m])
    amp_o = float(po[i_peak_o] - po[i_trough_o])

    resid = pm - po
    phase = {}
    for lo, hi, nm in zip(PHASE_EDGES[:-1], PHASE_EDGES[1:], PHASE_NAMES):
        sel = (tm >= lo) & (tm < hi)
        phase[nm] = {"mean": float(np.mean(resid[sel])) if sel.any() else float("nan"),
                     "n": int(sel.sum())}

    val = validity(sim)
    ym = yield_metrics(sim, v3)
    return {
        "batch": int(batch), "tag": tag,
        "peak_model": float(pm[i_peak_m]), "t_peak_model": float(tm[i_peak_m]),
        "trough_model": float(pm[i_trough_m]), "t_trough_model": float(tm[i_trough_m]),
        "peak_meas": float(po[i_peak_o]), "t_peak_meas": float(to[i_peak_o]),
        "trough_meas": float(po[i_trough_o]), "t_trough_meas": float(to[i_trough_o]),
        "amp_model": amp_m, "amp_meas": amp_o,
        "amp_ratio": amp_m / amp_o if amp_o > 1e-9 else float("nan"),
        "err_peak": float(pm[i_peak_m] - po[i_peak_o]),
        "err_trough": float(pm[i_trough_m] - po[i_trough_o]),
        "resid_mean": float(np.mean(resid)),
        "resid_rmse": float(np.sqrt(np.mean(resid ** 2))),
        "phase": phase,
        "ph_max_pre": val["ph_max_pre"],
        "valid": bool(val["valid"]), "flags": val["flags"],
        "n_ph_clamp": val["n_ph_clamp"], "n_ph_over7": val["n_ph_over7"],
        "yield_err": float(ym["rel_err_total"]),
    }


def _task(args):
    batch, params, tag = args[0], args[1], args[2]
    scale = args[3] if len(args) > 3 else 1.0
    t0 = time.time()
    r = one(batch, params, tag)
    r["sec"] = time.time() - t0
    r["scale"] = scale
    return r


def load_86():
    with open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8") as f:
        res = json.load(f)["results"]
    return [int(r["batch"]) for r in res], {int(r["batch"]): float(r["yield_err"])
                                            for r in res}


def load_pmap():
    from golden_params import COMBINED, build_params
    return {b: build_params(COMBINED[b]) for b in COMBINED}


def ph_coef_base():
    """pH 方程相关系数的基线值（**不是**批级标定量，故不在 `build_params()` 里）。

    `build_params()` 返回的 dict 只含批级扰动项，不含 pH 三系数与缓冲容量；
    它们住在 `make_params()` 的全局默认表里。R146 已踩过同型的坑
    （`final_validation_v2.json` 的 params 缺 `dist_flag`）。这里直接读引擎默认表。
    """
    from simulate import make_params
    par = make_params()
    return {"gamma1": float(par[62]), "gamma2": float(par[63]),
            "m_ph": float(par[64]), "abc": float(par[61])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("base", "jac"), default="jac")
    ap.add_argument("--knob", default="gamma1",
                    choices=("gamma1", "gamma2", "m_ph", "abc"),
                    help="被扫的 pH 方程系数（jac 阶段）")
    ap.add_argument("--batches", type=str, default="22,23,36,55,59,37")
    ap.add_argument("--scales", type=str, default="0.70,0.85,1.00,1.15")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", type=str, default="", help="输出文件名后缀（区分不同 knob 的扫描）")
    args = ap.parse_args()

    suffix = args.stage if not args.tag else f"{args.stage}_{args.tag}"
    out_path = os.path.join(ROOT, "runs", f"r149_ph_shape_{suffix}.json")
    pmap = load_pmap()
    b86, frozen = load_86()

    if args.stage == "base":
        batches = b86[: args.limit] if args.limit else b86
        tasks = [(b, pmap[b], "base") for b in batches]
        scales = None
    else:
        batches = [int(x) for x in args.batches.split(",") if x.strip()]
        scales = [float(x) for x in args.scales.split(",") if x.strip()]
        knob = args.knob
        k0 = ph_coef_base()[knob]
        print(f"  旋钮 {knob} 基线 = {k0:.6e}，标度 {scales}")
        tasks = []
        for s in scales:
            for b in batches:
                p = dict(pmap[b])
                p[knob] = k0 * s
                tasks.append((b, p, f"{knob}x{s:g}", s))

    print(f"[stage={args.stage}] 批 {len(batches)} 个，任务 {len(tasks)}，workers={args.workers}")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_task, tasks))
    print(f"  耗时 {time.time() - t0:.1f}s")

    # 口径闸门：标度 = 1 的点必须与冻结基准逐批一致
    gate = None
    base_rows = [r for r in rows if abs(r.get("scale", 1.0) - 1.0) < 1e-12]
    if base_rows:
        dmax = max(abs(r["yield_err"] - frozen[r["batch"]]) for r in base_rows
                   if r["batch"] in frozen)
        gate = {"baseline_vs_frozen_max_abs_delta": dmax}
        print(f"  [口径闸门] 基准 vs 冻结 max|Δyield_err| = {dmax:.3e}")
        if dmax > 1e-9:
            raise SystemExit(f"口径不符（{dmax:.3e}）——先修口径")

    # 汇总
    print("\n  批  tag     peak    trough   amp    amp/实  err_peak err_trough  valid  产率")
    for r in rows:
        print(f"  {r['batch']:>2d} {r['tag']:>6s} {r['peak_model']:.4f} {r['trough_model']:.4f}"
              f" {r['amp_model']:.4f} {r['amp_ratio']:6.2f}  {r['err_peak']:+.4f}   "
              f"{r['err_trough']:+.4f}   {'Y' if r['valid'] else 'N'}   {r['yield_err']:+.2%}")

    # 增益方向判定：同一批内 amp 随 s 的变化方向是否一致
    if args.stage == "jac":
        print("\n  [增益方向] 每批 amp 对 s 的单调性 / 峰谷是否反向")
        summary = {}
        for b in batches:
            rs = sorted([r for r in rows if r["batch"] == b], key=lambda r: r["scale"])
            if len(rs) < 2:
                continue
            amps = [r["amp_model"] for r in rs]
            peaks = [r["peak_model"] for r in rs]
            troughs = [r["trough_model"] for r in rs]
            d_amp = amps[-1] - amps[0]
            d_peak = peaks[-1] - peaks[0]
            d_tr = troughs[-1] - troughs[0]
            # 峰谷反向（一升一降）= 振幅型；同向 = 平移型
            kind = "振幅型" if d_peak * d_tr < 0 else "平移型"
            summary[b] = {"d_amp": d_amp, "d_peak": d_peak, "d_trough": d_tr, "kind": kind,
                          "amp": {r["tag"]: r["amp_model"] for r in rs},
                          "valid": {r["tag"]: r["valid"] for r in rs}}
            print(f"   b{b:>2d}  Δamp={d_amp:+.4f}  Δpeak={d_peak:+.4f}  Δtrough={d_tr:+.4f}"
                  f"  -> {kind}")
        n_amp = sum(1 for v in summary.values() if v["kind"] == "振幅型")
        print(f"\n   振幅型 {n_amp}/{len(summary)} 批")
    else:
        summary = {}

    out = {"stage": args.stage, "scales": scales, "batches": batches,
           "gate": gate, "elapsed_s": round(time.time() - t0, 1),
           "rows": rows, "summary": summary}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {out_path}")


if __name__ == "__main__":
    main()
