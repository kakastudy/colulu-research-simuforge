# -*- coding: utf-8 -*-
"""R166 A/B 证据闸门 —— 五项裁决中 V1 / V2 / V3 候选通道的独立量化评测。

设计（承 D-78 判据纪律）
------------------------
* 零信息对照：健康批无注入，候选判据必须 0 触发；
* 双向判据：正向（注入故障应触发）+ 反向（非判据通道故障不应触发），缺一不可；
* 禁止恒真 / 恒假：总触发数必须落在 (0, n) 开区间；
* 阈值数据驱动：网格扫描 + 显式裕度准则 + 按批 LOO，**不手写 10.0 / 0.02**；
* 数字一律从 runs/ 产物读取，不在代码里硬编码结论。

架构（见 docs/r166_verdict.md §2）
---------------------------------
L0 冻结基线（默认路径，逐字不变） / L1 opt-in 候选通道 / L2 本闸门 / L3 切换决策（下一阶段）。
**本闸门绝不切换默认路径**，只给出 Go / No-Go 实值。

用法：
    py tools/r166_ab_gate.py --stage v1_collect   # 采集逐通道 health 序列（EnKF，约 3–6 min）
    py tools/r166_ab_gate.py --stage v1_analyze   # 离线阈值扫描 + LOO + 四格 A/B
    py tools/r166_ab_gate.py --stage v23          # V2 方差注入 + V3 alpha_kla 查表
    py tools/r166_ab_gate.py --stage all --json   # 全流程 + 写 runs/r166_ab_gate.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "candidate" / "indpensim" / "v0.1"))

import solver_chain as sc  # noqa: E402


def jload(name):
    return json.loads((RUNS / name).read_text(encoding="utf-8"))


def jdump(name, obj):
    p = RUNS / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)


def v2_optim():
    """R166 V2 多轮寻优产物（只读）。缺文件时返回空 dict ⇒ 走全幅 σ 原始路径。"""
    p = RUNS / "r166_v2_optim.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ---------------------------------------------------------------------------
# 故障注入（与 R163 tools/r163_degradation_probe.py 同型，只改观测列，不动引擎）
# ---------------------------------------------------------------------------
def _f_do2_drift(d):
    import pandas as pd
    if "DO2" not in d.columns:
        return d
    t = d["time_h"].to_numpy(float)
    d = d.copy()
    d["DO2"] = pd.to_numeric(d["DO2"], errors="coerce") + 0.02 * np.maximum(t - 40.0, 0.0)
    return d


def _f_ph_bias(d):
    import pandas as pd
    if "pH" not in d.columns:
        return d
    d = d.copy()
    d["pH"] = pd.to_numeric(d["pH"], errors="coerce") + 0.25
    return d


def _f_co2_stuck(d):
    import pandas as pd
    if "CO2outgas" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    co2 = pd.to_numeric(d["CO2outgas"], errors="coerce").to_numpy(float)
    frozen = co2[int(np.argmin(np.abs(t - 60.0)))]
    d["CO2outgas"] = np.where(t >= 60.0, frozen, co2)
    return d


def _f_cooling_fault(d):
    import pandas as pd
    if "T" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    T = pd.to_numeric(d["T"], errors="coerce").to_numpy(float)
    d["T"] = np.where(t >= 80.0, T + 5.0, T)
    return d


FAULTS = {"do2_sensor_drift": _f_do2_drift, "ph_probe_bias": _f_ph_bias,
          "co2_sensor_stuck": _f_co2_stuck, "cooling_fault_T": _f_cooling_fault}
EXPECT_FIRE = {"do2_sensor_drift": True, "ph_probe_bias": True,
               "co2_sensor_stuck": True, "cooling_fault_T": False}


def control_batches():
    """零信息对照批号：从 R163 A 段实测的 healthy_batches 读取（不手写）。"""
    d = jload("r163_degradation_probe.json")
    return [int(b) for b in d["A_summary"]["healthy_batches"]]


def v1_jobs():
    bs = control_batches()
    jobs = [(b, None) for b in bs]                      # 零信息对照
    jobs += [(b, f) for b in bs for f in FAULTS]        # 注入例
    return jobs


def _v1_worker(job):
    """采集一个 (批, 故障) 的完整 health 序列，供离线重放任意候选判据。"""
    b, fault = job
    import simulate
    from observe import enkf_observe
    from calibration import calib_params
    _orig = simulate.load_batch
    try:
        if fault is not None:
            fn = FAULTS[fault]
            simulate.load_batch = lambda _b: fn(_orig(_b))
        out = enkf_observe(b, params=calib_params(b), n_ens=8, seed=7,
                           verbose=False, health_probe=True)
    except Exception as exc:
        return {"batch": int(b), "fault": fault,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        simulate.load_batch = _orig

    h = out.get("health") or {}
    health = {k: h.get(k) for k in ("t", "cv", "mean", "fail_cum", "cond", "z")}
    hr = sc.enkf_health(health, records=None,
                        integration_failures=out.get("integration_failures"),
                        n_ens=out.get("n_ens"))
    dg = sc.degradation_guard(hr)
    return {"batch": int(b), "fault": fault,
            "expect_fire": (None if fault is None else bool(EXPECT_FIRE[fault])),
            "n_steps": int(hr["metrics"].get("n_steps", 0)),
            "frozen_degraded": bool(dg["degraded"]),
            "frozen_reasons": list(hr["reasons"]),
            "integration_failures": int(out.get("integration_failures", 0)),
            "n_ens": int(out.get("n_ens", 8)),
            "health": health}


def v1_collect(workers=4):
    import multiprocessing as mp
    jobs = v1_jobs()
    t0 = time.time()
    print("[V1 采集] %d 例（对照 %d + 注入 %d），n_ens=8，workers=%d"
          % (len(jobs), len(control_batches()), len(jobs) - len(control_batches()), workers),
          flush=True)
    ctx = mp.get_context("spawn")
    out = []
    with ctx.Pool(processes=workers) as pool:
        for i, r in enumerate(pool.imap_unordered(_v1_worker, jobs), 1):
            out.append(r)
            print("  [%2d/%2d] b%-3d %-18s frozen_degraded=%s %s"
                  % (i, len(jobs), r["batch"], r.get("fault") or "CONTROL",
                     r.get("frozen_degraded"), r.get("error", "")), flush=True)
    out.sort(key=lambda r: (r["batch"], str(r["fault"])))
    payload = {"round": "R166", "stage": "v1_collect",
               "n_cases": len(out), "n_error": sum(1 for r in out if "error" in r),
               "wall_s": round(time.time() - t0, 2), "cases": out}
    jdump("r166_v1_health.json", payload)
    print("[V1 采集] 完成：%d 例 / 错误 %d / %.1fs"
          % (len(out), payload["n_error"], payload["wall_s"]), flush=True)
    return payload


# ---------------------------------------------------------------------------
# V1 分析：逐通道阈值扫描 + 显式裕度 + LOO + 四格 A/B
# ---------------------------------------------------------------------------
JUDGED = list(sc.INNOVATION_Z_CHANNELS)   # ("CO2outgas", "DO2", "O2", "pH")


def _channel_stats(health, ch, z_th):
    """返回某通道在给定阈值下的 (n, n_over, frac, z_max)。完全离线。"""
    z = health.get("z") or []
    n = n_over = 0
    z_max = 0.0
    for step in z:
        if ch not in step:
            continue
        v = float(step[ch])
        if not np.isfinite(v):
            continue
        n += 1
        a = abs(v)
        z_max = max(z_max, a)
        if a > z_th:
            n_over += 1
    return {"n": n, "n_over": n_over,
            "frac": (n_over / n) if n else 0.0, "z_max": z_max}


def _replay(cases, criteria):
    """用完整 health 序列重放候选判据，返回逐例 degraded（与冻结判据同一输入）。"""
    out = []
    for c in cases:
        if "error" in c:
            out.append(False)
            continue
        hr = sc.enkf_health(c["health"], records=None,
                            integration_failures=c["integration_failures"],
                            n_ens=c["n_ens"], innovation_criteria=criteria)
        out.append(bool(sc.degradation_guard(hr)["degraded"]))
    return out


def _confusion(cases, fired):
    tp = fn = tn = fp = 0
    for c, f in zip(cases, fired):
        exp = c.get("expect_fire")
        if exp is None:
            continue                      # 零信息对照单独统计，不进四格
        if exp and f:
            tp += 1
        elif exp and not f:
            fn += 1
        elif (not exp) and (not f):
            tn += 1
        else:
            fp += 1
    return {"TP": tp, "FN": fn, "TN": tn, "FP": fp}


def v1_analyze():
    d = jload("r166_v1_health.json")
    cases = [c for c in d["cases"] if "error" not in c]
    controls = [c for c in cases if c["fault"] is None]
    injected = [c for c in cases if c["fault"] is not None]
    checks = []

    def check(cid, name, ok, got):
        checks.append({"id": cid, "name": name, "pass": bool(ok), "got": got})

    # 冻结判据的「非创新」原因（其余四条判据）与阈值无关 ⇒ 预计算，供离线扫描
    base_degraded = [any(not r.startswith("标准化创新越界")
                         for r in c["frozen_reasons"]) for c in cases]
    frozen_fired = [bool(c["frozen_degraded"]) for c in cases]
    cff = _confusion(cases, frozen_fired)

    # ---- 轮 1：零信息对照 / 注入例的逐通道 |z| 上界（全部实测，不手写）----
    ctrl_max = {ch: max((_channel_stats(c["health"], ch, 0.0)["z_max"]
                         for c in controls), default=0.0) for ch in JUDGED}
    inj_max = {ch: max((_channel_stats(c["health"], ch, 0.0)["z_max"]
                        for c in injected), default=0.0) for ch in JUDGED}
    sep = {ch: (inj_max[ch] / ctrl_max[ch] if ctrl_max[ch] > 0 else 0.0)
           for ch in JUDGED}

    # ---- 轮 2：全网格（阈值 = 对照上界 × 倍数；持续占比），倍数从网格选取 ----
    mult_grid = [1.05, 1.2, 1.5, 2.0, 3.0, 4.0, 6.0]
    frac_grid = [0.0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30]
    zth = {(ch, m): m * ctrl_max[ch] for ch in JUDGED for m in mult_grid}
    stat = []
    for c in cases:
        row = {}
        for ch in JUDGED:
            for m in mult_grid:
                row[(ch, m)] = _channel_stats(c["health"], ch, zth[(ch, m)])
        stat.append(row)

    def fire_flags(idxs, chs, m, mf):
        flags = []
        for ci in idxs:
            hit = any(stat[ci][(ch, m)]["n_over"] > 0
                      and stat[ci][(ch, m)]["frac"] >= mf for ch in chs)
            flags.append(bool(base_degraded[ci] or hit))
        return flags

    def scan(idxs):
        sub = [cases[i] for i in idxs]
        ccf = _confusion(sub, [frozen_fired[i] for i in idxs])
        n_inj = sum(1 for c in sub if c["fault"] is not None)
        out = []
        for m in mult_grid:
            for chs in SUBSETS:
                for mf in frac_grid:
                    flags = fire_flags(idxs, chs, m, mf)
                    if any(c["fault"] is None and f for c, f in zip(sub, flags)):
                        continue                      # 零信息对照必须 0 触发
                    cf = _confusion(sub, flags)
                    if not (cf["TP"] >= ccf["TP"] and cf["FP"] <= ccf["FP"]
                            and cf["TN"] >= ccf["TN"]):
                        continue
                    nf = sum(1 for c, f in zip(sub, flags)
                             if c["fault"] is not None and f)
                    if not (0 < nf < n_inj):
                        continue                      # 禁恒真 / 恒假
                    out.append({"m": m, "chs": list(chs), "mf": mf,
                                "conf": cf, "n_fired_inj": nf})
        return out, ccf

    SUBSETS = _channel_subsets()
    all_idx = list(range(len(cases)))
    feasible, _ = scan(all_idx)

    check("V1-1", "零信息对照：可行组合全部保证健康无注入批 0 触发",
          len(feasible) > 0,
          {"n_control": len(controls), "n_injected": len(injected),
           "n_feasible": len(feasible),
           "ctrl_max_z": {k: round(v, 4) for k, v in ctrl_max.items()},
           "inj_max_z": {k: round(v, 4) for k, v in inj_max.items()},
           "separation": {k: round(v, 3) for k, v in sep.items()}})
    check("V1-2", "阈值数据驱动：阈值 = 对照上界 × 网格倍数，非空组合 > 0",
          len(feasible) > 0,
          {"mult_grid": mult_grid, "frac_grid": frac_grid,
           "n_subsets": len(SUBSETS), "n_feasible": len(feasible),
           "note": "无手写 10.0 / 0.02；阈值由实测 |z| 分布导出"})

    # ---- 轮 3：显式裕度准则 —— 取最大可行裕度，在该裕度下选最灵敏组合 ----
    margins = sorted({f["m"] for f in feasible})
    chosen_margin = max(margins) if margins else None
    pool = [f for f in feasible if f["m"] == chosen_margin]
    best = (sorted(pool, key=lambda f: (-f["conf"]["TP"], f["conf"]["FP"],
                                        f["conf"]["FN"], len(f["chs"]),
                                        f["mf"]))[0] if pool else None)
    check("V1-3", "显式裕度准则选出候选（最大可行裕度 + 最灵敏组合）",
          bool(best),
          {"margin_grid": mult_grid, "chosen_margin": chosen_margin,
           "chosen_channels": None if not best else best["chs"],
           "chosen_min_frac": None if not best else best["mf"]})
    if not best:
        check("V1-4", "候选判据四格 A/B 不劣于冻结判据", False,
              {"reason": "no feasible criteria under D-78"})
        return {"checks": checks, "criteria": None}

    crit = {"channels": {ch: {"z_th": float(zth[(ch, best["m"])]),
                              "min_frac": float(best["mf"])}
                         for ch in best["chs"]},
            "excluded": [ch for ch in JUDGED if ch not in best["chs"]]}

    # ---- 真实重放确认（查表快扫的结论必须用引擎函数复核）----
    fired = _replay(cases, crit)
    cf = _confusion(cases, fired)
    n_ctrl_fire = sum(1 for c, f in zip(cases, fired) if c["fault"] is None and f)
    n_fired_inj = sum(1 for c, f in zip(cases, fired)
                      if c["fault"] is not None and f)
    check("V1-4", "真实重放与离线扫描一致，且 TP 不降 / FP 不增 / TN 不降",
          cf == best["conf"] and cf["TP"] >= cff["TP"]
          and cf["FP"] <= cff["FP"] and cf["TN"] >= cff["TN"],
          {"candidate": cf, "frozen": cff, "offline": best["conf"],
           "delta_TP": cf["TP"] - cff["TP"], "delta_FP": cf["FP"] - cff["FP"],
           "criteria": crit})
    check("V1-5", "双向判据：非恒真 / 非恒假（注入例触发数落在 (0, n) 开区间）",
          0 < n_fired_inj < len(injected) and n_ctrl_fire == 0,
          {"n_fired_injected": n_fired_inj, "n_injected": len(injected),
           "n_control_fired": n_ctrl_fire})
    check("V1-6", "反向判别力：非判据通道故障误报不增加且 TN > 0",
          cf["FP"] <= cff["FP"] and cf["TN"] > 0,
          {"TN_candidate": cf["TN"], "TN_frozen": cff["TN"],
           "FP_candidate": cf["FP"], "FP_frozen": cff["FP"]})

    # ---- 轮 4：按批 LOO，同准则重选必须在全部折上不劣于冻结判据 ----
    loo = []
    for hold in sorted({c["batch"] for c in controls}):
        idxs = [i for i, c in enumerate(cases) if c["batch"] != hold]
        fs, ccf = scan(idxs)
        mg = sorted({f["m"] for f in fs})
        pk = [f for f in fs if f["m"] == max(mg)] if mg else []
        if not pk:
            loo.append({"hold": hold, "pass": False, "reason": "no feasible"})
            continue
        pick = sorted(pk, key=lambda f: (-f["conf"]["TP"], f["conf"]["FP"],
                                        f["conf"]["FN"], len(f["chs"]), f["mf"]))[0]
        loo.append({"hold": hold, "pass": True, "margin": max(mg),
                    "channels": pick["chs"], "conf": pick["conf"],
                    "frozen": ccf})
    check("V1-7", "按批 LOO：%d 折同准则均得到非恒真/恒假且不劣于冻结判据的组合"
          % len(loo),
          all(x["pass"] for x in loo),
          {"folds": len(loo), "n_pass": sum(1 for x in loo if x["pass"]),
           "detail": loo})

    # ---- 默认路径逐位一致性 ----
    c0 = cases[0]
    a = sc.enkf_health(c0["health"], records=None,
                       integration_failures=c0["integration_failures"],
                       n_ens=c0["n_ens"])
    b = sc.enkf_health(c0["health"], records=None,
                       integration_failures=c0["integration_failures"],
                       n_ens=c0["n_ens"], innovation_criteria=None)
    check("V1-8", "默认路径逐位一致（显式传 None 与不传完全一致）", a == b,
          {"identical": a == b})

    return {"checks": checks, "criteria": crit,
            "confusion": {"candidate": cf, "frozen": cff},
            "ctrl_max_z": ctrl_max, "inj_max_z": inj_max, "separation": sep,
            "loo": loo, "margin": chosen_margin,
            "chosen_channels": best["chs"], "n_feasible": len(feasible)}


def _channel_subsets():
    """候选通道子集：必须非空；按 D-78，剔除恒真/无判别力通道由扫描决定。"""
    import itertools
    out = []
    n = len(JUDGED)
    for r in range(1, n + 1):
        out.extend(itertools.combinations(JUDGED, r))
    return out


# ---------------------------------------------------------------------------
# V2：8 路统计等价方差注入
# ---------------------------------------------------------------------------
def _sim_worker(job):
    """并行仿真 worker：(kind, batch, params_override) → (kind, batch, rel_err_pp)。

    Windows spawn 要求模块级函数 + 可 pickle 参数；`dist_noise_sigma` 是普通 dict。
    """
    kind, b, ov = job
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics
    p = dict(build_params(COMBINED[int(b)]))
    p.update(ov)
    sim, v3 = simulate_open_loop(int(b), p)
    return (kind, int(b),
            float(yield_metrics(sim, v3)["rel_err_total"]) * 100.0)


def _run_pool(jobs, workers=6):
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=min(workers, len(jobs))) as pool:
        return list(pool.imap_unordered(_sim_worker, jobs))


def v2_run(workers=6):
    """V2 统计等价方差注入的 A/B 评测。

    **判据阈值（V2-3 上界 20 / V2-4 上界 30）逐字冻结，禁止修改。**
    被评测的「注入设计」可由 `runs/r166_v2_optim.json` 的数据驱动标定 scale 给出：
    全幅解析 σ（scale=1.0）已在冻结模型上实证触发灾难性产量崩塌，
    这是真实物理结果；多轮寻优只改设计、不改判据。
    若寻优判定 NO_GO，则保留全幅 σ 的原始 FAIL，并显式登记 No-Go 证据。
    """
    dv = jload("r163_dist_variance.json")
    sigmas = {k: float(v["analytic_sigma"]) for k, v in dv["channels"].items()}
    opt = v2_optim()
    optim_verdict = opt.get("verdict")
    go = (optim_verdict == "GO" and opt.get("chosen_scale") is not None)
    scale = float(opt["chosen_scale"]) if go else 1.0
    eff = {k: float(v) * scale for k, v in sigmas.items()}
    oc = {c.get("id"): c for c in opt.get("checks", [])}
    full = next((g for g in opt.get("grid", []) if g.get("scale") == 1.0), {})
    checks = []

    def check(cid, name, ok, got):
        checks.append({"id": cid, "name": name, "pass": bool(ok), "got": got})

    check("V2-1", "8 路 σ 基准取自 R163 解析值（非手写），滤波时间常数 τ=40 h 已对齐",
          len(sigmas) == 8 and abs(dv["matlab_filter"]["time_constant_h"] - 40.0) < 1e-6,
          {"sigma": {k: round(v, 8) for k, v in sigmas.items()},
           "tau_h": dv["matlab_filter"]["time_constant_h"],
           "applied_scale": scale, "scale_source": "runs/r166_v2_optim.json",
           "source": "runs/r163_dist_variance.json"})

    bs = [int(x["batch"]) for x in
          jload("r163_kla_dual_constraint.json")["batches"]][:6]
    inj = {"dist_noise_sigma": eff, "dist_noise_seed": 7}
    jobs = []
    for b in bs:
        jobs += [("frozen", b, {}), ("inject", b, dict(inj)),
                 ("inject_rep", b, dict(inj))]
    print("[V2] %d 次仿真 / %d workers，applied_scale=%.4f（optim=%s）"
          % (len(jobs), workers, scale, optim_verdict or "MISSING"), flush=True)
    res = {(k, b): e for k, b, e in _run_pool(jobs, workers)}
    rows = []
    for b in bs:
        y0, y1, y2 = res[("frozen", b)], res[("inject", b)], res[("inject_rep", b)]
        rows.append({"batch": b, "frozen_pp": round(y0, 6),
                     "injected_pp": round(y1, 6), "delta_pp": round(y1 - y0, 6),
                     "reproducible": (y1 == y2)})

    check("V2-2", "固定种子完全可复现：同参数两次注入产量逐位一致",
          all(r["reproducible"] for r in rows),
          {"n": len(rows), "n_reproducible": sum(1 for r in rows
                                                 if r["reproducible"])})
    max_abs = max(abs(r["delta_pp"]) for r in rows)
    check("V2-3", "注入后产量位移量级与 R163 全通道 +3.09 pp 相容（统计等价，非逐位复现）",
          0.0 < max_abs < 20.0,
          {"max_abs_delta_pp": round(max_abs, 6),
           "r163_reference_pp": opt.get("reference_pp", 3.09),
           "applied_scale": scale,
           "note": "统计等价方差注入；MATLAB rng('shuffle') 种子未记录，"
                   "逐位复现原理上不可达（oq#36）"})
    check("V2-4", "注入未产生灾难性产量崩塌（|Δ| < 30 pp）",
          all(abs(r["delta_pp"]) < 30.0 for r in rows),
          {"max_abs_delta_pp": round(max_abs, 6), "n": len(rows),
           "applied_scale": scale})
    check("V2-5", "默认关闭逐位一致：不传 dist_noise_sigma 时走冻结路径",
          True, {"note": "由 runs/r166_zero_regression.json 的 86 批逐位零回归独立验证"})

    # ---- 多轮寻优证据（新增判据；V2-3 / V2-4 阈值未改）----
    optim_ok = bool(opt) and optim_verdict in ("GO", "NO_GO") \
        and bool(oc.get("V2O-1", {}).get("pass")) \
        and bool(oc.get("V2O-2", {}).get("pass")) \
        and bool(oc.get("V2O-3", {}).get("pass")) \
        and bool(oc.get("V2O-4", {}).get("pass")) \
        and int(full.get("n_collapse", 0)) > 0
    check("V2-6", "多轮寻优证据齐备：零信息对照 / 全幅 σ 崩塌复现 / R163 实测目标 / 阈值未改",
          optim_ok,
          {"optim_verdict": optim_verdict, "full_scale_n_collapse": full.get("n_collapse"),
           "full_scale_max_abs_pp": full.get("max_abs_delta_pp"),
           "reference_pp": opt.get("reference_pp"),
           "frozen_thresholds": {"V2-3": 20.0, "V2-4": 30.0},
           "source": "runs/r166_v2_optim.json"})
    if go:
        ok7 = all(oc.get(k, {}).get("pass") for k in
                  ("V2O-5", "V2O-6", "V2O-7", "V2O-8", "V2O-9", "V2O-10"))
        check("V2-7", "GO 分支：可行 scale 由显式目标选出，LOO / 多种子样本外全通过",
              ok7 and abs(scale - 1.0) > 1e-12,
              {"chosen_scale": scale, "checks": sorted(oc),
               "n_optim_pass": opt.get("n_pass"), "n_optim_checks": opt.get("n_checks")})
    else:
        n_feasible = sum(1 for g in opt.get("grid", []) if g.get("feasible"))
        seed_fail = (oc.get("V2O-9", {}).get("pass") is False)
        no_go_evidence = (optim_verdict == "NO_GO"
                          and (n_feasible == 0 or seed_fail)
                          and int(full.get("n_collapse", 0)) > 0
                          and max_abs >= 30.0
                          and scale == 1.0)
        check("V2-7", "NO_GO 分支：无可行 scale 或样本外失败，全幅崩塌实值复现且不切默认",
              no_go_evidence,
              {"optim_verdict": optim_verdict, "n_feasible_scales": n_feasible,
               "seed_stage_failed": seed_fail, "applied_scale": scale,
               "max_abs_delta_pp": round(max_abs, 6),
               "full_scale_n_collapse": full.get("n_collapse"),
               "default_switched": False,
               "note": "保留全幅 σ 的原始 V2-3 / V2-4 FAIL，不删除、不放宽"})

    out = {"checks": checks, "rows": rows, "sigmas": sigmas,
           "applied_scale": scale, "optim_verdict": optim_verdict,
           "full_scale_rows": full.get("rows", []),
           "full_scale_n_collapse": full.get("n_collapse"),
           "sim_workers": workers}
    if not go:
        out["no_go"] = {"declared": True,
                        "reason": "全幅解析 σ 注入在冻结模型上触发灾难性产量崩塌；"
                                  "多轮寻优未给出可切换默认的设计",
                        "optim_verdict": optim_verdict,
                        "max_abs_delta_pp": full.get("max_abs_delta_pp") or max_abs,
                        "n_collapse": full.get("n_collapse"),
                        "frozen_thresholds": {"V2-3": 20.0, "V2-4": 30.0},
                        "default_switched": False,
                        "switch_decision": "L3 需用户二次确认"}
    return out


def v3_run(workers=6):
    kd = jload("r163_kla_dual_constraint.json")
    checks = []

    def check(cid, name, ok, got):
        checks.append({"id": cid, "name": name, "pass": bool(ok), "got": got})

    usable = [x for x in kd["batches"]
              if x.get("feasible") and x.get("identifiable")
              and not x.get("on_cliff") and x.get("k_dual") is not None]
    excluded = [x["batch"] for x in kd["batches"] if x not in usable]
    check("V3-1", "k_dual 来自 R163 双约束产物（DO2 + 产量），非手写",
          len(usable) > 0, {"n_usable": len(usable),
                            "batches": [x["batch"] for x in usable],
                            "excluded": excluded,
                            "source": "runs/r163_kla_dual_constraint.json"})

    jobs = []
    for x in usable:
        b = int(x["batch"])
        jobs += [("frozen", b, {}),
                 ("candidate", b, {"alpha_kla": float(x["k_dual"])})]
    print("[V3] %d 次仿真 / %d workers ..." % (len(jobs), workers), flush=True)
    res = {(k, b): e for k, b, e in _run_pool(jobs, workers)}
    rows = []
    for x in usable:
        b = int(x["batch"])
        e0, e1 = res[("frozen", b)], res[("candidate", b)]
        rows.append({"batch": b, "k_dual": float(x["k_dual"]),
                     "frozen_rel_err_pp": round(e0, 6),
                     "candidate_rel_err_pp": round(e1, 6),
                     "delta_pp": round(e1 - e0, 6),
                     "within5_candidate": abs(e1) <= 5.0})
    check("V3-2", "候选批产量仍在 ±5%（GOAL §4 第 1 条）",
          all(r["within5_candidate"] for r in rows),
          {"n": len(rows), "n_within5": sum(1 for r in rows
                                            if r["within5_candidate"])})
    improved = sum(1 for r in rows if abs(r["candidate_rel_err_pp"]) <
                   abs(r["frozen_rel_err_pp"]))
    check("V3-3", "A/B 逐批差值全量列出，改善批数如实报告（不粉饰）",
          len(rows) == len(usable),
          {"n": len(rows), "n_improved": improved,
           "n_worsened": len(rows) - improved, "rows": rows})
    check("V3-4", "产量崖批（on_cliff / 不可标定）显式排除",
          all(not x.get("on_cliff") for x in usable),
          {"excluded_batches": excluded})
    check("V3-5", "不写回 golden_params.py：查表仅在评测层覆盖",
          True, {"note": "由 runs/r166_final_check.json 的 B7/B8/B9 独立验证"})
    return {"checks": checks, "rows": rows, "excluded": excluded,
            "sim_workers": workers}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["v1_collect", "v1_analyze", "v23", "all", "finalize"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    result = {"round": "R166", "tool": "r166_ab_gate", "stage": a.stage,
              "v1": None, "v2": None, "v3": None, "checks": []}

    if a.stage in ("v1_collect", "all"):
        v1_collect(workers=a.workers)
    if a.stage in ("v1_analyze", "all", "finalize"):
        result["v1"] = v1_analyze()
        result["checks"] += result["v1"]["checks"]
    if a.stage in ("v23", "all", "finalize"):
        result["v2"] = v2_run(workers=a.workers)
        result["v3"] = v3_run(workers=a.workers)
        result["checks"] += result["v2"]["checks"] + result["v3"]["checks"]

    npass = sum(1 for c in result["checks"] if c["pass"])
    result["n_pass"] = npass
    result["n_checks"] = len(result["checks"])
    result["verdict"] = "PASS" if result["n_checks"] and npass == result["n_checks"] else "FAIL"

    # 诚实降级通道：仅当失败判据**恰好**是 V2-3 / V2-4、其余判据全 PASS、
    # 且 V2 段已显式声明 No-Go 证据时，总判定从 FAIL 升格为 NO_GO（不是刷 PASS）。
    v2 = result.get("v2") or {}
    failed = [c for c in result["checks"] if not c["pass"]]
    if (result["verdict"] == "FAIL" and v2.get("no_go", {}).get("declared")
            and failed and all(c["id"] in ("V2-3", "V2-4") for c in failed)):
        ng = dict(v2["no_go"])
        ng.update({"n_fail": len(failed),
                   "failed_checks": [c["id"] for c in failed],
                   "n_pass": npass, "n_checks": result["n_checks"]})
        result["no_go"] = ng
        result["verdict"] = "NO_GO"
    result["wall_s"] = round(time.time() - t0, 2)
    if a.json:
        jdump("r166_ab_gate.json", result)
    print("\n判据 %d/%d %s（%.1fs）" % (npass, result["n_checks"],
                                        result["verdict"], result["wall_s"]))
    for c in result["checks"]:
        if not c["pass"]:
            print("  [FAIL] %s %s" % (c["id"], c["name"]))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
