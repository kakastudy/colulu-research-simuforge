# -*- coding: utf-8 -*-
"""PH3：降阶集合观测器（EnKF）— 内部观测体系求解器。

架构（对齐 deepening_plan.md 第 4 层）：
- 全 33 状态按机理推进（成员带参扰动），观测更新只作用于观测相关子集
- 观测层（真实主义）：
    在线通道   DO2 / T / pH / Q / CO2outgas / O2（每 0.2h）
    化验延迟点 X_offline / P_offline / PAA_offline / vis（12h 粒度 + 4h 滞后，indpensim_run.m）
    注意：S 与 P 的"在线列"本工程视为仿真表出通道，不参与同化（防观测通胀，T7 登记）
- 增广随机游走参数：μp、m_s（PH1 层次先验）——为在线 μp 慢漂提供通路（PH2 μp 敏感度证据）
- I3：集合离散度 → ±1.96σ 区间 → 与 V3 真值做覆盖率经验证

回退链衔接（M2）：集合坍缩（spread→0）/发散 → 显式 fail 标记（本版仅标记）。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from simulate import (integrate_interval, guards, build_inp1, H_SAMPLE, IDX,
                      load_batch, build_initial_state, simulate_open_loop)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from knowledge_constraints import hier_priors

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 观测通道 → 状态索引 与映射（pH 经非线性）
ONLINE_OBS = {"DO2": IDX["DO2"], "T": IDX["T"], "Q": IDX["Q"],
              "CO2outgas": IDX["CO2"], "O2": IDX["O2"]}
OBS_R = {"DO2": 1.0,               # mg/L
         "T": 0.05,                # K
         "pH": 0.01,
         "Q": 25000.0,              # kJ/h 量级（V3 列 ×1000 后）
         "CO2outgas": 0.05,        # %
         "O2": 0.05,               # %
         "X_assay": 0.8, "P_assay": 0.6, "PAA_assay": 25.0, "vis_assay": 1.5,
         "NH3_assay": 30.0}        # T7 初值

ASSAY_OFFSET = 4.0  # indpensim_run.m Off_line_delay


def pH_of(x):
    return -np.log10(np.maximum(x, 1e-15))


def _initial_ensemble(y0, params, n_ens, rng):
    """θ_b 先验注入 + 状态小扰动；均值取「本批校准值」（PH1 层次先验的正确用法），
    不用通用值——否则成员动力学与本批校准基线系统性分离（b11 教训）。"""
    mup0 = float(params.get("mup", 0.041))
    ms0 = float(params.get("m_s", 0.029))
    mup_ens = np.clip(rng.normal(mup0, 0.0015, n_ens), 0.010, 0.080)
    # 绝对初值扰动（保守）
    y0_ens = np.tile(y0, (n_ens, 1)).astype(float)
    for idx_i, sig in [(IDX["S"], 0.03), (IDX["P"], 0.10), (IDX["PAA"], 40.0),
                       (IDX["CO2d"], 0.15)]:
        y0_ens[:, idx_i] = np.maximum(1e-6, y0_ens[:, idx_i] +
                                      rng.normal(0, sig, n_ens))
    y0_ens[:, IDX["mup"]] = mup_ens
    thetas = {"mup": mup_ens.copy(),
              "m_s": np.clip(rng.normal(ms0, 0.0015, n_ens), 0.005, 0.045)}
    return y0_ens, thetas


# 观测 → 允许更新的状态块（localization：防伪相关把未观测状态拉爆）
ALLOWED = {
    "DO2": [IDX["DO2"]], "T": [IDX["T"]], "pH": [IDX["pH_H"]],
    "CO2outgas": [IDX["CO2"]], "O2": [IDX["O2"]], "Q": [IDX["Q"]],
    "vis_assay": [IDX["vis"]], "NH3_assay": [IDX["NH3"]],
    "PAA_assay": [IDX["PAA"], 33],          # PAA 化验可校 μp（33=增广位）
    "P_assay": [IDX["P"], 33],              # P 化验可校 μp
}
PARAM_ROWS = (33, 34)
PARAM_DAMP = 0.05   # 参数更新强阻尼（μp ±0.001 → 60% 摆动的敏感度证据）


def localized_K(K, keys):
    """EnKF 增益定位：观测 k → 状态块；参数行按阻尼缩放。"""
    M = np.zeros_like(K)
    for j, k in enumerate(keys):
        cols = ALLOWED.get(k)
        if not cols:
            continue
        for ci in cols:
            M[ci, j] = K[ci, j]
    for ci in PARAM_ROWS:                    # 参数行统一阻尼（仅化验类观测驱动）
        for j, k in enumerate(keys):
            if k.endswith("_assay"):
                M[ci, j] = PARAM_DAMP * K[ci, j]
    return M


def phys_clamp(z_ens):
    """集合物理钳位：g/L 状态 ≥1e-3；pH_H（[H− +]）走 1e-12 下限，
    参数进先验域；温度进操作窗（T1 草案）。"""
    for j in range(31):
        if j == IDX["pH_H"]:
            continue  # [H+] 尺度 1e-7，禁止用 g/L 通用下限（b11 钳位教训）
        z_ens[:, j] = np.clip(z_ens[:, j], 1e-3, None)
    z_ens[:, IDX["pH_H"]] = np.clip(z_ens[:, IDX["pH_H"]], 1e-12, 1e-2)
    z_ens[:, 33] = np.clip(z_ens[:, 33], 0.010, 0.080)
    z_ens[:, 34] = np.clip(z_ens[:, 34], 0.005, 0.045)
    z_ens[:, IDX["T"]] = np.clip(z_ens[:, IDX["T"]], 290.0, 306.0)
    return z_ens


def enkf_update(z_ens, obs, R_map, probe=None):
    """确定性 EnKF（观测拼向量一次线性更新）+ 物理钳位 + 轻度膨胀（I2 稳健）。

    probe（R161 / D-75 降级触发器）：可选 dict，**纯旁路**——传 None 时函数行为与
    数值逐位不变。传入时逐次记录标准化创新（innovation / sqrt(R)）与增益条件数，
    供 `solver_chain.enkf_health()` 判定集合是否已失去可用性。记录口径：
      probe["z"]     list[dict[通道 -> 标准化创新]]（每步一次）
      probe["cond"]  list[float]（增益矩阵条件数，NaN 表示奇异）
    """
    n_ens, nz = z_ens.shape
    keys = list(obs.keys())
    yens, yvec = [], []
    for k in keys:
        ident, val = obs[k]
        yens.append(pH_of(z_ens[:, ident]) if k == "pH" else z_ens[:, ident])
        yvec.append(val)
    yens = np.column_stack(yens)                 # (n, ny)
    yvec = np.asarray(yvec, float)               # (ny,)
    zb = z_ens.mean(0)
    yb = yens.mean(0)
    Pzz = (z_ens - zb).T @ (z_ens - zb) / (n_ens - 1)
    Pyy = (yens - yb).T @ (yens - yb) / (n_ens - 1)
    Pzy = (z_ens - zb).T @ (yens - yb) / (n_ens - 1)
    R = np.diag([R_map.get(k, 1.0) for k in keys])
    K = np.linalg.solve(Pyy + R, Pzy.T).T        # (nz, ny)
    K = localized_K(K, keys)
    if probe is not None:
        sd = np.sqrt(np.maximum(np.diag(R), 1e-30))
        zres = (yvec - yens.mean(0)) / sd
        probe.setdefault("z", []).append(
            {k: float(v) for k, v in zip(keys, zres)})
        try:
            probe.setdefault("cond", []).append(
                float(np.linalg.cond(Pyy + R)))
        except Exception:
            probe.setdefault("cond", []).append(float("nan"))
    z_ens = z_ens + (yvec - yens) @ K.T          # (n,ny)·(ny,nz) → (n,nz)
    # 集合膨胀：温和复利（每步 0.05% → 全批 1.05^1320 ≈ 1.93×；旧 1.05/步 会 3e8 倍爆散 = NaN 真凶）
    z_ens = zb + (z_ens - zb) * 1.0005
    return phys_clamp(z_ens)


def enkf_observe(batch_no, params=None, n_ens=40, seed=7, verbose=True, out_path=None,
                  assim_online=True, assim_assay=True, obs_channels=None,
                  health_probe=False):
    """obs_channels: list[str]|None — 限制同化的在线通道集（PH3 单通道诊断）。

    health_probe（R161 / D-75）：默认 False ⇒ **输出与数值逐位不变**。
    置 True 时额外采集「集合健康度」旁路证据（供 solver_chain.enkf_health 判降级）：
      - 每步集合相对离散度 CV（X/P/PAA/mup/m_s 分通道）
      - 每步标准化创新 z = (观测 − 集合均值)/sqrt(R)（逐通道）
      - 每步成员级积分失败累计数与失败率
      - 集合条件数（Pyy+R）
    这些量**只写旁路字典**，不进入 z_ens 更新 ⇒ 不影响任何状态数值。
    """
    from scipy.integrate import solve_ivp
    from simulate import make_params as _mk  # no-op guard
    sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
    from simulate import load_batch, build_initial_state, make_params
    from calibration import calib_params

    params = params or calib_params(batch_no)
    # 105 维基参（随后每成员覆盖 par[0]/par[24]）
    par_base = make_params(alpha_kla=params.get("alpha_kla", 85.0),
                           N_conc_paa=params.get("N_conc_paa", 150000.0),
                           PAA_c=params.get("PAA_c", 530000.0),
                           mup=params.get("mup", 0.041),
                           mux=params.get("mux", 0.41),
                           c_oil=params.get("c_oil", 1000.0))
    par_base[24] = params.get("m_s", 0.029)
    par_base[48] = 285.0  # Tcin 标称（扰动经 inp1 注入）
    d = load_batch(batch_no)
    y0 = build_initial_state(d)
    rng = np.random.default_rng(seed)
    y_ens, thetas = _initial_ensemble(y0, params, n_ens, rng)
    n = 33
    z_ens = np.column_stack([y_ens, thetas["mup"], thetas["m_s"]])

    records = []
    t_current = d["time_h"].iloc[0]
    assay = {ch: pd.to_numeric(d[ch], errors="coerce") for ch in
             ("X_offline", "P_offline", "PAA_offline", "NH3_offline", "Viscosity_offline")}
    assay = {ch: {float(v3.time_h): float(v) for v3, v in
                  zip(d.loc[pd.to_numeric(d[ch], errors="coerce").notna()].itertuples(), [])} for ch in assay} if False else assay

    assay_points = {}
    for ch, ser in assay.items():
        pts = [(float(ix_t), float(v)) for ix_t, v in
               zip(ser.index, ser) if np.isfinite(v) and float(d.loc[ix_t, "time_h"]) > 20]
        assay_points[ch] = pts

    mv_row = d.iloc[0]
    fail_count = 0  # I2：成员级积分失败计数（显式暴露）
    t_idx = 0
    health = {"z": [], "cond": [], "cv": [], "mean": [], "fail_cum": [], "t": []} if health_probe else None
    for i in range(1, len(d)):
        row = d.iloc[i]
        t_sample = float(row["time_h"])
        if t_sample <= t_current:
            continue
        t_idx += 1
        inp1 = build_inp1(mv_row, inhib=2, dist_flag=1,
                          dist_tcin=params.get("dist_tcin_asym", 10) * min(1, t_current / 40) or 10)
        for e in range(n_ens):
            # 成员参数（105 维数组）——rhs 契约：par[0]=μp, par[24]=m_s
            par = par_base.copy()
            par[0] = float(z_ens[e, n]); par[24] = float(z_ens[e, n + 1])
            try:
                cand = integrate_interval(t_current, z_ens[e, :n], inp1, par)
                cand = guards(cand)
                if not np.isfinite(cand).all():
                    raise FloatingPointError("non-finite state（NaN 不抛异常的积分路径）")
                z_ens[e, :n] = cand
            except Exception:
                fail_count += 1
                # 成员级重采样：回到均值邻域（I2：失败计数在 out 顶层输出）；
                # isfinite 门保证 NaN 成员不过夜 → z_ens.mean(0) 永不被投毒（PH3 债务清偿）
                z_ens[e, :n] = z_ens.mean(0)[:n] + rng.normal(0, 1e-2, n)
            # 参数随机游走（慢漂）
            z_ens[e, n] += rng.normal(0, 2e-5)
            z_ens[e, n + 1] += rng.normal(0, 2e-4)
        # 在线观测同化
        obs = {}
        for ch, ident in ONLINE_OBS.items():
            val = float(row[ch]) if ch in d.columns else np.nan
            if np.isfinite(val) and t_sample > 20:
                if ch == "Q":
                    val = val * 1000.0  # 引擎 Q 状态为 kJ/h 量级，V3 列已 /1000（单位对齐）
                obs[("pH" if ch == "pH" else ch)] = (ident, val)
        val_ph = float(row["pH"])
        if np.isfinite(val_ph) and t_sample > 20:
            obs["pH"] = (IDX["pH_H"], val_ph)
        for k in ("T",):  # T 值即可 ~ 全在线
            pass
        # 化验延迟点：t_sample − 4h 时刻的化验值 = 状态(t_sample−4h)
        act_obs = dict(obs)
        for ch, pts in assay_points.items():
            for t_lab, v in pts:
                if abs(t_lab - t_sample) < 0.11:
                    delay_state_t = t_sample - ASSAY_OFFSET
                    # 取状态在 delay_state_t 的剖面：用"缓存上时刻状态"？→ 简化：以区间内插
                    # 本实现：化验观测以当刻状态近似（4h 滞后由 θ 层吸收，T7 登记简化）
                    ident_map = {"X_offline": None, "P_offline": IDX["P"],
                                 "PAA_offline": IDX["PAA"],
                                 "Viscosity_offline": IDX["vis"],
                                 "NH3_offline": IDX["NH3"]}
                    if ch == "X_offline":
                        continue  # X 为多室和，暂未列入同化（记录用）
                    act_obs[ch.replace("_offline", "_assay")] = (ident_map[ch], v)
        # 同化源过滤（二分诊断开关）
        if not assim_online:
            act_obs = {k: v for k, v in act_obs.items() if k.endswith("_assay")}
        if not assim_assay:
            act_obs = {k: v for k, v in act_obs.items() if not k.endswith("_assay")}
        if act_obs:
            z_ens = enkf_update(z_ens, act_obs, OBS_R,
                                probe=({"z": health["z"], "cond": health["cond"]}
                                       if health_probe else None))
        t_current = t_sample
        mv_row = row

        z_mean = z_ens.mean(0)
        z_std = z_ens.std(0, ddof=1)
        records.append({
            "time_h": t_sample,
            "P_mean": float(z_mean[IDX["P"]]), "P_sd": float(z_std[IDX["P"]]),
            "S_mean": float(z_mean[IDX["S"]]), "S_sd": float(z_std[IDX["S"]]),
            "X_sum": float(z_mean[IDX["A0"] + IDX["A0"] + 0]) if False else
                      float(z_mean[IDX["A0"]] + z_mean[IDX["A1"]] + z_mean[IDX["A3"]] + z_mean[IDX["A4"]]),
            "X_sd": float(np.sqrt(z_std[IDX["A0"]] ** 2 + z_std[IDX["A1"]] ** 2
                                   + z_std[IDX["A3"]] ** 2 + z_std[IDX["A4"]] ** 2)),
            "PAA_mean": float(z_mean[IDX["PAA"]]), "PAA_sd": float(z_std[IDX["PAA"]]),
            "mup_mean": float(z_mean[n]), "mup_sd": float(z_std[n]),
            "ms_mean": float(z_mean[n + 1]), "ms_sd": float(z_std[n + 1]),
        })
        if health_probe:
            # 集合健康度旁路采样（不参与任何数值路径）：
            #  CV = 集合标准差 / |集合均值|（相对离散度；spread→0 时 CV→0）
            #  mean 同时记录：用于屏蔽「地板饱和步」（状态被钳在物理地板上时
            #  所有成员必然相同 ⇒ CV→0 是守卫产物而非集合发散，见 solver_chain 的
            #  SPREAD_FLOOR_GUARD）。
            _sd = z_ens.std(0, ddof=1)
            _mn = z_ens.mean(0)
            _x_mean = float(_mn[IDX["A0"]] + _mn[IDX["A1"]] + _mn[IDX["A3"]] + _mn[IDX["A4"]])
            _x_sd = float(_sd[IDX["A0"]] + _sd[IDX["A1"]] + _sd[IDX["A3"]] + _sd[IDX["A4"]])
            health["t"].append(float(t_sample))
            health["cv"].append({
                "X": _x_sd / max(abs(_x_mean), 1e-12),
                "P": float(_sd[IDX["P"]] / max(abs(_mn[IDX["P"]]), 1e-12)),
                "PAA": float(_sd[IDX["PAA"]] / max(abs(_mn[IDX["PAA"]]), 1e-12)),
                "S": float(_sd[IDX["S"]] / max(abs(_mn[IDX["S"]]), 1e-12)),
                "mup": float(_sd[n] / max(abs(_mn[n]), 1e-12)),
                "ms": float(_sd[n + 1] / max(abs(_mn[n + 1]), 1e-12)),
            })
            health["mean"].append({
                "X": _x_mean,
                "P": float(_mn[IDX["P"]]),
                "PAA": float(_mn[IDX["PAA"]]),
                "S": float(_mn[IDX["S"]]),
                "mup": float(_mn[n]),
                "ms": float(_mn[n + 1]),
            })
            health["fail_cum"].append(int(fail_count))
        if verbose and i % 200 == 0:
            print(f"  t={t_sample:.0f}h X={records[-1]['X_sum']:.1f}±{records[-1]['X_sd']:.2f} "
                  f"P={records[-1]['P_mean']:.1f} mup={records[-1]['mup_mean']:.4f}", flush=True)

    out = {"batch": batch_no, "n_ens": n_ens, "records": records,
            "integration_failures": int(fail_count)}
    if health_probe:
        out["health"] = health
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, default=str)
    return out


def _death_corr(sim, coef):
    """PH2 死亡项修正：X_corr = X − (kd1·X + kd2·X·A_t1 + kd3·X·A_t1²)/100。
    A_t1 = a0/(a1+a3+a4)（引擎内培养年龄比）。coef 来自 runs/hier_est/death_term.json。
    注意（R63 澄清, 工具 trace_death_corr11.py）：本函数自行重算 A_t1 = a0/(a1+a3+a4)。
    该公式口径在化验对齐点上为 0.22~0.51 的健康有界值，随培养成熟缓慢衰减。
    sim 记录表内的同名呈现列是另一约定的度量（数值 60~4500，量级不同、约定倒置），
    两者不可互换。死亡项修正一律以本口径 a0/(a1+a3+a4) 为准。"""
    a0 = sim["A0"].to_numpy(float)
    a1 = sim["A1"].to_numpy(float)
    a3 = sim["A3"].to_numpy(float)
    a4 = sim["A4"].to_numpy(float)
    at1 = a0 / np.maximum(a1 + a3 + a4, 1e-9)
    X = sim["X"].to_numpy(float)
    corr = (coef["kd1"] * X + coef["kd2"] * X * at1 + coef["kd3"] * X * at1 ** 2) / 100.0
    return np.maximum(X - corr, 0.0)


def load_death_coef():
    p = os.path.join(ROOT, "runs", "hier_est", "death_term.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return {"kd1": d["beta"][0], "kd2": d["beta"][1], "kd3": d["beta"][2],
             "r2": d["r2"], "n_points": d["n_points"]}


def ensemble_smooth(batch_no, n_ens=50, seed=11, out_path=None, verbose=True,
                     death_term=True):
    """集合平滑器（稳健版内部观测）：从快校准网格后验采 θ_b → 引擎全量重放 →
    状态轨迹后验（均值 ± 1.96σ）→ 对 V3 化验真值做 ±1.96σ 覆盖率（I3）。

    定位：回溯型内部观测（历史批次重构/QA）；在线滚动版（EnKF 精调）按 D1 连续推进。
    """
    import hier_est

    # θ_b 池优先级：细网格协议 v2 日志（分辨力高）> v1 日志 > 现算
    sweep = None
    v2log = os.path.join(ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
    if os.path.exists(v2log):
        v2s = {r["batch"]: r for r in hier_est._iter_log(v2log)}
        if batch_no in v2s and len(v2s) >= 10:
            sweep = v2s[batch_no].get("sweep")
    if sweep is None:
        tlog = hier_est.load_theta_log()
        thetas = {r["batch"]: r for r in tlog}
        if batch_no in thetas:
            sweep = thetas[batch_no].get("sweep")
    if sweep is None:
        sweep = hier_est.quick_calibrate(batch_no)["sweep"]

    valid = [r for r in sweep if r["loss"] < 9e5 and np.isfinite(r.get("co2d", np.nan))]
    losses = np.array([r["loss"] for r in valid])
    T = max(np.median(losses), 1e-6)
    w = np.exp(-(losses - losses.min()) / T); w /= w.sum()

    rng = np.random.default_rng(seed)
    d = load_batch(batch_no)
    y0 = build_initial_state(d)
    v3 = d
    dcoef = load_death_coef() if death_term else None
    if verbose:
        _on = f"on (R2={dcoef['r2']}, n={dcoef['n_points']})" if dcoef else "off"
        print("death-term layer:", _on.encode("gbk", "replace").decode("gbk"), flush=True)
    tracks, failed = [], 0
    for e in range(n_ens):
        cell = valid[rng.choice(len(valid), p=w)]
        th = {"mux": float(cell["mux"]) + rng.normal(0, 0.010),
              "mup": float(cell["mup"]) + rng.normal(0, 0.0015),
              "m_s": float(cell["m_s"]) + rng.normal(0, 0.0015)}
        params = {"mux": th["mux"], "mup": th["mup"], "m_s": th["m_s"], "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": 10}
        try:
            sim, _ = simulate_open_loop(batch_no, params)
            if dcoef is not None:
                sim = sim.copy()
                sim["X"] = _death_corr(sim, dcoef)  # PH2 死亡层（v0.2 候选）
            tracks.append(sim[["time_h", "S", "P", "X", "PAA", "CO2d"]]
                          .set_index("time_h"))
            if verbose:
                print(f"  member {e+1}/{n_ens} ok, loss={cell['loss']:.3f}", flush=True)
        except Exception as ee:
            failed += 1
            if verbose:
                print(f"  member {e+1} fail (I2):", type(ee).__name__, str(ee)[:80], flush=True)
    n_ok = len(tracks)
    big = pd.concat(tracks, keys=range(n_ok))
    grp = big.groupby(level=1)
    mean = grp.mean(); sd = grp.std(ddof=1)
    out = {"batch": batch_no, "n_ens_eff": n_ok, "n_fail": failed,
            "mean": mean.reset_index(), "sd": sd.reset_index()}
    cov = {}
    for ch, col in (("X_offline", "X"), ("P_offline", "P"), ("PAA_offline", "PAA")):
        num = den = 0
        for i, v in enumerate(pd.to_numeric(v3[ch], errors="coerce")):
            if not np.isfinite(v) or float(v3.loc[i, "time_h"]) <= 20:
                continue
            t_lab = float(v3.loc[i, "time_h"]) - 4.0
            if t_lab not in mean.index:
                continue
            den += 1
            if abs(mean.loc[t_lab, col] - float(v)) <= 1.96 * max(sd.loc[t_lab, col], 1e-9):
                num += 1
        cov[ch] = {"coverage_95ci": round(num / den, 3) if den else np.nan, "n": den}
    out["coverage"] = cov
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"batch": batch_no, "n_ens_eff": len(tracks),
                       "coverage": cov, "mean": mean.round(4).reset_index().to_dict("records"),
                       "sd": sd.round(4).reset_index().to_dict("records")}, f, default=str)
    if verbose:
        print("I3 coverage:", json.dumps(cov))
    return out


def coverage_check(res, v3):
    """I3：±1.96σ 区间对真值的覆盖率（X/P 化验点）。"""
    rows = pd.DataFrame(res)
    cov = {}
    for ch, key_mean, key_sd in (("X_offline", "X_sum", "X_sd"),
                                  ("P_offline", "P_mean", "P_sd"),
                                  ("PAA_offline", "PAA_mean", "PAA_sd")):
        if ch not in v3.columns:
            continue
        num = int(0); den = int(0)
        for i, v in enumerate(pd.to_numeric(v3[ch], errors="coerce")):
            if not np.isfinite(v) or float(v3.loc[i, "time_h"]) <= 20:
                continue
            rows_i = rows.iloc[(rows["time_h"] - float(v3.loc[i, "time_h"])).abs().argmin()]
            mu, sd = rows_i[key_mean], rows_i[key_sd]
            den += 1
            if abs(mu - float(v)) <= 1.96 * max(sd, 1e-9):
                num += 1
        cov[ch] = {"coverage_95ci": num / den if den else np.nan, "n": den}
    return cov


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=11)
    ap.add_argument("--ens", type=int, default=50)
    ap.add_argument("--mode", choices=["smooth", "enkf"], default="smooth")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    outp = a.out or f"runs/hier_est/{a.mode}_{a.batch:02d}.json"
    if a.mode == "smooth":
        res = ensemble_smooth(a.batch, n_ens=a.ens, out_path=outp)
    else:
        res = enkf_observe(a.batch, n_ens=a.ens, out_path=outp)
        v3 = load_batch(a.batch)
        print("I3 coverage:", json.dumps(coverage_check(res["records"], v3)))
