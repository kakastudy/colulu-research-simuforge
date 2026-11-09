# -*- coding: utf-8 -*-
"""逐批黏度剖面打印（诊断用）：obs / sim / ratio，按化验时刻对齐。

用法: python tools/r133_vis_profile.py 3,29,33
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, build_params  # noqa: E402
from simulate import simulate_open_loop  # noqa: E402


def main(argv):
    batches = [int(x) for x in (argv[1] if len(argv) > 1 else "3").split(",")]
    for b in batches:
        v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                      f"batch_{b:02d}.csv"))
        sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))
        t = v3["time_h"].to_numpy(float)
        v = v3["Viscosity_offline"].to_numpy(float)
        m = np.isfinite(v)
        ts = sim["time_h"].to_numpy(float)
        vs = sim["vis"].to_numpy(float)
        pred = np.interp(t[m], ts, vs)
        nrmse = np.sqrt(np.mean((pred - v[m]) ** 2)) / np.mean(v[m]) * 100
        print(f"=== b{b}  nRMSE={nrmse:.1f}%  vis_scale={COMBINED[b].get('vis_scale')}"
              f"  sim_peak={vs.max():.1f}@{ts[np.argmax(vs)]:.0f}  sim_end={vs[-1]:.1f}")
        for tt, vv, pp in zip(t[m], v[m], pred):
            print(f"   t={tt:6.1f} obs={vv:7.1f} sim={pp:7.1f} r={pp / vv:.2f}")


if __name__ == "__main__":
    main(sys.argv)
