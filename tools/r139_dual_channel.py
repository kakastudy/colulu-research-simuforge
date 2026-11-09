# -*- coding: utf-8 -*-
"""R139 Part D：双通道（OUR + CER）一致性检验 —— 区分「X 错」与「呼吸标度错」。

## 为什么需要第二通道

R138 的单通道观测器 `X_est = X_model·(OUR_meas/OUR_model)^α` 在 4/86 批失效，
且失效方向一致：**把本来准的批搞坏**（b36 11.6→42.5、b50 5.9→28.4、b92 8.7→22.9）。

R138 的归因是"ratio 偏离 1 的可辨识性不足"，但没有给出可算的判据：
- 用 ratio 的 CV（稳定性）不行（gain~CV 仅 +0.421）
- 用 ratio 的晚期越界时长 R139-A 也不行：J5 拦得准（4/4，误拦 1/82），
  但一旦据此冻结校正，52/86 批被误触发、中位 5.69→13.17。因为**晚期 ratio 上冲
  在大多数批上是真实的模型缺陷，恰恰是观测器要修的东西**。

## 本工具的假设

模型 OUR 与 CER 都由同一个 X 驱动（呼吸的氧/碳两侧）：
    OUR_model ∝ X·Y_O2_X ,   CER_model ∝ X·Y_CO2_X
而 `Y_O2_X / Y_CO2_X / m_O2_X` 是**逐批随机参数**（R138 已记录 b8 = 800/200/15，
默认 650/160/17.5）。所以：

    r_OUR = OUR_meas/OUR_model = (X真/X模型) · (Y_O2_X真/Y_O2_X模型)
    r_CER = CER_meas/CER_model = (X真/X模型) · (Y_CO2_X真/Y_CO2_X模型)

⇒ **两式的 X 因子里相同，相除即消掉**：
    r_CER / r_OUR = RQ_meas / RQ_model        （RQ = CER/OUR，呼吸商）
    r_OUR · r_CER = (X真/X模型)² · (标度积)

所以：
- `|log(r_OUR/r_CER)|` 大 ⇒ 呼吸标度在两通道间不自洽 ⇒ **ratio 偏离不能归因于 X**
  ⇒ 单通道观测器不可信，应当报警（GOAL §4.5 失败可见）或收缩。
- 该量小时，取两通道的几何平均可把量测噪声降 √2，且对单通道标度误差不敏感。

## 用法
    python tools/r139_dual_channel.py --all86
    python tools/r139_dual_channel.py --all86 --estimator geo
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")
OUT = os.path.join(ROOT, "runs", "p3", "r139_dual_channel.json")

ALPHA = 0.60
RATIO_CLIP = (0.5, 2.0)
SMOOTH_WIN = 9
RATIO_SMOOTH = 5


def load_full(batch):
    cf = os.path.join(CACHE, f"b{batch:02d}.json")
    if not os.path.exists(cf):
        return None
    d = json.load(open(cf, encoding="utf-8"))
    t = np.array(d["t"], float)
    sim = d["sim"]
    v3 = pd.read_csv(os.path.join(DATA, f"batch_{batch:02d}.csv"))
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    m = np.isfinite(xl) & (xl > 2.0)
    if m.sum() < 6:
        return None

    def ch(col, key):
        v = pd.to_numeric(v3[col], errors="coerce").to_numpy(float)
        s = pd.Series(v).rolling(SMOOTH_WIN, center=True, min_periods=2).median().to_numpy()
        vs = np.where(np.isfinite(s), s, v)
        return np.interp(t, tv, vs), np.array(sim[key], float)

    our_m, our_p = ch("OUR", "OUR")
    cer_m, cer_p = ch("CER", "CER")
    return dict(b=batch, t=t, xm=np.array(sim["X"], float),
                our_m=our_m, our_p=our_p, cer_m=cer_m, cer_p=cer_p,
                tlab=tv[m], xlab=xl[m])


def ratios(rec):
    """模型网格上的两通道观测比值（裁剪 + 平滑）。"""
    def one(meas, pred):
        raw = np.clip(meas / np.maximum(pred, 1e-9), *RATIO_CLIP)
        return pd.Series(raw).rolling(RATIO_SMOOTH, center=True, min_periods=1).median().to_numpy()
    return one(rec["our_m"], rec["our_p"]), one(rec["cer_m"], rec["cer_p"])


def nrmse(x, y):
    return float(np.sqrt(np.mean((x - y) ** 2)) / abs(np.mean(y)) * 100)


def estimate(rec, r_our, r_cer, alpha, mode):
    """mode: our | cer | geo | min（保守：取远离 1 的那个通道）。"""
    if mode == "our":
        g = r_our
    elif mode == "cer":
        g = r_cer
    elif mode == "geo":
        g = np.sqrt(np.clip(r_our, *RATIO_CLIP) * np.clip(r_cer, *RATIO_CLIP))
    elif mode == "min":
        # 取更接近 1 的通道（保守收缩）——两通道不一致时宁可少校正
        g = np.where(np.abs(np.log(r_our)) <= np.abs(np.log(r_cer)), r_our, r_cer)
    else:
        raise ValueError(mode)
    xm = np.interp(rec["tlab"], rec["t"], rec["xm"])
    gg = np.interp(rec["tlab"], rec["t"], g)
    return xm, xm * gg ** alpha


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 5:
        return None
    rx = pd.Series(x[m]).rank().to_numpy()
    ry = pd.Series(y[m]).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", default=None)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--fail-nrmse", type=float, default=20.0)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.all86:
        bs = [int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
    elif args.batches:
        bs = [int(x) for x in args.batches.split(",")]
    else:
        bs = sorted(int(f[1:3]) for f in os.listdir(CACHE) if f.startswith("b") and f.endswith(".json"))

    recs = [r for r in (load_full(b) for b in bs) if r]
    rows = []
    for rec in recs:
        r_our, r_cer = ratios(rec)
        fin = np.isfinite(r_our) & np.isfinite(r_cer)
        cons_ts = np.abs(np.log(r_our[fin] / r_cer[fin]))
        row = {"b": rec["b"],
               "r_our_med": float(np.median(r_our[fin])),
               "r_cer_med": float(np.median(r_cer[fin])),
               "cons_med": float(np.median(cons_ts)),
               "cons_p90": float(np.percentile(cons_ts, 90)),
               "n_lab": int(len(rec["xlab"]))}
        for mode in ("our", "cer", "geo", "min"):
            _, xe = estimate(rec, r_our, r_cer, args.alpha, mode)
            row[f"n_{mode}"] = nrmse(xe, rec["xlab"])
        row["n_model"] = nrmse(np.interp(rec["tlab"], rec["t"], rec["xm"]), rec["xlab"])
        rows.append(row)

    no = np.array([r["n_our"] for r in rows])
    nm = np.array([r["n_model"] for r in rows])
    fail = no > args.fail_nrmse
    gain = nm - no

    print("=" * 96)
    print(f"R139-D  双通道一致性（OUR vs CER）      n={len(rows)} 批   失效判据：ours nRMSE>{args.fail_nrmse:.0f}%（{fail.sum()} 批）")
    print("=" * 96)
    g_our = float(np.median([r["r_our_med"] for r in rows]))
    g_cer = float(np.median([r["r_cer_med"] for r in rows]))
    print(f"  全局 median r_OUR = {g_our:.4f}   median r_CER = {g_cer:.4f}"
          f"   （模型 OUR 偏高 {(1/g_our-1)*100:.1f}%，CER 偏高 {(1/g_cer-1)*100:.1f}%）")

    print("\n--- 失效批 ---")
    print(f"  {'批':>4s} {'r_OUR':>7s} {'r_CER':>7s} {'cons中位':>9s} {'cons_p90':>9s}"
          f" {'X模型':>7s} {'OUR法':>7s} {'CER法':>7s} {'几何':>7s} {'保守':>7s}")
    for r in sorted(rows, key=lambda z: -z["n_our"]):
        if r["n_our"] <= args.fail_nrmse:
            continue
        print(f"  b{r['b']:<3d} {r['r_our_med']:7.3f} {r['r_cer_med']:7.3f} {r['cons_med']:9.3f}"
              f" {r['cons_p90']:9.3f} {r['n_model']:7.2f} {r['n_our']:7.2f} {r['n_cer']:7.2f}"
              f" {r['n_geo']:7.2f} {r['n_min']:7.2f}")

    cons = [r["cons_med"] for r in rows]
    print("\n--- 一致性判据的判别力 ---")
    print(f"  cons_med（中位） vs ours nRMSE  ρ={spearman(cons, no):+.3f}"
          f"；vs gain ρ={spearman(cons, gain):+.3f}")
    print(f"  cons_p90        vs ours nRMSE  ρ={spearman([r['cons_p90'] for r in rows], no):+.3f}")
    print(f"  |log(r_OUR/r_CER)| 的水平差 vs ours nRMSE "
          f"ρ={spearman([abs(np.log(r['r_our_med']/r['r_cer_med'])) for r in rows], no):+.3f}")

    for thr in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30):
        flag = np.array([c >= thr for c in cons])
        print(f"  cons_med ≥ {thr:.2f} → 拦下 {(flag & fail).sum()}/{fail.sum()} 失效批，"
              f"误拦 {(flag & ~fail).sum()}/{len(rows)-fail.sum()}")

    print("\n--- 四种估计量在 86 批上的整体表现 ---")
    print(f"  {'估计量':<12s}{'中位':>9s}{'p90':>9s}{'<15%':>8s}{'<20%':>8s}{'>20%':>7s}")
    print(f"  {'A 模型':<12s}{np.median(nm):9.2f}{np.percentile(nm,90):9.2f}"
          f"{(nm<15).sum():8d}{(nm<20).sum():8d}{(nm>20).sum():7d}")
    for mode, nm2 in (("OUR(R138)", "n_our"), ("CER 单通道", "n_cer"),
                      ("几何平均", "n_geo"), ("保守取近1", "n_min")):
        a = np.array([r[nm2] for r in rows])
        print(f"  {mode:<12s}{np.median(a):9.2f}{np.percentile(a,90):9.2f}"
              f"{(a<15).sum():8d}{(a<20).sum():8d}{(a>20).sum():7d}")

    # ---- Part E：决定性检验 —— ratio 到底反映 X 偏差还是通道标度 ----
    # 若 ratio 主要由 X 偏差驱动，则 ρ(r_ch, X_lab/X_model) 应接近 +1；
    # 若是通道标度（Y_O2_X / Y_CO2_X 逐批随机）驱动，则相关性显著弱。
    print("\n" + "=" * 96)
    print("R139-E  决定性检验：ratio 反映的是 X 偏差，还是呼吸通道标度偏差？")
    print("=" * 96)
    tx, ro, rc = [], [], []
    for rec in recs:
        r_our, r_cer = ratios(rec)
        xm_lab = np.interp(rec["tlab"], rec["t"], rec["xm"])
        fin = np.isfinite(r_our) & np.isfinite(r_cer)
        tx.append(float(np.median(rec["xlab"] / np.maximum(xm_lab, 1e-9))))
        ro.append(float(np.median(r_our[fin])))
        rc.append(float(np.median(r_cer[fin])))
    tx, ro, rc = np.array(tx), np.array(ro), np.array(rc)
    print(f"  真实 X 比值 median(X_lab/X_model)：中位 {np.median(tx):.4f}（<1 表示模型 X 偏高）")
    print(f"  ρ( r_OUR , X_lab/X_model )  = {spearman(ro, tx):+.3f}   ← R138 的前提")
    print(f"  ρ( r_CER , X_lab/X_model )  = {spearman(rc, tx):+.3f}")
    print(f"  ρ( r_OUR , r_CER )          = {spearman(ro, rc):+.3f}")
    # 弹性：用 log-log 回归斜率看 ratio 传过去多少
    for nm3, arr in (("r_OUR", ro), ("r_CER", rc)):
        m = np.isfinite(arr) & np.isfinite(tx) & (arr > 0) & (tx > 0)
        k = np.polyfit(np.log(tx[m]), np.log(arr[m]), 1)
        pred = np.exp(np.polyval(k, np.log(tx[m])))
        r2 = 1 - np.sum((arr[m] - pred) ** 2) / np.sum((arr[m] - arr[m].mean()) ** 2)
        print(f"  log {nm3} ~ log(X_lab/X_model)：斜率 {k[0]:+.3f}，R² {r2:.3f}")
    print("  → 斜率≈1 且 R²高 ⇒ 该通道忠实反映 X；斜率≪1 或 R²低 ⇒ 该通道被标度噪声主导")

    # ---- Part F：α 扫描（每通道各自的弹性不同，R138 把 OUR 的 1/β=0.6 直接套用是错的）----
    print("\n" + "=" * 96)
    print("R139-F  α 扫描：每个通道的最优弹性不同（OUR β≈1.42，CER β≈1.00）")
    print("=" * 96)
    grid = np.arange(0.4, 1.45, 0.1)
    print(f"  {'α':>5s}{'OUR中位':>9s}{'OUR<20%':>9s}{'CER中位':>9s}{'CER<20%':>9s}"
          f"{'几何中位':>10s}{'几何<20%':>10s}{'几何p90':>9s}")
    best = {}
    for a in grid:
        acc = {"our": [], "cer": [], "geo": []}
        for rec in recs:
            r_our, r_cer = ratios(rec)
            for mode in acc:
                _, xe = estimate(rec, r_our, r_cer, a, mode)
                acc[mode].append(nrmse(xe, rec["xlab"]))
        line = {k: (float(np.median(v)), int((np.array(v) < 20).sum()), float(np.percentile(v, 90)))
                for k, v in acc.items()}
        for k in line:
            if k not in best or line[k][0] < best[k][0]:
                best[k] = (line[k][0], a)
        print(f"  {a:5.2f}{line['our'][0]:9.2f}{line['our'][1]:9d}"
              f"{line['cer'][0]:9.2f}{line['cer'][1]:9d}"
              f"{line['geo'][0]:10.2f}{line['geo'][1]:10d}{line['geo'][2]:9.2f}")
    for k, (v, a) in best.items():
        print(f"  → {k} 最优 α={a:.2f}（中位 {v:.2f}%）")

    # ---- Part G：加权对数组合（用回归定权，再看 CV）----
    print("\n" + "=" * 96)
    print("R139-G  加权组合 log X_est = log X_model + w·α_cer·log r_CER + (1-w)·α_our·log r_OUR")
    print("=" * 96)
    # 先在全量上做无截距回归（因变量 = 真实 X 比值的对数）
    A, Y = [], []
    for rec in recs:
        r_our, r_cer = ratios(rec)
        xm_lab = np.interp(rec["tlab"], rec["t"], rec["xm"])
        lm = np.log(np.maximum(rec["xlab"] / np.maximum(xm_lab, 1e-9), 1e-6))
        lo = np.interp(rec["tlab"], rec["t"], r_our)
        lc = np.interp(rec["tlab"], rec["t"], r_cer)
        # 减去批内均值以消除批级水平（否则回归被批间差异主导）
        A.append(np.column_stack([np.log(np.maximum(lo, 1e-6)) - np.log(np.maximum(lo, 1e-6)).mean(),
                                  np.log(np.maximum(lc, 1e-6)) - np.log(np.maximum(lc, 1e-6)).mean()]))
        Y.append(lm - lm.mean())
    A, Y = np.vstack(A), np.concatenate(Y)
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    print(f"  批内去均值回归：系数 OUR {coef[0]:+.3f}，CER {coef[1]:+.3f}"
          f"（两者之和 {coef.sum():+.3f}）")

    json.dump({"meta": {"alpha": args.alpha, "n": len(rows), "fail_nrmse": args.fail_nrmse,
                        "g_our": g_our, "g_cer": g_cer,
                        "rho_our_x": spearman(ro, tx), "rho_cer_x": spearman(rc, tx),
                        "rho_our_cer": spearman(ro, rc),
                        "loglog_slope_our": float(np.polyfit(np.log(tx), np.log(ro), 1)[0]),
                        "loglog_slope_cer": float(np.polyfit(np.log(tx), np.log(rc), 1)[0]),
                        "reg_coef_our": float(coef[0]), "reg_coef_cer": float(coef[1])},
               "rows": rows}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
