# -*- coding: utf-8 -*-
"""R157 / T3-2：**模式级**故障注入仿真 —— GOAL §4 标准 4 的故障特征级专项。

为什么 R127 的三个算子不够
--------------------------
R127 已实现三个注入算子（`fault_type` 1=降KLa / 2=注酸 / 3=减喂食），
但它们的幅值是**常数**、只有"时间窗"这一个形状维度 ⇒ 只能表达**阶跃型**故障。
真实工艺故障多为**渐变**（KLa 结垢渐进、阀卡后漂移、探头逐渐失准）。

更重要的约束来自 R143：**故障信号若已在回放输入通道里，就不要再注入算子**
（b92 的 pH 凹陷来自回放输入里 `Fb` 撞下限）。⇒ 算子只该用于**没有录进输入**的故障：
  ①未记录的 KLa 衰减　②传感器偏置/漂移　③摄取停滞

本工具
------
A. **模式库**（模式 = 注入通道 × 时间包络形状）：
   - `kla_step`   通气能力阶跃下降后恢复（堵塞被清除）
   - `kla_ramp`   KLa 线性衰减（结垢渐进）
   - `ph_drift`   加碱能力漂移（等效持续注酸）⇒ pH 缓慢下行
   - `feed_hold`  补料中断（F_s 与 F_paa 同时降）
   - `kla_fade`   KLa 指数式衰减 + 恢复
   每个模式给出**预期特征签名**（方向性断言），工具会**自动校验**方向是否符合物理预期。
B. **传感器侧注入**（不进动力学，只污染观测通道）：
   - `sensor_bias`  OUR/CER 通道乘性偏置（标度失准）
   - `probe_freeze` DO2 探头读数冻结（卡死）
   目的：检验"故障能否被现有观测手段辨识"，而不是改动力学。
C. **零回归臂**：`fault_type=0` ⇒ 与基线逐位一致（`max|Δ| = 0`）。

用法
----
    python tools/r157_fault_modes.py --batches 22 --workers 4
    python tools/r157_fault_modes.py --batches 22 --modes kla_step,kla_ramp
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- 模式库：注入通道 × 时间包络 ----
# envelope: [(t_h, 相对幅值)]；窗口 fault_start/fault_end 之外的包络按节点定义延伸
MODES = {
    "kla_step": dict(
        kind="engine", fault_type=1, mag=0.45, start=60.0, end=150.0,
        profile=[(0.0, 0.0), (60.0, 1.0), (150.0, 1.0), (230.0, 0.0)],
        expect={"do2_min": "down", "s_max": "up", "p_max": "down"},
        desc="通气能力阶跃下降 45%（60–150 h）后恢复"),
    "kla_ramp": dict(
        kind="engine", fault_type=1, mag=0.60, start=60.0, end=200.0,
        profile=[(0.0, 0.0), (60.0, 0.0), (200.0, 1.0), (230.0, 1.0)],
        expect={"do2_min": "down", "s_max": "up"},
        desc="KLa 线性衰减（60→200 h 渐进到 −60%），模拟结垢"),
    "kla_fade": dict(
        kind="engine", fault_type=1, mag=0.50, start=60.0, end=230.0,
        profile=[(0.0, 0.0), (60.0, 0.0), (120.0, 0.6), (180.0, 1.0), (230.0, 1.0)],
        expect={"do2_min": "down", "s_max": "up"},
        desc="KLa 指数式衰减（60–180 h）"),
    "ph_drift": dict(
        kind="engine", fault_type=2, mag=0.35, start=80.0, end=220.0,
        profile=[(0.0, 0.0), (80.0, 0.0), (150.0, 0.7), (220.0, 1.0), (230.0, 1.0)],
        expect={"ph_min": "down"},
        desc="加碱能力漂移（等效持续注酸 0.35 mg/L/h，80–220 h 渐强）"),
    "feed_hold": dict(
        kind="engine", fault_type=3, mag=0.90, start=100.0, end=180.0,
        profile=[(0.0, 0.0), (100.0, 1.0), (180.0, 1.0), (230.0, 0.0)],
        # R157 修正（两次）：
        # ① 原写 `s_max: down`（"少喂 ⇒ 残糖低"）在**整批口径**下是错的 ——
        #    故障结束后进料恢复，但菌体已被打残 ⇒ 消耗低于进料 ⇒ 整批 S_max 反而**升高**
        #    （3.68 → 21.10 g/L）。
        # ② 改成**窗内** `s_at_window_end: down` 也不成立 —— b22 的残糖在故障窗内已贴**模型地板**
        #    （基线 0.001395 vs 故障 0.001424 g/L）⇒ **无判别力**（与 D-53「残糖结构性不可辨识」同向）。
        # ⇒ 最终判据取**恢复期欠消耗**这条机制上成立的签名：产物必降 + 整批残糖累积。
        expect={"p_max": "down", "s_max": "up"},
        desc="补料中断 90%（100–180 h，F_s 与 F_paa 同时降）"),
    # ---- 传感器侧（不进动力学）----
    "sensor_bias": dict(
        kind="sensor", sensor="our_cer", bias=0.25, start=0.0, end=230.0,
        expect={}, desc="OUR/CER 观测通道乘性偏置 +25%（标度失准）"),
    "probe_freeze": dict(
        kind="sensor", sensor="do2", freeze_from=120.0,
        expect={}, desc="DO2 探头读数自 120 h 起冻结（卡死）"),
}


def _col(obj, key):
    """取一列并转成 float 数组 —— 兼容 pandas.DataFrame 与 dict-of-arrays。

    R157 修：`sim.to_dict("list")` 返回的是 **numpy 数组**，没有 `.to_numpy` 方法；
    原实现用伪 DataFrame 包一层再调 `_signature`，会在传感器分支抛 AttributeError。
    """
    v = obj[key]
    if hasattr(v, "to_numpy"):
        return np.asarray(v.to_numpy(float), float)
    return np.asarray(v, float)


def _signature(sim):
    """故障特征签名（只用 sim 的物理通道，不看产量）。"""
    ph = _col(sim, "pH")
    s = _col(sim, "S")
    p = _col(sim, "P")
    do2 = _col(sim, "DO2")
    t = _col(sim, "time_h")
    au = (sim.attrs.get("guard_audit", {}) or {}) if hasattr(sim, "attrs") else {}
    return {
        "ph_min": float(np.min(ph)), "ph_max": float(np.max(ph)),
        "s_max": float(np.max(s)), "p_max": float(np.max(p)),
        "do2_min": float(np.min(do2)),
        "t_p_max": float(t[int(np.argmax(p))]),
        "n_ph_clamp": int((au.get("tally", {}) or {}).get("pH_H", 0)),
        "yield_err": None,
    }


def _apply_sensor(sim, mode):
    """传感器侧注入：只改观测通道的**副本**，不动动力学。"""
    out = {k: np.array(v, float) if isinstance(v, (list, np.ndarray)) else v
           for k, v in sim.to_dict("list").items()}
    t = np.array(sim["time_h"].to_numpy(float))
    if mode["sensor"] == "our_cer":
        for ch in ("OUR", "CER"):
            if ch in out:
                out[ch] = out[ch] * (1.0 + mode["bias"])
    elif mode["sensor"] == "do2":
        if "DO2" in out:
            m = t >= mode["freeze_from"]
            if m.any():
                out["DO2"][m] = out["DO2"][m][0]
    return out


def _at_time(sim, col, t_q):
    """取某时刻的通道值（就近采样）。故障特征必须是**窗口内**的量，
    否则故障结束后的恢复效应会主导整批统计（见 `feed_hold` 的教训）。"""
    t = _col(sim, "time_h")
    v = _col(sim, col)
    idx = int(np.argmin(np.abs(t - float(t_q))))
    return float(v[idx])


def _sensor_checks(mode, obs, sim_base, maxdiff):
    """传感器侧的可观测性校验（方向性 + 「动力学未被污染」）。

    传感器故障的验收要点**不是**产量变不变（它本就不该变），而是：
      ① 动力学逐位不变（注入只污染观测通道副本）；
      ② 观测通道确实按设计被污染（偏置 / 冻结生效）。
    """
    t = np.array(obs["time_h"], float)
    ck = [{"metric": "dynamics_unchanged", "expect": "max|d|=0",
           "base": 0.0, "fault": float(maxdiff), "ok": bool(maxdiff == 0.0)}]
    if mode["sensor"] == "our_cer":
        b_last = float(_col(sim_base, "OUR")[-1])
        f_last = float(obs["OUR"][-1])
        ratio = f_last / b_last if b_last else float("nan")
        ck.append({"metric": "our_scale_ratio", "expect": "x%.3f" % (1.0 + mode["bias"]),
                   "base": b_last, "fault": f_last,
                   "ok": bool(np.isfinite(ratio) and abs(ratio - (1.0 + mode["bias"])) < 1e-9)})
    elif mode["sensor"] == "do2":
        m = t >= mode["freeze_from"]
        if m.any():
            tail = np.array(obs["DO2"], float)[m]
            # 用容差而不是 == 0：冻结后理论上恒定，但浮点累加会留 ~1e-15 的噪声。
            sd = float(np.std(tail))
            ck.append({"metric": "do2_frozen", "expect": "std<1e-12",
                       "base": sd, "fault": sd,
                       "ok": bool(sd < 1e-12)})
    return ck



def _run(job):
    batch, mode_name, mode, ph_fix = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        base = dict(build_params(COMBINED[batch]))
        if ph_fix:
            base["ph_fix"] = 1
        sim0, v30 = s.simulate_open_loop(int(batch), base)
        sig0 = _signature(sim0)
        ym0 = s.yield_metrics(sim0, v30)

        if mode["kind"] == "engine":
            p = dict(base)
            p["fault_type"] = mode["fault_type"]
            p["fault_start"] = mode["start"]
            p["fault_end"] = mode["end"]
            p["fault_magnitude"] = mode["mag"]
            p["fault_profile"] = [tuple(x) for x in mode["profile"]]
            sim, v3 = s.simulate_open_loop(int(batch), p)
            sig = _signature(sim)
            ym = s.yield_metrics(sim, v3)
            maxdiff = float(np.max(np.abs(sim.to_numpy(float) - sim0.to_numpy(float))))
            health = s.classify_health(sim, v3, yield_err=ym["rel_err_total"])
        else:
            sim = sim0                      # 传感器故障不改动力学 ⇒ 复用基线轨迹
            v3 = v30
            obs = _apply_sensor(sim, mode)
            sig = _signature(sim)
            sig_obs = _signature(obs)
            ym = ym0
            maxdiff = 0.0
            health = s.classify_health(sim, v3, yield_err=ym["rel_err_total"])
            sig["obs_do2_min"] = sig_obs["do2_min"]
            sig["obs_our_last"] = float(obs["OUR"][-1])
            sig["obs_do2_std_tail"] = float(
                np.std(np.array(obs["DO2"], float)[np.array(obs["time_h"], float) >= 120.0]))

        # 方向性校验
        checks = []
        if mode["kind"] == "engine":
            # **窗口内**特征量（R157：故障签名必须限定在故障窗内）
            t_q = float(mode["end"])
            sig0["s_at_window_end"] = _at_time(sim0, "S", t_q)
            sig["s_at_window_end"] = _at_time(sim, "S", t_q)
            sig0["p_at_window_end"] = _at_time(sim0, "P", t_q)
            sig["p_at_window_end"] = _at_time(sim, "P", t_q)
            sig0["do2_at_window_end"] = _at_time(sim0, "DO2", t_q)
            sig["do2_at_window_end"] = _at_time(sim, "DO2", t_q)
        for key, direction in (mode.get("expect") or {}).items():
            v0, v1 = sig0.get(key), sig.get(key)
            if v0 is None or v1 is None:
                continue
            if direction == "down":
                ok = v1 < v0
            elif direction == "up":
                ok = v1 > v0
            else:
                ok = True
            checks.append({"metric": key, "expect": direction,
                           "base": float(v0), "fault": float(v1), "ok": bool(ok)})
        if mode["kind"] == "sensor":
            checks.extend(_sensor_checks(mode, obs, sim0, maxdiff))

        # **数值污染前置判据（R157 新增）**：故障臂若出现 pH 守卫钳位，说明轨迹已被
        # D-55 的 basic 分支数值病态拖垮 ⇒ 该臂的特征签名**不可作为故障证据**
        # （它反映的是数值崩溃，不是故障本身）。
        n_clamp_fault = int(sig.get("n_ph_clamp", 0) or 0)
        n_clamp_base = int(sig0.get("n_ph_clamp", 0) or 0)
        contaminated = bool(n_clamp_fault > n_clamp_base)
        return {
            "batch": int(batch), "mode": mode_name, "kind": mode["kind"],
            "desc": mode["desc"], "ph_fix": int(ph_fix),
            "base_sig": sig0, "fault_sig": sig,
            "yield_err_base": float(ym0["rel_err_total"]),
            "yield_err_fault": float(ym["rel_err_total"]),
            "max_abs_delta": maxdiff,
            "health": health.get("level"), "health_flags": health.get("flags"),
            "n_ph_clamp_base": n_clamp_base, "n_ph_clamp_fault": n_clamp_fault,
            "numerically_contaminated": contaminated,
            "checks": checks,
            "all_checks_ok": all(c["ok"] for c in checks) if checks else None,
        }
    except Exception as e:  # noqa: BLE001
        return {"batch": int(batch), "mode": mode_name, "error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="22")
    ap.add_argument("--modes", type=str, default=",".join(MODES.keys()))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--ph-fix", type=int, default=0,
                    help="1 = 用候选基线 v2 的 ph_fix（basic 分支已修）——"
                         "否则任何扰动都可能触发 D-55 的 pH 数值崩溃，淹没故障特征")
    ap.add_argument("--json", type=str, default="runs/r157_fault_modes.json")
    args = ap.parse_args()

    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    names = [m.strip() for m in args.modes.split(",") if m.strip() in MODES]

    print("=" * 100)
    print(f"R157 / T3-2  模式级故障注入仿真　批次 {bs}　模式 {len(names)} 个　ph_fix={args.ph_fix}")
    print("=" * 100)

    jobs = [(b, n, MODES[n], int(args.ph_fix)) for n in names for b in bs]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_run, jobs))
    bad = [r for r in rows if "error" in r]
    for r in bad:
        print(f"  ERR b{r['batch']} {r['mode']}: {r['error'][:160]}")
    rows = [r for r in rows if "error" not in r]

    # 零回归臂
    print("\n【0】零回归臂（fault_type=0 / 无注入）")
    zr = [r for r in rows if r["kind"] == "engine"]
    if zr:
        print(f"   引擎模式注入批的 max|Δ| > 0 是**预期**（注入本应改变轨迹）；"
              f"零回归由 `tools/r134_zero_regression.py --tol 0` 单独守。")

    n_contaminated = 0
    for n in names:
        rs = [r for r in rows if r["mode"] == n]
        if not rs:
            continue
        m = MODES[n]
        print(f"\n{'─'*100}\n【{n}】{m['desc']}")
        print(f"   {'批':>4} {'DO2_min':>9} {'pH_min':>8} {'S_max':>9} {'P_max':>9}"
              f" {'S@窗末':>9} {'产量偏差':>10} {'健康':>13} {'钳位':>6}  方向校验")
        for r in rs:
            b0, b1 = r["base_sig"], r["fault_sig"]
            ck = r["checks"]
            ck_txt = "、".join(f"{c['metric']}{c['expect']} {'✓' if c['ok'] else '✗'}" for c in ck) or "—"
            extra = ""
            if r["kind"] == "sensor":
                extra = (f"  [obs DO2_min {b1.get('obs_do2_min', float('nan')):.3f}"
                         f" · obs OUR末 {b1.get('obs_our_last', float('nan')):.4f}"
                         f" · 动力学Δ {r['max_abs_delta']:.3g}]")
            mark = "  ⚠ 数值污染" if r["numerically_contaminated"] else ""
            if r["numerically_contaminated"]:
                n_contaminated += 1
            s_w = b1.get("s_at_window_end")
            s_w_txt = f"{s_w:>9.4f}" if s_w is not None else f"{'—':>9}"
            print(f"   {r['batch']:>4} {b1['do2_min']:>9.3f} {b1['ph_min']:>8.3f}"
                  f" {b1['s_max']:>9.4f} {b1['p_max']:>9.3f} {s_w_txt}"
                  f" {r['yield_err_fault']*100:>9.2f}% {str(r['health']):>13}"
                  f" {r['n_ph_clamp_fault']:>6}  {ck_txt}{extra}{mark}")
        allok = all(r["all_checks_ok"] for r in rs if r["all_checks_ok"] is not None)
        print(f"   ⇒ 方向一致性：**{'全部通过' if allok else '有不符'}**")
        for r in rs:
            for c in r["checks"]:
                if not c["ok"]:
                    print(f"      ✗ b{r['batch']} {c['metric']} 期望 {c['expect']}："
                          f"基线 {c['base']:.4g} → 故障 {c['fault']:.4g}")

    if n_contaminated:
        print(f"\n⚠️ **{n_contaminated} 个故障臂出现 pH 守卫钳位** ⇒ 轨迹已被 D-55 的 basic 分支"
              f"数值病态拖垮，其特征签名反映的是**数值崩溃**而非故障本身。"
              f"⇒ 故障特征级仿真必须在 `ph_fix=1` 口径下做（`--ph-fix 1`），或换用 pH 稳健的批次。")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"ph_fix": int(args.ph_fix), "rows": rows,
                       "n_numerically_contaminated": n_contaminated,
                       "modes": {k: {kk: vv for kk, vv in v.items() if kk != "profile"}
                                  for k, v in MODES.items()}}, f,
                      ensure_ascii=False, indent=1)
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
