# -*- coding: utf-8 -*-
"""R139 Part A：OUR 观测比值的可靠性门控判据（水平 / 漂移 / 段间一致性）。

## 要解决的问题

R138 的 `X_est = X_model·median5(OUR_meas/OUR_model)^α`（α=0.60）把 86 批 X nRMSE
中位从 23.99% 压到 5.69%，但有 4 批失效（b36 ratio 1.561→42.5%；b50/b92 endR 1.55/1.61）。
根因是**可辨识性**：ratio 偏离 1 时，分不清「模型 X 错」还是「模型 OUR 标度错而 X 对」。

R138 已证：用 ratio 的 **CV**（稳定性）做门控不成立（gain~CV 仅 +0.421，
且 CV 小的批反而更易出现轻微负增益）。本工具改查三个候选：
  J1 水平离群  |log(med / g0)|      g0 = 86 批 med 的中位（系统性标度先验）
  J2 批内漂移  |log(med_late / med_early)|
  J3 段间极差  max(段中位) / min(段中位)

## 判据必须是「可在线算的」

观测器在 t 时刻只能看到已经发生的 OUR。所以门控量分两类：
  - 事后量（用全时程，可作诊断金标准，不可作在线门控）
  - 在线量（只用 t ≤ 当前时刻的窗口，滚动计算）
本工具两个都算，并报告「在线量在什么时刻能作出与事后量同向的判断」。

## 用法
    python tools/r139_ratio_gate.py --all86
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")
OUT = os.path.join(ROOT, "runs", "p3", "r139_ratio_gate.json")

ALPHA = 0.60
RATIO_CLIP = (0.5, 2.0)
SMOOTH_WIN = 9        # 化验 OUR 平滑（9 点 ≈ 1.8h），与 R138 一致
RATIO_SMOOTH = 5

SEG = [(48.0, 120.0), (120.0, 180.0), (180.0, 1e9)]   # 早 / 中 / 晚


def load_full(batch):
    """全时程 OUR 量测 + 模型序列（不裁到化验点）。"""
    cf = os.path.join(CACHE, f"b{batch:02d}.json")
    if not os.path.exists(cf):
        return None
    d = json.load(open(cf, encoding="utf-8"))
    t = np.array(d["t"], float)
    xm = np.array(d["sim"]["X"], float)
    om = np.array(d["sim"]["OUR"], float)

    v3 = pd.read_csv(os.path.join(DATA, f"batch_{batch:02d}.csv"))
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    ol = pd.to_numeric(v3["OUR"], errors="coerce").to_numpy(float)
    s = pd.Series(ol).rolling(SMOOTH_WIN, center=True, min_periods=2).median().to_numpy()
    ols = np.where(np.isfinite(s), s, ol)
    m = np.isfinite(xl) & (xl > 2.0)
    if m.sum() < 6:
        return None
    return dict(b=batch, t=t, xm=xm, om=om, tv=tv, ols=ols,
                tlab=tv[m], xlab=xl[m])


def ratio_series(rec):
    """模型网格上的观测比值（已裁剪、已平滑）。"""
    om = np.interp(rec["t"], rec["tv"], rec["ols"])
    raw = np.clip(om / np.maximum(rec["om"], 1e-9), *RATIO_CLIP)
    sm = pd.Series(raw).rolling(RATIO_SMOOTH, center=True, min_periods=1).median().to_numpy()
    return sm


def seg_med(t, r, lo, hi):
    m = (t >= lo) & (t < hi) & np.isfinite(r)
    if m.sum() < 5:
        return None
    return float(np.median(r[m]))


def stats(rec, r):
    t = rec["t"]
    med = float(np.median(r[np.isfinite(r)]))
    se = [seg_med(t, r, lo, hi) for lo, hi in SEG]
    q25, q75 = np.percentile(r[np.isfinite(r)], [25, 75])
    out = {"b": rec["b"], "med": med, "iqr_rel": float((q75 - q25) / max(med, 1e-9))}
    for nm, v in zip(("se", "sm", "sl"), se):
        out[nm] = v
    if se[0] and se[2]:
        out["drift"] = float(np.log(se[2] / se[0]))          # J2
        out["span"] = float(max(se) / min(se))               # J3
    else:
        out["drift"] = out["span"] = None
    # ---- J4/J5：校正幅度视角（观测器实际施加的增益 = ratio^α）----
    fin = np.isfinite(r)
    lr = np.log(r[fin])
    out["abs_p90"] = float(np.percentile(np.abs(lr), 90))                  # 全时程校正幅度 p90
    out["abs_max"] = float(np.max(np.abs(lr)))                             # 峰值校正幅度
    late = (t >= 150.0) & fin
    out["late_p90"] = float(np.percentile(r[late], 90)) if late.sum() > 20 else None
    out["late_over"] = float(np.mean(r[late] > 1.30)) if late.sum() > 20 else None  # 晚期越界时长占比
    # 单次施加的最大增益（α 折算后）
    out["gain_max"] = float(np.exp(ALPHA * out["abs_max"]))
    return out


def online_stats(rec, r, t_now):
    """只用 t ≤ t_now 的窗口：可分性检查。"""
    m = (rec["t"] <= t_now) & np.isfinite(r)
    if m.sum() < 50:
        return None
    rr = r[m]
    tt = rec["t"][m]
    med = float(np.median(rr))
    a = seg_med(tt, rr, 48.0, 120.0)
    b = seg_med(tt, rr, 120.0, 1e9)
    return {"med": med, "drift": float(np.log(b / a)) if (a and b) else None}


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 5:
        return None
    rx = pd.Series(x[m]).rank().to_numpy()
    ry = pd.Series(y[m]).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def j_curve(vals, fail, grids):
    """在阈值网格上算：拦下多少失效批 / 误拦多少正常批。"""
    rows = []
    for g in grids:
        flag = np.array(vals) >= g
        rows.append({"thr": float(g),
                     "caught": int((flag & np.array(fail)).sum()),
                     "n_fail": int(np.sum(fail)),
                     "false": int((flag & ~np.array(fail)).sum()),
                     "n_ok": int(np.sum(~np.array(fail)))})
    return rows


def lab_metrics(x, y):
    res = x - y
    mo = abs(np.mean(y))
    return float(np.sqrt(np.mean(res ** 2)) / mo * 100)


def observe_gated(rec, alpha, thr, win_h, frac):
    """带门控的观测器：滚动窗口内越界占比超阈值 → 冻结（其后不再施加校正）。

    冻结而不回滚：已施加的校正是 t 时刻的合法信息，事后撤销等于用未来数据。
    """
    t, r = rec["t"], ratio_series(rec)
    dt = float(t[1] - t[0])
    w = max(8, int(win_h / dt))
    over = pd.Series((r > thr).astype(float)).rolling(w, min_periods=max(4, w // 4)).mean().to_numpy()
    frozen = over >= frac
    i_freeze = int(np.argmax(frozen)) if frozen.any() else -1
    if i_freeze >= 0:
        frozen[i_freeze:] = True
    gain = np.where(frozen, 1.0, np.clip(r, *RATIO_CLIP) ** alpha)
    xm = np.interp(rec["tlab"], t, rec["xm"])
    g = np.interp(rec["tlab"], t, gain)
    return xm, xm * g, (float(t[i_freeze]) if i_freeze >= 0 else None)


def part_c(bs, alpha, thr, win_h, frac, obs_rows):
    """门控 vs 无门控的 86 批对比。"""
    base = {r["batch"]: r for r in obs_rows}
    recs = [r for r in (load_full(b) for b in bs) if r]
    rows = []
    for rec in recs:
        xm, xg, t_freeze = observe_gated(rec, alpha, thr, win_h, frac)
        n_gate = lab_metrics(xg, rec["xlab"])
        n_model = lab_metrics(xm, rec["xlab"])
        b = rec["b"]
        n_orig = base[b]["obs"]["nrmse"] if b in base else None
        rows.append({"b": b, "n_model": n_model, "n_r138": n_orig, "n_gated": n_gate,
                     "freeze_at": t_freeze})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", default=None)
    ap.add_argument("--fail-nrmse", type=float, default=20.0,
                    help="判定观测器失效的 nRMSE 阈值（默认 20%%）")
    ap.add_argument("--part", default="ab", choices=["ab", "c", "abc"])
    ap.add_argument("--thr", type=float, default=1.30, help="门控比值阈值")
    ap.add_argument("--win", type=float, default=24.0, help="滚动窗口小时数")
    ap.add_argument("--frac", type=float, default=0.50, help="窗口内越界占比触发阈值")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.all86:
        bs = [int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
    elif args.batches:
        bs = [int(x) for x in args.batches.split(",")]
    else:
        bs = sorted(int(f[1:3]) for f in os.listdir(CACHE) if f.startswith("b") and f.endswith(".json"))

    # 观测器基线（R138 产物）——用它的 obs nrmse 作"是否失效"的金标准
    obs = json.load(open(os.path.join(ROOT, "runs", "p3", "r138_our_observer.json"), encoding="utf-8"))
    base = {r["batch"]: r for r in obs["rows"]}

    rows = []
    for b in bs:
        rec = load_full(b)
        if not rec:
            continue
        r = ratio_series(rec)
        s = stats(rec, r)
        if b in base:
            s["nrmse_model"] = base[b]["model"]["nrmse"]
            s["nrmse_obs"] = base[b]["obs"]["nrmse"]
            s["peakR_obs"] = base[b]["obs"]["peak_ratio"]
            s["endR_obs"] = base[b]["obs"]["end_ratio"]
        s["online_120"] = online_stats(rec, r, 120.0)
        s["online_168"] = online_stats(rec, r, 168.0)
        rows.append(s)

    g0 = float(np.median([r["med"] for r in rows]))
    fail = [r.get("nrmse_obs", 0) > args.fail_nrmse for r in rows]

    print("=" * 94)
    print(f"R139-A  OUR 观测比值门控判据      n={len(rows)} 批   失效判据 obs nRMSE > {args.fail_nrmse:.0f}%"
          f"（{sum(fail)} 批失效）")
    print("=" * 94)
    print(f"  全局 ratio 中位 g0 = {g0:.4f}（模型 OUR 偏高 {(1/g0-1)*100:.1f}%，与 R136 的 1.242× 同向）")

    print("\n--- 失效批明细 ---")
    print(f"  {'批':>4s} {'med':>7s} {'med/g0':>7s} {'drift':>7s} {'span':>6s} {'iqr':>6s}"
          f" {'X模型':>7s} {'X观测':>7s} {'peakR':>6s} {'endR':>6s}")
    for r, f in sorted(zip(rows, fail), key=lambda z: -(z[0].get("nrmse_obs") or 0)):
        if not f:
            continue
        print(f"  b{r['b']:<3d} {r['med']:7.3f} {r['med']/g0:7.3f} {r['drift']:+7.3f} {r['span']:6.3f}"
              f" {r['iqr_rel']:6.3f} {r['nrmse_model']:7.2f} {r['nrmse_obs']:7.2f}"
              f" {r['peakR_obs']:6.3f} {r['endR_obs']:6.3f}")

    # ---- 三个判据 ----
    J1 = [abs(np.log(r["med"] / g0)) for r in rows]
    J2 = [abs(r["drift"]) if r["drift"] is not None else np.nan for r in rows]
    J3 = [r["span"] - 1.0 if r["span"] is not None else np.nan for r in rows]
    CV = [r["iqr_rel"] for r in rows]

    print("\n--- 判据与观测器残差的关系（Spearman，正=判据越大越差）---")
    no = [r.get("nrmse_obs", np.nan) for r in rows]
    nm = [r.get("nrmse_model", np.nan) for r in rows]
    gain = [m - o for m, o in zip(nm, no)]
    for nmj, v in (("J1 水平 |log(med/g0)|", J1), ("J2 漂移 |log(late/early)|", J2),
                   ("J3 段间极差 span-1", J3), ("(对照) IQR/med  CV 类", CV)):
        print(f"  {nmj:<26s} vs obs nRMSE  ρ={spearman(v,no):+.3f}"
              f"   vs gain  ρ={spearman(v,gain):+.3f}")

    print("\n--- 门控曲线：J1 水平离群 ---")
    for c in j_curve(J1, fail, np.arange(0.05, 0.85, 0.10)):
        print(f"  阈值 {c['thr']:.2f} → 拦下 {c['caught']}/{c['n_fail']} 失效批，误拦 {c['false']}/{c['n_ok']}")
    print("\n--- 门控曲线：J2 漂移 ---")
    for c in j_curve(J2, fail, np.arange(0.05, 0.85, 0.10)):
        print(f"  阈值 {c['thr']:.2f} → 拦下 {c['caught']}/{c['n_fail']} 失效批，误拦 {c['false']}/{c['n_ok']}")
    print("\n--- 门控曲线：J3 段间极差 ---")
    for c in j_curve(J3, fail, np.arange(0.05, 0.85, 0.10)):
        print(f"  阈值 {c['thr']:.2f} → 拦下 {c['caught']}/{c['n_fail']} 失效批，误拦 {c['false']}/{c['n_ok']}")

    # ---- 在线可分性：t=120 / 168 时刻的判据与事后判据是否同向 ----
    def sp(a, b):
        v = spearman(a, b)
        return "  n/a" if v is None else f"{v:+.3f}"

    print("\n--- 在线可分性（只用 t≤T 的历史，能否提前识别）---")
    for key, T in (("online_120", 120.0), ("online_168", 168.0)):
        on = [r[key] for r in rows]
        j1o = [(abs(np.log(o["med"] / g0)) if o else np.nan) for o in on]
        j2o = [(abs(o["drift"]) if (o and o["drift"] is not None) else np.nan) for o in on]
        print(f"  T={T:.0f}h：J1_online~J1_full ρ={sp(j1o, J1)}"
              f"；J2_online~J2_full ρ={sp(j2o, J2)}"
              f"；J1_online~obs nRMSE ρ={sp(j1o, no)}")

    # ---- 校正幅度视角：J4（全时程 |log ratio| p90）/ J5（晚期越界时长）----
    J4 = [r["abs_p90"] for r in rows]
    J5 = [r["late_over"] if r["late_over"] is not None else np.nan for r in rows]
    GM = [r["gain_max"] for r in rows]
    print("\n--- 判据（校正幅度视角）---")
    for nmj, v in (("J4 |log ratio| p90", J4), ("J5 晚期 ratio>1.3 时长占比", J5),
                   ("   单次最大增益 gain_max", GM)):
        print(f"  {nmj:<26s} vs obs nRMSE  ρ={sp(v, no)}   vs gain  ρ={sp(v, gain)}")
    for c in j_curve(J4, fail, np.arange(0.20, 0.75, 0.05)):
        print(f"  J4 阈值 {c['thr']:.2f} → 拦下 {c['caught']}/{c['n_fail']}，误拦 {c['false']}/{c['n_ok']}")
    for c in j_curve(J5, fail, np.arange(0.05, 0.55, 0.05)):
        print(f"  J5 阈值 {c['thr']:.2f} → 拦下 {c['caught']}/{c['n_fail']}，误拦 {c['false']}/{c['n_ok']}")

    # ---- 推荐门控：J1 + J2 组合 ----
    print("\n--- 组合门控（J1>a 或 J2>b）---")
    best = None
    for a in (0.15, 0.20, 0.25, 0.30):
        for b in (0.10, 0.15, 0.20):
            flag = [(j1 >= a) or (j2 >= b if np.isfinite(j2) else False)
                    for j1, j2 in zip(J1, J2)]
            c = int(np.sum(np.array(flag) & np.array(fail)))
            f_ = int(np.sum(np.array(flag) & ~np.array(fail)))
            score = (c - 0.5 * f_)
            if best is None or score > best[0]:
                best = (score, a, b, c, f_)
            print(f"  J1>{a:.2f} 或 J2>{b:.2f} → 拦下 {c}/{sum(fail)}，误拦 {f_}/{len(rows)-sum(fail)}")
    if best:
        print(f"  → 最佳（净收益口径）：J1>{best[1]:.2f} 或 J2>{best[2]:.2f}"
              f"，拦下 {best[3]}/{sum(fail)}，误拦 {best[4]}")

    # ---- 二维：J1（水平）× J5（晚期越界）----
    print("\n--- 二维门控（J1 水平 × J5 晚期越界时长）---")
    for a in (0.15, 0.20, 0.25, 0.30, 0.35):
        lst = []
        for b in (0.05, 0.10, 0.15, 0.20, 0.30):
            flag = [(j1 >= a) or (j5 >= b if np.isfinite(j5) else False)
                    for j1, j5 in zip(J1, J5)]
            c = int(np.sum(np.array(flag) & np.array(fail)))
            f_ = int(np.sum(np.array(flag) & ~np.array(fail)))
            lst.append(f"{b:.2f}:{c}/{f_}")
        print(f"  J1>{a:.2f}  " + "  ".join(lst) + "   （格式 J5阈值:拦下/误拦）")

    out = {"meta": {"alpha": ALPHA, "g0": g0, "n": len(rows),
                    "fail_nrmse": args.fail_nrmse, "segments": SEG},
           "rows": rows}

    # ---- Part C：门控冻结能否救回失效批 ----
    if "c" in args.part:
        print("\n" + "=" * 94)
        print(f"R139-C  门控冻结：ratio > {args.thr:.2f} 在 {args.win:.0f}h 窗内占比 ≥ {args.frac:.2f} → 冻结校正")
        print("=" * 94)
        cr = part_c(bs, ALPHA, args.thr, args.win, args.frac, obs["rows"])
        n0 = np.array([r["n_model"] for r in cr])
        n1 = np.array([r["n_r138"] for r in cr])
        n2 = np.array([r["n_gated"] for r in cr])
        print(f"  n={len(cr)} 批")
        print(f"  {'':<18s}{'中位':>9s}{'p90':>9s}{'<15%':>8s}{'<20%':>8s}")
        for nm, arr in (("A 模型(基准)", n0), ("B 原观测器(R138)", n1), ("C 门控冻结", n2)):
            print(f"  {nm:<18s}{np.median(arr):9.2f}{np.percentile(arr,90):9.2f}"
                  f"{(arr<15).sum():8d}{(arr<20).sum():8d}")
        print(f"\n  {'批':>4s} {'模型':>7s} {'R138':>7s} {'门控':>7s} {'Δ':>7s}  冻结时刻")
        for r in cr:
            if r["n_r138"] is not None and r["n_r138"] > args.fail_nrmse:
                ft = f"{r['freeze_at']:.1f}h" if r["freeze_at"] is not None else "未触发"
                print(f"  b{r['b']:<3d} {r['n_model']:7.2f} {r['n_r138']:7.2f} {r['n_gated']:7.2f}"
                      f" {r['n_gated']-r['n_r138']:+7.2f}  {ft}")
        worse = [(r["b"], r["n_gated"] - r["n_r138"]) for r in cr
                 if r["n_r138"] is not None and r["n_gated"] - r["n_r138"] > 1.0]
        print(f"\n  门控使 nRMSE 恶化 >1pt 的批：{len(worse)} 个"
              + (f"（{', '.join(f'b{b}({d:+.1f})' for b, d in worse[:12])}）" if worse else ""))
        print(f"  改善批数：{sum(1 for r in cr if r['n_r138'] is not None and r['n_gated'] < r['n_r138'] - 0.1)}"
              f"；冻结触发批数：{sum(1 for r in cr if r['freeze_at'] is not None)}")
        out["part_c"] = {"thr": args.thr, "win_h": args.win, "frac": args.frac, "rows": cr}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
