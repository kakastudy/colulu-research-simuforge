# -*- coding: utf-8 -*-
"""R145 / D-32：五批钳位批 + 健康对照的 pH 预算扫描。

问题
----
`r145_d32_terms.py` 在 b92 上发现：t=200 时
  - `gamma1*(ph_prod + r_p)` = **−1.45e-08**（负！代谢产酸项整体是"碱化"的）
  - buffer 项 = −9.15e-08（把 [H+] 往 ~1.5e-08 即 pH 7.8 拉）
  ⇒ 产酸项不仅"小"，而是**变号了**。pH 因此没有平衡点，一路滑向 basic 分支的奇点。

本工具要回答
------------
Q1 该现象是否只在 b92？其余 4 批钳位批（b37/b50/b51/b91）如何？
Q2 变号的直接原因是什么？怀疑：尾段底物 S 高 → `P_inhib` 高斯门控关闭 → `r_p` 只剩
   `−mu_h·P`（水解）→ 净产酸转负。
Q3 若把水解通道按"青霉素水解生成青霉噻唑酸（产酸）"处理（即 pH 方程里对
   `mu_h·P` 取 **相反的符号**），产酸项能否回到正值？缺口有多大？

用法
----
  python tools/r145_d32_scan.py                  # 默认 6 批
  python tools/r145_d32_scan.py --batches 8,37,50,51,91,92
"""
import argparse
import json
import os
import sys

import numpy as np

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
sys.path.insert(0, os.path.join(_THIS, "..", "candidate", "indpensim", "v0.1"))

from r145_d32_terms import run  # noqa: E402

OUT_DIR = os.path.abspath(os.path.join(_THIS, "..", "runs", "p3"))


def scan_batch(batch):
    rows, sim, v3 = run(batch, stride=1)
    if not rows:
        return None
    acid = np.array([r["acid_term"] for r in rows])
    ph = np.array([r["ph"] for r in rows])
    s = np.array([r["s"] for r in rows])
    p = np.array([r["P"] for r in rows])
    t = np.array([r["t"] for r in rows])
    pin = np.array([r["P_inhib"] for r in rows])
    rp = np.array([r["r_p"] for r in rows])
    php = np.array([r["ph_prod"] for r in rows])

    g1 = 3.25e-7   # par[62]（R145 修正：原写 3.25e-6 差 10 倍）
    mu_h = 0.0026   # k4 在 pH 6.5 的取值（仅用于该列的粗略诊断）
    # 水解若按"产酸"处理：acid' = acid + 2*gamma1*mu_h*P
    acid_alt = acid + 2.0 * g1 * mu_h * p

    # 首次 pH 越 7 与首次钳位（pH 恰为 3.000±1e-3 且前一点 > 4）
    idx_over7 = np.where(ph >= 7.0)[0]
    first_over7 = float(t[idx_over7[0]]) if len(idx_over7) else None
    clamped = np.where((ph < 3.5) & (np.r_[9.0, ph[:-1]] > 4.0))[0]
    first_clamp = float(t[clamped[0]]) if len(clamped) else None

    # "净产酸转负"的最早时刻
    neg = np.where(acid < 0)[0]
    first_neg = float(t[neg[0]]) if len(neg) else None

    tail = t >= max(150.0, (t[-1] - 60.0))
    return {
        "batch": batch,
        "t_end": float(t[-1]),
        "ph_max": float(ph.max()),
        "ph_end": float(ph[-1]),
        "first_over7_t": first_over7,
        "first_clamp_t": first_clamp,
        "first_acid_neg_t": first_neg,
        "acid_neg_frac": float(np.mean(acid < 0)),
        "tail": {
            "t_lo": float(t[tail][0]),
            "s_med": float(np.median(s[tail])),
            "s_max": float(np.max(s[tail])),
            "P_med": float(np.median(p[tail])),
            "P_inhib_med": float(np.median(pin[tail])),
            "r_p_med": float(np.median(rp[tail])),
            "ph_prod_med": float(np.median(php[tail])),
            "acid_med": float(np.median(acid[tail])),
            "acid_alt_med": float(np.median(acid_alt[tail])),
            "acid_alt_min": float(np.min(acid_alt[tail])),
            "acid_min": float(np.min(acid[tail])),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,37,50,51,91,92")
    ap.add_argument("--all", action="store_true", help="扫 86 批合规集")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    if args.all:
        ref = json.load(open(os.path.join(_THIS, "..", "runs", "final_validation_v2.json"),
                             encoding="utf-8"))
        batches = sorted(r["batch"] for r in ref["results"])
    else:
        batches = [int(b) for b in args.batches.split(",") if b.strip()]

    from multiprocessing import Pool
    with Pool(min(args.workers, os.cpu_count() or 1)) as pool:
        out = [r for r in pool.map(scan_batch, batches, chunksize=1) if r is not None]

    print(f"{'批':>4} {'t_end':>6} {'pHmax':>6} {'pH末':>6} {'首越7':>7} {'首钳位':>7} "
          f"{'首转负':>7} {'负占比':>6} | {'S中位':>7} {'P中':>6} {'P_inh':>6} "
          f"{'r_p':>8} {'产酸中位':>10} {'产酸最小':>10} {'改符号后':>10}",
          flush=True)
    for r in out:
        tl = r["tail"]
        print(f"{r['batch']:>4} {r['t_end']:>6.0f} {r['ph_max']:>6.3f} {r['ph_end']:>6.3f} "
              f"{(r['first_over7_t'] if r['first_over7_t'] is not None else float('nan')):>7.1f} "
              f"{(r['first_clamp_t'] if r['first_clamp_t'] is not None else float('nan')):>7.1f} "
              f"{(r['first_acid_neg_t'] if r['first_acid_neg_t'] is not None else float('nan')):>7.1f} "
              f"{r['acid_neg_frac']:>6.1%} | {tl['s_med']:>7.2f} {tl['P_med']:>6.2f} "
              f"{tl['P_inhib_med']:>6.3f} {tl['r_p_med']:>8.4f} "
              f"{tl['acid_med']:>10.2e} {tl['acid_min']:>10.2e} {tl['acid_alt_med']:>10.2e}",
              flush=True)

    if not args.no_write:
        os.makedirs(OUT_DIR, exist_ok=True)
        name = "r145_d32_scan_all86.json" if args.all else "r145_d32_scan.json"
        p = os.path.join(OUT_DIR, name)
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n落盘 {p}")


if __name__ == "__main__":
    main()
