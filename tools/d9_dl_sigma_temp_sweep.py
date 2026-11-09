# -*- coding: utf-8 -*-
"""R129t: DL σ̂ 温度扫描——降低 T_EB 锐化后验，检查 σ_pop。

当前 T_EB=1.0 → var_w >> var_between → σ_pop=0。
降低 T_EB 使后验更锐化 → var_w 减小 → σ_pop 可能非零。
"""
import sys

sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
import hier_est as he


def main():
    print("=" * 80, flush=True)
    print("R129t: DL σ̂ 温度扫描", flush=True)
    print("=" * 80, flush=True)

    v1 = he.load_theta_log()
    v2 = he._iter_log(he.PROTOCOLS['v2'][1])
    print(f"v1: {len(v1)} 批 | v2: {len(v2)} 批\n", flush=True)

    temps = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

    for param in ("mux", "mup", "m_s"):
        print(f"Parameter: {param}", flush=True)
        print(f"  {'T_EB':>6} | {'σ_pop':>10} | {'var_w':>12} | {'var_b':>12} | {'n':>4}", flush=True)
        for temp in temps:
            he.T_EB = temp
            result = he.dl_sigma(v2, param)
            sigma_pop = result.get("sigma_pop", float('nan'))
            var_w = result.get("var_mean", float('nan'))
            n = result.get("n", 0)

            # Also compute var_b directly
            th_mean = []
            for r in v2:
                sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
                if len(sw) < 2:
                    continue
                arr = np.array([c["loss"] for c in sw])
                w = np.exp(-(arr - arr.min()) / (temp or 1.0))
                w /= w.sum()
                vals = np.array([c[param] for c in sw])
                th_mean.append(float(w @ vals))
            th_mean = np.array(th_mean)
            var_b = float(np.var(th_mean, ddof=1)) if len(th_mean) > 1 else 0.0

            print(f"  {temp:>6.3f} | {sigma_pop:>10.5f} | {var_w:>12.7f} | {var_b:>12.7f} | {n:>4}", flush=True)
        print(flush=True)

    # Reset T_EB
    he.T_EB = 1.0
    print(f"Reference: MATLAB σ_gen — μx 0.025 / μp 0.0025 / m_s none", flush=True)


if __name__ == "__main__":
    main()
