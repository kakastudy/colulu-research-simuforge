# -*- coding: utf-8 -*-
"""R158 / T3-3 侦察：PAT 通道的**量纲**与保真度口径核证。

背景
----
T3-1（T3 多通道 I3）刚给出结论：**P / PAA 通道结构性不可辨识**（D-64）。
T3-3 要做 Raman/PAA PLS 通道的**大规模接线 + 消融**。

侦察中发现的疑点
----------------
R120 记录的 PAT 保真度是 `r = 0.9995`，但那是用**相关系数**算的
（`np.corrcoef(pat, engine_PAA)`）⇒ **对线性缩放完全不敏感**。
本脚本用缓存 b22 实测：

    pat vs engine PAA:  r = 0.9291
    scale ratio (median) = 930.6     ← **~1000 倍量纲差**

若引擎 PAA 与化验 PAA 同为 mg/L（~10³），而 PLS 输出是 ~10⁰，
则 PAT 通道存在 **1000× 量纲错误**。相关系数口径**永远发现不了**这个错误
—— 这正是 R157「判据自身的证伪测试」纪律（D-69）的又一次实例：
**相关系数对缩放不变 ⇒ 不能作为「量纲正确」的证据**。

本脚本要回答
--------------
1. PLS 对**化验标定谱**（Batch_01，V6 存储谱 + PAA_offline 化验）输出什么量级？
   → 若 PLS 对化验谱输出 ~10³（mg/L）⇒ **PLS 本身量纲正确**，
     错误在"把 mg/L 的引擎 PAA 喂进合成层"这一步。
2. 合成层里 PAA 峰的标定：`PAA_INC * PAA_v`，`PAA_INC = 1700`。
   若设计输入是 g/L（~1.4）⇒ 峰幅 ~2380，与葡萄糖峰（~1714）同量级；
   若误传 mg/L（~1400）⇒ 峰幅 ~2.38e6，比葡萄糖峰大 1400 倍 ⇒ 光谱形状被 PAA 峰支配。
3. 引擎 PAA 与化验 PAA 是否同量纲？（决定要不要 /1000）

用法
----
    python tools/r158_raman_unit_probe.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import raman_pipeline as rp


def _sec(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def probe_batch01():
    """V6 .mat 的 Batch_01：真实存储谱 + 真实化验 ⇒ PLS 的**标定量纲**。"""
    import scipy.io as sio
    p = os.path.join(ROOT, "IndPenSim_V2.01", "IndPenSim_V2.02",
                     "IndPenSim_V2_export_V6.mat")
    m = sio.loadmat(p, struct_as_record=False, squeeze_me=True,
                    variable_names=["Raw_Batch_data"])
    rb = m["Raw_Batch_data"]
    b1 = getattr(rb, "Batch_01")

    def chan_of(name):
        obj = getattr(b1, name)
        # mat_struct 既可能走 _fieldnames（嵌套 struct），也可能直接持有 y 数组
        if hasattr(obj, "_fieldnames") or hasattr(obj, "y"):
            try:
                return np.asarray(obj["y"], dtype=float).ravel()
            except TypeError:
                return np.asarray(getattr(obj, "y"), dtype=float).ravel()
        return np.asarray(obj, dtype=float).ravel()

    stored = np.asarray(getattr(getattr(b1, "Raman_Spec"), "Intensity"))[:, :1215]

    def to_grid(name, n_t):
        y = chan_of(name)
        idx = np.arange(len(y))
        ok = np.isfinite(y)
        if ok.sum() < 2:
            return np.zeros(n_t)
        return np.interp(np.arange(n_t), idx[ok], y[ok])

    n_t = stored.shape[1]
    lab_paa = chan_of("PAA_offline")
    lab_x = chan_of("X_offline")
    lab_v = chan_of("Viscosity_offline")
    S_i = to_grid("S", n_t)
    P_i = to_grid("P", n_t)

    _sec("[1] V6 Batch_01：PLS 在**真实存储谱**上的输出量级（标定量纲）")
    print("stored spectrum shape:", stored.shape)
    print("lab PAA_offline (raw) : min %.4g max %.4g  n=%d"
          % (np.nanmin(lab_paa), np.nanmax(lab_paa), len(lab_paa)))
    print("lab X_offline  (raw)  : min %.4g max %.4g" % (np.nanmin(lab_x), np.nanmax(lab_x)))
    print("lab Viscosity (raw)   : min %.4g max %.4g" % (np.nanmin(lab_v), np.nanmax(lab_v)))
    print("S  grid: min %.4g max %.4g" % (np.nanmin(S_i), np.nanmax(S_i)))
    print("P  grid: min %.4g max %.4g" % (np.nanmin(P_i), np.nanmax(P_i)))

    pred_stored = rp.predict_paa(stored)
    ok = np.isfinite(lab_paa)
    print("\nPLS(stored spectra) -> PAA_pred: min %.4g max %.4g"
          % (np.nanmin(pred_stored), np.nanmax(pred_stored)))
    r = np.corrcoef(pred_stored[ok], lab_paa[ok])[0, 1]
    ratio = np.median(lab_paa[ok] / np.abs(pred_stored[ok]))
    print("corr(pred, lab) = %.4f   median lab/|pred| = %.4g" % (r, ratio))

    # 合成层：分别用 mg/L 与 g/L 两种口径的 PAA 喂进去
    for scale_name, paa_in in (("mg/L 直接传", to_grid("PAA_offline", n_t)),
                               ("g/L (÷1000)", to_grid("PAA_offline", n_t) / 1000.0)):
        spec = rp.synth_batch(np.clip(P_i, 0, None), np.clip(lab_x, 0, None),
                              np.clip(lab_v, 0, None), S_i[:n_t], np.clip(paa_in, 0, None))
        corr = [np.corrcoef(spec[:, t], stored[:, t])[0, 1]
                for t in range(0, min(spec.shape[1], stored.shape[1]),
                               max(1, min(spec.shape[1], stored.shape[1]) // 13))
                if np.std(spec[:, t]) > 0 and np.std(stored[:, t]) > 0]
        pred = rp.predict_paa(spec)
        rr = np.corrcoef(pred[ok], lab_paa[ok])[0, 1]
        print("  [合成 PAA 口径=%s] synth-vs-stored r=%.4f  PLS corr=%.4f  "
              "pred range %.4g..%.4g"
              % (scale_name, float(np.mean(corr)), rr, np.nanmin(pred), np.nanmax(pred)))
    return True


def probe_cache_units():
    """缓存里 sim.PAA 与化验 PAA_offline 的量纲关系。

    注意：cache['off'][ch] 是 **[[t, value], ...]** 的点对列表（不是标量数组），
    早期版本按标量数组读 ⇒ 统计失真。此处按点对解析。
    """
    _sec("[2] 缓存 platform/.cache/bXX.json：引擎 PAA vs 化验 PAA 量纲")
    cache_dir = os.path.join(ROOT, "platform", ".cache")
    rows = []
    for fn in sorted(os.listdir(cache_dir)):
        if not (fn.startswith("b") and fn.endswith(".json")):
            continue
        b = int(fn[1:3])
        d = json.load(open(os.path.join(cache_dir, fn), encoding="utf-8"))
        sim_paa = np.asarray(d["sim"]["PAA"], float)
        # off[ch] = [[t, v], ...]
        pts = np.asarray([p for p in d["off"]["PAA"] if p is not None], float)
        if pts.size == 0:
            continue
        t_lab, v_lab = pts[:, 0], pts[:, 1]
        ok = np.isfinite(v_lab)
        if ok.sum() < 5:
            continue
        # 引擎 PAA 在化验时点的取值
        t_sim = np.asarray(d["t"], float)
        sim_at = np.interp(t_lab[ok], t_sim, sim_paa)
        rows.append({
            "batch": b,
            "sim_paa_med": float(np.median(sim_paa)),
            "off_paa_med": float(np.median(v_lab[ok])),
            "ratio_at_lab": float(np.median(v_lab[ok] / np.abs(sim_at))),
            "n_lab": int(ok.sum()),
        })
    df = pd.DataFrame(rows)
    print(df.head(10).to_string(index=False))
    print("\nratio(lab/sim) 中位数 = %.4f   最小 %.4f  最大 %.4f"
          % (df["ratio_at_lab"].median(), df["ratio_at_lab"].min(),
             df["ratio_at_lab"].max()))
    print("sim_paa_med 中位数 = %.4g" % df["sim_paa_med"].median())
    print("off_paa_med 中位数 = %.4g" % df["off_paa_med"].median())
    print("=> 引擎 PAA 与化验 PAA **同量纲**（比值 ~1 附近，非 1000）"
          if 0.5 < df["ratio_at_lab"].median() < 2.0
          else "=> 比值显著偏离 1，需要进一步判读")
    return df


def probe_pat_scale(batch=22):
    """缓存驱动 PAT：量纲 + 保真度 + 对缩放的不敏感性演示。"""
    _sec("[3] 缓存驱动 PAT（batch=%d）：量纲与「相关系数掩盖量纲错误」演示" % batch)
    cache_dir = os.path.join(ROOT, "platform", ".cache")
    d = json.load(open(os.path.join(cache_dir, "b%02d.json" % batch), encoding="utf-8"))
    sim = d["sim"]
    P = np.clip(np.asarray(sim["P"], float), 0, None)
    X = np.clip(np.asarray(sim["X"], float), 0, None)
    V = np.clip(np.asarray(sim["vis"], float), 0, None)
    S = np.asarray(sim["S"], float)
    PAA = np.asarray(sim["PAA"], float)

    spec = rp.synth_batch(P, X, V, S, PAA)
    pat = rp.predict_paa(spec)
    r = float(np.corrcoef(pat, PAA)[0, 1])
    ratio = float(np.median(PAA / np.abs(pat)))
    print("引擎 PAA : %.4g .. %.4g" % (PAA.min(), PAA.max()))
    print("PAT 输出 : %.4g .. %.4g" % (pat.min(), pat.max()))
    print("r(pat, enginePAA) = %.4f      scale ratio = %.4g" % (r, ratio))
    print("\n=> 相关系数 %.4f 完全看不出 %g 倍量纲差："
          % (r, ratio))
    print("   把 pat × %g 就能对上引擎量纲，但 r 不变。"
          % ratio)

    # 缩放不变性的形式化演示
    print("\n演示：pat × 1000 后的 r = %.4f（与原始 %.4f 逐位相同）"
          % (float(np.corrcoef(pat * 1000.0, PAA)[0, 1]), r))

    # 若把 PAA 改成 g/L 喂进合成层
    spec2 = rp.synth_batch(P, X, V, S, PAA / 1000.0)
    pat2 = rp.predict_paa(spec2)
    r2 = float(np.corrcoef(pat2, PAA)[0, 1])
    print("\n改喂 g/L 后：pat2 = %.4g .. %.4g   r=%.4f  scale ratio=%.4g"
          % (pat2.min(), pat2.max(), r2, float(np.median(PAA / np.abs(pat2)))))
    return {"r": r, "ratio": ratio, "r_g_per_L": r2}


def main():
    out = {}
    try:
        probe_batch01()
        out["batch01"] = True
    except Exception as e:
        print("[skip] Batch_01 探测失败:", type(e).__name__, str(e)[:200])
        out["batch01"] = False
    try:
        out["units_df"] = probe_cache_units().to_dict("records")
    except Exception as e:
        print("[skip] 缓存单位探测失败:", type(e).__name__, str(e)[:200])
    try:
        out["pat"] = probe_pat_scale()
    except Exception as e:
        print("[skip] PAT 量纲探测失败:", type(e).__name__, str(e)[:200])

    p = os.path.join(ROOT, "runs", "r158_raman_unit_probe.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("\nwritten:", p)


if __name__ == "__main__":
    main()
