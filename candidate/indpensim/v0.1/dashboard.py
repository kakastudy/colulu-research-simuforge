# -*- coding: utf-8 -*-
"""M5 仿真引擎 + 看板入口（v0.3：双工作台分页）。

工作台模式（侧栏单选，互斥页）：
  🚀 运行面板 — 批次/参数/仿真 + 产率卡片 + B 档两阶段 + C 档寻优（结果自动持久化）
  📚 运行记录 — 列表浏览；**点「查看」某一条才进入该条的历史面板**，面板内可返回列表

运行：python -m streamlit run candidate/indpensim/v0.1/dashboard.py （DASH_NO_UI=1 走无头导入）
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from simulate import simulate_open_loop, yield_metrics, classify_crash
from soft_sensing import estimate_batch
from stage2_estimator import estimate_stage2
from calibration import calib_params, GOLDEN_NORMAL, GOLDEN_FAULT
from optimize import optimize_feed
from knowledge_constraints import paa_pat_trigger
import runstore

GOLDEN = GOLDEN_NORMAL + GOLDEN_FAULT

ONLINE_PAIRS = [
    ("DO2", "DO2", 0.0), ("O2", "O2", 0.0), ("V", "V", 0.0), ("pH", "pH", 0.0),
    ("T", "T", 0.0), ("Q", "Q", 0.0), ("CO2outgas", "CO2outgas", 0.0),
    ("NH3", "NH3_offline", 4.0), ("vis", "Viscosity_offline", 4.0),
    ("CO2d", None, 0.0),
]
OFFLINE_PAIRS = [
    ("S", "S", 0.0), ("P", "P", 0.0), ("X", "X_offline", 4.0),
    ("PAA", "PAA_offline", 4.0), ("NH3", "NH3_offline", 4.0),
]


def load_batch_data(batch_no):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return pd.read_csv(os.path.join(root, "data", "processed", "batches",
                                    f"batch_{batch_no:02d}.csv"))


def run_simulation(batch_no: int, params: dict):
    sim, _ = simulate_open_loop(batch_no, params)
    return sim


def pair_frame(sim, v3, sim_col, v3_col, lag=0.0):
    """Sim/V3 对照帧；lag>0 对齐化验时刻并扣 4h 滞后；返回 None 表示无该通道。"""
    if sim_col not in sim.columns:
        return None
    t_sim = sim["time_h"].to_numpy(float)
    s_all = sim[sim_col].to_numpy(float)
    have_v3 = v3_col is not None and v3_col in v3.columns
    if have_v3 and lag == 0.0:
        t_v3 = v3["time_h"].to_numpy(float)
        s_at = np.interp(t_v3, t_sim, s_all)
        v = pd.to_numeric(v3[v3_col], errors="coerce").to_numpy(float)
        okm = np.isfinite(v)
        return pd.DataFrame({"Sim": s_at[okm], "V3": v[okm]}, index=t_v3[okm])
    if have_v3 and lag > 0:
        mask = pd.to_numeric(v3[v3_col], errors="coerce").notna().to_numpy()
        if mask.sum() < 2:
            return pd.DataFrame({"Sim": pd.Series(s_all, index=t_sim)})
        lab = v3.loc[mask, "time_h"].to_numpy(float)
        s_at = np.interp(lab - lag, t_sim, s_all)
        v = pd.to_numeric(v3.loc[mask, v3_col], errors="coerce").to_numpy(float)
        return pd.DataFrame({"Sim": s_at, "V3": v}, index=lab)
    return pd.DataFrame({"Sim": pd.Series(s_all, index=t_sim)})


def batch_summary(sim, v3):
    ym = yield_metrics(sim, v3)
    lvl, reasons = classify_crash(sim, yield_err=float(ym["rel_err_total"]))
    return ym, lvl, reasons


TIER_DESC = {
    "A": "**做什么**：A 档机理引擎 — 把 V3 的实际操作量（补料/通气/搅拌/控温）回放到 33 维"
         "机理 ODE 求全状态轨迹，再与 V3 真值对产量/轨迹/守恒逐项评估。**为什么**：这是正问题"
         "基线，先证明引擎复现基准，后续软测量与寻优才有可信底板。看什么：产量偏差 ≤±5% 即达标。",
    "B": "**做什么**：B 档软测量（逆问题）— 从线上易测量（DO2/CO₂/pH/温度/尾气 OUR/CER）"
         "反推难确定的批次级参数（μx/μp/m_s/dTcin）。两阶段设计：第一段在线网格（54 组合）；"
         "第二段把 μp 锚定到 P_offline 化验（12h/滞后 4h）解决 μp 不可辨识性。看什么：第二阶段"
         "产率偏差与 P_offline RMSE 是核心结论指标。",
    "C": "**做什么**：C 档反设计寻优 — 把 V3 参考配方按倍率缩放（糖/油/前体补料、通气、搅拌），"
         "用 Nelder-Mead 在'仿真结果'上搜索更优操作条件。track_target=对准 V3 目标产量；"
         "max_yield=生产设计最大化。看什么：收敛曲线与最优倍率（越出验证域会有告警）。",
}


def b_trend_charts(result):
    """B stage-1 趋势：按 mup 聚合的 online_rmse / yield_err（54 组合 sweep）。"""
    sw = pd.DataFrame(result.get("sweep") or [])
    if len(sw) < 3:
        st.caption("（该记录无 sweep 数据——旧版记录，重跑一次即可获得趋势）")
        return
    agg = sw.groupby("mup").agg(online_rmse=("online_rmse", "mean"),
                                yield_err=("yield_err", "mean"),
                                崩溃率=("crashed", "mean")).reset_index().set_index("mup")
    st.caption("趋势一（探索性）：扫描 μp 对在线匹配误差与产率偏差的聚合影响"
               "（每 μp 为多组合均值；低识别力的 μp 表现为该曲线分叉大）")
    st.line_chart(agg[["online_rmse"]], use_container_width=True)
    st.line_chart(agg[["yield_err"]], use_container_width=True)


def b2_trend_charts(r2):
    """B stage-2 趋势：P_offline RMSE 与产率偏差 vs mup（扫描曲线）。"""
    scan = pd.DataFrame(r2.get("scan") or [])
    if "yield_err" not in scan.columns and len(scan):
        scan = scan.set_index("mup")
        st.caption("（旧版记录无产量列——重跑一次可获得完整扫描趋势）")
        st.line_chart(scan[["p_rmse"]], use_container_width=True)
        return
    if not len(scan):
        st.caption("（无扫描数据）")
        return
    scan = scan.set_index("mup")
    st.caption("趋势二：μp 扫描下的 P_offline 化验拟合误差（目标函数）——最小点即识别点")
    st.line_chart(scan[["p_rmse"]], use_container_width=True)
    st.caption("趋势三：μp 扫描下的产率偏差（独立评估）——陡峭斜率 = μp 的写实敏感度")
    st.line_chart(scan[["yield_err"]], use_container_width=True)


def c_trend_charts(r):
    """C 档收敛曲线：逐评估产量 + 累计最优（max_yield→最大；track_target→离目标最近）。"""
    hist = pd.DataFrame(r.get("history") or [])
    if not len(hist):
        st.caption("（该记录无收敛历史——旧版记录，重跑一次即可获得）")
        return
    h = hist.dropna(subset=["yield_g"]).set_index("eval")
    if not len(h):
        st.caption("（全部评估发散/越界）")
        return
    if r.get("objective", "max_yield") == "max_yield":
        best = h["yield_g"].cummax()
    else:
        target = float(r.get("opt_err_vs_v3", 0) * 0) if False else None
        # track_target：以离基线产量与 V3 目标的接近度衡量（无 V3 目标数值时退化为产量本身）
        # 观测：优化器输出 opt_err_vs_v3 为对 V3 偏差；由 opt 产量与偏差反推 V3 目标
        if "opt_yield_g" in r and "opt_err_vs_v3" in r:
            target = float(r["opt_yield_g"]) / (1.0 + float(r["opt_err_vs_v3"]))
        else:
            target = float(h["yield_g"].iloc[0])
        gap = (h["yield_g"] - target).abs()
        best = h["yield_g"].loc[gap.cummin().values == gap.values].drop_duplicates()
        best = best[~best.index.duplicated()] if len(best) else h["yield_g"]
    h = h.copy()
    h["best_so_far"] = best.reindex(h.index).ffill() if len(best) else h["yield_g"]
    chart = pd.DataFrame({"产量": h["yield_g"], "最优": h["best_so_far"]}, index=h.index)
    st.caption(f"趋势四：C 档收敛曲线（目标 {r.get('objective', 'max_yield')}，"
               f"{len(hist)} 次评估）")
    st.line_chart(chart, use_container_width=True)


def render_sim_panel(batch_no, sim, v3):
    ym, lvl, reasons = batch_summary(sim, v3)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("仿真产率 (g)", f"{ym['total_sim_g']:,.0f}")
    col2.metric("V3 产率 (g)", f"{ym['total_v3_g']:,.0f}")
    col3.metric("产率偏差", f"{ym['rel_err_total']:+.1%}")
    col4.metric("CO2d 峰值", f"{sim['CO2d'].max():.2f}",
                "⚠️ 穿越阈值" if sim["CO2d"].max() > 7.57 else "✅ 未穿越")
    col5.metric("崩溃分级", {"normal": "✅ normal", "benign": "🟡 benign",
                            "catastrophic": "🔴 catastrophic"}.get(lvl, lvl))
    with st.expander("崩溃分级证据链（I2 失败可见）"):
        for r in reasons or ["未穿越 CO2d 阈值"]:
            st.caption("· " + str(r))

    st.subheader("在线通道对比 (Sim vs V3)")
    cols = st.columns(3)
    for i, (sch, vch, lag) in enumerate(ONLINE_PAIRS):
        df = pair_frame(sim, v3, sch, vch, lag)
        if df is None:
            continue
        with cols[i % 3]:
            st.line_chart(df, use_container_width=True)
            label = sch if vch is None or vch == sch else f"{sch} ↔ {vch}"
            note = ("（仅 sim 有此通道）" if vch is None
                    else ("（化验滞后 4h 对齐）" if lag else ""))
            st.caption(label + note)

    st.subheader("离线通道对比 (Sim vs V3)")
    cols2 = st.columns(3)
    for i, (sch, vch, lag) in enumerate(OFFLINE_PAIRS):
        df = pair_frame(sim, v3, sch, vch, lag)
        if df is None:
            continue
        with cols2[i % 3]:
            st.line_chart(df, use_container_width=True)
            st.caption((sch if vch == sch else f"{sch} ↔ {vch}")
                       + ("（化验 +4h 滞后对齐）" if lag else ""))


# ---------------- 🚀 运行面板 ----------------

def run_panel():
    st.header("🚀 运行面板")
    with st.expander("🧭 A 档机理仿真 — 这一步在做什么？（工作说明）", expanded=False):
        st.markdown(TIER_DESC["A"])
    batch_no = st.sidebar.selectbox("选择批次", GOLDEN, index=GOLDEN.index(11))
    _cal = calib_params(batch_no)
    _sched = _cal.get("m_s_schedule")
    st.sidebar.caption(f"该批黄金校准基线：mux={_cal['mux']}, mup={_cal['mup']}, "
                       f"m_s={_cal['m_s']}, dTcin={_cal['dist_tcin_asym']:+d}"
                       + (f"，时变 m_s={_sched}" if _sched else ""))

    st.sidebar.header("仿真参数（默认=本批校准）")
    mux = st.sidebar.slider("μx (比生长速率)", 0.30, 0.50, float(_cal["mux"]), 0.01,
                            key=f"mux_{batch_no}")
    mup = st.sidebar.slider("μp (比产物速率)", 0.020, 0.080, float(_cal["mup"]), 0.001,
                            key=f"mup_{batch_no}")
    alpha_kla = st.sidebar.slider("KLa (传质系数)", 50.0, 120.0, 85.0, 5.0,
                                  key=f"kla_{batch_no}")
    m_s = st.sidebar.slider("m_s (维持系数)", 0.005, 0.030, float(_cal["m_s"]), 0.001,
                            key=f"ms_{batch_no}")
    dtcin = st.sidebar.slider("ΔTcin (温度扰动)", 0.0, 30.0, float(_cal["dist_tcin_asym"]), 1.0,
                              key=f"dt_{batch_no}")
    force = st.sidebar.checkbox("忽略已有记录，强制重算", value=False, key=f"force_{batch_no}")

    params = {
        "mux": mux, "mup": mup, "alpha_kla": alpha_kla,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s,
    }
    if _sched:
        params["m_s_schedule"] = _sched
        st.sidebar.info(f"已并入本批时变 m_s 调度 {_sched}")

    state_key = f"sim_active_{batch_no}"
    if st.sidebar.button("运行仿真", type="primary"):
        cached = None if force else runstore.has_run("A", batch_no, params)
        if cached:
            meta, sim_df = runstore.load_run(cached)
            st.session_state[state_key] = {"params": params, "sim": sim_df,
                                           "cached_key": cached}
            st.sidebar.success(f"记录命中 {cached}（秒开）")
        else:
            v3_ = load_batch_data(batch_no)
            with st.spinner("仿真求解中（约 8 s）..."):
                sim = run_simulation(batch_no, params)
            ym, lvl, _rs = batch_summary(sim, v3_)
            key = runstore.save_run("A", batch_no, params, sim_df=sim,
                                    metrics={"yield_err": float(ym["rel_err_total"]),
                                             "co2d_max": float(sim["CO2d"].max()),
                                             "crash_level": lvl})
            st.session_state[state_key] = {"params": params, "sim": sim,
                                           "cached_key": key}
            st.session_state.pop(f"b_result_{batch_no}", None)
            st.sidebar.success(f"已计算并保存记录 {key}")

    active = st.session_state.get(state_key)
    if active is not None:
        sim = active["sim"]
        v3 = load_batch_data(batch_no)
        if active.get("cached_key"):
            st.info(f"🟢 当前展示来自历史记录 {active['cached_key']}（未重算）")
        render_sim_panel(batch_no, sim, v3)

        st.header("B 档软测量估算")
        with st.expander("这一步在做什么？（工作说明）", expanded=False):
            st.markdown(TIER_DESC["B"])
        st.caption("在线通道网格（54 组合，54×8s ≈ 7–8 分钟）；发散组合自动置劣解不中断；结果持久化。")
        if st.button("运行软测量估算（全网格 ~8 分钟）"):
            b_payload = {"grid": "v1_online54"}
            bkey = None if force else runstore.has_run("B", batch_no, b_payload)
            prog = st.progress(0.0, text="B 档网格搜索进行中...")
            if bkey:
                meta, _s = runstore.load_run(bkey)
                result = meta["extra"]["result"]
                st.success(f"记录命中 {bkey}（秒开）")
            else:
                try:
                    result = estimate_batch(batch_no, verbose=False,
                                            on_progress=lambda d, t: prog.progress(
                                                min(d / t, 0.99), text=f"B 档网格 {d}/{t}"))
                except Exception as e:
                    prog.empty()
                    st.error(f"B 档估算失败：{type(e).__name__}: {e}")
                    result = None
                if result is not None:
                    bkey = runstore.save_run("B", batch_no, b_payload,
                                             metrics={"yield_err": None
                                                      if (isinstance(result["yield_err"], float)
                                                          and result["yield_err"] != result["yield_err"])
                                                      else result["yield_err"],
                                                      "online_rmse": result["online_rmse"],
                                                      "crashed": bool(result["crashed"])},
                                             extra={"result": result})
                    st.success(f"已计算并保存记录 {bkey}")
            prog.progress(1.0, text="完成")
            if result is not None:
                st.session_state[f"b_result_{batch_no}"] = result
                st.success(f"估算参数: mux={result['params']['mux']:.2f} "
                           f"mup={result['params']['mup']:.4f} "
                           f"m_s={result['params']['m_s']:.4f} "
                           f"dTcin={result['params']['dist_tcin_asym']:+d}")
                c1, c2, c3 = st.columns(3)
                yerr = result["yield_err"]
                c1.metric("估算产率偏差",
                          "NaN（网格全发散）" if yerr != yerr else f"{yerr:+.1%}")
                c2.metric("在线 RMSE", f"{result['online_rmse']:.4f}")
                c3.metric("估算批崩溃", "⚠️ CRASH" if result["crashed"] else "✅ ok")
                with st.expander("Top-5 组合"):
                    st.dataframe(result["top5"])
                st.subheader("扫描趋势图")
                b_trend_charts(result)
                st.caption("⚠️ 纯在线通道对 mup 辨识力有限；请运行第二阶段获得可辨识 mup。")

        st.subheader("B 档第二阶段：mup 锚定 P_offline（~1–2 分钟）")
        st.caption("以第一阶段参数为基单维扫描 mup，目标 = P_offline 化验轨迹 RMSE（§14.3）。")
        if st.button("运行第二阶段估计（需先跑第一阶段）"):
            res1 = st.session_state.get(f"b_result_{batch_no}")
            if res1 is None:
                st.error("请先运行第一阶段（上方按钮）得到参数基线")
            else:
                b2_payload = {"stage1_hash": runstore.params_hash(res1["params"]),
                              "grid": "v1_mup10"}
                bkey2 = None if force else runstore.has_run("B2", batch_no, b2_payload)
                p2 = st.progress(0.0, text="stage-2 扫描 mup...")
                if bkey2:
                    meta2, _s = runstore.load_run(bkey2)
                    r2 = meta2["extra"]["result"]
                    st.success(f"记录命中 {bkey2}（秒开）")
                else:
                    try:
                        r2 = estimate_stage2(batch_no, res1["params"], v3=v3,
                                             on_progress=lambda d, t: p2.progress(
                                                 d / t, text=f"stage-2 {d}/{t}"))
                    except Exception as e:
                        st.error(f"stage-2 失败：{type(e).__name__}: {e}")
                        r2 = None
                    if r2 is not None:
                        bkey2 = runstore.save_run("B2", batch_no, b2_payload,
                                                  metrics={"yield_err": r2["yield_err"],
                                                           "p_offline_rmse": r2["p_offline_rmse"],
                                                           "co2d_max": r2["co2d_max"]},
                                                  extra={"result": r2})
                        st.success(f"已计算并保存记录 {bkey2}")
                p2.progress(1.0, text="完成")
                if r2 is not None:
                    s1, s2, s3 = st.columns(3)
                    s1.metric("mup (stage-1 → stage-2)",
                              f"{r2['stage1_mup']:.3f} → {r2['stage2_mup']:.4f}")
                    s2.metric("产率偏差", f"{r2['yield_err']:+.1%}")
                    s3.metric("P_offline RMSE", f"{r2['p_offline_rmse']:.2f} g/L")
                    st.caption(f"CO2d 峰值 {r2['co2d_max']:.2f}（"
                               f"{'⚠️ 穿越' if r2['co2d_max'] > 7.57 else '✅ 未穿越'}），"
                               f"化验点数 {r2['n_lab']}")
                    b2_trend_charts(r2)

        st.header("C 档反设计寻优（MV 倍率）")
        with st.expander("这一步在做什么？（工作说明）", expanded=False):
            st.markdown(TIER_DESC["C"])
        st.caption("MV 倍率优化（Nelder-Mead，3–5 分钟）；越域 [0.90,1.25] 显式告警。")
        cvars = st.multiselect("寻优维度（MV）", ["Fs", "Foil", "Fpaa", "Fg", "RPM"],
                               default=["Fs", "Foil"], key=f"cvars_{batch_no}")
        cobj = st.radio("目标模式", ["track_target", "max_yield"], horizontal=True,
                        key=f"cobj_{batch_no}")
        citer = st.slider("最大迭代", 10, 60, 30, 5, key=f"citer_{batch_no}")
        if st.button("运行 C 档寻优", type="secondary"):
            if not cvars:
                st.error("至少选择一个 MV 维度")
            else:
                c_payload = {"vars": cvars, "objective": cobj, "maxiter": citer}
                ckey = None if force else runstore.has_run("C", batch_no, c_payload)
                _prog = st.progress(0.0, text="C 档寻优进行中（每次评估 ~8s）...")
                if ckey:
                    meta, _s = runstore.load_run(ckey)
                    r = meta["extra"]["result"]
                    st.success(f"记录命中 {ckey}（秒开）")
                else:
                    try:
                        r = optimize_feed(int(batch_no), var_names=cvars, maxiter=int(citer),
                                          objective=cobj, verbose=False)
                    except Exception as e:
                        st.error(f"C 档寻优失败：{type(e).__name__}: {e}")
                        r = None
                    if r is not None:
                        ckey = runstore.save_run("C", batch_no, c_payload,
                                                 metrics={"baseline_yield_g": r["baseline_yield_g"],
                                                          "opt_yield_g": r["opt_yield_g"],
                                                          "improvement_pct": r["improvement_pct"],
                                                          "opt_err_vs_v3": r["opt_err_vs_v3"],
                                                          "crash_level": r["crash_level"]},
                                                 extra={"result": r})
                        st.success(f"已计算并保存记录 {ckey}")
                _prog.progress(1.0, text="完成")
                if r is not None:
                    a, b_, c_ = st.columns(3)
                    a.metric("基线产量 (g)", f"{r['baseline_yield_g']:,.0f}")
                    b_.metric("寻优后产量 (g)", f"{r['opt_yield_g']:,.0f}",
                              f"{r['improvement_pct']:+.2%}")
                    c_.metric("对 V3 偏差", f"{r['opt_err_vs_v3']:+.1%}")
                    st.success(f"最优倍率: {r['x_best']}（崩溃分级 {r['crash_level']}，"
                               f"{r['n_evals']} 评分 / {r['wall_s']:.0f}s）")
                    c_trend_charts(r)
                    with st.expander("崩溃证据链"):
                        for rr in r["crash_reasons"] or ["无穿越"]:
                            st.caption("· " + str(rr))
    else:
        st.info("👈 选择批次并点击「运行仿真」开始（同参数二次运行自动从记录秒开）")


# ---------------- 📚 运行记录 ----------------

def record_detail(key):
    meta, sim_df = runstore.load_run(key)
    if meta is None:
        st.error("记录不存在（可能已被删除）")
        if st.button("← 返回记录列表"):
            st.session_state.pop("record_open", None)
            st.rerun()
        return
    b = meta["batch"]
    st.header(f"📚 记录详情：{key}")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("批次", b)
    a2.metric("档位", meta["tier_label"])
    a3.metric("时间", meta["created"].split("T")[0])
    a4.metric("轨迹", "有" if meta.get("sim_pickle") else "指标型")
    if st.button("← 返回记录列表"):
        st.session_state.pop("record_open", None)
        st.rerun()

    with st.expander("记录参数/指标 JSON"):
        st.json({"payload": meta["payload"], "metrics": meta["metrics"]})

    v3 = load_batch_data(b)
    if sim_df is not None:
        st.subheader("历史轨迹回放（未重算，数据取自记录）")
        render_sim_panel(b, sim_df, v3)
    else:
        st.caption("该档位（B/B2/C）为指标型记录，不含轨迹。")
        m = meta["metrics"]
        rr = meta["extra"].get("result") or {}
        st.subheader("趋势图（基于该记录的计算历史）")
        if meta["tier"] == "B":
            x1, x2, x3 = st.columns(3)
            yerr = m.get("yield_err")
            x1.metric("产率偏差", "NaN" if yerr is None else f"{yerr:+.1%}")
            x2.metric("在线 RMSE", f"{m.get('online_rmse', 0):.4f}")
            x3.metric("崩溃", "⚠️ CRASH" if m.get("crashed") else "✅ ok")
            if rr.get("top5"):
                st.dataframe(rr["top5"])
            b_trend_charts(rr)
        if meta["tier"] == "B2":
            x1, x2, x3 = st.columns(3)
            x1.metric("产率偏差", f"{m.get('yield_err', 0):+.1%}")
            x2.metric("P_offline RMSE", f"{m.get('p_offline_rmse', 0):.2f} g/L")
            x3.metric("CO2d 峰值", f"{m.get('co2d_max', 0):.2f}")
            b2_trend_charts(rr)
        if meta["tier"] == "C":
            x1, x2, x3 = st.columns(3)
            x1.metric("基线产量 (g)", f"{m.get('baseline_yield_g', 0):,.0f}")
            x2.metric("寻优产量 (g)", f"{m.get('opt_yield_g', 0):,.0f}",
                      f"{m.get('improvement_pct', 0):+.2%}")
            x3.metric("对 V3 偏差", f"{m.get('opt_err_vs_v3', 0):+.1%}")
            if rr:
                st.success(f"最优倍率: {rr.get('x_best')}（崩溃分级 {rr.get('crash_level')}）")
            c_trend_charts(rr)
    if st.button("🗑 删除该记录"):
        runstore.delete_run(key)
        st.session_state.pop("record_open", None)
        st.rerun()


def records_panel():
    st.header("📚 运行记录（持久化 runs/dashboard_results/）")
    c1, c2 = st.columns([1, 3])
    tf = c1.selectbox("档位过滤", ["全部", "A", "B", "B2", "C"], key="rec_tier_page")
    tfo = None if tf == "全部" else tf
    records = runstore.list_runs(tier=tfo)
    if not records:
        st.info("该过滤条件下暂无记录；在「🚀 运行面板」运行 A/B/C 档将自动生成。")
        return
    rows = [{"运行键": m["run_key"], "档位": m["tier_label"], "批次": m["batch"],
             "产率偏差": (f"{m['metrics']['yield_err']:+.1%}"
                          if m["metrics"].get("yield_err") is not None else "—"),
             "轨迹": "有" if m.get("sim_pickle") else "—",
             "创建时间": m["created"]} for m in records]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.subheader("点击查看某一条记录的历史面板")
    for m in records[:40]:
        line = st.columns([6, 2, 1])
        line[0].caption(f"`{m['run_key']}` · {m['tier_label']} · 批{m['batch']} · "
                        f"产率偏差 {('—' if m['metrics'].get('yield_err') is None else format(m['metrics']['yield_err'], '+.1%'))} · {m['created']}")
        if line[2].button("查看", key=f"view_{m['run_key']}"):
            st.session_state["record_open"] = m["run_key"]
            st.rerun()


def stats_panel():
    """🔍 观测工作台（PH3 交付）：集合平滑器内部观测 — CI 带 + I3 覆盖率。"""
    st.header("🔍 观测工作台（内部观测体系 / 集合平滑器）")
    st.markdown(TIER_DESC.get("OBS", "**做什么**：θ_b 后验采样 → 引擎重放 → 状态轨迹"
              "均值 ±1.96σ（CI）+ 对 V3 化验真值的覆盖率（I3）——为内部观测体系（菌丝/微生物状态）"
              "提供数值估计。回溯型（历史批次重构）。"))
    batch_no = st.sidebar.selectbox("选择批次", GOLDEN, index=GOLDEN.index(8),
                                    key="obs_batch")
    _cal = calib_params(batch_no)
    n_ens = st.sidebar.slider("集合成员数", 20, 120, 50, 10, key=f"nens_{batch_no}")
    st.sidebar.caption(f"本批校准基线（成员均值来源）：mux={_cal['mux']}, μp={_cal['mup']}, "
                       f"m_s={_cal['m_s']}（快校准日志优先 v2 池）")
    run_key_state = f"stats_active_{batch_no}"
    if st.sidebar.button("运行内部观测（~n_ens×8s）", type="primary"):
        _v3 = load_batch_data(batch_no)
        with st.spinner(f"集合平滑器运行中（{n_ens} 成员 × ~8s）..."):
            import observe as _obs
            r = _obs.ensemble_smooth(batch_no, n_ens=n_ens, seed=11, out_path=None)
        st.session_state[run_key_state] = r
        runstore.save_run("O", batch_no,
                          {"mode": "ens_smooth", "seed": 11},
                          metrics={"coverage": r["coverage"], "n_ens_eff": r["n_ens_eff"],
                                   "n_fail": r.get("n_fail", 0)}, extra={"result": r})
        st.sidebar.success("已计算并保存观测记录（档位 O）")
    st.sidebar.header("📚 已保存观测记录（档位 O）")
    obs_records = runstore.list_runs(tier="O", batch_no=batch_no)
    sel_obs = st.sidebar.selectbox(
        "拉取历史观测", ["（不拉取）"] + [m["run_key"] for m in obs_records],
        key=f"obs_pick_{batch_no}")
    active = st.session_state.get(run_key_state)
    if sel_obs != "（不拉取）":
        meta, sim_df = runstore.load_run(sel_obs)
        if meta and "result" in (meta.get("extra") or {}):
            active = meta["extra"]["result"]
            st.info(f"🟢 观测记录命中 {sel_obs}（秒开）")
    if active is None:
        st.info("👈 点击「运行内部观测」或从侧栏拉取历史观测记录")
        return
    cov = active["coverage"]
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("有效成员", active["n_ens_eff"])
    a2.metric("成员级失败", active.get("n_fail", 0))
    a3.metric("X 覆盖率（I3）", f"{int(cov['X_offline']['coverage_95ci'] * 100)}%"
              f"（n={cov['X_offline']['n']}）")
    a4.metric("P / PAA 覆盖率", f"{int(cov['P_offline']['coverage_95ci'] * 100)}% / "
              f"{int(cov['PAA_offline']['coverage_95ci'] * 100)}%")
    st.caption("X 覆盖率已并入 PH2 死亡动力学修正层（death-term, 默认启用）并升至 ~62%；"
               "P/PAA 保持 93.8%/87.5%。剩余 X 缺口与残差白化目标继续推进（PH2 全池复验）。")
    mean = active["mean"]
    sd = active["sd"]
    st.subheader("状态轨迹后验（均值 ±1.96σ）")
    df = pd.DataFrame({"t": mean["time_h"], "X_mean": mean["X_sum"],
                       "X_lo": mean["X_sum"] - 1.96 * sd["X_sum"],
                       "X_hi": mean["X_sum"] + 1.96 * sd["X_sum"],
                       "P_mean": mean["P_mean"], "P_lo": mean["P_mean"] - 1.96 * sd["P_mean"],
                       "P_hi": mean["P_mean"] + 1.96 * sd["P_mean"]})
    st.line_chart(df.set_index("t"), use_container_width=True)
    # PAT 前向通道卡片（P3-V1+，条件触发器驱动——R91/R103）
    st.subheader("PAT 前向通道（Raman 合成层 — 条件触发）")
    _tp, _tr = paa_pat_trigger(_cal["mup"])
    if _tp:
        st.warning(f"🟠 μ={_cal['mup']} > 0.055（触发）: {_tr}——建议接入 raman_pat_channel 的锚定修正层"
                   "（docs/raman_pat_integration_spec.md §1；剩余批 22/23 类高 μp 校准观察）")
    else:
        st.success(f"🟢 校准 μp={_cal['mup']} ≤ 0.055: 引擎 PAA 状态在保真域内，PAT 直接前向或作对照参考")
    st.caption("覆盖率为验收判据之一；PAA 局部保真按批异质（R90-91），本卡片给出条件触发预告。")


def main():
    st.set_page_config(page_title="青霉素发酵仿真看板", layout="wide")
    st.title("🧫 工业青霉素补料分批发酵罐仿真看板")
    mode = st.sidebar.radio("工作台", ["🚀 运行面板", "📚 运行记录", "🔍 观测工作台"], key="mode")

    if mode == "📚 运行记录":
        open_key = st.session_state.get("record_open")
        if open_key:
            record_detail(open_key)
        else:
            records_panel()
    elif mode == "🔍 观测工作台":
        stats_panel()
    else:
        run_panel()


if os.environ.get("DASH_NO_UI") != "1":
    main()
