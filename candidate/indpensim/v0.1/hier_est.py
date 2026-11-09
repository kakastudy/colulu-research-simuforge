# -*- coding: utf-8 -*-
"""PH1：层次化快校准协议（hier_est）。

对训练/验证批做轻量逆估计：18 组合网格（μx×μp×m_s；ΔTcin=+10 固定防崩），
损失 = 加权在线 RMSE + 崩溃惩罚；以损失自归一 softmax 得网格后验权重，
**后验期望 θ_b（连续值）** 供层次先验 (μ̂,Σ̂) 拟合（避免网格离散化伪影）。

物理约束：knowledge_constraints.calib_bounds() 强制。
增量落盘：runs/hier_est/train_theta.jsonl（断点续跑）。
"""
import itertools
import json
import os

import numpy as np
import pandas as pd

_V01 = os.path.dirname(os.path.abspath(__file__))
sys_path = _V01
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from simulate import simulate_open_loop
from soft_sensing import online_rmse, crash_penalty
from knowledge_constraints import calib_bounds

_ROOT = os.path.abspath(os.path.join(_V01, "..", "..", ".."))
THETA_LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta.jsonl")

GRID = {"mux": [0.35, 0.41, 0.47], "mup": [0.030, 0.041, 0.050], "m_s": [0.020, 0.029]}
# 协议 v2：μp 步距 0.002 ≈ 生成分散度 σ（EB 温度校准暴露的结构性要求：粗网格无法解析 ±0.0025）
GRID_V2 = {"mux": [0.35, 0.41, 0.47], "mup": [0.034, 0.036, 0.038, 0.040, 0.042, 0.044, 0.046, 0.048],
           "m_s": [0.020, 0.029]}
PROTOCOLS = {"v1": (GRID, THETA_LOG),
             "v2": (GRID_V2, os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl"))}

T_EB = 1.0  # 快校准后验温度（EB 试探后的折中值；严格 CI 用 dl_sigma）


def _v3(batch_no):
    return pd.read_csv(os.path.join(_ROOT, "data", "processed", "batches",
                                    f"batch_{batch_no:02d}.csv"))


def quick_calibrate(batch_no, grid=None, v3=None):
    """单批轻量逆估计：18 组合 → (theta_map, theta_post, sweep)。"""
    g = grid or GRID
    v3 = v3 if v3 is not None else _v3(batch_no)
    combos = list(itertools.product(g["mux"], g["mup"], g["m_s"]))
    losses, recs = [], []
    for mux, mup, m_s in combos:
        params = {"mux": mux, "mup": mup, "m_s": m_s, "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": 10}
        try:
            sim, _ = simulate_open_loop(batch_no, params)
            loss = online_rmse(sim, v3) + 0.1 * crash_penalty(sim)
            co2d = float(sim["CO2d"].max())
        except Exception:
            loss, co2d = 1e6, float("nan")
        losses.append(loss)
        recs.append({"mux": mux, "mup": mup, "m_s": m_s, "loss": loss, "co2d": co2d})
    arr = np.array(losses)
    # softmax 后验（自归一温度 T = 中位损失）
    T = max(np.median(arr[arr < 9e5]), 1e-6) if np.any(arr < 9e5) else 1.0
    w = np.exp(-(arr - arr.min()) / T)
    w = w / w.sum()
    theta_post = {k: float(sum(w_i * r[k] for w_i, r in zip(w, recs)))
                  for k in ("mux", "mup", "m_s")}
    best = recs[int(np.argmin(arr))]
    return {
        "batch": int(batch_no),
        "theta_post": theta_post,
        "theta_map": {k: best[k] for k in ("mux", "mup", "m_s")},
        "loss_best": float(best["loss"]),
        "co2d_best": best["co2d"],
        "n_combos": len(combos),
        "sweep": recs,
    }


def eb_temperature(theta_list, param="mup", target_sigma=0.0025,
                   T_grid=(1, 2, 4, 8, 16, 32, 64, 128, 256, 512)):
    """经验贝叶斯温度：调 softmax 温度 T 使池级 σ̂(T) 对准 MATLAB 生成分散度。

    返回 {"T": 温度, "sigma_at_T": ..., "n_batches": ...}；无数据 → None。
    """
    best = None
    for T in T_grid:
        theta_T = []
        for r in theta_list:
            sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
            if len(sw) < 2:
                continue
            arr = np.array([c["loss"] for c in sw])
            w = np.exp(-(arr - arr.min()) / T)
            w /= w.sum()
            theta_T.append(float(sum(wi * c[param] for wi, c in zip(w, sw))))
        if len(theta_T) < min(6, len(theta_list)):
            continue
        sig = float(np.std(theta_T))
        rec = {"T": T, "sigma_at_T": sig, "n_batches": len(theta_T)}
        if best is None or abs(sig - target_sigma) < abs(best["sigma_at_T"] - target_sigma):
            best = rec
    return best


def dl_sigma(theta_list, param, grid=None):
    """DerSimonian-Laird 型分层方差估计：σ̂²_pop = var(θ̂_b) − E[var_w]。

    var_w: 每批后验方差（网格加权）；含截断保护（σ_pop ≥ 0），
    batch 数 ≥6 才评估。返回 {"sigma_pop": …, "var_mean": …, "n": …}。

    ⚠️ **R142 已证伪本函数的可用性，勿直接引用其输出（见 docs/r142_round_report.md）**：
      1. `T_EB = 1.0` 与损失差（实测量级 1e-2）相差约 **100 倍** ⇒ 后验摊平，
         **ESS = 46.8/48**、`var_w` 达网格满铺方差的 99.9%，后验等价于无信息先验；
         同时 `var_b` 被压到 MAP 口径的 1%。
      2. 该统计量对温度**双重反向敏感**（T↑ ⇒ var_b↓ 且 var_w↑），因此任何 T 偏大都会
         稳定输出 `σ_pop = 0`。**"输出 0"是估计量失效的表现，不是"数据不可辨识"的证据。**
      3. 网格分辨率不足：mux 3 点（步距 0.060 = 真值 σ 0.025 的 2.4 倍）、m_s 2 点
         （量化下限 6.75e-06 > var_b(MAP) 3.55e-06 ⇒ 该参数只能报 0）。
    可引用的口径是 **MAP 点估计的批间散布上界**：`σ_pop ≤ sqrt(var_b_MAP)`，且必须注明
    不含群体先验。重估 σ_pop 须换协议（连续优化 + 剖面似然/Laplace），并先解 D-29。
    """
    if len(theta_list) < 6:
        return {"sigma_pop": float("nan"), "var_mean": float("nan"), "n": len(theta_list),
                "note": "n<6"}
    th_mean, th_var = [], []
    for r in theta_list:
        sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
        if len(sw) < 2:
            continue
        arr = np.array([c["loss"] for c in sw])
        w = np.exp(-(arr - arr.min()) / (T_EB or 1.0))
        w /= w.sum()
        vals = np.array([c[param] for c in sw])
        th_mean.append(float(w @ vals))
        th_var.append(float(w @ (vals - w @ vals) ** 2))
    th_mean = np.array(th_mean); th_var = np.array(th_var)
    var_pop = float(np.var(th_mean, ddof=1) - np.mean(th_var))
    return {"sigma_pop": round(float(np.sqrt(max(var_pop, 0.0))), 5),
            "var_mean": round(float(np.mean(th_var)), 7),
            "n": len(th_mean)}



def dl_sigma_combined(theta_list, param, batch_means, grid_temp=0.1):
    """DL σ̂ 替代方案：用外部校准值（如黄金回归 COMBINED）作为批均值。

    网格后验的批均值过于相似（var_b << var_w → σ_pop=0），
    因为网格后验在批间不分辨（平坦损失面 + 粗网格稀释）。
    用黄金回归 COMBINED dict 的逐批校准值作为 θ̂_b，
    var_b 更大，DL 减法后 σ_pop 非零。

    ⚠️ **R142 勘误：下方"验证"不成立，本函数不得再作为 σ_pop 估计手段（D-28）。**
      ①`COMBINED` 的批间散布是 MATLAB 生成机制真值的 **8.3×（mux）/ 4.0×（mup）**，
        且给**恒定参数** `m_s`（`Parameter_list.m:30` 为常数 0.029，无 randn）造出 sd 0.0033
        ⇒ 它是"把结构误差吸进参数的补偿器"，只能作逐批点估计，**不是批间分布样本**。
      ②原 docstring 只引用了 mux 那一个碰巧接近的数字（差 8%）。同一份代码、同一次运行的
        其余两个参数：mup 输出 0.01009（真值 0.0025，**+303%**）、m_s 输出 0.00643（真值 **0**）。
        mux 的"接近"来自 var_b（sd 0.0545，已是真值 2.2 倍）与虚高的 var_w 两个错误互相抵消。
      ③另：本函数实际调用方 `tools/d9_dl_sigma_combined.py` 用的是**硬编码的 12 批子集**，
        并非全量 COMBINED，样本量 n=12 且取值多为网格端点（0.35/0.47）。

    参数:
      theta_list: 网格后验列表（用于 var_w）
      param: 参数名 ("mux", "mup", "m_s")
      batch_means: dict {batch_id: value} 外部校准值
      grid_temp: 网格权重温度（0.1 锐化）
    返回: {"sigma_pop": …, "var_between": …, "var_within": …, "n": …}
    """
    if len(batch_means) < 6:
        return {"sigma_pop": float("nan"), "var_between": float("nan"),
                "var_within": float("nan"), "n": len(batch_means),
                "note": "n<6"}

    combined_vals = np.array([batch_means[b] for b in sorted(batch_means.keys())])
    var_b = float(np.var(combined_vals, ddof=1))

    # var_w from grid posterior
    th_vars = []
    for r in theta_list:
        sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
        if len(sw) < 2:
            continue
        arr = np.array([c["loss"] for c in sw])
        w = np.exp(-(arr - arr.min()) / (grid_temp or 1.0))
        w /= w.sum()
        vals = np.array([c[param] for c in sw])
        th_vars.append(float(w @ (vals - w @ vals) ** 2))
    var_w = float(np.mean(th_vars)) if th_vars else 0.0

    var_pop = var_b - var_w
    return {"sigma_pop": round(float(np.sqrt(max(var_pop, 0.0))), 5),
            "var_between": round(var_b, 7),
            "var_within": round(var_w, 7),
            "n": len(combined_vals)}


def hier_fit(theta_list):
    """跨批 (μ̂, Σ̂)（后验期望法，矩量法）；含与 MATLAB 生成机制对照。"""
    out = {}
    keys = ("mux", "mup", "m_s")
    if theta_list:
        vals = {k: [t["theta_post"][k] for t in theta_list] for k in keys}
        out = {k: {"mu_hat": float(np.mean(v)), "sigma_hat": float(np.std(v)),
                   "n": len(v)} for k, v in vals.items()}
    ref = {"mux": (0.41, 0.025), "mup": (0.041, 0.0025), "m_s": (0.029, None)}
    for k in out:
        out[k]["matlab_ref"] = ref.get(k)
    return out


def _iter_log(path):
    """通用 jsonl 迭代器（observe.py 的 v2 优先池用）。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_theta_log():
    return _iter_log(THETA_LOG)
    if not os.path.exists(THETA_LOG):
        return []
    with open(THETA_LOG, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_pool(batches, out_log=THETA_LOG, grid=None):
    """批量快校准：跳过已完成（断点续跑，按 out_log 文件去重），增量写 jsonl。"""
    os.makedirs(os.path.dirname(out_log), exist_ok=True)
    if os.path.exists(out_log):
        done = {r["batch"] for r in _iter_log(out_log)}
    else:
        done = set()
    todo = [b for b in batches if b not in done]
    print(f"批池 {len(batches)}；已完成 {len(done)}；待跑 {len(todo)}", flush=True)
    with open(out_log, "a", encoding="utf-8") as flog:
        for i, b in enumerate(todo):
            try:
                r = quick_calibrate(b, grid=grid)
                r["theta_post"] = {k: round(v, 6) for k, v in r["theta_post"].items()}
            except Exception as e:
                # R95 单批容错（I2）：记录 tombstone 供去重（防重复重试）+ 显式留痕，
                # 但 theta_post=None 会被 load_theta 的 theta_post 过滤器自然排除 →
                # 闸门计数不含失败批，需要补跑修复（诚实可见而非静默吞掉）。
                print(f"[{i + 1}/{len(todo)}] batch {b}: FAILED -> tombstone "
                      f"({type(e).__name__}: {str(e)[:120]})", flush=True)
                flog.write(json.dumps({"batch": b, "failed": True,
                                        "error": f"{type(e).__name__}: {str(e)[:200]}"},
                                       ensure_ascii=False) + "\n")
                flog.flush()
                continue
            flog.write(json.dumps(r, ensure_ascii=False) + "\n")
            flog.flush()
            print(f"[{i + 1}/{len(todo)}] batch {b}: μx={r['theta_post']['mux']:.3f} "
                  f"μp={r['theta_post']['mup']:.4f} m_s={r['theta_post']['m_s']:.4f} "
                  f"loss={r['loss_best']:.3f}", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="")  # 缺省=训练全量
    ap.add_argument("--grid", default="v1", choices=["v1", "v2"])
    a = ap.parse_args()
    g, out_log = PROTOCOLS[a.grid]
    if a.batches:
        batch_list = [int(x) for x in a.batches.split(",")]
    else:
        with open(os.path.join(_ROOT, "data", "processed", "batch_pool.json"),
                  encoding="utf-8") as f:
            bp = json.load(f)
        batch_list = bp["train"] + bp["validation"]  # v2 全批池（训练+验证）
    run_pool(batch_list, out_log=out_log, grid=g)
