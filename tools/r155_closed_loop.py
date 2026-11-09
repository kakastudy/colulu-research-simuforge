# -*- coding: utf-8 -*-
"""R155 / D-54：葡萄糖补料闭环（opt-in）pilot。

目的
----
R154 的判决是：P 形状误差 = 门控占空误差（corr −0.92），而门控的自变量残糖是
"1.0 g/L/h 收支的 0.002 g/L 残差"，开环回放 recipe 剖面时无法把它修对（D-53）。
本工具检验唯一剩下的路径：**给 Fs 加反馈**（D-54），即把模型从
"I/O 回放器"变成"带葡萄糖控制器的仿真器"。

判据（pilot 阶段）
------------------
1. 门控占空是否从 ~0.13 抬到实测的 0.60（0–60 h）
2. P 的 0–60 相位是否从 −0.034 向 0 靠
3. 产量 `yield_err` 是否还在 ±5%（闭环必然改总进料，产量变了是预期的）
4. valid 不得下降

用法
----
    python tools/r155_closed_loop.py --batches 3,22,55 --configs pi_a,pi_gate
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

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")
SP = 0.002      # 门控中心 = 葡萄糖设定值 2 mg/L（g/L）
SD = 0.0015     # 门控半宽（par[3]）

# 闭环配置：u = clip(1 - w*(kp*e + ki*I), u_lo, u_hi)，e = (S-SP)/scale，w = 1/(1+(S/s_act)^2)
CONFIGS = {
    # 全域比例反馈：S 一偏离就改进料，最激进
    "pi_a":    {"sp": SP, "scale": SP, "kp": 0.10, "ki": 0.0, "u_lo": 0.0, "u_hi": 2.0},
    # 全域 PI：靠积分项吃掉稳态偏差
    "pi_b":    {"sp": SP, "scale": SP, "kp": 0.10, "ki": 0.02, "u_lo": 0.0, "u_hi": 2.0},
    # 门控邻域闭环：只在 S < ~50 mg/L 时起作用，保留初始糖峰的形状（不动回放前半段）
    "pi_gate": {"sp": SP, "scale": SP, "kp": 0.30, "ki": 0.0, "u_lo": 0.0, "u_hi": 2.0, "s_act": 0.05},
    # 门控邻域 PI
    "pi_gp":   {"sp": SP, "scale": SP, "kp": 0.20, "ki": 0.02, "u_lo": 0.0, "u_hi": 2.0, "s_act": 0.05},
    # ---- 第二轮：定点干预 + 温和增益（第一轮全域配置在 80 h 撞 pH 3.000 钳位）----
    # 只在 0–60 h 起作用，之后完全回放 ⇒ 不动后段产酸/产碱平衡
    "pi_w60":  {"sp": SP, "scale": SP, "kp": 0.30, "ki": 0.0, "u_lo": 0.0, "u_hi": 1.5,
                "s_act": 0.05, "t_off": 60.0},
    # 同上但限幅收紧（不允许完全断料，记录剖面最小 8 L/h）
    "pi_w60m": {"sp": SP, "scale": SP, "kp": 0.10, "ki": 0.0, "u_lo": 0.5, "u_hi": 1.5,
                "s_act": 0.05, "t_off": 60.0},
    # 只动生长期（0–45 h），把门控启动点提前
    "pi_w45":  {"sp": SP, "scale": SP, "kp": 0.20, "ki": 0.0, "u_lo": 0.3, "u_hi": 1.5,
                "s_act": 0.05, "t_off": 45.0},
    # 覆盖整个产素期但用小增益
    "pi_w120m": {"sp": SP, "scale": SP, "kp": 0.06, "ki": 0.0, "u_lo": 0.6, "u_hi": 1.4,
                 "s_act": 0.0, "t_off": 120.0},
}


def gate_of(s_gL):
    """P_inhib 的归一化门控值（与 model.py 同式）。"""
    s = np.asarray(s_gL, float)
    return 2.5 * np.exp(-0.5 * ((s - SP) / SD) ** 2) / np.sqrt(2.0 * np.pi)


def duty(sim_s, v3, t0, t1, thr=0.5):
    """窗口内实测/模型 S 对应门控 > thr 的时间占比（按 time_h 插值对齐）。"""
    t = np.arange(t0, t1 + 1e-9, 0.5)
    tm = np.asarray(v3["time_h"], float)
    sm_m = np.interp(t, tm, np.asarray(v3["S"], float))
    ts = np.asarray(sim_s["time_h"], float)
    sm_s = np.interp(t, ts, np.asarray(sim_s["S"], float))
    return float(np.mean(gate_of(sm_m) > thr)), float(np.mean(gate_of(sm_s) > thr))


def metrics(sim, v3):
    import simulate as s
    ym = s.yield_metrics(sim, v3)
    sm = s.shape_metrics(sim, v3, channels=("P",))["P"]
    va = s.validity(sim)
    d_m, d_s = duty(sim, v3, 0.0, 60.0)
    d_m2, d_s2 = duty(sim, v3, 60.0, 120.0)
    t = np.asarray(sim["time_h"], float)
    sres = float(np.median(np.interp(np.arange(30, 121, 1.0), t, np.asarray(sim["S"], float))))
    fs = np.asarray(sim["Fs"], float)
    fs_used = np.asarray(sim["Fs_ctl"], float) if "Fs_ctl" in sim else fs
    return {
        "yield_err": float(ym["rel_err_total"]),
        "p_relrmse": float(sm["rel_rmse"]),
        "peak_ratio": float(sm["peak_ratio"]),
        "end_ratio": float(sm["end_ratio"]),
        "phase": {k: float(sm["phase"][k]["mean"]) for k in PHASE_KEYS},
        "valid": bool(va["valid"]),
        "flags": list(va["flags"]),
        "duty_meas_0_60": d_m, "duty_sim_0_60": d_s,
        "duty_meas_60_120": d_m2, "duty_sim_60_120": d_s2,
        "s_resid_sim": sres,
        "fs_total_rec": float(np.trapz(fs, t)),
        "fs_total_used": float(np.trapz(fs_used, t)),
    }


def one(job):
    batch, cfgs = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        bp = dict(build_params(COMBINED[batch]))
        sim0, v30 = s.simulate_open_loop(int(batch), bp)
        base = metrics(sim0, v30)
        rec = {"batch": int(batch), "base": base, "arms": []}
        for name in cfgs:
            p1 = dict(bp)
            p1["fs_ctl"] = CONFIGS[name]
            sim1, v31 = s.simulate_open_loop(int(batch), p1)
            m1 = metrics(sim1, v31)
            m1["arm"] = name
            rec["arms"].append(m1)
        return rec
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-800:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="3,22,55,59,60,36")
    ap.add_argument("--configs", type=str, default="pi_a,pi_gate")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r155_closed_loop_pilot.json")
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",") if x.strip()]
    cfgs = [x.strip() for x in args.configs.split(",") if x.strip()]
    jobs = [(b, cfgs) for b in batches]
    out = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(one, jobs):
                out.append(r)
                print("done", r.get("batch"), r.get("error", ""), flush=True)
    else:
        for j in jobs:
            r = one(j)
            out.append(r)
            print("done", r.get("batch"), r.get("error", ""), flush=True)

    ok = [r for r in out if "error" not in r]
    print("\n=== 汇总（%d 批）===" % len(ok))
    hdr = f"{'':10s}{'yield':>9s}{'p_rrmse':>9s}{'ph0-60':>9s}{'ph60-120':>10s}{'duty0-60':>9s}{'duty_s':>8s}{'valid':>6s}{'fs比':>7s}"
    print(hdr)
    if ok:
        b = ok
        print(f"{'base':10s}"
              f"{np.median([r['base']['yield_err'] for r in b])*100:9.2f}"
              f"{np.median([r['base']['p_relrmse'] for r in b]):9.4f}"
              f"{np.mean([r['base']['phase']['0-60'] for r in b]):9.4f}"
              f"{np.mean([r['base']['phase']['60-120'] for r in b]):10.4f}"
              f"{np.mean([r['base']['duty_sim_0_60'] for r in b]):9.3f}"
              f"{np.mean([r['base']['duty_sim_0_60'] for r in b]):8.3f}"
              f"{sum(r['base']['valid'] for r in b):6d}"
              f"{1.0:7.3f}")
    for name in cfgs:
        rows = [(r, a) for r in ok for a in r["arms"] if a["arm"] == name]
        if not rows:
            continue
        y = np.array([a["yield_err"] for _, a in rows], float)
        pr = np.array([a["p_relrmse"] for _, a in rows], float)
        p0 = np.array([a["phase"]["0-60"] for _, a in rows], float)
        p6 = np.array([a["phase"]["60-120"] for _, a in rows], float)
        du = np.array([a["duty_sim_0_60"] for _, a in rows], float)
        rt = np.array([a["fs_total_used"] / max(a["fs_total_rec"], 1e-9) for _, a in rows], float)
        print(f"{name:10s}{np.median(y)*100:9.2f}{np.median(pr):9.4f}{np.mean(p0):9.4f}"
              f"{np.mean(p6):10.4f}{np.mean(du):9.3f}{np.mean(du):8.3f}"
              f"{sum(1 for _, a in rows if a['valid']):6d}{np.median(rt):7.3f}")
    print(f"{'meas':10s}{'':9s}{'':9s}{'':9s}{'':10s}"
          f"{np.mean([r['base']['duty_meas_0_60'] for r in ok]):9.3f}")

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.json)), exist_ok=True)
    with open(os.path.join(ROOT, args.json), "w", encoding="utf-8") as f:
        json.dump({"configs": CONFIGS, "batches": batches, "rows": out}, f, indent=1)
    print("\n->", args.json)


if __name__ == "__main__":
    main()
