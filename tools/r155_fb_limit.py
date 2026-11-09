# -*- coding: utf-8 -*-
"""R155 / D-41 L1：pH 高位停碱（`fb_limit`）的效果与代价。

背景
----
R149 判定：pH 越 7 不可逆的根因是**回放的 Fb 没有限幅** —— 记录值是控制器对实测
pH 6.50 的输出，模型的 pH 已经偏离时它照加不误。D-41 登记了三条候选装置（L1 停碱 /
L2 线性回撤 / L3 反解维持 6.5），全部 opt-in、默认关闭。

本轮先验 L1：`fb_limit={"ph_stop":6.90,"mode":"step"|"linear","width":0.2}`。
判据不是"能不能修好 pH"，而是三件事：
  1. 钳位批（clamp）能否清零 —— 有效域能否打开
  2. 越 7 是否消失 —— pH_max_pre 是否降到 7.0 以下
  3. 产量是否保住 —— R147 已证明 b37 的产量标定**依赖钳位期多水解**（prod_only 下 +64pt），
     若 L1 也让产量同向暴涨，则 L1 与 D-36 同型：它是标定的支撑结构，不可单独拆

用法
----
    python tools/r155_fb_limit.py --batches 37,50,51,91,92,40,43,49,54,3,22,55
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

CFGS = {
    # 主臂：pH≥6.90 直接停碱
    "step690": {"ph_stop": 6.90, "mode": "step"},
    # 次臂：从 6.90 起按 (6.90−pH)/0.2 线性回撤（到 6.70 完全停）
    "lin690": {"ph_stop": 6.90, "mode": "linear", "width": 0.20},
    # 零效应对照：ph_stop=15 ⇒ g≡1（用来证明本装置在"不触发"时不动数值）
    "off": {"ph_stop": 15.0, "mode": "step"},
}


def one(job):
    batch, cfgs = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        bp = dict(build_params(COMBINED[batch]))
        sim0, v30 = s.simulate_open_loop(int(batch), bp)
        ym0 = s.yield_metrics(sim0, v30)
        sm0 = s.shape_metrics(sim0, v30, channels=("P",))["P"]
        h0 = s.classify_health(sim0, v30, yield_err=ym0["rel_err_total"])
        base = {"yield_err": float(ym0["rel_err_total"]),
                "p_relrmse": float(sm0["rel_rmse"]),
                "phase": {k: float(sm0["phase"][k]["mean"]) for k in PHASE_KEYS},
                "valid": bool(s.validity(sim0)["valid"]),
                "ph_max": float(h0["ph_max_pre"]), "n_clamp": int(h0["n_ph_clamp"]),
                "health": h0["level"], "p_drop_rel": float(h0["p_drop_rel"]),
                "a0": {c: sim0[c].to_numpy(float) for c in sim0.columns}}
        arms = []
        for name in cfgs:
            p1 = dict(bp)
            p1["fb_limit"] = CFGS[name]
            sim1, v31 = s.simulate_open_loop(int(batch), p1)
            ym = s.yield_metrics(sim1, v31)
            sm = s.shape_metrics(sim1, v31, channels=("P",))["P"]
            h1 = s.classify_health(sim1, v31, yield_err=ym["rel_err_total"])
            a = {"arm": name, "yield_err": float(ym["rel_err_total"]),
                 "p_relrmse": float(sm["rel_rmse"]),
                 "phase": {k: float(sm["phase"][k]["mean"]) for k in PHASE_KEYS},
                 "valid": bool(s.validity(sim1)["valid"]),
                 "ph_max": float(h1["ph_max_pre"]), "n_clamp": int(h1["n_ph_clamp"]),
                 "health": h1["level"], "p_drop_rel": float(h1["p_drop_rel"]),
                 "max_abs_delta": float(np.max([np.max(np.abs(sim1[c].to_numpy(float) - base["a0"][c]))
                                                for c in sim1.columns if c in base["a0"]
                                                and len(base["a0"][c]) == len(sim1[c])])),
                 "cols_diff": sorted(set(sim1.columns) ^ set(base["a0"]))}
            arms.append(a)
        base.pop("a0")
        return {"batch": int(batch), "base": base, "arms": arms}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-600:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str,
                    default="37,50,51,91,92,40,43,49,54,3,22,55")
    ap.add_argument("--configs", type=str, default="step690,lin690,off")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r155_fb_limit.json")
    args = ap.parse_args()

    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    cfgs = [x.strip() for x in args.configs.split(",") if x.strip()]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, [(b, cfgs) for b in bs]))
    for r in rows:
        print("done", r.get("batch"), r.get("error", ""), flush=True)

    ok = [r for r in rows if "error" not in r]
    print(f"\n=== D-41 L1（{len(ok)} 批）===")
    print(f"{'':9s}{'钳位批':>7s}{'越7批':>6s}{'valid':>6s}{'yield中位':>10s}{'yield最差':>10s}{'|Δ|产量中位':>11s}")
    b = ok
    print(f"{'base':9s}{sum(1 for r in b if r['base']['n_clamp'] > 0):7d}"
          f"{sum(1 for r in b if np.isfinite(r['base']['ph_max']) and r['base']['ph_max'] >= 7.0):6d}"
          f"{sum(1 for r in b if r['base']['valid']):6d}"
          f"{np.median([r['base']['yield_err'] for r in b])*100:10.2f}"
          f"{min(r['base']['yield_err'] for r in b)*100:10.2f}{0:11.2f}")
    for name in cfgs:
        pairs = [(r, a) for r in ok for a in r["arms"] if a["arm"] == name]
        if not pairs:
            continue
        dy = np.array([abs(a["yield_err"] - r["base"]["yield_err"]) for r, a in pairs], float)
        print(f"{name:9s}{sum(1 for _, a in pairs if a['n_clamp'] > 0):7d}"
              f"{sum(1 for _, a in pairs if np.isfinite(a['ph_max']) and a['ph_max'] >= 7.0):6d}"
              f"{sum(1 for _, a in pairs if a['valid']):6d}"
              f"{np.median([a['yield_err'] for _, a in pairs])*100:10.2f}"
              f"{min(a['yield_err'] for _, a in pairs)*100:10.2f}{np.median(dy)*100:11.2f}")

    print("\n逐批（yield% / ph_max / clamp）:")
    for r in ok:
        line = f"  b{r['batch']:<4d} base {r['base']['yield_err']*100:7.2f} {r['base']['ph_max']:6.3f} {r['base']['n_clamp']:4d}"
        for a in r["arms"]:
            line += f" | {a['arm']} {a['yield_err']*100:7.2f} {a['ph_max']:6.3f} {a['n_clamp']:4d}"
        print(line)

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.json)), exist_ok=True)
    json.dump({"configs": CFGS, "rows": rows},
              open(os.path.join(ROOT, args.json), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n->", args.json)


if __name__ == "__main__":
    main()
