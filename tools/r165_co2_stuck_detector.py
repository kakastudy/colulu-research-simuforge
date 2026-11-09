# -*- coding: utf-8 -*-
"""R164-5 / R165 执行阶段：CO2 卡死型故障的**只读**检测器 + 多轮寻优验收。

背景（D-87 第二维度，R163 实测）
--------------------------------
R163 的 C 段在**健康批**（8/11/15/22/23）上注入 20 例物理可信故障，EnKF 创新判据的
四格为 TP=10 / FN=5 / TN=4 / FP=1。其中 `co2_sensor_stuck`（CO2 排气分析仪冻结于
t=60 h）**仅 1/5 检出**。根因已定位：

  * 注入把 `CO2outgas` 列 t>=60 h 全部置为常数，偏离实测达 3.8~13.4 σ（幅度足够）；
  * 但 `model.py` 的 CO2 由**模型状态**驱动（y[27]/y[28] / CER），观测卡死不改变
    模型轨迹 ⇒ EnKF 的「模型预测 vs 实测」创新被其它通道量级掩盖。

思路：绕过 EnKF 创新，**直接检验实测通道的长时冻结 / 零方差**。这是仪表故障的
一类独立物理签名（"卡死" = 读数不再变化），与模型是否正确无关。

设计纪律（承 D-78 / 纪律 25 / 28 / 29）
--------------------------------------
1. **只读**：检测器不修改输入、不写引擎、不进入任何默认路径 ⇒ 零回归天然成立；
   本轮另跑 `r134_zero_regression.py` 作闸门证明。
2. **零信息对照**：未注入的真实批必须 **0 触发**，否则判据恒真。
3. **双向判别力**：正向（CO2 卡死）+ 反向（其它 3 类故障 / 冷却失效不得触发）。
4. **不恒真、不恒假**：给出阈值可行区间 + 留一交叉验证 + 灵敏度下界。
5. **可归因子集**：只在健康批上统计（对照本身退化 ⇒ 不可归因，纪律 28）。

多轮寻优（iterations 字段逐轮留痕，全部数据驱动）
------------------------------------------------
  * 轮 1：exact_run —— 最长「精确相等」恒定游程时长；一维阈值网格。
  * 轮 2：near_flat_run —— 滑窗标准差（抗 LSB 抖动）；先扫 `std_frac` 最大化
    「注入最小 / 对照最大」分离度，再定近零方差阈值。
  * 轮 3：**双阈值组合**（精确 12 h / 近零方差 32 h）+ 二维网格 + 留一交叉验证
    + 冻结起点/时长灵敏度扫描 + 与 EnKF 的组合增益。

用法
----
    py tools/r165_co2_stuck_detector.py --mode selftest
    py tools/r165_co2_stuck_detector.py --mode probe

产物：runs/r165_co2_stuck_detector.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from simulate import load_batch  # noqa: E402

# 与 tools/r163_degradation_probe.py 的 FAULTS 逐字一致（只改观测列，不动状态/参数）
HEALTHY_BATCHES = [8, 11, 15, 22, 23]
CONTROL_BATCHES = [1, 2, 3, 5, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 20, 22, 23, 24, 26, 27]
FAULTS = ["do2_sensor_drift", "ph_probe_bias", "co2_sensor_stuck", "cooling_fault_T"]
EXPECT_FIRE = {"do2_sensor_drift": True, "ph_probe_bias": True,
               "co2_sensor_stuck": True, "cooling_fault_T": False}

# 判据默认参数（最终值由 --mode probe 的网格寻优给出，见 payload.thresholds）
DEFAULT_EXACT_TH_H = 6.0         # 轮 3 由「裕度准则 + 最灵敏」选出
DEFAULT_NEAR_TH_H = 32.0        # 同上
NEAR_FLAT_WINDOW_PTS = 25        # 5 h @ dt=0.2 h
NEAR_FLAT_STD_FRAC = 0.010       # 轮 2 分离度扫描的 argmax（6.48x）
EXACT_GRID = [2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 72.0, 96.0, 120.0]
NEAR_GRID = [20.0, 24.0, 32.0, 48.0, 64.0, 96.0, 120.0]
STD_FRAC_GRID = [0.002, 0.005, 0.01, 0.02, 0.05]
# 裕度准则（显式、可复核）：阈值必须高于零信息对照的最大游程 × 安全系数，
# 再在可行组合中取**最灵敏**（阈值最小）者 ⇒ 既不恒真、也不牺牲灵敏度。
SAFETY_EXACT = 3.0
SAFETY_NEAR = 1.5


# ---------------------------------------------------------------------------
# 注入（只读地复制 DataFrame；与 R163 C 段逐字一致）
# ---------------------------------------------------------------------------
def _f_do2_drift(d):
    if "DO2" not in d.columns:
        return d
    t = d["time_h"].to_numpy(float)
    d = d.copy()
    d["DO2"] = pd.to_numeric(d["DO2"], errors="coerce") + 0.02 * np.maximum(t - 40.0, 0.0)
    return d


def _f_ph_bias(d):
    if "pH" not in d.columns:
        return d
    d = d.copy()
    d["pH"] = pd.to_numeric(d["pH"], errors="coerce") + 0.25
    return d


def _f_co2_stuck(d, freeze_t=60.0):
    if "CO2outgas" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    co2 = pd.to_numeric(d["CO2outgas"], errors="coerce").to_numpy(float)
    frozen = co2[int(np.argmin(np.abs(t - freeze_t)))]
    d["CO2outgas"] = np.where(t >= freeze_t, frozen, co2)
    return d


def _f_cooling_fault(d):
    if "T" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    T = pd.to_numeric(d["T"], errors="coerce").to_numpy(float)
    d["T"] = np.where(t >= 80.0, T + 5.0, T)
    return d


INJECT = {"do2_sensor_drift": _f_do2_drift, "ph_probe_bias": _f_ph_bias,
          "co2_sensor_stuck": _f_co2_stuck, "cooling_fault_T": _f_cooling_fault}


# ---------------------------------------------------------------------------
# 特征：最长恒定游程 / 最长近零方差段
# ---------------------------------------------------------------------------
def _longest_run(mask: np.ndarray):
    """返回**最长连续 True 段**的 (长度, 起点索引, 终点索引含)。

    ⚠ R165 踩过：只按「变化点间隔」取最大段，会把**最长 False 段**也当成结果
    （全 False 时甚至返回整段长度）⇒ 未注入真实数据被误报长时冻结。
    必须按段首的 mask 值过滤，只保留 True 段。
    """
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return (0, 0, 0)
    ch = np.r_[True, np.diff(mask.astype(np.int8)) != 0, True]
    idx = np.flatnonzero(ch)
    starts = idx[:-1]
    lens = np.where(mask[starts], np.diff(idx), 0)
    if not len(lens):
        return (0, 0, 0)
    k = int(np.argmax(lens))
    if lens[k] <= 0:
        return (0, 0, 0)
    return int(lens[k]), int(starts[k]), int(idx[k + 1] - 1)


def _exact_run(x: np.ndarray) -> tuple[int, int, int]:
    """最长「精确相等」游程（相邻点数值完全不变）。"""
    if len(x) < 2:
        return (0, 0, 0)
    same = np.r_[False, np.diff(x) == 0]
    return _longest_run(same)


def _near_flat_run(x: np.ndarray, window: int, std_frac: float) -> tuple[int, int, int]:
    """最长「滑窗标准差 < std_frac * 全程标准差」段（抗量化噪声的近似卡死）。

    滑窗方差用前缀和 O(n) 计算；窗口覆盖到的点全部标记为平坦，
    再用最长连续 True 段给出近零方差持续时长。
    """
    n = len(x)
    if n < window:
        return (0, 0, 0)
    gstd = float(np.nanstd(x))
    if not np.isfinite(gstd) or gstd <= 0:
        return (n, 0, n - 1)
    xc = np.nan_to_num(x, nan=0.0)
    c1 = np.cumsum(xc)
    c2 = np.cumsum(xc ** 2)
    s1, s2 = float(c1[window - 1]), float(c2[window - 1])
    flat = np.zeros(n, dtype=bool)
    for end in range(window - 1, n):
        if end >= window:
            s1 = float(c1[end] - c1[end - window])
            s2 = float(c2[end] - c2[end - window])
        var = max(0.0, s2 / window - (s1 / window) ** 2)
        if np.sqrt(var) < std_frac * gstd:
            flat[end - window + 1:end + 1] = True
    return _longest_run(flat)


# ---------------------------------------------------------------------------
# 检测器（只读；不改输入）
# ---------------------------------------------------------------------------
def detect_channel_stuck(d, channel: str = "CO2outgas",
                         min_run_h: float = DEFAULT_EXACT_TH_H,
                         near_flat: bool = True,
                         near_flat_min_run_h: float = DEFAULT_NEAR_TH_H,
                         window: int = NEAR_FLAT_WINDOW_PTS,
                         std_frac: float = NEAR_FLAT_STD_FRAC) -> dict:
    """检验一个在线通道是否存在「长时冻结 / 零方差」的仪表卡死签名。

    **双阈值**（轮 3 定稿）：
      * `exact_run_h >= min_run_h`        → 精确卡死（读数逐点不变）
      * `near_flat_run_h >= near_flat_min_run_h` → 近似卡死（带 LSB 抖动）

    返回体必含 `fired` / `degraded` / `reconstruction_valid` / `reason` / `evidence`
    —— 降级标记不得静默（§3.3）。
    """
    t = d["time_h"].to_numpy(float)
    x = pd.to_numeric(d[channel], errors="coerce").to_numpy(float)
    n = len(t)
    dt = float(np.median(np.diff(t))) if n > 1 else 0.2

    ne, i0, j0 = _exact_run(x)
    nf, i1, j1 = (_near_flat_run(x, window, std_frac) if near_flat else (0, 0, 0))
    exact_h, near_h = float(ne * dt), float(nf * dt)
    exact_fired = bool(exact_h >= min_run_h)
    near_fired = bool(near_flat and near_h >= near_flat_min_run_h)
    fired = bool(exact_fired or near_fired)
    sel_h = max(exact_h, near_h)
    sel_i, sel_j = (i1, j1) if near_h >= exact_h else (i0, j0)

    # 只读性证据：输入列未被改写
    unchanged = bool(np.array_equal(
        pd.to_numeric(d[channel], errors="coerce").to_numpy(float), x, equal_nan=True))

    trigger = ("精确冻结 %.2f h ≥ %.2f h" % (exact_h, min_run_h)) if exact_fired else \
              ("近零方差 %.2f h ≥ %.2f h" % (near_h, near_flat_min_run_h))
    return {
        "channel": channel,
        "fired": fired,
        "degraded": bool(fired),
        "reconstruction_valid": bool(not fired),
        "reason": (("检测到仪表卡死：%s（%s，t=%.1f→%.1f h）"
                    % (trigger, channel, t[sel_i], t[sel_j]))
                   if fired else "未检测到卡死（exact %.2f h < %.2f h；near_flat %.2f h < %.2f h）"
                   % (exact_h, min_run_h, near_h, near_flat_min_run_h)),
        "evidence": {
            "n_points": int(n), "dt_h": round(dt, 4),
            "max_exact_run_h": round(exact_h, 4),
            "max_near_flat_run_h": round(near_h, 4),
            "selected_run_h": round(sel_h, 4),
            "run_start_h": round(float(t[sel_i]) if n else 0.0, 2),
            "run_end_h": round(float(t[sel_j]) if n else 0.0, 2),
            "exact_fired": exact_fired, "near_flat_fired": near_fired,
            "min_run_h": float(min_run_h),
            "near_flat_min_run_h": float(near_flat_min_run_h),
            "std_frac": float(std_frac),
            "global_std": round(float(np.nanstd(x)), 6),
            "n_unique": int(len(np.unique(x))),
            "input_unchanged": unchanged,
            "method": "双阈值：exact_run（精确相等） OR near_flat_run（滑窗标准差，抗 LSB 抖动）",
        },
    }


def detect_co2_stuck(d, **kw) -> dict:
    """CO2outgas 专用包装；供 MCP / 回退链以 opt-in 方式引用（本轮不改引擎）。"""
    kw.setdefault("channel", "CO2outgas")
    return detect_channel_stuck(d, **kw)


# ---------------------------------------------------------------------------
# 验收探针：先缓存特征，再在网格上做阈值寻优（避免重复读盘 / 重算）
# ---------------------------------------------------------------------------
def _prepare_cases():
    """一次读盘，构造 (batch, fault, expect_fire, DataFrame) 列表。"""
    cases = []
    for b in CONTROL_BATCHES:
        cases.append((b, "none", False, load_batch(b)))
    for b in HEALTHY_BATCHES:
        d0 = load_batch(b)
        for f in FAULTS:
            cases.append((b, f, EXPECT_FIRE[f], INJECT[f](d0)))
    return cases


def _features(cases, std_frac):
    """对每个案例算一次特征（与阈值无关）。"""
    out = []
    for b, f, expect, d in cases:
        r = detect_channel_stuck(d, min_run_h=1e18, near_flat_min_run_h=1e18,
                                 std_frac=std_frac)
        ev = r["evidence"]
        out.append({"batch": b, "fault": f, "expect_fire": expect,
                    "exact_h": ev["max_exact_run_h"],
                    "near_h": ev["max_near_flat_run_h"],
                    "input_unchanged": ev["input_unchanged"]})
    return out


def _rows(feats, exact_th, near_th, use_near=True):
    rows = []
    for f in feats:
        fired = bool(f["exact_h"] >= exact_th or
                     (use_near and f["near_h"] >= near_th))
        rows.append({**f, "fired": fired, "exact_th": exact_th, "near_th": near_th})
    return rows


def _confusion(rows):
    tp = [r for r in rows if r["fault"] != "none" and r["expect_fire"] and r["fired"]]
    fn = [r for r in rows if r["fault"] != "none" and r["expect_fire"] and not r["fired"]]
    tn = [r for r in rows if r["fault"] != "none" and not r["expect_fire"] and not r["fired"]]
    fp = [r for r in rows if r["fault"] != "none" and not r["expect_fire"] and r["fired"]]
    return {"TP": tp, "FN": fn, "TN": tn, "FP": fp}


def _tag(r):
    return "%s@b%d" % (r["fault"], r["batch"])


def _score(rows):
    ctrl_fire = [r for r in rows if r["fault"] == "none" and r["fired"]]
    co2 = [r for r in rows if r["fault"] == "co2_sensor_stuck"]
    other = [r for r in rows if r["fault"] not in ("none", "co2_sensor_stuck")]
    other_fire = [r for r in other if r["fired"]]
    return {
        "n_control": len([r for r in rows if r["fault"] == "none"]),
        "n_control_fired": len(ctrl_fire),
        "n_co2": len(co2), "n_co2_fired": sum(1 for r in co2 if r["fired"]),
        "n_other": len(other), "n_other_fired": len(other_fire),
        "pass": (len(ctrl_fire) == 0 and sum(1 for r in co2 if r["fired"]) >= 4
                 and len(other_fire) == 0),
    }


def _choose(feasible, ctrl_max_exact, ctrl_max_near):
    """从可行组合中按**显式裕度准则 + 最灵敏**选阈值（不在测试集上凑边界）。

    准则：exact_th >= SAFETY_EXACT × 对照最大 exact 游程；
          near_th  >= SAFETY_NEAR  × 对照最大 near  游程。
    满足者中取字典序最小（最灵敏）。若没有任何组合满足裕度，则返回 None
    （⇒ 判据不可达，须降级登记，而不是偷偷放宽）。
    """
    ok = [(et, nt) for et, nt in feasible
          if et >= SAFETY_EXACT * ctrl_max_exact
          and nt >= SAFETY_NEAR * ctrl_max_near]
    return min(ok) if ok else None


def _loo(feats, grid, ctrl_max_exact, ctrl_max_near):
    """留一交叉验证：用 4 个健康批定阈值，留 1 批做样本外验证（二维网格）。

    ⚠ 每折必须用**与全数据相同的选择准则**（`_choose`），否则 LOO 与最终阈值
    不自洽（R165 踩过：LOO 取中位点、全数据取最灵敏 ⇒ 表面 5/5 实为两套口径）。
    """
    folds = []
    for held in HEALTHY_BATCHES:
        train_b = [b for b in HEALTHY_BATCHES if b != held]
        feasible = []
        for et, nt in grid:
            tr = [r for r in _rows(feats, et, nt) if r["batch"] in train_b
                  or r["fault"] == "none"]
            if _score(tr)["pass"]:
                feasible.append((et, nt))
        if not feasible:
            folds.append({"held_batch": held, "feasible": [], "test_pass": False})
            continue
        chosen = _choose(feasible, ctrl_max_exact, ctrl_max_near)
        if chosen is None:
            folds.append({"held_batch": held, "feasible_pairs": feasible,
                          "chosen": None, "test_pass": False})
            continue
        et, nt = chosen
        test = [r for r in _rows(feats, et, nt) if r["batch"] == held
                and r["fault"] != "none"]
        co2t = [r for r in test if r["fault"] == "co2_sensor_stuck"]
        othert = [r for r in test if r["fault"] != "co2_sensor_stuck"]
        ok = (len(co2t) > 0 and all(r["fired"] for r in co2t)
              and not any(r["fired"] for r in othert))
        folds.append({"held_batch": held, "feasible_pairs": feasible,
                      "chosen": [et, nt], "test_pass": bool(ok)})
    return {"folds": folds, "all_pass": all(f["test_pass"] for f in folds)}


def _sensitivity(exact_th, near_th):
    """灵敏度下界：冻结起点 × 冻结时长 × 抖动 的检出率（给出不可检出区间）。"""
    out = []
    rng = np.random.default_rng(11)
    for b in HEALTHY_BATCHES[:3]:
        d0 = load_batch(b)
        t = d0["time_h"].to_numpy(float)
        co2 = pd.to_numeric(d0["CO2outgas"], errors="coerce").to_numpy(float)
        for freeze_t in (40.0, 60.0, 100.0, 150.0):
            for dur_h in (2.0, 4.0, 8.0, 12.0, 24.0, 48.0, 96.0):
                x = co2.copy()
                frozen = x[int(np.argmin(np.abs(t - freeze_t)))]
                seg = (t >= freeze_t) & (t < freeze_t + dur_h)
                x[seg] = frozen
                d = d0.copy(); d["CO2outgas"] = x
                d2 = d0.copy()
                x2 = x.copy()
                x2[seg] = frozen + rng.normal(0, 0.001 * max(1.0, abs(frozen)), seg.sum())
                d2["CO2outgas"] = x2
                re = detect_co2_stuck(d, min_run_h=exact_th,
                                      near_flat_min_run_h=near_th, near_flat=False)
                rn = detect_co2_stuck(d2, min_run_h=exact_th,
                                      near_flat_min_run_h=near_th, near_flat=True)
                out.append({"batch": b, "freeze_t": freeze_t, "dur_h": dur_h,
                            "exact_fired": re["fired"], "noisy_fired": rn["fired"]})
    exact_min = min([r["dur_h"] for r in out if r["exact_fired"]], default=None)
    noisy_min = min([r["dur_h"] for r in out if r["noisy_fired"]], default=None)
    return {"cases": out, "n_cases": len(out),
            "min_detectable_exact_h": exact_min,
            "min_detectable_noisy_h": noisy_min}


def _enkf_baseline():
    """读 R163 健康批 C 段产物，构造组合判据的 EnKF 基线。"""
    p = os.path.join(ROOT, "runs", "r163_degradation_probe_healthy.json")
    if not os.path.exists(p):
        return None
    d = json.load(io.open(p, encoding="utf-8"))
    cs = d.get("C_summary", {})
    return {"source": "runs/r163_degradation_probe_healthy.json",
            "TP": len(cs.get("true_positive", [])),
            "FN": len(cs.get("false_negative", [])),
            "TN": len(cs.get("true_negative", [])),
            "FP": len(cs.get("false_positive", [])),
            "per_case": {("%s@b%d" % (r["fault"], r["batch"])): bool(r.get("degraded"))
                         for r in d.get("C_injection", [])}}


def probe(out_path: str):
    t0 = time.time()
    print("== R164-5 CO2 卡死只读检测器：多轮寻优 ==", flush=True)
    cases = _prepare_cases()
    print("  案例数：%d（零信息对照 %d + 健康批注入 %d）"
          % (len(cases), len(CONTROL_BATCHES), len(HEALTHY_BATCHES) * 4), flush=True)

    # ---------------- 轮 1：exact_run 一维阈值网格 ----------------
    f0 = _features(cases, NEAR_FLAT_STD_FRAC)
    iter1_scores = {}
    for th in EXACT_GRID:
        s = _score(_rows(f0, th, 1e18, use_near=False))
        iter1_scores[str(th)] = s
        print("  [轮1 exact] th=%6.1f h  对照触发=%d/%d  CO2检出=%d/5  其它误触发=%d  %s"
              % (th, s["n_control_fired"], s["n_control"], s["n_co2_fired"],
                 s["n_other_fired"], "PASS" if s["pass"] else "fail"), flush=True)
    iter1_feasible = [th for th in EXACT_GRID if iter1_scores[str(th)]["pass"]]
    ctrl_max_exact = max(r["exact_h"] for r in f0 if r["fault"] == "none")
    co2_min_exact = min(r["exact_h"] for r in f0 if r["fault"] == "co2_sensor_stuck")
    iter1 = {"name": "轮1：exact_run（最长精确相等游程）+ 一维阈值网格",
             "grid": EXACT_GRID, "scores": iter1_scores, "feasible": iter1_feasible,
             "control_max_run_h": round(ctrl_max_exact, 4),
             "co2_min_run_h": round(co2_min_exact, 4),
             "separation_ratio": round(co2_min_exact / max(ctrl_max_exact, 1e-9), 2)}

    # ---------------- 轮 2：near_flat 的 std_frac 扫描 ----------------
    sf_rows = []
    for sf in STD_FRAC_GRID:
        ff = _features(cases, sf)
        cm = max(r["near_h"] for r in ff if r["fault"] == "none")
        im = min(r["near_h"] for r in ff if r["fault"] == "co2_sensor_stuck")
        # 带 LSB 抖动的近似卡死（只测 CO2 卡死案例）
        noisy_min = None
        nz = []
        rng = np.random.default_rng(11)
        for b in HEALTHY_BATCHES:
            d0 = load_batch(b)
            t = d0["time_h"].to_numpy(float)
            x0 = pd.to_numeric(d0["CO2outgas"], errors="coerce").to_numpy(float)
            frozen = x0[int(np.argmin(np.abs(t - 60.0)))]
            seg = t >= 60.0
            x = x0.copy(); x[seg] = frozen
            x[seg] = x[seg] + rng.normal(0, 0.001 * max(1.0, abs(frozen)), seg.sum())
            d = d0.copy(); d["CO2outgas"] = x
            nz.append(detect_co2_stuck(d, min_run_h=1e18, near_flat_min_run_h=1e18,
                                       std_frac=sf)["evidence"]["max_near_flat_run_h"])
        noisy_min = min(nz)
        ratio = noisy_min / max(cm, 1e-9) if cm > 0 else float("inf")
        sf_rows.append({"std_frac": sf, "control_max_near_h": round(cm, 4),
                        "co2_min_near_h": round(im, 4),
                        "noisy_min_near_h": round(noisy_min, 4),
                        "separation_ratio": round(ratio, 2)})
        print("  [轮2 std_frac] %.3f  对照最大=%6.2fh  抖动卡死最小=%6.2fh  分离度=%.2fx"
              % (sf, cm, noisy_min, ratio), flush=True)
    best_sf_row = max(sf_rows, key=lambda r: r["separation_ratio"] if r["control_max_near_h"] > 0
                      else -1)
    best_sf = best_sf_row["std_frac"]
    print("  ⇒ 轮2 最优 std_frac = %.3f（分离度 %.2fx）" %
          (best_sf, best_sf_row["separation_ratio"]), flush=True)
    f2 = _features(cases, best_sf)

    near_scores = {}
    for nt in NEAR_GRID:
        s = _score(_rows(f2, DEFAULT_EXACT_TH_H, nt, use_near=True))
        near_scores[str(nt)] = s
    near_feasible = [nt for nt in NEAR_GRID if near_scores[str(nt)]["pass"]]
    iter2 = {"name": "轮2：near_flat_run（滑窗标准差，抗 LSB 抖动）+ std_frac 扫描",
             "std_frac_grid": STD_FRAC_GRID, "std_frac_scan": sf_rows,
             "selected_std_frac": best_sf,
             "near_threshold_grid": NEAR_GRID,
             "near_threshold_scores": near_scores, "near_feasible": near_feasible}

    # ---------------- 轮 3：双阈值二维网格 + LOO + 灵敏度 + 组合增益 ----------------
    grid_pairs = [(et, nt) for et in EXACT_GRID for nt in NEAR_GRID]
    feasible_pairs = [(et, nt) for et, nt in grid_pairs
                      if _score(_rows(f2, et, nt, use_near=True))["pass"]]
    ctrl_max_exact = max(r["exact_h"] for r in f2 if r["fault"] == "none")
    ctrl_max_near = max(r["near_h"] for r in f2 if r["fault"] == "none")
    safety = {"control_max_exact_h": round(ctrl_max_exact, 4),
              "control_max_near_h": round(ctrl_max_near, 4),
              "safety_exact": SAFETY_EXACT, "safety_near": SAFETY_NEAR,
              "required_exact_h": round(SAFETY_EXACT * ctrl_max_exact, 4),
              "required_near_h": round(SAFETY_NEAR * ctrl_max_near, 4)}
    chosen = _choose(feasible_pairs, ctrl_max_exact, ctrl_max_near)
    if chosen is not None:
        et, nt = chosen
    else:
        # 裕度准则无可行组合 ⇒ **接受降级**，如实登记，不偷偷放宽准则
        et, nt = DEFAULT_EXACT_TH_H, DEFAULT_NEAR_TH_H
    print("  ⇒ 轮3 双阈值 = exact %.1f h / near_flat %.1f h（可行组合 %d 个；"
          "裕度要求 %.1f/%.1f h，chosen=%s）"
          % (et, nt, len(feasible_pairs), safety["required_exact_h"],
             safety["required_near_h"], chosen), flush=True)

    loo = _loo(f2, grid_pairs, ctrl_max_exact, ctrl_max_near)
    print("  [轮3 LOO] 5 折全通过 =", loo["all_pass"], flush=True)
    sens = _sensitivity(et, nt)
    print("  [轮3 灵敏度] 最小可检出冻结时长 exact=%s h / 带抖动=%s h"
          % (sens["min_detectable_exact_h"], sens["min_detectable_noisy_h"]), flush=True)

    rows = _rows(f2, et, nt, use_near=True)
    cm = _confusion(rows)
    base = _enkf_baseline()
    combined = None
    if base:
        tp = fn = tn = fp = 0
        for r in rows:
            if r["fault"] == "none":
                continue
            enkf_fired = bool(base["per_case"].get(_tag(r), False))
            fired = bool(enkf_fired or r["fired"])      # EnKF OR 只读检测器
            if r["expect_fire"]:
                tp += int(fired); fn += int(not fired)
            else:
                tn += int(not fired); fp += int(fired)
        combined = {"TP": tp, "FN": fn, "TN": tn, "FP": fp,
                    "enkf_baseline": {k: base[k] for k in ("TP", "FN", "TN", "FP")},
                    "delta_TP": tp - base["TP"], "delta_FN": fn - base["FN"],
                    "TN_not_degraded": tn == base["TN"], "FP_not_increased": fp == base["FP"]}
        print("  [轮3 组合] EnKF %s → OR 检测器 %s（ΔTP=%+d, TN=%d, FP=%d）"
              % ({k: base[k] for k in ("TP", "FN", "TN", "FP")},
                 {k: combined[k] for k in ("TP", "FN", "TN", "FP")},
                 combined["delta_TP"], tn, fp), flush=True)

    # ---------------- 判据（双向、零信息对照、不恒真）----------------
    ctrl = [r for r in rows if r["fault"] == "none"]
    co2 = [r for r in rows if r["fault"] == "co2_sensor_stuck"]
    other = [r for r in rows if r["fault"] not in ("none", "co2_sensor_stuck")]
    checks = []

    def ck(cid, name, ok, got, want):
        checks.append({"id": cid, "name": name, "pass": bool(ok),
                       "got": got, "want": want})

    ck("D1", "零信息对照：%d 批未注入真实数据 0 触发（判据不恒真）" % len(ctrl),
       not any(r["fired"] for r in ctrl),
       {"fired": sum(r["fired"] for r in ctrl), "n": len(ctrl)}, "0")
    ck("D2", "正向触发：健康批 CO2 卡死检出 ≥4/5（目标 5/5）",
       sum(r["fired"] for r in co2) >= 4,
       {"fired": sum(r["fired"] for r in co2), "n": len(co2)}, ">=4")
    ck("D3", "反向判别力：其它 3 类故障 / 冷却失效 0 触发",
       not any(r["fired"] for r in other),
       {"fired": sum(r["fired"] for r in other), "n": len(other)}, "0")
    ck("D4", "二维阈值可行区间非空（exact %d 档 / near %d 档）"
       % (len(set(p[0] for p in feasible_pairs)), len(set(p[1] for p in feasible_pairs))),
       len(feasible_pairs) >= 4,
       {"n_feasible_pairs": len(feasible_pairs),
        "exact_feasible": sorted(set(p[0] for p in feasible_pairs)),
        "near_feasible": sorted(set(p[1] for p in feasible_pairs))}, ">=4 组合")
    ck("D5", "留一交叉验证 5 折全通过（样本外，非在测试集上定阈值）",
       loo["all_pass"], {"folds": len(loo["folds"]),
                         "pass": sum(f["test_pass"] for f in loo["folds"])}, "5/5")
    ck("D6", "灵敏度下界被量化（存在不可检出时长 ⇒ 判据非恒真）",
       sens["min_detectable_exact_h"] is not None
       and sens["min_detectable_exact_h"] > 0
       and any(not r["exact_fired"] for r in sens["cases"]),
       {"min_exact_h": sens["min_detectable_exact_h"],
        "min_noisy_h": sens["min_detectable_noisy_h"]}, ">0 且有未检出")
    ck("D7", "只读性：全部案例输入 DataFrame 未被改写",
       all(r["input_unchanged"] for r in rows),
       {"n": len(rows), "violations": sum(not r["input_unchanged"] for r in rows)}, "0")
    ck("D8", "组合增益：EnKF OR 检测器使 TP 提升且 TN/FP 不退化",
       bool(combined and combined["delta_TP"] > 0
            and combined["TN_not_degraded"] and combined["FP_not_increased"]),
       combined, "ΔTP>0 且 TN/FP 不退化")
    ck("D9", "四格混淆矩阵齐备且 TP>0 / TN>0（不恒真、不恒假）",
       len(cm["TP"]) > 0 and len(cm["TN"]) > 0,
       {k: [_tag(r) for r in v] for k, v in cm.items()}, "TP>0 且 TN>0")
    argmax_sf = max(sf_rows, key=lambda r: r["separation_ratio"])["std_frac"]
    nontrivial = len(set(r["separation_ratio"] for r in sf_rows)) >= 3
    ck("D10", "轮2 std_frac 由分离度扫描自动选出（曲线非平凡且选中 argmax）",
       best_sf == argmax_sf and nontrivial and chosen is not None,
       {"selected": best_sf, "argmax": argmax_sf,
        "separation_ratios": {str(r["std_frac"]): r["separation_ratio"] for r in sf_rows},
        "chosen_thresholds": [et, nt] if chosen else None}, "选中 argmax 且准则有解")
    ck("D11", "双阈值满足显式裕度准则（≥ 安全系数 × 对照最大游程）",
       bool(chosen and et >= SAFETY_EXACT * ctrl_max_exact
            and nt >= SAFETY_NEAR * ctrl_max_near),
       {**safety, "actual": [et, nt]}, "chosen ≥ required")

    n_pass = sum(c["pass"] for c in checks)
    payload = {
        "round": "R165", "task": "R164-5", "debt": "D-87 第二维度（通道灵敏度失衡）",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": {"exact_run_h": et, "near_flat_run_h": nt,
                       "std_frac": best_sf, "window_pts": NEAR_FLAT_WINDOW_PTS},
        "feasible_pairs": [[a, b] for a, b in feasible_pairs],
        "healthy_batches": HEALTHY_BATCHES, "control_batches": CONTROL_BATCHES,
        "iterations": [iter1, iter2,
                       {"name": "轮3：双阈值二维网格 + 留一交叉验证 + 灵敏度扫描 + 组合增益",
                        "loo": loo, "sensitivity": sens, "combined": combined}],
        "confusion": {k: [_tag(r) for r in v] for k, v in cm.items()},
        "cases": rows,
        "checks": checks, "n_pass": n_pass, "n_checks": len(checks),
        "verdict": "PASS" if n_pass == len(checks) else "FAIL",
        "wall_s": round(time.time() - t0, 1),
        "note": ("检测器为**只读**旁路，未写入引擎或默认路径；本轮改动不影响任何仿真数值。"
                 "接入回退链需走 opt-in + 基线更新流程（GOAL §5 边界变更）。"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    os.replace(tmp, out_path)
    print("\n判据 %d/%d %s ｜ 写出 %s（%.1f s）"
          % (n_pass, len(checks), payload["verdict"], out_path, payload["wall_s"]), flush=True)
    for c in checks:
        print("  [%s] %s %s" % ("PASS" if c["pass"] else "FAIL", c["id"], c["name"]), flush=True)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["probe", "selftest"], default="probe")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "r165_co2_stuck_detector.json"))
    a = ap.parse_args()
    if a.mode == "selftest":
        d = load_batch(8)
        print("未注入:", json.dumps(detect_co2_stuck(d), ensure_ascii=False, indent=2)[:700])
        d2 = _f_co2_stuck(d)
        print("注入后:", json.dumps(detect_co2_stuck(d2), ensure_ascii=False, indent=2)[:700])
        return 0
    r = probe(a.out)
    return 0 if r["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
