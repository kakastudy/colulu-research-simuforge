# -*- coding: utf-8 -*-
"""R152 / D-42：产素门控三个旋钮的可用性判定。

前置结论（`tools/r152_gate_probe.py`）
-------------------------------------
`P_inhib = 2.5/sqrt(2π)·exp(−0.5·((s−mean_P)/P_std_dev)²)`，`mean_P=0.002 g/L`、**`P_std_dev=1.5e−3 g/L`（1.5 mg/L）**。60–120 h 实测 S 中位 0.0010、模型 0.0014，
两者差 0.4 mg/L —— 是门控宽度的 0.27 倍 ⇒ 门控**不会**被这点差翻转，产素差距另有来源。

本工具要回答的**唯一问题**
------------------------
有没有一个旋钮，能**只抬 60–120 h、不抬 120–180 h**？
（120–180 h 当前已经是 +0.02，抬它是净损失；这是 R150「一阶旋钮改不动二阶形状」的判据。）

臂
--
`base` / `meanP{1.25,1.5,2.0}` / `sd{2,5,10}` / `pcritPAA{0.5,2}`。
- `mean_P` 平移门控中心：把窗口挪到模型 S 的众数附近。
- `P_std_dev` 放宽门控：从"硬开关"变成"宽窗"，降低对 S 误差的敏感度，但**所有相位一起抬**。
- `P_crit_PAA` 验证 PAA 门控确实饱和（若 ×0.5 与 ×2 无差异 ⇒ tanh 已饱和，可从嫌疑人名单删除）。

**`base` 臂含口径闸门**：其 P relRMSE / 峰比 / 末比 / 产量必须与 `runs/r151_shape_baseline.json` 逐位相同
（`max|Δ|=0`），否则说明覆盖口泄漏到默认路径。

用法
----
    python tools/r152_gate_scan.py                      # 6 批（默认）
    python tools/r152_gate_scan.py --batches 3,22,36,55,59,50 --workers 6
    python tools/r152_gate_scan.py --all86              # 86 批 × 9 臂（约 90 min，慎用）
"""
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
DEFAULT_BATCHES = (3, 22, 36, 55, 59, 50)   # 覆盖"主体批"与 2 个 invalid 批


def arms_for(base_mean_P, base_sd, base_pcrit):
    """臂集：门控三旋钮 + 降解通道（mu_h）。

    R152 §1 已用 `r152_gate_probe.py` 排除门控：60–120 h 的 `P_inhib` 模型 0.862 vs
    "若糖取实测值" 0.848 —— **门控开得比实测糖对应的还大**，不是缺产素的原因。
    剩 `dP/dt = r_p − (mu_h + k_deg + D)·P` 里的降解项。水解不耗糖 ⇒ 可以同时满足
    「S 对（+0.4%）而 P 低 22%」，这是唯一与 R150 实测兼容的通道。
    """
    return [
        ("base", {}),
        ("mu_h0.95", {"mu_h_scale": 0.95}),
        ("mu_h0.90", {"mu_h_scale": 0.90}),
        ("mu_h0.80", {"mu_h_scale": 0.80}),
        ("meanP1.25", {"mean_P": base_mean_P * 1.25}),
        ("meanP1.50", {"mean_P": base_mean_P * 1.50}),
        ("sd2", {"P_std_dev": base_sd * 2.0}),
        ("sd5", {"P_std_dev": base_sd * 5.0}),
        ("pcritPAA2", {"P_crit_PAA": base_pcrit * 2.0}),
    ]


def one(job):
    batch, arms, bases = job
    from golden_params import COMBINED, build_params
    import simulate as s

    out = []
    for name, ov in arms:
        p = dict(build_params(COMBINED[batch]))
        p.update(ov)
        sim, v3 = s.simulate_open_loop(int(batch), p)
        ym = s.yield_metrics(sim, v3)
        sm = s.shape_metrics(sim, v3, channels=("P",))["P"]
        va = s.validity(sim)
        out.append({
            "arm": name,
            "p_relrmse": sm["rel_rmse"],
            "p_r2": sm["r2"],
            "peak_ratio": sm["peak_ratio"],
            "end_ratio": sm["end_ratio"],
            "phase": {k: sm["phase"][k]["mean"] for k in PHASE_KEYS},
            "yield_err": float(ym["rel_err_total"]),
            "valid": bool(va["valid"]),
        })
    return {"batch": int(batch), "base": bases, "arms": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--all86", action="store_true")
    args = ap.parse_args()

    from params import make_params
    par = make_params()
    base_mean_P, base_sd, base_pcrit = float(par[4]), float(par[3]), float(par[79])
    arms = arms_for(base_mean_P, base_sd, base_pcrit)

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    elif args.all86:
        d = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8"))
        bs = sorted({int(r["batch"]) for r in (d.get("rows") or []) if "batch" in r})
    else:
        bs = list(DEFAULT_BATCHES)

    bases = {"mean_P": base_mean_P, "P_std_dev": base_sd, "P_crit_PAA": base_pcrit}
    print(f"[r152] batches={len(bs)}  arms={len(arms)}  base: mean_P={base_mean_P:g} "
          f"P_std_dev={base_sd:g} P_crit_PAA={base_pcrit:g}", flush=True)

    jobs = [(b, arms, bases) for b in bs]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, jobs))

    # ---- 口径闸门：base 臂必须与 R151 基线逐位一致 ----
    gate_path = os.path.join(ROOT, "runs", "r151_shape_baseline.json")
    gate = "skipped"
    if os.path.exists(gate_path):
        ref = {r["batch"]: r for r in json.load(open(gate_path, encoding="utf-8"))["rows"]}
        worst = 0.0
        for r in rows:
            b = r["batch"]
            if b not in ref:
                continue
            base_arm = r["arms"][0]
            for k_new, k_ref in (("p_relrmse", "p_relrmse"), ("peak_ratio", "p_peak_ratio"),
                                 ("end_ratio", "p_end_ratio"), ("yield_err", "yield_err")):
                worst = max(worst, abs(base_arm[k_new] - ref[b][k_ref]))
        gate = "PASS" if worst == 0.0 else f"FAIL(max|Δ|={worst:.3e})"
        print(f"口径闸门（base 臂 vs r151 基线）：{gate}", flush=True)

    # ---- 汇总：跨批均值 ----
    def agg(arm_name, key):
        vs = []
        for r in rows:
            for a in r["arms"]:
                if a["arm"] == arm_name:
                    vs.append(a[key])
        return float(np.mean(vs))

    def agg_phase(arm_name, ph):
        vs = []
        for r in rows:
            for a in r["arms"]:
                if a["arm"] == arm_name:
                    vs.append(a["phase"][ph])
        return float(np.mean(vs))

    summary = {"batches": bs, "n": len(bs), "base": bases, "gate": gate, "arms": {}}
    print(f"\n=== 跨批均值（{len(bs)} 批）===")
    hdr = f"{'arm':12s} {'relRMSE':>8s} {'峰比':>6s} {'末比':>6s} " + \
          " ".join(f"{k:>8s}" for k in PHASE_KEYS) + f" {'产量%':>7s}"
    print(hdr)
    for name, _ in arms:
        rec = {"p_relrmse": agg(name, "p_relrmse"), "peak_ratio": agg(name, "peak_ratio"),
               "end_ratio": agg(name, "end_ratio"), "yield_err": agg(name, "yield_err"),
               "phase": {k: agg_phase(name, k) for k in PHASE_KEYS},
               "n_valid": int(sum(1 for r in rows for a in r["arms"]
                                  if a["arm"] == name and a["valid"]))}
        summary["arms"][name] = rec
        print(f"{name:12s} {rec['p_relrmse']:8.4f} {rec['peak_ratio']:6.3f} {rec['end_ratio']:6.3f} " +
              " ".join(f"{rec['phase'][k]:+8.4f}" for k in PHASE_KEYS) +
              f" {rec['yield_err'] * 100:+7.2f}")

    b = summary["arms"]["base"]
    print("\n=== 相对 base 的变化（相位 60-120 与 120-180 是关键）===")
    print(f"{'arm':12s} {'d(60-120)':>10s} {'d(120-180)':>11s} {'d(0-60)':>9s} {'d(产量%)':>9s} {'选择性':>8s}")
    for name, _ in arms[1:]:
        a = summary["arms"][name]
        d1 = a["phase"]["60-120"] - b["phase"]["60-120"]
        d2 = a["phase"]["120-180"] - b["phase"]["120-180"]
        d0 = a["phase"]["0-60"] - b["phase"]["0-60"]
        dy = (a["yield_err"] - b["yield_err"]) * 100
        sel = d1 / abs(d2) if abs(d2) > 1e-6 else float("inf")
        print(f"{name:12s} {d1:+10.4f} {d2:+11.4f} {d0:+9.4f} {dy:+9.2f} {sel:8.2f}")

    print("\n读法：**想要的臂是 d(60-120) > 0 且 d(120-180) <= 0.01**（选择性 > 1.5）；"
          "\n      若所有臂的 d(60-120) 与 d(120-180) 同号同量级 ⇒ 三个旋钮都不是形状旋钮。")

    op = os.path.join(ROOT, "runs", "r152_gate_scan.json")
    json.dump({"summary": summary, "rows": rows}, open(op, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
