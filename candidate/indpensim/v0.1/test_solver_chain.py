# -*- coding: utf-8 -*-
"""R161 / D-75：回退链算子层单元测试（solver_chain）。

与 tools/r161_fallback_chain_probe.py 的分工：
  - 本文件：**单元级**、秒级、每次闸门都跑（pytest 自动收集）
  - 探针：**集成级**、分钟级、需显式调用（跑真实 EnKF 批次）

纪律（继承 D-78）：凡新增判据，必须有「不该触发」与「该触发」两组样本，
且必须做零信息对照（无证据 ⇒ 不得判健康）。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import solver_chain as sc  # noqa: E402


def _health(cv, fail_cum=None, z=None, cond=None, n=None, mean=None):
    n = n or len(cv)
    h = {"t": [float(i) for i in range(n)],
         "cv": [dict(c) for c in cv],
         "fail_cum": list(fail_cum) if fail_cum is not None else [0] * n}
    if z is not None:
        h["z"] = z
    if cond is not None:
        h["cond"] = cond
    if mean is not None:
        h["mean"] = [dict(mean) for _ in range(n)]
    return h


def test_health_nominal_is_healthy():
    """健康集合不得误报降级（假阳性率必须为 0）。"""
    h = _health([{"X": 3e-2, "P": 5e-2, "mup": 4e-2}],
                z=[{"DO2": 0.5}], cond=[1e4])
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert r["healthy"], r["reasons"]
    assert r["reasons"] == []


def test_health_spread_collapse_triggers():
    """集合 spread→0 必须触发（§3.2 EnKF 行）。

    持续性要求：连续 ≥ SPREAD_COLLAPSE_MIN_STEPS 步越限才算坍塌。
    """
    h = _health([{"X": 1e-12, "P": 5e-2}] * 5, z=[{"DO2": 0.5}] * 5,
                cond=[1e4] * 5, mean={"X": 20.0, "P": 5.0})
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert not r["healthy"]
    assert any("spread" in s for s in r["reasons"]), r["reasons"]


def test_health_floor_saturation_is_not_collapse():
    """地板饱和步不得误判为集合坍塌（R161 实测修正）。

    证据：b8 的 S 通道 raw_min(CV)=6.59e−16，全部来自「残糖被 guards 钳在
    1e-3 地板上」⇒ 所有成员必然相同 ⇒ CV→0 是守卫产物而非集合发散。
    """
    h = _health([{"S": 6.6e-16, "X": 2.8e-5, "P": 3.5e-2}] * 8,
                z=[{"DO2": 0.5}] * 8, cond=[1e4] * 8,
                mean={"S": 1.0e-3, "X": 20.0, "P": 5.0})
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert r["healthy"], r["reasons"]


def test_health_single_step_spike_is_not_collapse():
    """单点越限不构成持续坍塌（持续性判据）。"""
    h = _health([{"X": 3e-2, "P": 5e-2}, {"X": 1e-12, "P": 5e-2}] +
                [{"X": 3e-2, "P": 5e-2}] * 3,
                z=[{"DO2": 0.5}] * 5, cond=[1e4] * 5,
                mean={"X": 20.0, "P": 5.0})
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert r["healthy"], r["reasons"]


def test_health_fail_rate_triggers():
    """成员级积分失败率越限必须触发。"""
    h = _health([{"X": 3e-2, "P": 5e-2}], fail_cum=[0, 40])
    r = sc.enkf_health(h, integration_failures=40, n_ens=40)
    assert not r["healthy"]
    assert any("失败率" in s for s in r["reasons"]), r["reasons"]


def test_health_innovation_triggers():
    """标准化创新越界必须触发（限判据白名单通道）。"""
    h = _health([{"X": 3e-2, "P": 5e-2}], z=[{"CO2outgas": 12.0}],
                cond=[1e4])
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert not r["healthy"]
    assert any("创新" in s for s in r["reasons"]), r["reasons"]


def test_health_excluded_channel_innovation_does_not_trigger():
    """非判据通道（Q/T）创新越限**不得**触发降级（D-78 纪律 + D-82）。

    实测依据（b8 真实批，1050 步）：Q 越限 99.1%（|z|max=4720）、T 越限 76.8%
    （|z|max=19.8），而根因是**模型的** T 偏高 2–4 K、Q 发散 4 倍 ⇒ 这些通道的
    |z| 在所有批上恒真越限。若纳入判据，创新判据即退化为恒真判据。
    """
    h = _health([{"X": 3e-2, "P": 5e-2}], z=[{"Q": 4720.0, "T": 19.8}],
                cond=[1e4])
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert r["healthy"], r["reasons"]
    # 但越限事实必须被记录（不得静默丢弃）
    excluded = r["metrics"].get("innovation_over_limit_counts_excluded", {})
    assert excluded.get("Q", 0) >= 1 and excluded.get("T", 0) >= 1


def test_health_singular_cov_triggers():
    """增益协方差近奇异必须触发。"""
    h = _health([{"X": 3e-2, "P": 5e-2}], z=[{"DO2": 0.5}], cond=[1e15])
    r = sc.enkf_health(h, integration_failures=0, n_ens=40)
    assert not r["healthy"]
    assert any("奇异" in s for s in r["reasons"]), r["reasons"]


def test_health_zero_info_not_healthy():
    """零信息对照：无探针 / 空序列 / 无 cv 键 ⇒ 不得判健康（纪律 19）。"""
    for h in (None, {"t": [], "cv": [], "fail_cum": []},
              {"t": [0.0, 1.0], "fail_cum": [0, 0]}):
        r = sc.enkf_health(h)
        assert not r["healthy"], (h, r["reasons"])
        assert r["reasons"], "不健康必须给原因（§3.3 禁止静默）"


def test_degradation_guard_is_explicit():
    """降级触发器必须永远返回显式 tier 与 reasons。"""
    h = _health([{"X": 1e-12, "P": 5e-2}] * 5, mean={"X": 20.0, "P": 5.0})
    hr = sc.enkf_health(h)
    g = sc.degradation_guard(hr)
    assert g["tier"] == sc.TIER_MHE
    assert g["degraded"] is True
    assert g["explicit"] is True
    assert g["reasons"]
    # 健康时不得降级
    hok = sc.enkf_health(_health([{"X": 3e-2}], z=[{"DO2": 0.1}], cond=[1e4]))
    gok = sc.degradation_guard(hok)
    assert gok["tier"] == sc.TIER_ENKF and not gok["degraded"]


def test_chain_exhausted_is_explicit_failure():
    """链穷尽 ⇒ explicit_failure（不得输出貌似合理的数）。"""
    hr = sc.enkf_health(_health([{"X": 1e-12, "P": 5e-2}] * 5, mean={"X": 20.0, "P": 5.0}))
    chain = sc.resolve_tier(hr, mhe_result=None, steady_result=None)
    assert chain["tier"] == sc.TIER_FAILED
    rings = [t["ring"] for t in chain["trace"]]
    assert rings == [sc.TIER_ENKF, sc.TIER_MHE, sc.TIER_STEADY, sc.TIER_FAILED]
    assert chain["reasons"]


def test_chain_healthy_stays_on_enkf():
    """健康批 ⇒ 停在 EnKF 环，不得降级。"""
    hr = sc.enkf_health(_health([{"X": 3e-2}], z=[{"DO2": 0.1}], cond=[1e4]))
    chain = sc.resolve_tier(hr)
    assert chain["tier"] == sc.TIER_ENKF
    assert len(chain["trace"]) == 1


def test_chain_mhe_pass_stops_at_mhe():
    """EnKF 不健康但 MHE 可解 ⇒ 停在 MHE 环。"""
    hr = sc.enkf_health(_health([{"X": 1e-12, "P": 5e-2}] * 5, mean={"X": 20.0, "P": 5.0}))
    mhe = {"solver_failed": False, "no_structure": False,
           "rel_improvement": 0.5, "message": "ok"}
    chain = sc.resolve_tier(hr, mhe_result=mhe)
    assert chain["tier"] == sc.TIER_MHE
    assert [t["ring"] for t in chain["trace"]] == [sc.TIER_ENKF, sc.TIER_MHE]


def test_chain_steady_state_fallback():
    """MHE 失败但稳态基线可信 ⇒ 停在稳态基线环。"""
    hr = sc.enkf_health(_health([{"X": 1e-12, "P": 5e-2}] * 5, mean={"X": 20.0, "P": 5.0}))
    mhe = {"solver_failed": True, "no_structure": True,
           "rel_improvement": 0.0, "message": "fail"}
    steady = sc.steady_state_baseline(1000.0, {"CO2": 400.0, "P": 300.0},
                                      x_hint_g=300.0)
    chain = sc.resolve_tier(hr, mhe_result=mhe, steady_result=steady)
    assert chain["tier"] == sc.TIER_STEADY


def test_mhe_structured_residual_solvable():
    """有结构的残差 ⇒ MHE 判为可解。"""
    r = sc.mhe_step(lambda x: np.array([x[0] - 0.5, x[1] + 0.25]),
                     x0=np.array([0.0, 0.0]),
                     bounds=[(-2.0, 2.0), (-2.0, 2.0)])
    assert not r["solver_failed"], r["message"]
    assert not r["no_structure"]
    assert np.allclose(r["x"], [0.5, -0.25], atol=1e-3)


def test_mhe_flat_residual_no_structure():
    """无结构残差 ⇒ MHE 判为残差无结构（→ 降级稳态基线）。"""
    r = sc.mhe_step(lambda x: np.array([1.0, 1.0]),
                     x0=np.array([0.0, 0.0]),
                     bounds=[(-2.0, 2.0), (-2.0, 2.0)])
    assert r["no_structure"], r


def test_mhe_solver_exception_is_failed():
    """求解器异常 ⇒ 显式 solver_failed。"""
    def boom(x):
        raise RuntimeError("synthetic")
    r = sc.mhe_step(boom, x0=np.array([0.0]), bounds=[(-1.0, 1.0)])
    assert r["solver_failed"]


def test_steady_state_backsolve_and_closure():
    """稳态基线：反解 + C 平衡闭合判据。"""
    ok = sc.steady_state_baseline(1000.0, {"CO2": 400.0, "P": 300.0},
                                  x_hint_g=300.0)
    assert ok["credible"]
    assert ok["tier"] == sc.TIER_STEADY
    assert abs(ok["x_carbon_g"] - 300.0) < 1e-9

    bad = sc.steady_state_baseline(1000.0, {"CO2": 100.0, "P": 100.0},
                                   x_hint_g=2000.0)
    assert not bad["credible"]
    assert bad["tier"] == sc.TIER_FAILED
    assert abs(bad["c_error_pct"] - 120.0) < 1e-6


def test_steady_state_boundary_exactly_20pct():
    """判据是「>20% 才失败」，恰好 20% 判为可信。"""
    r = sc.steady_state_baseline(1000.0, {"CO2": 0.0, "P": 0.0},
                                 x_hint_g=1200.0)
    assert abs(r["c_error_pct"] - 20.0) < 1e-9
    assert r["credible"]


def test_classify_enkf_output_without_probe_is_degraded():
    """无 health 探针的 EnKF 输出 ⇒ 不得判健康（无证据不得默认健康）。"""
    chain = sc.classify_enkf_output({"records": [], "integration_failures": 0,
                                      "n_ens": 40})
    assert chain["tier"] != sc.TIER_ENKF
    assert chain["reasons"]
