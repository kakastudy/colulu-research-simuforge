import re

p = "tools/r135_b55_b91_attrib.py"
s = open(p, encoding="utf-8").read()
start = s.index("def analyse(batch")
end = s.index("def main():")
new_block = '''def _verdict(err0_pct, el, probes):
    """按弹性谱下结论。

    判据修正记录（首版错在哪）：首版把"弹性 >=2pp"直接叫"瓶颈候选"，这是把
    **敏感性**当成了**归因**。对一台已经在红线内的批，"Fs +10% 让产量掉 96pp"
    不代表底物供给是残差的原因，只代表**产量对进料极度敏感**（贴着分岔边界）。
    正确的两件事必须分开说：
      - 抑制项 delta ~ 0  -> 该机制**未激活**，可从解释里**排除**（硬证据）；
      - 产率/进料 delta 很大 -> **高杠杆**，但方向一错就过冲，**不可用于修补**。
    """
    flags = []
    d_paa = abs(el["C1_paa_inhib_off"])
    d_do2 = abs(el["C2_do2_inhib_off"])
    lev_a = abs(el["A_yield_ceiling_mup_x110"])
    lev_b = abs(el["B_substrate_feed_x110"])
    lev = max(lev_a, lev_b)
    within = abs(err0_pct) <= 5.0

    if d_paa < 0.5:
        flags.append("PAA 抑制项未激活(delta~0)")
    if d_do2 < 0.5:
        flags.append("DO2 抑制项未激活(delta~0)")
    if within:
        flags.append("落点在 ±5% 红线内")
    if lev >= 20.0:
        flags.append(f"高产率杠杆 {lev:.0f}pp/10% -> 近分岔，不可微调")

    if within and lev >= 20.0:
        verdict = "redline_near_bifurcation"
        why = (f"基线 {err0_pct:+.2f}% 已在红线内，但 10% 级进料/产率变化即可把产量推出 ±20%"
               f"（A {el['A_yield_ceiling_mup_x110']:+.1f}pp / B {el['B_substrate_feed_x110']:+.1f}pp）"
               f" -> 落点贴着分岔边界，只能评估不能微调")
    elif within:
        verdict = "redline_clean"
        why = (f"基线 {err0_pct:+.2f}%，产率/进料弹性仅 {lev:.1f}pp/10%（远离分岔），"
               f"抑制项 delta~0 -> 该批无未解释的产量残差")
    elif lev >= 20.0:
        verdict = "high_leverage"
        why = (f"基线 {err0_pct:+.2f}% 超红线，产率/进料杠杆 {lev:.0f}pp/10% -> "
               f"可移动但会跨分岔，属结构性不可修补（强行凑参的路径已封）")
    else:
        verdict = "structural"
        why = (f"基线 {err0_pct:+.2f}%，三个维度弹性全部 <20pp（产率 {lev_a:.1f} / 进料 {lev_b:.1f} / "
               f"抑制 {d_paa:.1f},{d_do2:.1f}）-> 瓶颈不在这些维度，需改 ODE（V1+）")
    return verdict, why + "；" + "；".join(flags)


def analyse(batch):
    base = calib_params(batch)
    sim0, v3 = simulate_open_loop(batch, base)
    err0 = _yield_err(sim0, v3)

    probes = {}

    def run(tag, over):
        p = dict(base)
        p.update(over)
        sim, _ = simulate_open_loop(batch, p)
        e = _yield_err(sim, v3)
        probes[tag] = {"err": e, "delta_pp": round((e - err0) * 100.0, 2)}
        return e

    run("A_yield_ceiling_mup_x110", {"mup": base["mup"] * UPLIFT})
    run("B_substrate_feed_x110", {"mv_scales": {"Fs": UPLIFT}})
    run("C1_paa_inhib_off", {"P_crit_PAA": -1.0e3})
    run("C2_do2_inhib_off", {"P_crit_DO2": -1.0e3})
    run("D_all", {"mup": base["mup"] * UPLIFT, "mv_scales": {"Fs": UPLIFT},
                  "P_crit_PAA": -1.0e3, "P_crit_DO2": -1.0e3})

    diag = _diag(sim0, v3)
    el = {k: v["delta_pp"] for k, v in probes.items() if k != "D_all"}
    verdict, why = _verdict(err0 * 100.0, el, probes)
    additivity = {
        "sum_of_singles_pp": round(sum(el.values()), 2),
        "joint_pp": probes["D_all"]["delta_pp"],
        "interaction_pp": round(probes["D_all"]["delta_pp"] - sum(el.values()), 2),
    }
    return {
        "batch": int(batch),
        "mu_p": round(float(base["mup"]), 5),
        "err_base_pct": round(err0 * 100.0, 2),
        "probes": probes,
        "elasticity_pp_per_10pct": el,
        "additivity": additivity,
        "diag": diag,
        "verdict": verdict,
        "why": why,
    }


'''
s = s[:start] + new_block + s[end:]
open(p, "w", encoding="utf-8").write(s)
print("rewrote analyse/_verdict block")
