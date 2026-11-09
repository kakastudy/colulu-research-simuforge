# -*- coding: utf-8 -*-
"""R133 冒烟：确认 vis_out_scale 只改上报列、不改产量路径。

检查项：
  1. build_params 带出 vis_out_scale；
  2. sim 同时有 vis（化验口径）与 vis_state（ODE 状态），比值 == scale；
  3. yield_err 与冻结基线（runs/final_validation_v2_R131_FROZEN.json）逐批一致；
  4. 关闭 vis_out_scale 时 vis == vis_state（默认行为未变）。

用法：python tools/r133_smoke.py [batches]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, build_params  # noqa: E402
from simulate import simulate_open_loop, yield_metrics  # noqa: E402


def frozen(b):
    p = os.path.join(ROOT, "runs", "final_validation_v2_R131_FROZEN.json")
    d = json.load(open(p, encoding="utf-8"))
    rows = d["results"] if isinstance(d, dict) and "results" in d else d
    return next(r for r in rows if int(r["batch"]) == b)


def main(argv):
    batches = [int(x) for x in (argv[1] if len(argv) > 1 else "8,3,11").split(",")]
    ok = True
    for b in batches:
        v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                      f"batch_{b:02d}.csv"))
        cp = COMBINED[b]
        scale = cp.get("vis_out_scale", 1.0)
        p = build_params(cp)
        sim, _ = simulate_open_loop(b, p)
        ym = yield_metrics(sim, v3)
        ref = frozen(b)
        dy = abs(ym["rel_err_total"] - ref["yield_err"])
        has_state = "vis_state" in sim.columns
        ratio = (float(sim["vis"].iloc[-1]) / float(sim["vis_state"].iloc[-1])
                 if has_state else 1.0)
        # 关闭标度：走默认路径
        p0 = dict(p)
        p0.pop("vis_out_scale", None)
        sim0, _ = simulate_open_loop(b, p0)
        ym0 = yield_metrics(sim0, v3)
        same = np.allclose(sim["vis"].to_numpy() / max(scale, 1e-12),
                           sim0["vis"].to_numpy(), rtol=1e-9, atol=1e-9)
        ok_b = (dy < 1e-12) and abs(ym0["rel_err_total"] - ref["yield_err"]) < 1e-12 \
            and (not has_state or abs(ratio / scale - 1) < 1e-9) and same
        ok = ok and ok_b
        print(f"b{b:>3} scale={scale:.4f} yield_err(sim)={ym['rel_err_total']*100:+.4f}pt "
              f"frozen={ref['yield_err']*100:+.4f}pt |Δ|={dy*100:.2e} "
              f"ratio={ratio:.4f} vis_state={'Y' if has_state else 'N'} "
              f"scaled==raw*scale:{same}  => {'OK' if ok_b else 'FAIL'}")
    print("ALL OK" if ok else "HAS FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
