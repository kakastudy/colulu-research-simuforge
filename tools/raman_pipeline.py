# -*- coding: utf-8 -*-
"""P3-m1 Raman 引擎侧合成 + PAA PLS 管线（Python 复刻 Raman_Sim.m + Substrate_prediction.m）。

来源核证（R50）：PLS 系数 b唯一的官方标定对象即 Raman_Sim 合成谱 → 合成层与 PLS 自洽。
合成（Raman_Sim.m L4-L175，MATLAB 1-based → numpy 0-based 中心位 = peaka-1）：
  baseline(参考谱 verify reference_Specra.txt) + increase1*shift1*370000
  + 累积平滑噪声×10（randi(3) ±50 → cumsum → smooth(25)）
  + 葡萄糖峰(S/(0.005+S)*1714.3) + PAA峰(1700*PAA) + PenG 峰(100000*P)
PLS（Substrate_prediction.m）：savgol(poly2,win5,沿波长) → diff(波长轴)
  → bins(0-based 349:500 与 799:860) → PAA_pred = feat·b[3,:] → 3 点因果平滑。
验证模式：对 V6 .mat Batch_01（有存储光谱+通道）双算：合成 vs 存储谱相关 +
  PLS(PAA_pred) vs PAA_offline 化验相关。
"""
import io
import os
import sys

import numpy as np

if not (isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding == "gbk"):
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REF = os.path.join(ROOT, "IndPenSim_V2.01", "IndPenSim_V2.02", "reference_Specra.txt")
PLS = os.path.join(ROOT, "IndPenSim_V2.01", "IndPenSim_V2.02", "PAA_PLS_model.mat")

WL_MAX = 2200


def load_reference():
    a = np.loadtxt(REF)
    assert a.shape[0] >= WL_MAX and a.shape[1] == 2, f"reference shape {a.shape}"
    return a[:WL_MAX, 1].astype(float)  # MATLAB (1:Wavenumber_max) 切片


def _gauss_peak(center0, width, length_mult, div=1.0):
    """Raman_Sim.m 的截断高斯峰（0-based 中心=center0=peaka-1, std=width/2,
    填充窗 ±width*length_mult，B 型峰整体除以 div=4.3）。"""
    n = WL_MAX
    p = np.zeros(n)
    std = width / 2.0
    L = int(length_mult * width)
    for x in range(-L, L + 1):
        idx = center0 + x
        if 0 <= idx < n:
            p[idx] = 1.0 / (std * np.sqrt(2 * np.pi)) * np.exp(-0.5 * (x / std) ** 2) / div
    return p


PEAKS_G = _gauss_peak(218, 70, 2) + _gauss_peak(638, 20, 2, 4.3) + _gauss_peak(1052, 100, 2)
PEAKS_PAA = _gauss_peak(418, 60, 2) + _gauss_peak(838, 15, 2, 4.3)
PEAKS_P = _gauss_peak(799, 30, 4) + _gauss_peak(1199, 30, 30)
GLUC_INC = 800000.0 * 3 / 1400.0
PAA_INC = 1700000.0 / 1000.0
PROD_INC = 100000.0
K_G = 0.005
A_C, B_C, C_C, D_C = -0.00178143846614472 * 0.1, 1.05644816081515, -0.0681439987249108 * 0.1, -0.02
SCALING = 370000.0


def _shift1():
    j = np.arange(1, WL_MAX + 1)
    return np.exp(j / (WL_MAX * 0.5)) - 0.5


def smooth_ma(x, w):
    """MATLAB smooth(x, w)（对称滑动均值, 端部收缩窗口）。"""
    if w <= 1:
        return x.copy()
    pad = w // 2
    xp = np.concatenate([np.full(pad, x[0]), x, np.full(len(x) - len(x) * 0 + pad, x[-1])])
    out = np.convolve(xp, np.ones(w) / w, mode="valid")
    return out[: len(x)] if len(out) >= len(x) else out


def synth_batch(P_v, X_v, visc_v, S_v, PAA_v, seed=20261029):
    """向量态数组（每时刻一个值）→ 光谱矩阵 (WL_MAX × n_t)。PAA pred 也可直接调用。"""
    ref = load_reference()
    sh = _shift1()
    n_t = len(P_v)
    k = np.arange(1, n_t + 1, dtype=float)
    Time_S = k / (n_t - 1.0)  # k/(T/h) 归一化时间（%~.m 中 k=样本序, T/h=总样本数）
    increase1 = A_C * (X_v / 40.0) + B_C * (P_v / 40.0) + C_C * (visc_v / 100.0) + D_C * Time_S
    spec = increase1[None, :] * sh[:, None] * SCALING + ref[:, None]
    # 噪声：randi(3) → {0,+50,-50} → cumsum → smooth(25) → ×10（每时刻独立抽 — M 端为每波长）
    rng = np.random.default_rng(seed)
    rn = rng.integers(1, 4, size=WL_MAX)
    rnd = np.where(rn == 1, 0.0, np.where(rn == 2, 50.0, -50.0))
    noise = 10.0 * smooth_ma(np.cumsum(rnd), 25)
    spec = spec + noise[:, None]
    spec = spec + (PEAKS_G * GLUC_INC)[:, None] * (S_v[None, :] / (K_G + S_v[None, :]))
    spec = spec + (PEAKS_PAA * PAA_INC)[:, None] * PAA_v[None, :]
    spec = spec + (PEAKS_P * PROD_INC)[:, None] * P_v[None, :]
    return spec


def predict_paa(spec):
    """spec (WL_MAX × n_t) → PAA_pred (n_t,)（Substrate_prediction.m 管线）。"""
    from scipy.signal import savgol_filter
    sg = savgol_filter(spec, 5, 2, axis=0)  # sgolayfilt(2,5) 沿波长轴
    d = np.diff(sg, axis=0)  # 波长轴差分 → (WL_MAX-1 × n_t)
    feat = np.concatenate([d[349:500, :], d[799:860, :]], axis=0)  # MATLAB [350:500+800:860]
    import scipy.io as sio
    b = np.asarray(sio.loadmat(PLS, struct_as_record=False, squeeze_me=True)["b"])
    pred = feat.T @ b[3, :]  # No_LV = 4（b 第 4 行）
    out = pred.copy()
    for j in range(2, len(pred)):
        out[j] = (out[j - 1] + out[j - 2] + pred[j]) / 3.0
    return out


if __name__ == "__main__":
    # 校 syntaxis + Batch_01 验证
    import scipy.io as sio
    m = sio.loadmat(os.path.join(ROOT, "IndPenSim_V2.01", "IndPenSim_V2.02",
                                 "IndPenSim_V2_export_V6.mat"),
                    struct_as_record=False, squeeze_me=True, variable_names=["Raw_Batch_data"])
    rb = m["Raw_Batch_data"]
    b1 = getattr(rb, "Batch_01")
    stored = np.asarray(getattr(getattr(b1, "Raman_Spec"), "Intensity"))[:, :1215]
    def chan_of(name):
        """V6 .mat 通道是 {t: [], y: []} 结构体；返回 y 数组。"""
        obj = getattr(b1, name)
        if hasattr(obj, "_fieldnames") or hasattr(obj, "y"):
            y = getattr(obj, "y")
        else:
            y = obj
        return np.asarray(y, dtype=float).ravel()

    chan = {c: chan_of(c) for c in ("S", "P", "X_offline", "Viscosity_offline", "PAA_offline")}
    # 各通道长度可能不同（化验通道欠采样）——以最长者建格
    n_t = max(len(v) for v in chan.values())
    print("channels:", {c: v.shape for c, v in chan.items()})

    def to_grid(name):
        """把通道（可能稀疏化验 t/y）展到全长均匀网格。"""
        y = chan[name]
        idx = np.arange(len(y))
        ok = np.isfinite(y)
        if ok.sum() < 2:
            return np.zeros(n_t)
        return np.interp(np.arange(n_t), idx[ok], y[ok])

    X_i = to_grid("X_offline")
    V_i = np.clip(to_grid("Viscosity_offline"), 0, None)
    PAA_i = np.clip(to_grid("PAA_offline"), 0, None)
    S_i, P_i = to_grid("S")[:n_t], chan["P"][:n_t] if len(chan["P"]) == n_t else to_grid("P")
    spec = synth_batch(P_i, np.clip(X_i, 0, None), V_i, S_i[:n_t], PAA_i, seed=20261029)
    # 与存储谱的逐时间相关性（结构一致 = 峰位/漂移形状还原）
    corr = [
        (t, np.corrcoef(spec[:, t], stored[:, t])[0, 1])
        for t in range(0, min(spec.shape[1], stored.shape[1]), max(1, min(spec.shape[1], stored.shape[1]) // 13))
        if np.std(spec[:, t]) > 0 and np.std(stored[:, t]) > 0
    ]
    cor = float(np.mean([c for _, c in corr]))
    print(f"synth vs stored r(mean of {len(corr)} snapshots) = {cor:.4f}")
    paa_pred = predict_paa(spec)
    y_raw = chan["PAA_offline"]  # 化验真实落点（未插值的原始 y）
    ok_lab = np.isfinite(y_raw)
    if ok_lab.sum() >= 3:
        r_pls = np.corrcoef(paa_pred[ok_lab], y_raw[ok_lab])[0, 1]
        print(f"PLS PAA_pred vs PAA_offline(raw lab points) r = {r_pls:.4f} (n_lab={int(ok_lab.sum())})")
    # PLS 直读存储谱（绕开合成层）→ 分离『合成还原误差』与『PLS 测量精度』
    paa_pred2 = predict_paa(stored)
    if ok_lab.sum() >= 3:
        r_pls2 = np.corrcoef(paa_pred2[ok_lab], y_raw[ok_lab])[0, 1]
        print(f"PLS on stored spectra vs PAA_offline r = {r_pls2:.4f}")
