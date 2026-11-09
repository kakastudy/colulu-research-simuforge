# -*- coding: utf-8 -*-
"""算子目录 —— **单一真源**（L1 Python 库与 L2 MCP 协议都从这里派生）。

三层算子
--------
1. `CAPABILITIES`：14 个 Agent 能力，本体在 `mcp_server.py`（R167 登记的 A/B/C/D 全档）。
2. `V2_EXTENSIONS`：仿真平台 v2 新增的 4 个引擎级能力（全量仿真 / 参数扫描 / 参数目录 / 响应量目录）。
3. `PRIMITIVES`：底层算子，本体散落在 `candidate/indpensim/v0.1/*.py` 与 `platform_v2/*.py`。
   R167 登记的 12 个算子全部在内（`R167_OPERATOR_ALIASES`），并扩展到引擎各模块公开的计算函数。

为什么 MCP 不把 50 个底层算子逐个注册成工具
-------------------------------------------
工具太多会淹没 Agent 的上下文。底层算子统一经两个**元工具**访问：
`list_operators` 发现 + `invoke_operator` 调用。需要 JSON 原生参数的算子在 MCP 层可直接调，
需要内存对象（DataFrame / ndarray）的算子标 `python_objects=True`，只在 L1 Python 库里可调用
—— 这是**能力边界，不是缺失**，会在 `list_operators` 返回体里明说。

参数 schema 从 `inspect.signature` 反射生成，不手写第二份清单：
闸门断言「schema 参数名集合 == 函数签名参数名集合」，杜绝清单漂移。
"""
from __future__ import annotations

import inspect
import types
from typing import Any, get_args, get_origin

from ._bootstrap import engine_module, load_mcp_server
from ._paths import bootstrap_paths, preserved_cwd
from .result import jsonable

# ---------------------------------------------------------------------------
# 1. 14 个 Agent 能力（与 ENGINE_CONTRACT §2 / platform/ops_registry.py 一一对应）
# ---------------------------------------------------------------------------
LIGHT, MEDIUM, HEAVY = "light", "medium", "heavy"

# 参数中文说明（只补描述，参数名与类型一律从函数签名反射）
PARAM_DOCS: dict[str, dict[str, str]] = {
    "simulate_batch": {
        "batch_no": "批号，1–100；黄金集外批次走标称基线",
        "params": "参数覆盖字典，键覆盖黄金校准参数（mux/mup/m_s/mv_scales/Tcin 等）",
    },
    "evaluate_batch": {
        "batch_no": "批号，1–100", "params": "参数覆盖字典（可选）",
    },
    "golden_set_validate": {
        "dw": "是否按批加权汇总",
        "full": "True=86 批全量（约 10 分钟）；False=13 批快速冒烟",
        "n_jobs": "并行进程数，上限 6",
    },
    "estimate_batch": {"batch_no": "批号，1–100", "quick": "快速网格（保留参数，实现为 54 组合固定网格）"},
    "estimate_batch_stage2": {"batch_no": "批号，1–100；约 10 分钟"},
    "reconstruct_batch": {
        "batch_no": "批号，1–100", "n_ens": "集合成员数，上限 50",
        "fallback_chain": "D 档四环回退链（须 opt_in=true 才放行）",
    },
    "batch_fallback_tier": {
        "batch_no": "批号，1–100", "n_ens": "集合成员数，上限 50", "seed": "集合随机种子",
    },
    "optimize_feed": {
        "batch_no": "批号，1–100", "vars": "寻优变量列表（Fs/Foil/Fpaa/Fg/RPM）",
        "maxiter": "最大迭代次数，上限 25", "objective": "max_yield 或 track_target",
    },
    "advise_control": {
        "batch_no": "批号，1–100", "t_window_start": "时间窗起点 h",
        "t_window_end": "时间窗终点 h", "candidates": "候选 MV 倍率字典列表（可选）",
    },
    "trajectory_check": {"batch_no": "批号，1–100"},
    "element_balance_check": {"batch_no": "批号，1–100"},
    "discover_residual": {
        "batch_no": "批号，1–100", "max_terms": "稀疏结构最大项数，上限 8",
        "theta_source": "θ 来源（log / 其他已登记来源）",
    },
    "observe_online": {
        "batch_no": "批号，1–100", "n_ens": "集合成员数，上限 50", "seed": "集合随机种子",
        "stride": "输出抽稀步长，上限 200", "health_probe": "集合健康度探针（须 opt_in=true）",
    },
}


def _cap(cid, tier, layer, label, cost, source, desc, group):
    return {"id": cid, "tier": tier, "layer": layer, "label": label,
            "cost": cost, "source": source, "desc": desc, "group": group}


CAPABILITIES: list[dict] = [
    _cap("solver_info", "A", "求解器", "求解器能力清单", LIGHT, "mcp_server.py",
         "版本 / 四档算子 / 黄金集 / 参数键清单。零算力，常用作装载链路自检。", "A 档·仿真与验收"),
    _cap("simulate_batch", "A", "仿真引擎", "开环回放仿真", LIGHT, "simulate.py",
         "33 维 ODE 开环回放，返回 6h 粒度轨迹摘要、末态、产量与崩溃分级。约 8 s。", "A 档·仿真与验收"),
    _cap("evaluate_batch", "A", "仿真引擎", "产量评估与崩溃分级", LIGHT, "simulate.py",
         "只返回产量指标 + 证据化崩溃分级，比 simulate_batch 轻。", "A 档·仿真与验收"),
    _cap("golden_set_validate", "A", "验收算子", "黄金集全量复验", HEAVY, "validate.py",
         "86 批并行复验（RMSE / within5% / 崩溃分级），约 10 分钟。", "A 档·仿真与验收"),
    _cap("trajectory_check", "A", "验收算子", "逐点轨迹对照", LIGHT, "trajectory_metrics.py",
         "GOAL §4.2：S/X/P/DO/T/pH 等逐点对照 V3，返回 RMSE/bias/nRMSE/相关系数。", "A 档·仿真与验收"),
    _cap("element_balance_check", "A", "验收算子", "C/N 元素平衡", LIGHT, "conservation_metrics.py",
         "GOAL §4.3：批级 C/N 账与 RQ；注意 V3 尾气与液相账内在不自洽，输出用于证据链。", "A 档·仿真与验收"),
    _cap("estimate_batch", "B", "软测量求解器", "B 档参数反演", MEDIUM, "soft_sensing.py",
         "在线量测 54 组合网格反演 (mux, mup, m_s)；发散组合置劣解不中断。", "B 档·观测与估计"),
    _cap("estimate_batch_stage2", "B", "软测量求解器", "二阶段 μp 精化", MEDIUM, "stage2_estimator.py",
         "以 P_offline 化验为锚局部精化 μp，约 10 分钟。", "B 档·观测与估计"),
    _cap("reconstruct_batch", "B", "集合平滑求解器", "批次状态重构", HEAVY, "observe.py",
         "集合平滑回溯重构，返回状态均值 ±1.96σ 与 I3 覆盖率；fallback_chain 可接 D 档回退链。", "B 档·观测与估计"),
    _cap("batch_fallback_tier", "D", "回退链算子", "回退链层级判定", MEDIUM, "solver_chain.py",
         "只读判定 enkf / mhe / steady_state / explicit_failure，返回体恒含降级理由。", "B 档·观测与估计"),
    _cap("discover_residual", "B", "结构发现算子", "结构残差发现", HEAVY, "residual_discovery.py",
         "SINDy 式稀疏辨识；返回体恒含 identifiable / degraded / 判据，菌丝分室恒不可辨识。", "B 档·观测与估计"),
    _cap("observe_online", "B", "在线观测器", "在线 EnKF 同化", HEAVY, "observe.py",
         "在线 5 通道 + 延迟化验点同化，只读；返回体恒含 degraded / reconstruction_valid。", "B 档·观测与估计"),
    _cap("optimize_feed", "C", "寻优求解器", "补料轨迹寻优", HEAVY, "optimize.py",
         "MV 倍率 Nelder-Mead 反设计，带灾难崩溃约束与收敛 history。", "C 档·反设计与咨询"),
    _cap("advise_control", "C", "咨询算子", "时间窗反事实咨询", HEAVY, "mcp_server.py",
         "时间窗内 MV 反事实重放 + T1 操作窗校验；运行期连续调控已判封死（D-57）。", "C 档·反设计与咨询"),
]
CAP_BY_ID = {c["id"]: c for c in CAPABILITIES}

# ---------------------------------------------------------------------------
# 2. 平台 v2 的 4 个引擎级扩展（实现在 penops/_v2.py 的薄适配层）
# ---------------------------------------------------------------------------
V2_EXTENSIONS: list[dict] = [
    _cap("run_simulation", "A", "仿真引擎 v2", "全量仿真与指标", MEDIUM, "platform_v2/engine_api.py",
         "单一装配口径（build_params(COMBINED[b]) + 覆盖）跑一次完整仿真；返回全量轨迹、产量、"
         "形状指标、五通道健康分级、守恒、守卫审计、轨迹级指标。", "V2·仿真与扫描"),
    _cap("parameter_scan", "C", "参数扫描", "一维/二维参数扫描", HEAVY, "platform_v2/scan.py",
         "逐点完整仿真的响应曲面；失败点显式标注且不参与统计，不渲染成 0 值。", "V2·仿真与扫描"),
    _cap("param_catalog", "A", "参数目录", "AST 派生参数目录", LIGHT, "platform_v2/param_catalog.py",
         "从 simulate.py 的 AST 派生可用参数键、控件类型与有效域；零算力。", "V2·仿真与扫描"),
    _cap("list_responses", "A", "参数扫描", "扫描响应量目录", LIGHT, "platform_v2/scan.py",
         "列出全部扫描响应量（key / 标签 / 单位）；零算力。", "V2·仿真与扫描"),
]
V2_BY_ID = {c["id"]: c for c in V2_EXTENSIONS}

# ---------------------------------------------------------------------------
# 3. 底层算子目录（module.attr 全限定名）
# ---------------------------------------------------------------------------
# R167 登记的 12 个名字（ops_registry.OPERATORS），用 alias 保留以便核对不漏
R167_OPERATOR_ALIASES = {
    "model.rhs": "model.rhs",
    "simulate.integrate_interval": "integrate_interval",
    "simulate.simulate_open_loop": "simulate_open_loop",
    "simulate.yield_metrics": "yield_metrics",
    "simulate.classify_crash": "classify_crash",
    "golden_params.build_params": "build_params",
    "soft_sensing.estimate_batch": "estimate_batch",
    "stage2_estimator.estimate_stage2": "estimate_stage2",
    "optimize.optimize_feed": "optimize_feed",
    "hier_est.hier_fit": "hier_fit",
    "conservation_metrics.element_balance": "element_balance",
    "trajectory_metrics.trajectory_metrics": "trajectory_metrics",
}

# 需要内存对象（DataFrame / ndarray / 状态向量）的算子 ⇒ Python 库可调用，
# MCP 层不接（Agent 无法用 JSON 描述一个 DataFrame）。显式列出，不猜测。
PYTHON_OBJECTS = {
    "model.rhs", "model.compute_mu_e", "simulate.integrate_interval",
    "simulate.simulate_open_loop", "simulate.guards", "simulate.build_initial_state",
    "simulate.build_inp1", "simulate.yield_metrics", "simulate.classify_crash",
    "simulate.classify_health", "simulate.validity", "simulate.shape_metrics",
    "simulate.trajectory_metrics", "simulate.print_report",
    "trajectory_metrics.trajectory_metrics", "conservation.element_balance",
    "mechanism_cclosure.mechanism_c_closure", "soft_sensing.online_rmse",
    "soft_sensing.crash_penalty", "observe.enkf_update", "observe.coverage_check",
    "calibrate.rmse_channel", "calibrate.crash_penalty",
    "stage2_estimator.p_offline_rmse", "residual_discovery.sparse_fit",
    "residual_discovery.discover_batch", "hier_est.hier_fit",
    "hier_est.eb_temperature", "hier_est.dl_sigma", "hier_est.dl_sigma_combined",
    "validate.summarize_rows", "validate.golden_all_rows",
    "param_catalog.validate_overrides", "conservation_metrics.element_balance",
    "conservation_metrics.run", "trajectory_metrics.run",
    "solver_chain.enkf_health", "solver_chain.degradation_guard",
    "solver_chain.mhe_step", "solver_chain.steady_state_baseline",
    "solver_chain.resolve_tier", "solver_chain.classify_enkf_output",
    "knowledge_constraints.validate_t1",
    "scan.run_sweep",
}


def _prim(name, layer, kind, desc):
    module, attr = name.split(".", 1)
    return {"name": name, "module": module, "attr": attr, "layer": layer,
            "kind": kind, "desc": desc, "alias": R167_OPERATOR_ALIASES.get(name),
            "python_objects": name in PYTHON_OBJECTS}


PRIMITIVES: list[dict] = [
    # --- 引擎与装配 ---------------------------------------------------------
    _prim("model.rhs", "仿真引擎", "ODE", "33 维状态方程右端项（内存对象入参）"),
    _prim("model.compute_mu_e", "仿真引擎", "动力学", "潜在比生长速率计算"),
    _prim("model.state_names", "仿真引擎", "元数据", "33 个状态名清单（零算力）"),
    _prim("model.default_initial_state", "仿真引擎", "元数据", "默认初值向量"),
    _prim("params.make_params", "仿真引擎", "装配", "从命名参数构造 par 向量"),
    _prim("golden_params.build_params", "仿真引擎", "装配", "批级黄金覆盖 → 仿真参数字典（唯一装配口径）"),
    _prim("golden_params.params_for", "仿真引擎", "装配", "按批号取黄金参数"),
    _prim("golden_params.apply_candidate_v2", "仿真引擎", "装配", "候选基线 v2 的 opt-in 参数变换"),
    _prim("simulate.simulate_open_loop", "仿真引擎", "主仿真", "33 维 ODE + BDF 开环回放（返回 sim/v3）"),
    _prim("simulate.integrate_interval", "仿真引擎", "积分器", "单区间积分"),
    _prim("simulate.guards", "仿真引擎", "守卫", "物理地板钳制与守卫审计"),
    _prim("simulate.load_batch", "仿真引擎", "数据", "载入 V3 批次 CSV"),
    _prim("simulate.build_initial_state", "仿真引擎", "装配", "构造初值"),
    _prim("simulate.build_inp1", "仿真引擎", "装配", "构造输入行"),
    _prim("simulate.compute_our_cer", "仿真引擎", "代谢", "尾气 O2/CO2 → OUR/CER"),
    # --- 指标、判据、守恒 ---------------------------------------------------
    _prim("simulate.yield_metrics", "验收算子", "指标", "终末收获 + 罐内产量（与 MATLAB 逐位同构）"),
    _prim("simulate.classify_crash", "验收算子", "判据", "旧崩溃判据（D-38：黄金集上恒真，仅作兼容）"),
    _prim("simulate.classify_health", "验收算子", "判据", "五通道健康分级（normal/degraded/catastrophic）"),
    _prim("simulate.validity", "验收算子", "判据", "pH 数值有效性判定（不钳位且不越 7.0）"),
    _prim("simulate.shape_metrics", "验收算子", "指标", "P/S 分相位形状指标（产量指标对 P 轨迹失明）"),
    _prim("simulate.trajectory_metrics", "验收算子", "指标", "逐点通道指标（simulate 版）"),
    _prim("trajectory_metrics.trajectory_metrics", "验收算子", "指标", "逐点通道指标（独立模块版）"),
    _prim("conservation_metrics.element_balance", "验收算子", "守恒", "C/N 元素平衡（V3 口径）"),
    _prim("conservation.element_balance", "验收算子", "守恒", "C 平衡（sim/v3 口径）"),
    _prim("mechanism_cclosure.mechanism_c_closure", "验收算子", "守恒", "机理层碳闭合"),
    _prim("knowledge_constraints.control_hard", "约束算子", "边界", "T1 操作窗硬约束常量"),
    _prim("knowledge_constraints.calib_bounds", "约束算子", "边界", "标定参数上下界"),
    _prim("knowledge_constraints.validate_t1", "约束算子", "边界", "T1 操作窗校验（ok + reasons）"),
    # --- 软测量与估计 -------------------------------------------------------
    _prim("soft_sensing.estimate_batch", "软测量求解器", "B 档反演", "在线量测网格反演批次参数"),
    _prim("soft_sensing.online_rmse", "软测量求解器", "指标", "在线通道 RMSE"),
    _prim("soft_sensing.crash_penalty", "软测量求解器", "罚函数", "崩溃惩罚项"),
    _prim("stage2_estimator.estimate_stage2", "软测量求解器", "B 档二阶段", "P_offline 锚定 μp 精化"),
    _prim("stage2_estimator.load_v3", "软测量求解器", "数据", "载入 V3 化验数据"),
    _prim("stage2_estimator.p_offline_rmse", "软测量求解器", "指标", "离线 P 化验 RMSE"),
    _prim("observe.enkf_observe", "在线观测器", "同化", "在线 EnKF 5 通道同化（只读）"),
    _prim("observe.ensemble_smooth", "集合平滑", "重构", "回溯型集合平滑重构"),
    _prim("observe.coverage_check", "集合平滑", "指标", "I3 置信区间覆盖率"),
    _prim("hier_est.hier_fit", "分层估计", "估计", "分层贝叶斯拟合"),
    _prim("hier_est.quick_calibrate", "分层估计", "校准", "单批快速校准"),
    _prim("calibrate.calibrate_batch", "分层估计", "校准", "单批参数标定"),
    _prim("calibrate.rmse_channel", "分层估计", "指标", "单通道 RMSE"),
    _prim("residual_discovery.discover_batch", "结构发现", "SINDy", "单批 S/P 残差结构发现"),
    _prim("residual_discovery.sparse_fit", "结构发现", "SINDy", "候选库全子集最小二乘 + BIC"),
    _prim("identifiability.sensitivity_analysis", "可辨识性", "敏感度", "参数局部敏感度分析"),
    # --- 回退链 D 档 --------------------------------------------------------
    _prim("solver_chain.enkf_health", "回退链算子", "健康度", "集合健康度判据（通道白名单 + 持续性）"),
    _prim("solver_chain.degradation_guard", "回退链算子", "触发器", "降级触发器，恒返回显式 tier + reasons"),
    _prim("solver_chain.mhe_step", "回退链算子", "MHE", "受约束滚动优化单步（SLSQP）"),
    _prim("solver_chain.steady_state_baseline", "回退链算子", "基线", "稳态碳平衡基线解算"),
    _prim("solver_chain.resolve_tier", "回退链算子", "编排", "四环链编排，穷尽则 explicit_failure"),
    _prim("solver_chain.classify_enkf_output", "回退链算子", "判据", "EnKF 输出分类"),
    _prim("solver_chain.mhe_estimate_batch", "回退链算子", "MHE", "批次级 MHE 估计"),
    # --- 寻优与验收 ---------------------------------------------------------
    _prim("optimize.optimize_feed", "寻优求解器", "C 档寻优", "MV 倍率 Nelder-Mead 反设计"),
    _prim("validate.validate_batch", "验收算子", "复验", "单批复验"),
    _prim("validate.golden_all_rows", "验收算子", "复验", "多批并行复验行"),
    _prim("validate.summarize_rows", "验收算子", "汇总", "RMSE / within5 / catastrophic 汇总"),
    _prim("param_catalog.build_catalog", "参数目录", "AST", "从 simulate.py 派生参数目录（零算力）"),
    _prim("param_catalog.validate_overrides", "参数目录", "守卫", "覆盖键校验（L3 拒绝 / 未知键 / 非有限数）"),
    _prim("scan.run_sweep", "参数扫描", "批量仿真", "扫描 runner（需要 job 对象，建议用 parameter_scan）"),
]
PRIM_BY_NAME = {p["name"]: p for p in PRIMITIVES}

# ---------------------------------------------------------------------------
# 4. MCP 元工具（发现与透传底层算子）
# ---------------------------------------------------------------------------
META_TOOLS: list[dict] = [
    _cap("list_operators", "-", "元工具", "底层算子目录", LIGHT, "penops/registry.py",
         "列出全部底层算子的名字 / 层 / 说明 / 是否需内存对象；支持按层过滤。", "元工具"),
    _cap("invoke_operator", "-", "元工具", "调用底层算子", MEDIUM, "penops/registry.py",
         "按全限定名调用底层算子（如 simulate.classify_health）。需要内存对象的算子仅 Python 库可用。", "元工具"),
    _cap("runtime_status", "-", "元工具", "运行时装载核验", LIGHT, "penops/registry.py",
         "14 能力 + v2 扩展 + 全部底层算子的 import/callable 核验，含路径与 backend。", "元工具"),
]
META_BY_ID = {m["id"]: m for m in META_TOOLS}

# ---------------------------------------------------------------------------
# 5. 反射：签名 → JSON Schema
# ---------------------------------------------------------------------------
def _annotation_type(ann: Any) -> str | None:
    if ann is inspect.Parameter.empty or ann is Any or ann is None:
        return None
    origin = get_origin(ann)
    if origin is not None:
        # Union / X | None / Optional
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return _annotation_type(args[0])
        if origin in (dict,):
            return "object"
        if origin in (list, tuple, set):
            return "array"
        return None
    if isinstance(ann, types.UnionType):  # Python 3.10 的 X | Y
        args = [a for a in get_args(ann) if a is not type(None)]
        return _annotation_type(args[0]) if len(args) == 1 else None
    if ann is int:
        return "integer"
    if ann is float:
        return "number"
    if ann is bool:
        return "boolean"
    if ann is str:
        return "string"
    if ann in (dict,):
        return "object"
    if ann in (list, tuple, set):
        return "array"
    return None


def signature_schema(fn, docs: dict[str, str] | None = None,
                     *, add_confirm: bool = False) -> dict:
    """从函数签名派生 JSON Schema；参数名/必填/默认值不可能与实现漂移。"""
    docs = docs or {}
    sig = inspect.signature(fn)
    props: dict[str, dict] = {}
    required: list[str] = []
    for name, p in sig.parameters.items():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        typ = _annotation_type(p.annotation)
        item: dict[str, Any] = {}
        if typ:
            item["type"] = typ
        if name in docs:
            item["description"] = docs[name]
        if p.default is not inspect.Parameter.empty:
            try:
                item["default"] = jsonable(p.default)
            except (TypeError, ValueError):
                pass
        else:
            required.append(name)
        props[name] = item
    if add_confirm:
        props["confirm"] = {
            "type": "boolean",
            "description": "重调用确认闸：本工具耗时长，必须显式传 true 才会执行",
            "default": False,
        }
    schema: dict[str, Any] = {"type": "object", "properties": props,
                              "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def capability_function(cid: str):
    """取能力函数本体（14 能力来自 mcp_server；v2 扩展来自 _v2 适配层）。"""
    if cid in CAP_BY_ID:
        return getattr(load_mcp_server(), cid, None)
    if cid in V2_BY_ID:
        from . import _v2
        return getattr(_v2, cid, None)
    return None


def capability_schema(cid: str) -> dict:
    c = CAP_BY_ID.get(cid) or V2_BY_ID.get(cid)
    if c is None:
        raise KeyError(cid)
    fn = capability_function(cid)
    if not callable(fn):
        raise RuntimeError(f"能力 {cid} 不可调用，无法派生 schema")
    return signature_schema(fn, PARAM_DOCS.get(cid), add_confirm=(c["cost"] == HEAVY))


def mcp_tools(*, profile: str = "capabilities") -> list[dict]:
    """生成 MCP tools/list 的返回体。profile='full' 时把底层算子也逐个注册。"""
    ids = [c["id"] for c in CAPABILITIES] + [c["id"] for c in V2_EXTENSIONS]
    out: list[dict] = []
    for cid in ids:
        c = CAP_BY_ID.get(cid) or V2_BY_ID[cid]
        out.append({
            "name": cid,
            "description": f"[{c['tier']} 档 · {c['layer']} · {c['cost']}] {c['label']}：{c['desc']}",
            "inputSchema": capability_schema(cid),
        })
    for m in META_TOOLS:
        out.append({"name": m["id"], "description": m["desc"],
                    "inputSchema": META_SCHEMAS[m["id"]]})
    if profile == "full":
        for p in PRIMITIVES:
            if p["python_objects"]:
                continue
            out.append({
                "name": "op__" + p["name"].replace(".", "__"),
                "description": f"[底层算子 · {p['layer']}] {p['desc']}",
                "inputSchema": {"type": "object",
                                "properties": {"kwargs": {"type": "object",
                                                          "description": "传给算子的关键字参数"}},
                                "additionalProperties": False},
            })
    return out


META_SCHEMAS: dict[str, dict] = {
    "list_operators": {
        "type": "object",
        "properties": {
            "layer": {"type": "string", "description": "按层过滤（如 仿真引擎 / 验收算子），留空返回全部"},
            "agent_safe_only": {"type": "boolean", "default": False,
                                "description": "只返回 JSON 参数可直接调用的算子"},
        },
        "additionalProperties": False,
    },
    "invoke_operator": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "算子全限定名，如 model.state_names / knowledge_constraints.control_hard"},
            "kwargs": {"type": "object", "description": "关键字参数字典", "default": {}},
        },
        "required": ["name"], "additionalProperties": False,
    },
    "runtime_status": {"type": "object", "properties": {}, "additionalProperties": False},
}


# ---------------------------------------------------------------------------
# 6. 运行时装载核验（import + callable，不是文件存在性）
# ---------------------------------------------------------------------------
def primitive_function(name: str):
    p = PRIM_BY_NAME.get(name)
    if p is None:
        return None
    with preserved_cwd():
        mod = engine_module(p["module"])
    return getattr(mod, p["attr"], None)


def runtime_status() -> dict:
    """逐项核验：能力 / 扩展 / 底层算子。任何一项不 callable 都显式报出原因。"""
    bootstrap_paths()
    from ._bootstrap import backend_info
    caps, prims = [], []
    for c in CAPABILITIES + V2_EXTENSIONS:
        err, fn = None, None
        try:
            fn = capability_function(c["id"])
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        caps.append({"id": c["id"], "loaded": callable(fn), "error": err or (
            None if callable(fn) else "不可调用"), "layer": c["layer"],
            "cost": c["cost"], "tier": c["tier"]})
    for p in PRIMITIVES:
        err, fn = None, None
        try:
            fn = primitive_function(p["name"])
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        prims.append({"name": p["name"], "loaded": callable(fn), "error": err or (
            None if callable(fn) else "不可调用"), "layer": p["layer"],
            "python_objects": p["python_objects"]})
    from ._paths import check_layout
    layout = check_layout()
    return {
        "ok": all(x["loaded"] for x in caps) and all(x["loaded"] for x in prims) and layout["ok"],
        "layout": layout,
        "backend": backend_info(),
        "n_capabilities": len(caps), "n_capabilities_loaded": sum(x["loaded"] for x in caps),
        "n_primitives": len(prims), "n_primitives_loaded": sum(x["loaded"] for x in prims),
        "capabilities": caps, "primitives": prims,
        "r167_aliases": sorted(R167_OPERATOR_ALIASES.values()),
        "l3_exposed": False,
    }


def list_operators(layer: str | None = None, agent_safe_only: bool = False) -> dict:
    rows = PRIMITIVES
    if layer:
        rows = [p for p in rows if layer in p["layer"]]
    if agent_safe_only:
        rows = [p for p in rows if not p["python_objects"]]
    return {
        "ok": True,
        "n": len(rows),
        "levels": {"capabilities": len(CAPABILITIES), "v2_extensions": len(V2_EXTENSIONS),
                   "primitives": len(PRIMITIVES)},
        "note": ("python_objects=true 的算子需要 DataFrame / ndarray / 状态向量等内存对象，"
                 "只在 L1 Python 库中可调用；MCP 层不接受这类入参（这是能力边界，不是缺失）。"),
        "operators": rows,
        "capabilities": [c["id"] for c in CAPABILITIES + V2_EXTENSIONS],
    }
