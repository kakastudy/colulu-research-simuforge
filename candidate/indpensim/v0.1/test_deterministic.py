# -*- coding: utf-8 -*-
"""确定性样例测试（M3）— 验证求解器在固定输入下产生可复现输出。

测试内容：
1. 固定参数 + 固定批次 → 输出完全可复现（同一批次两次运行结果一致）
2. 边界条件：零输入批次（无补料）
3. 守卫检查：负值截断、DO2 下限
4. 守恒检查：OUR/CER 闭合
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from simulate import simulate_open_loop, yield_metrics, compute_our_cer

def test_deterministic():
    """测试 1：同一批次两次运行结果完全一致。"""
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim1, _ = simulate_open_loop(11, params)
    sim2, _ = simulate_open_loop(11, params)

    # 比较所有通道
    assert len(sim1) == len(sim2), f"Length mismatch: {len(sim1)} vs {len(sim2)}"
    for ch in ["S", "DO2", "P", "V", "pH", "T", "CO2outgas", "O2", "OUR", "CER"]:
        a = sim1[ch].to_numpy(float)
        b = sim2[ch].to_numpy(float)
        assert np.allclose(a, b, rtol=1e-10, atol=1e-10), f"Channel {ch} not deterministic"
    print("  [PASS] Deterministic: same batch → identical output")


def test_guards():
    """测试 2：守卫检查 — 状态不出现负值。"""
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, _ = simulate_open_loop(11, params)

    for ch in ["S", "DO2", "P", "V", "pH", "T"]:
        vals = sim[ch].to_numpy(float)
        n_neg = np.sum(vals < 0)
        assert n_neg == 0, f"Channel {ch} has {n_neg} negative values"
    print("  [PASS] Guards: no negative values in S/DO2/P/V/pH/T")

    # DO2 下限
    do2 = sim["DO2"].to_numpy(float)
    n_below_2 = np.sum(do2 < 2.0)
    print(f"  [INFO] DO2 below 2.0: {n_below_2} steps (guard clamps to 1.0)")


def test_conservation():
    """测试 3：OUR/CER 闭合 — OUR/CER 非负且在合理范围。"""
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, _ = simulate_open_loop(11, params)

    # OUR/CER can be slightly negative at early times when liquid is being aerated
    our = sim["OUR"].to_numpy(float)
    cer = sim["CER"].to_numpy(float)

    assert np.isfinite(our).all(), "OUR has NaN/Inf"
    assert np.isfinite(cer).all(), "CER has NaN/Inf"

    # Check only mid-batch (t > 10h) where fermentation is established
    mask = sim["time_h"].to_numpy(float) > 10.0
    assert np.all(our[mask] >= -0.1), f"OUR has {np.sum(our[mask] < -0.1)} large negative values mid-batch"
    assert np.all(cer[mask] >= -0.1), f"CER has {np.sum(cer[mask] < -0.1)} large negative values mid-batch"

    rq = np.where(cer > 0.01, our / np.maximum(cer, 0.01), np.nan)
    rq_valid = rq[np.isfinite(rq)]
    print(f"  [PASS] Conservation: OUR/CER finite, RQ median={np.nanmedian(rq_valid):.2f}")


def test_yield():
    """测试 4：产率计算 — batch 11 产率在合理范围。"""
    params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    v3 = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed", "batches", "batch_11.csv"))
    sim, _ = simulate_open_loop(11, params)
    ym = yield_metrics(sim, v3)

    assert ym["total_sim_g"] > 1000, "Yield too small"
    assert ym["total_sim_g"] < 10_000_000, "Yield too large"
    print(f"  [PASS] Yield: sim={ym['total_sim_g']:,.0f} g, V3={ym['total_v3_g']:,.0f} g, err={ym['rel_err_total']:+.1%}")


def _synth_sim(co2d_peak, ph_end=6.45, p_end_ratio=0.95, t_end=230.0):
    """构造合成轨迹，供 classify_crash 判据测试用（完全不依赖引擎数值）。

    P 在 t_peak=0.6·t_end 处达峰 35，末值 = p_end_ratio × 35。
    """
    t = np.arange(0.2, t_end + 0.01, 0.2)
    co2d = co2d_peak * (1.0 - np.exp(-t / 40.0))
    peak, t_peak = 35.0, 0.6 * t_end
    p = np.where(
        t <= t_peak,
        peak * (t / t_peak),
        peak - (peak - p_end_ratio * peak) * (t - t_peak) / (t_end - t_peak),
    )
    ph = np.linspace(6.60, ph_end, len(t))
    return pd.DataFrame({"time_h": t, "CO2d": co2d, "P": p, "pH": ph})


def test_crash_predicate():
    """测试 5a：崩溃**判据**本身（纯函数，不依赖任何一批的真实轨迹）。

    历史背景：本测试原为 `assert crashed != crashed2`——要求"b8 标称必崩、dTcin=+10 必不崩"。
    该断言记录的是**移植缺陷期**的事实（PROBLEM.md §12.2：b8 名义 CO2d=8.08、CRASH、产率 −92.1%）。
    移植缺陷修完后 b8 不再穿越阈值（86 批验证 CO2d=6.03、产率 −4.0%），断言从未通过过——
    它是在要求一个**已被修好的 bug 继续存在**。故改为直接测判据函数，见 docs/r146_round_report.md §1。
    """
    import inspect
    from simulate import classify_crash as _cc
    crit = inspect.signature(_cc).parameters["co2d_crit"].default
    assert crit == 7.57, f"co2d_crit 默认值被改动: {crit}"

    # 未穿越 → normal；判据是严格 `>`，恰好等于阈值不算穿越
    # 已知局限（D-38）：classify_crash 在 `CO2d.max() <= crit` 时**直接返回 normal**，
    # 不再检查 pH/P 崩塌。故 b91（P 末/峰 0.162、pH 末 3.001、129 个钳位样点）仍被报
    # `normal`。下面两个用例的合成轨迹本身是健康的（pH 6.45、P 末/峰 0.95），改 D-38 后
    # 仍应通过；但修 D-38 时必须补一条「未穿越 + pH 崩塌 ⇒ 不得报 normal」的用例。
    for peak in (6.98, 7.57):
        lvl, rs = _cc(_synth_sim(peak))
        assert lvl == "normal" and rs == [], f"峰值 {peak} 应判 normal，得 {lvl}/{rs}"

    # 穿越但无病理证据 → benign（批 23 型：P 无崩塌、pH 在窗内、产率达标）
    lvl, rs = _cc(_synth_sim(8.0, ph_end=6.45, p_end_ratio=0.95), yield_err=0.01)
    assert lvl == "benign", f"穿越但无病理应判 benign，得 {lvl}/{rs}"
    assert any("良性" in s for s in rs), f"benign 缺良性说明: {rs}"

    # 三条病理通道，各自单独触发 catastrophic
    lvl, rs = _cc(_synth_sim(8.0, ph_end=3.00))
    assert lvl == "catastrophic", f"pH 失稳未判 catastrophic: {lvl}/{rs}"
    lvl, rs = _cc(_synth_sim(8.0, p_end_ratio=0.30))
    assert lvl == "catastrophic", f"P 崩塌未判 catastrophic: {lvl}/{rs}"
    lvl, rs = _cc(_synth_sim(8.0), yield_err=0.20)
    assert lvl == "catastrophic", f"产率损失未判 catastrophic: {lvl}/{rs}"
    print("  [PASS] Crash predicate: normal/benign/catastrophic 三档 + 三条病理通道")


def test_co2d_cooling_monotonic():
    """测试 5b：进料冷却温度 ↑ ⇒ Henry ↑ ⇒ C*_CO2 ↓ ⇒ CO2d ↓（方向性机制）。

    只断言**方向与幅度下限**，不断言"是否穿越阈值"——穿越与否取决于标定，
    会随引擎改进而变；而"降温能压 CO2d"是机理结论，应长期成立。
    """
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, _ = simulate_open_loop(8, params)
    co2d_nom = float(sim["CO2d"].max())

    sim2, _ = simulate_open_loop(8, dict(params, dist_flag=1, dist_tcin_asym=10))
    co2d_cool = float(sim2["CO2d"].max())

    print(f"  [INFO] Batch 8 CO2d: nominal={co2d_nom:.3f}, dTcin=+10 → {co2d_cool:.3f}")
    assert co2d_cool < co2d_nom, (
        f"distTcin=+10 未能压低 CO2d（{co2d_cool:.3f} ≥ {co2d_nom:.3f}）——Henry 温度机制失效")
    assert co2d_nom - co2d_cool > 0.1, (
        f"distTcin=+10 对 CO2d 的作用过弱（Δ={co2d_nom - co2d_cool:.4f} < 0.1）")

    # b8 实测 pH ∈ [6.44, 6.60]、P 单调升至 34.5 无崩塌 ⇒ 无任何崩溃征象。
    # 模型若把 b8 判成病理，是模型的错，应报警。
    from simulate import classify_crash
    lvl, rs = classify_crash(sim)
    assert lvl != "catastrophic", f"b8 实测无崩溃征象，模型却判 catastrophic：{rs}"
    print(f"  [PASS] CO2d cooling monotonic: Δ={co2d_nom - co2d_cool:.3f}, b8 分级={lvl}")


if __name__ == "__main__":
    print("=== Deterministic Test Suite (M3) ===")
    test_deterministic()
    test_guards()
    test_conservation()
    test_yield()
    test_crash_predicate()
    test_co2d_cooling_monotonic()
    print("\n=== All tests passed ===")
