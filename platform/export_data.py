# -*- coding: utf-8 -*-
"""平台数据导出器 —— 把算子库的运行产物打成前端可直接消费的单一数据包。

设计原则
--------
1. **只有一份真值**：KPI / 通道健康 / 分类全部读 `runs/` 下既有证据，
   导出器不重算指标（避免"平台数字 vs 报告数字"再次分叉——R132 的教训）。
2. **仿真轨迹走缓存**：`platform/.cache/bXX.json` 存在即复用，
   重跑只在算子改动后发生。
3. **一次导出，离线可用**：输出 `platform/data.js`（`window.FERM_DATA = {...}`），
   前端零 fetch、无 CORS 依赖。

用法
----
python platform/export_data.py            # 全量（缺缓存则跑仿真）
python platform/export_data.py --no-sim   # 只导 KPI，不跑仿真（秒级）
"""
import argparse
import importlib.util
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ops_registry as ops  # noqa: E402  —— R167：装载核验与契约版本的唯一真源

OUT_DIR = os.path.join(ROOT, "platform")
CACHE_DIR = os.path.join(OUT_DIR, ".cache")

# 轨迹通道：(数据键, 显示名, 单位, 仿真列, V3 列, 是否离线)
SERIES_CH = [
    ("S", "底物 S", "g/L", "S", "S", False),
    ("P", "青霉素 P", "g/L", "P", "P", False),
    ("X", "菌丝 X", "g/L", "X", "X_offline", True),
    ("PAA", "前体 PAA", "g/L", "PAA", "PAA_offline", True),
    ("DO2", "溶氧 DO2", "%", "DO2", "DO2", False),
    ("OUR", "耗氧速率 OUR", "g/L/h", "OUR", "OUR", False),
    ("vis", "黏度", "cP", "vis", "Viscosity_offline", True),
    ("CER", "CO₂ 释放率", "g/L/h", "CER", "CER", False),
]

# 通道中文名与分组（用于健康矩阵）
CH_META = {
    "DO2": ("溶氧", "%", "在线"),
    "P": ("青霉素", "g/L", "在线"),
    "T": ("温度", "K", "在线"),
    "pH": ("pH", "-", "在线"),
    "V": ("体积", "L", "在线"),
    "Wt": ("重量", "kg", "在线"),
    "OUR": ("耗氧速率", "g/L/h", "尾气"),
    "CER": ("CO₂ 释放率", "g/L/h", "尾气"),
    "CO2outgas": ("尾气 CO₂", "%", "尾气"),
    "O2": ("尾气 O₂", "%", "尾气"),
    "X_offline": ("菌丝(化验)", "g/L", "离线"),
    "P_offline": ("青霉素(化验)", "g/L", "离线"),
    "PAA_offline": ("前体(化验)", "g/L", "离线"),
    "NH3_offline": ("氨氮(化验)", "g/L", "离线"),
    "Viscosity_offline": ("黏度(化验)", "cP", "离线"),
}

STEP_H = 2.0   # 轨迹下采样步长


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def contract_version():
    """契约版本 = **头部与表体两者取最大**（R167 修 D-65 的第二处口径分叉）。

    R134 把「只读标题」改成「只扫表体」，修好了当时的 v1.59→v1.61；但 R166 的
    v1.96 只升了头部、未追加表体行 ⇒ 只扫表体会停在 **v1.94**，平台再次落后。
    唯一真源移到 `ops_registry._contract_version()`（头部 + 表体全扫），
    服务侧 `/api/health` 与本导出器共用它，杜绝再次分叉。
    """
    return ops._contract_version()


def series_for(b):
    """一批的轨迹（带缓存）。"""
    cache = os.path.join(CACHE_DIR, f"b{b:02d}.json")
    if os.path.exists(cache):
        return load_json(cache)

    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop

    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                  f"batch_{b:02d}.csv"))
    sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))

    ts = sim["time_h"].to_numpy(float)
    grid = np.arange(ts[0], ts[-1] + 1e-9, STEP_H)
    out = {"t": [round(float(x), 2) for x in grid], "sim": {}, "obs": {}, "off": {}}
    for key, _label, _unit, scol, ocol, offline in SERIES_CH:
        if scol not in sim.columns:
            continue
        out["sim"][key] = [round(float(x), 4) for x in np.interp(grid, ts, sim[scol].to_numpy(float))]
        if ocol not in v3.columns:
            continue
        tv = v3["time_h"].to_numpy(float)
        ov = v3[ocol].to_numpy(float)
        m = np.isfinite(ov)
        if offline:
            idx = np.where(m)[0]
            out["off"][key] = [[round(float(tv[i]), 1), round(float(ov[i]), 4)] for i in idx]
        else:
            out["obs"][key] = [round(float(x), 4) for x in np.interp(grid, tv, ov)]
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    return out


def build_x_obs():
    """X 通道的 B 档软测量摘要（R139 v2 双通道观测器）。

    A 档机理值（channels 里的 X_offline，nRMSE 23.5%）与 B 档估计（3.17%）是
    **并列的两个输出**，不是替代关系：A 档进控制/产量路径，B 档只做状态估计上报。
    缺这个文件时返回 None，前端不渲染该面板（不伪造数据）。
    """
    p = os.path.join(ROOT, "runs", "p3", "r139_observer_v2.json")
    if not os.path.exists(p):
        return None
    d = load_json(p)
    rows = d.get("rows") or []
    if not rows:
        return None
    nm = np.array([r["n_model"] for r in rows], float)
    nf = np.array([r["n_final"] for r in rows], float)
    m = d.get("meta", {})
    return {
        "method": "双通道输出误差观测器（OUR 定批级标度 + CER 定时间形）",
        "formula": "log(X_est/X_model) = p·mean(log r_OUR) + q·(log r_CER − mean)",
        "p": round(float(m.get("pq", [0, 0])[0]), 3),
        "q": round(float(m.get("pq", [0, 0])[1]), 3),
        "n": len(rows),
        "a": {"nrmse_med": round(float(np.median(nm)), 2),
              "lt15": int((nm < 15).sum())},
        "b": {"nrmse_med": round(float(np.median(nf)), 2),
              "nrmse_p90": round(float(np.percentile(nf, 90)), 2),
              "nrmse_max": round(float(nf.max()), 2),
              "lt15": int((nf < 15).sum())},
        "cv": m.get("cv") or {},
        "cv_struct": m.get("cv_struct") or {},
        "gate": {"thr": m.get("gate_thr"), "g0": round(float(m.get("g0", 0)), 3),
                 "batch": [r["b"] for r in rows if r.get("gated")]},
        "note": "门控批回退 A 档并显式报警；观测器为后处理，不进 ODE，产量路径零影响。",
    }


def build_operators():
    """算子库目录（静态描述，随代码手改；导出时与文件存在性交叉校验）。"""
    spec = [
        {"name": "model.rhs", "kind": "ODE", "file": "model.py",
         "desc": "105 维参数 / 33 维状态的机理右端；含形态学、产物、底物、供氧、传热耦合。",
         "args": ["t", "y", "inp1", "par"]},
        {"name": "integrate_interval", "kind": "积分器", "file": "simulate.py",
         "desc": "单采样区间 BDF 积分（rtol 1e-3 / atol 1e-6 / max_step 0.2h），对齐 MATLAB ode15s。",
         "args": ["t0", "y0", "inp1", "par"]},
        {"name": "simulate_open_loop", "kind": "主仿真", "file": "simulate.py",
         "desc": "以 V3 实测被控量序列驱动的开环回放；返回逐 0.2h 的全通道轨迹。",
         "args": ["batch_no", "params"]},
        {"name": "yield_metrics", "kind": "指标", "file": "simulate.py",
         "desc": "产量口径：harvested = −Σ(Fremoved·P)·h 与批末 V·P 之和，对齐 PROBLEM §7.2。",
         "args": ["sim", "v3"]},
        {"name": "classify_crash", "kind": "判据", "file": "simulate.py",
         "desc": "证据化崩溃分级 normal/benign/catastrophic，避免阈值单点误伤。",
         "args": ["sim", "yield_err"]},
        {"name": "build_params", "kind": "装配", "file": "golden_params.py",
         "desc": "批级覆盖字典 → 仿真参数；**唯一装配口径**，禁止绕过。",
         "args": ["cp"]},
        {"name": "estimate_batch", "kind": "B 档反演", "file": "soft_sensing.py",
         "desc": "在线通道网格反演 (mux, mup, m_s)，54 组合；发散组合自动置劣解。",
         "args": ["batch_no"]},
        {"name": "estimate_stage2", "kind": "B 档二阶段", "file": "stage2_estimator.py",
         "desc": "在 B 档解附近做局部精化，输出参数置信区间。", "args": ["batch_no"]},
        {"name": "optimize_feed", "kind": "C 档寻优", "file": "optimize.py",
         "desc": "补料轨迹寻优（m_s 调度 / 喂食窗口），带约束与收敛诊断。",
         "args": ["batch_no", "vars"]},
        {"name": "hier_est", "kind": "分层估计", "file": "hier_est.py",
         "desc": "批间分层贝叶斯估计，给出群体参数与个体偏差。", "args": ["batch_no"]},
        {"name": "conservation_metrics", "kind": "守恒校验", "file": "conservation_metrics.py",
         "desc": "C/H/N/O 元素平衡闭合度，用于机理自洽性体检。", "args": ["sim"]},
        {"name": "trajectory_metrics", "kind": "通道指标", "file": "trajectory_metrics.py",
         "desc": "在线通道 RMSE / nRMSE / bias / R²。", "args": ["sim", "v3"]},
    ]
    # R167 / D-65：把「文件存在 ⇒ 已装载」改为「运行时 import + callable ⇒ 已装载」。
    # 旧口径是恒真的（12 个 .py 一直在磁盘上），并掩盖了 hier_est 根本不是函数这一事实。
    for s in spec:
        if s["name"] == "hier_est":
            s["name"] = "hier_fit"          # 勘误：真实可调用入口是 hier_est.hier_fit
            s["desc"] = "批间分层贝叶斯估计（EM/MAP 交替），给出群体参数与个体偏差。"
    runtime = {o["name"]: o for o in ops.status()["operators"]}
    # 目录名 → 运行时可调用名（旧目录里有两个是"模块名"而非函数名）
    alias = {"conservation_metrics": "element_balance"}
    for s in spec:
        r = runtime.get(alias.get(s["name"], s["name"]), {})
        s["loaded"] = bool(r.get("loaded"))
        s["exists"] = s["loaded"]          # 兼容旧字段；语义已改为运行时装载
        s["layer"] = r.get("layer", "?")
        s["module"] = r.get("module", "")
        s["attr"] = r.get("attr", s["name"])   # 目录名 ≠ 函数名的两处（model.rhs / element_balance）
        s["runtime_name"] = r.get("name", s["name"])  # 与 /api/ops 的 operators[].name 对齐
        s["file"] = r.get("file", s["file"])
        s["error"] = r.get("error")
    n_loaded = sum(1 for s in spec if s["loaded"])

    # 批级可覆盖参数面（与 build_params 透传列表保持一致）
    knobs = [
        {"key": "mux", "label": "μx 最大比生长", "default": 0.41, "scope": "批级", "effect": "菌丝增长幅度"},
        {"key": "mup", "label": "μp 比产率", "default": 0.041, "scope": "批级", "effect": "产物合成速率"},
        {"key": "alpha_kla", "label": "KLa 传质系数", "default": 85.0, "scope": "批级", "effect": "供氧能力"},
        {"key": "m_s", "label": "维持系数", "default": 0.029, "scope": "批级", "effect": "底物→维持消耗"},
        {"key": "m_paa", "label": "PAA 维持", "default": 1.05, "scope": "批级", "effect": "前体消耗"},
        {"key": "biomass_death_rate", "label": "衰亡速率", "default": 0.0, "scope": "批级", "effect": "菌丝衰减（R130）"},
        {"key": "late_death_rate", "label": "晚期衰亡", "default": 0.0, "scope": "批级", "effect": "μg 门控衰亡（R130b）"},
        {"key": "death_recycle", "label": "自溶回收", "default": 0.0, "scope": "批级", "effect": "死菌丝→底物/产物（R131）"},
        {"key": "vis_scale", "label": "黏度生成标度", "default": 1.0, "scope": "批级", "effect": "黏度生成项，经 kla 反馈产量"},
        {"key": "vis_decay_rate", "label": "黏度松弛速率", "default": 0.0, "scope": "批级", "effect": "一阶黏度损失（R133 新增）"},
        {"key": "vis_out_scale", "label": "黏度化验换算", "default": 1.0, "scope": "批级", "effect": "上报通道换算，不反馈（R133 新增）"},
        {"key": "paa_gate_mode", "label": "PAA 相门控", "default": 0, "scope": "批级", "effect": "0=off / 1=X₁门控 / 2=+dP/dt"},
        {"key": "fault_type", "label": "故障注入", "default": 0, "scope": "批级", "effect": "1=缺氧 / 2=pH扰动 / 3=减料"},
    ]
    return {"operators": spec, "knobs": knobs,
            "n_loaded": n_loaded, "n_total": len(spec),
            "check": "runtime import + callable（非 os.path.exists）"}


def build_topology():
    """过程拓扑：节点 + 连线 + 回路（L1 骨架，前端固定渲染）。"""
    return {
        "nodes": [
            {"id": "seed", "label": "种子罐", "sub": "Seed", "x": 90, "y": 210, "w": 110,
             "primary": {"label": "接种量", "value": 5.0, "unit": "%"},
             "secondary": {"label": "种龄", "value": 48, "unit": "h"}},
            {"id": "reactor", "label": "发酵罐", "sub": "Reactor 2000 L", "x": 300, "y": 170, "w": 190, "h": 130,
             "primary": {"label": "产量", "value": 31.6, "unit": "g/L"},
             "secondary": {"label": "体积", "value": 58.7, "unit": "m³"}},
            {"id": "harvest", "label": "收获/下游", "sub": "Harvest", "x": 590, "y": 210, "w": 120,
             "primary": {"label": "收率", "value": 92.4, "unit": "%"},
             "secondary": {"label": "效价", "value": 1.42, "unit": "g/kg"}},
        ],
        "edges": [["seed", "reactor"], ["reactor", "harvest"]],
        "loops": [
            {"id": "feed", "label": "补料", "anchor": "reactor", "side": "bottom-left",
             "primary": {"label": "补料流率", "value": 8.0, "unit": "L/h"},
             "secondary": {"label": "累计", "value": 1240, "unit": "L"}},
            {"id": "air", "label": "通气", "anchor": "reactor", "side": "left",
             "primary": {"label": "空气流率", "value": 30.0, "unit": "m³/h"},
             "secondary": {"label": "OTR", "value": 6.8, "unit": "g/L/h"}},
            {"id": "agit", "label": "搅拌", "anchor": "reactor", "side": "bottom",
             "primary": {"label": "转速", "value": 100, "unit": "rpm"},
             "secondary": {"label": "功率", "value": 18.5, "unit": "kW"}},
            {"id": "cool", "label": "冷却", "anchor": "reactor", "side": "right",
             "primary": {"label": "冷却水", "value": 105, "unit": "m³/h"},
             "secondary": {"label": "罐温", "value": 297.9, "unit": "K"}},
            {"id": "offgas", "label": "尾气分析", "anchor": "reactor", "side": "top",
             "primary": {"label": "CER", "value": 0.42, "unit": "g/L/h"},
             "secondary": {"label": "RQ", "value": 1.05, "unit": "-"}},
            {"id": "assay", "label": "离线化验", "anchor": "reactor", "side": "bottom-right",
             "primary": {"label": "取样间隔", "value": 12, "unit": "h"},
             "secondary": {"label": "滞后", "value": 4.0, "unit": "h"}},
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "data.js"))
    args = ap.parse_args()

    t0 = time.time()
    fv = load_json(os.path.join(ROOT, "runs", "final_validation_v2.json"))
    d6 = load_json(os.path.join(ROOT, "p3", "d6_health_view.json")) \
        if os.path.exists(os.path.join(ROOT, "p3", "d6_health_view.json")) \
        else load_json(os.path.join(ROOT, "runs", "p3", "d6_health_view.json"))
    # T1-3 / R167：健康分级的权威来源改为 classify_health 五通道验收产物。
    # 旧 catastrophic=0 来自 final_validation_v2.json 的 crash_level，D-38 已判 86/86 恒真。
    acc = load_json(os.path.join(ROOT, "runs", "r156_acceptance.json"))
    health_by_batch = {int(r["batch"]): r.get("health", "unknown")
                       for r in acc.get("rows", [])}
    flags_by_batch = {int(r["batch"]): r.get("health_flags", [])
                      for r in acc.get("rows", [])}
    summary = acc.get("summary", {})

    rows = fv["results"] if isinstance(fv, dict) and "results" in fv else fv
    if isinstance(rows, dict):
        rows = list(rows.values())

    # 通道分类：优先用最近一轮（R133 重跑了黏度后的版本）
    cls_p = os.path.join(ROOT, "runs", "p3", "r133_channel_class.json")
    if not os.path.exists(cls_p):
        cls_p = os.path.join(ROOT, "runs", "p3", "r132_channel_class.json")
    cls = load_json(cls_p)

    # ---- 批次表 ----
    batches = []
    for r in rows:
        b = int(r["batch"])
        e = float(r["yield_err"])
        ch = d6["batches"][str(b)]
        batches.append({
            "b": b,
            "type": r.get("type", "normal"),
            "yield_err": round(e * 100, 3),          # pt
            "yield_sim": round(float(r["yield_sim"]), 2),
            "yield_v3": round(float(r["yield_v3"]), 2),
            "crash": r.get("crash_level", "normal"),       # 旧字段保留（D-38 恒真），UI 不再引用
            "health": health_by_batch.get(b, "unknown"),   # T1-3：classify_health 五通道
            "health_flags": flags_by_batch.get(b, []),
            "reasons": r.get("crash_reasons", []),
            "avg_nrmse": round(float(ch["avg_nrmse"]), 2),
            "d6_health": ch["batch_health"],      # 保留 D6 口径但不再覆盖 classify_health
            "critical": int(ch["critical_count"]),
            "params": {k: v for k, v in (r.get("params") or {}).items()},
        })
    batches.sort(key=lambda x: x["b"])

    # ---- 通道表 + 健康矩阵 ----
    # nRMSE 与健康计数以 D6 为准（矩阵的数据源），分类器只补 R²/gain/相位/形状/分类，
    # 避免"表格里的数"和"热图里的数"来自两套口径。
    keys = [k for k in cls["channels"].keys()]
    channels = []
    for k in keys:
        c = cls["channels"][k]
        lab, unit, grp = CH_META.get(k, (k, "-", "其它"))
        dvals = [d6["batches"][str(x["b"])]["channels"][k]["nrmse"]
                 for x in batches if k in d6["batches"][str(x["b"])]["channels"]]
        hcnt = {"healthy": 0, "warning": 0, "critical": 0}
        for x in batches:
            cc = d6["batches"][str(x["b"])]["channels"].get(k)
            if cc and cc["health"] in hcnt:
                hcnt[cc["health"]] += 1
        med = float(np.median(dvals)) if dvals else float(c["nrmse"])
        channels.append({
            "key": k, "label": lab, "unit": unit, "group": grp,
            "nrmse": round(med, 2),
            "r2": None if c.get("r2") is None else round(float(c["r2"]), 3),
            "gain": None if c.get("gain") is None else round(float(c["gain"]), 3),
            "lag": None if c.get("lag_h") is None else round(float(c["lag_h"]), 1),
            "shape": None if c.get("shape_err") is None else round(float(c["shape_err"]), 2),
            "bias": None if c.get("bias_pct") is None else round(float(c["bias_pct"]), 2),
            "cls": c.get("class", "?"),
            "why": c.get("why", ""),
            "health": hcnt,
        })
    channels.sort(key=lambda x: -x["nrmse"])

    matrix = {"channels": [c["key"] for c in channels],
              "batches": [x["b"] for x in batches],
              "values": []}
    for c in matrix["channels"]:
        row = []
        for x in matrix["batches"]:
            cc = d6["batches"][str(x)]["channels"].get(c)
            row.append(None if cc is None else round(float(cc["nrmse"]), 1))
        matrix["values"].append(row)

    # ---- 系列 ----
    series = {}
    if not args.no_sim:
        for i, x in enumerate(batches):
            try:
                series[str(x["b"])] = series_for(x["b"])
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] b{x['b']} series failed: {exc}")
            if (i + 1) % 10 == 0:
                print(f"  series {i + 1}/{len(batches)}")

    # ---- KPI ----
    n = len(batches)
    within = sum(1 for x in batches if abs(x["yield_err"]) <= 5.0)
    rmse = float(np.sqrt(np.mean([(x["yield_err"] / 100.0) ** 2 for x in batches]))) * 100
    # T1-3：catastrophic 改读 classify_health 五通道（normal 77 / degraded 5 / catastrophic 4）
    n_health = summary.get("n_health", {})
    cat = int(n_health.get("catastrophic", 0))
    hp = int(d6.get("healthy_pairs", 0))
    tp = int(d6.get("total_pairs", 1))

    st = ops.status()
    data = {
        "meta": {
            "title": "IndPenSim 青霉素发酵仿真平台",
            "subtitle": "Penicillin fed-batch digital twin · A/B/C/D 四档求解器平台",
            "contract": contract_version(),
            "generated": time.strftime("%Y-%m-%d %H:%M"),
            "batches": n,
            "engine": "candidate/indpensim/v0.1",
            "build": "R167",
            "capabilities": st["n_tools_loaded"],
            "operators_loaded": st["n_operators_loaded"],
            "data_sources": ["runs/final_validation_v2.json（产量）",
                             "runs/r156_acceptance.json（classify_health 五通道）",
                             "runs/p3/d6_health_view.json（通道健康矩阵）"],
        },
        "kpi": {
            "rmse": round(rmse, 2), "rmse_limit": 3.5,
            "within": within, "within_total": n,
            "catastrophic": cat,
            "catastrophic_source": "classify_health 五通道 · runs/r156_acceptance.json",
            "catastrophic_batches": summary.get("catastrophic_batches", []),
            "degraded": int(n_health.get("degraded", 0)),
            "degraded_batches": summary.get("degraded_batches", []),
            "normal": int(n_health.get("normal", 0)),
            "healthy_pairs": hp, "total_pairs": tp,
            "healthy_pct": round(100.0 * hp / tp, 1),
        },
        # R167：观察-控制工作台的离线数据（不重算指标，全部来自 runs/ 与运行时装载核验）
        "workbench": {
            "architecture": [
                {"layer": "L0", "name": "冻结基线", "state": "默认路径逐字不变",
                 "detail": "86 批 max|Δ| = 0.00e+00 / RMSE 2.345% / 86/86"},
                {"layer": "L1", "name": "opt-in 候选", "state": "默认关闭",
                 "detail": "V1 逐通道判据 / V2 方差注入 / V3 k_dual 查表"},
                {"layer": "L2", "name": "证据闸门", "state": "18/20 NO_GO",
                 "detail": "零信息对照 + 双向判据 + 数据驱动阈值 + LOO + A/B 四格"},
                {"layer": "L3", "name": "切换决策", "state": "未执行 · 保持 opt-in",
                 "detail": "需用户二次确认 + 独立基线冻结（docs/roadmap_next.md §8.8 (a)）"},
            ],
            "tools": st["tools"], "operators": st["operators"],
            "n_tools": st["n_tools_loaded"], "n_operators": st["n_operators_loaded"],
            "all_loaded": st["all_loaded"],
            "l3": ops.evidence()["l3"],
            "no_go": "V2 全幅 σ 注入多种子样本外失效 ⇒ NO_GO；不切默认、不宣称 MATLAB 逐位复现",
            "ph3_note": "运行期连续调控已判封死（D-57）；advise_control 仅作开环设定点标定咨询",
        },
        "evidence": ops.evidence(),
        "channels": channels,
        "batches": batches,
        "matrix": matrix,
        "series": series,
        "x_obs": build_x_obs(),
        "topology": build_topology(),
        "operators": build_operators(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("// 由 platform/export_data.py 生成，勿手改\n")
        f.write("window.FERM_DATA = ")
        f.write(payload)
        f.write(";\n")

    print(json.dumps({"ok": True, "batches": n, "rmse": round(rmse, 2),
                      "within": within, "catastrophic": cat,
                      "healthy_pairs": f"{hp}/{tp}",
                      "series": len(series),
                      "bytes": os.path.getsize(args.out),
                      "elapsed_s": round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
