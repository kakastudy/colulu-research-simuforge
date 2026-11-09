# -*- coding: utf-8 -*-
"""平台能力注册表 —— 把 A/B/C/D 四档的算子 / 求解器 / 仿真引擎装载为平台可调用能力。

R167 / D-65 设计原则
--------------------
1. **运行时装载，不是文件存在性**。能力必须在进程内 import 成功且 `callable` 为真，
   否则 `loaded=False`；平台不得再显示「已装载」。旧 `app.js:785` 的
   `o.exists = os.path.exists(file)` 属恒真口径（D-65 同型），本模块取代之。
2. **唯一真源**。直接复用 `candidate/indpensim/v0.1/mcp_server.py` 的 **14 个工具函数
   本体**，不复制实现 ⇒ 平台能力与 Agent 服务逐字同源，杜绝「平台数字 vs 服务数字」分叉。
3. **L0 冻结基线零改动**。本模块只做 import + 调用，不修改任何引擎模块、不改默认参数、
   不触碰 `COMBINED` / `INNOVATION_Z_*` / `alpha_kla` / 零回归基准 / `data/`。
4. **L3 保持 opt-in（用户 2026-11-06 裁决）**。R166 的 V1 逐通道判据 / V2 方差注入 /
   V3 `k_dual` 写回**不进入注册表**；`FORBIDDEN_KEYS` 对相关参数做硬拒绝；
   `fallback_chain` / `health_probe` 等 opt-in 开关须显式 `opt_in=true` 才放行。
5. **重调用显式确认**。`cost=heavy` 的能力（全量 86 批复验 / Nelder-Mead / 集合平滑等）
   须 `confirm=true`，避免前端误触导致长任务。

用法
----
    import ops_registry as ops
    ops.status()                       # 运行时装载核验
    ops.invoke("evaluate_batch", {"batch_no": 8})   # 调用
"""
from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
if PKG not in sys.path:
    sys.path.insert(0, PKG)

LOCK = threading.Lock()

# L3 候选参数：出现即拒绝（不因平台升级夹带 GOAL §5 边界变更）
FORBIDDEN_KEYS = {
    "dist_noise_sigma": "R166 / V2：8 路方差注入，多轮寻优判定 NO_GO，保持 opt-in",
    "dist_noise_seed": "R166 / V2：方差注入种子，同上",
    "innovation_criteria": "R166 / V1：逐通道创新判据，L3 未裁决",
    "k_dual": "R166 / V3：alpha_kla 双约束查表，仅评测层，未写回",
    "alpha_kla_override": "R166 / V3：写回黄金参数属 L3",
}

# 需要显式 opt_in=true 的开关（默认值必须为 False）
OPT_IN_PARAMS = {"fallback_chain", "health_probe"}

# 成本分档：heavy 需 confirm=true
COST_LIGHT, COST_MEDIUM, COST_HEAVY = "light", "medium", "heavy"


def _p(name, typ, default=None, required=False, desc=""):
    return {"name": name, "type": typ, "default": default,
            "required": required, "desc": desc}


# ---------------------------------------------------------------------------
# 14 个能力（与 mcp_server.py 的 @mcp.tool 一一对应）
# ---------------------------------------------------------------------------
TOOLS = [
    {"id": "solver_info", "tier": "A", "layer": "求解器", "label": "求解器能力清单",
     "cost": COST_LIGHT, "source": "mcp_server.py",
     "desc": "版本 / 四档算子 / 黄金集 / 参数键能力清单。零算力，用作装载链路自检。",
     "params": []},
    {"id": "simulate_batch", "tier": "A", "layer": "仿真引擎", "label": "开环回放仿真",
     "cost": COST_LIGHT, "source": "simulate.py",
     "desc": "33 维 ODE 开环回放，返回降采样全状态轨迹摘要。",
     "params": [_p("batch_no", "int", None, True, "批号（1–100）"),
                _p("params", "json", None, False, "参数覆盖字典（可选）")]},
    {"id": "evaluate_batch", "tier": "A", "layer": "仿真引擎", "label": "产量评估与崩溃分级",
     "cost": COST_LIGHT, "source": "simulate.py",
     "desc": "产量指标 + 证据化崩溃分级（yield_metrics / classify_crash）。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("params", "json", None, False, "参数覆盖字典（可选）")]},
    {"id": "golden_set_validate", "tier": "A", "layer": "验收算子", "label": "黄金集全量复验",
     "cost": COST_HEAVY, "source": "validate.py",
     "desc": "86 批并行复验（RMSE / within5% / 崩溃分级）。耗时约 10 分钟，须显式确认。",
     "params": [_p("dw", "bool", True, False, "是否按批加权"),
                _p("full", "bool", True, False, "全 86 批（False 仅 12 批）"),
                _p("n_jobs", "int", 6, False, "并行数（上限 6）")]},
    {"id": "estimate_batch", "tier": "B", "layer": "软测量求解器", "label": "B 档参数反演",
     "cost": COST_MEDIUM, "source": "soft_sensing.py",
     "desc": "在线通道 54 组合网格反演 (mux, mup, m_s)；发散组合自动置劣解。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("quick", "bool", True, False, "快速网格")]},
    {"id": "estimate_batch_stage2", "tier": "B", "layer": "软测量求解器", "label": "二阶段 μp 精化",
     "cost": COST_MEDIUM, "source": "stage2_estimator.py",
     "desc": "在 B 档解附近以 P_offline 为锚做局部精化。",
     "params": [_p("batch_no", "int", None, True, "批号")]},
    {"id": "reconstruct_batch", "tier": "B", "layer": "集合平滑求解器", "label": "批次状态重构",
     "cost": COST_HEAVY, "source": "observe.py",
     "desc": "集合平滑回溯型重构；fallback_chain=True 时接入 D 档四环回退链（须 opt-in）。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("n_ens", "int", 50, False, "集合成员数（上限 50）"),
                _p("fallback_chain", "bool", False, False, "D 档回退链（opt-in）")]},
    {"id": "batch_fallback_tier", "tier": "D", "layer": "回退链算子", "label": "回退链层级判定",
     "cost": COST_MEDIUM, "source": "solver_chain.py",
     "desc": "只读判定某批的层级：enkf / mhe / steady_state / explicit_failure，返回体恒含降级理由。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("n_ens", "int", 20, False, "集合成员数（上限 50）"),
                _p("seed", "int", 7, False, "集合种子")]},
    {"id": "optimize_feed", "tier": "C", "layer": "寻优求解器", "label": "补料轨迹寻优",
     "cost": COST_HEAVY, "source": "optimize.py",
     "desc": "MV 倍率 Nelder-Mead 反设计，带灾难崩溃约束。耗时分钟级，须显式确认。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("vars", "json", None, False, "寻优变量列表（可选）"),
                _p("maxiter", "int", 25, False, "最大迭代（上限 25）"),
                _p("objective", "str", "max_yield", False, "目标")]},
    {"id": "advise_control", "tier": "C", "layer": "咨询算子", "label": "时间窗反事实咨询",
     "cost": COST_HEAVY, "source": "mcp_server.py",
     "desc": "PH4 时间窗 MV 反事实咨询 + T1 操作窗硬约束校验。运行期连续调控已判封死（D-57），仅开环设定点标定。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("t_window_start", "float", 60.0, True, "窗口起点 h"),
                _p("t_window_end", "float", 120.0, True, "窗口终点 h"),
                _p("candidates", "json", None, False, "候选 MV 倍率列表（可选）")]},
    {"id": "trajectory_check", "tier": "A", "layer": "验收算子", "label": "逐点轨迹对照",
     "cost": COST_LIGHT, "source": "trajectory_metrics.py",
     "desc": "GOAL §4.2 轨迹级逐点对照 V3（RMSE / nRMSE / bias / R²）。",
     "params": [_p("batch_no", "int", None, True, "批号")]},
    {"id": "element_balance_check", "tier": "A", "layer": "验收算子", "label": "C/N 元素平衡",
     "cost": COST_LIGHT, "source": "conservation_metrics.py",
     "desc": "GOAL §4.3 批级 C/N 元素平衡闭合度。",
     "params": [_p("batch_no", "int", None, True, "批号")]},
    {"id": "discover_residual", "tier": "B", "layer": "结构发现算子", "label": "结构残差发现",
     "cost": COST_HEAVY, "source": "residual_discovery.py",
     "desc": "PH2 / SINDy 式稀疏辨识；返回体恒含「不可辨识 / 降级」标记。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("max_terms", "int", 3, False, "最大项数"),
                _p("theta_source", "str", "log", False, "θ 来源")]},
    {"id": "observe_online", "tier": "B", "layer": "在线观测器", "label": "在线 EnKF 同化",
     "cost": COST_HEAVY, "source": "observe.py",
     "desc": "PH5 在线 EnKF 同化（只读）；health_probe=True 开启健康探针（须 opt-in）。",
     "params": [_p("batch_no", "int", None, True, "批号"),
                _p("n_ens", "int", 20, False, "集合成员数（上限 50）"),
                _p("seed", "int", 7, False, "集合种子"),
                _p("stride", "int", 50, False, "输出抽稀步长"),
                _p("health_probe", "bool", False, False, "健康探针（opt-in）")]},
]

TOOL_BY_ID = {t["id"]: t for t in TOOLS}

# ---------------------------------------------------------------------------
# 12 个算子目录（运行时核验用；hier_est 已勘误为真实可调用的 hier_fit）
# ---------------------------------------------------------------------------
OPERATORS = [
    ("model.rhs", "model", "rhs", "仿真引擎", "ODE"),
    ("integrate_interval", "simulate", "integrate_interval", "仿真引擎", "积分器"),
    ("simulate_open_loop", "simulate", "simulate_open_loop", "仿真引擎", "主仿真"),
    ("yield_metrics", "simulate", "yield_metrics", "验收算子", "指标"),
    ("classify_crash", "simulate", "classify_crash", "验收算子", "判据"),
    ("build_params", "golden_params", "build_params", "仿真引擎", "装配"),
    ("estimate_batch", "soft_sensing", "estimate_batch", "软测量求解器", "B 档反演"),
    ("estimate_stage2", "stage2_estimator", "estimate_stage2", "软测量求解器", "B 档二阶段"),
    ("optimize_feed", "optimize", "optimize_feed", "寻优求解器", "C 档寻优"),
    ("hier_fit", "hier_est", "hier_fit", "分层估计求解器", "分层估计"),
    ("element_balance", "conservation_metrics", "element_balance", "验收算子", "守恒校验"),
    ("trajectory_metrics", "trajectory_metrics", "trajectory_metrics", "验收算子", "通道指标"),
]

# 数值型参数的硬上限（防误触导致长任务）
_CAPS = {"n_jobs": 6, "maxiter": 25, "n_ens": 50, "max_terms": 8, "stride": 200}

_MCP = None
_MCP_ERROR = None


def _mcp_module():
    """惰性 import mcp_server（进程内，不启动服务、不监听端口）。"""
    global _MCP, _MCP_ERROR
    if _MCP is None and _MCP_ERROR is None:
        try:
            _MCP = importlib.import_module("mcp_server")
        except Exception as exc:  # noqa: BLE001
            _MCP_ERROR = f"{type(exc).__name__}: {exc}"
    return _MCP


def _verify_operators():
    out = []
    for name, mod_name, attr, layer, kind in OPERATORS:
        err, loaded = None, False
        try:
            mod = importlib.import_module(mod_name)
            loaded = callable(getattr(mod, attr, None))
            if not loaded:
                err = f"{mod_name}.{attr} 不可调用"
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        out.append({"name": name, "module": mod_name, "attr": attr,
                    "file": mod_name + ".py", "layer": layer, "kind": kind,
                    "loaded": loaded, "error": err})
    return out


def status():
    """运行时装载核验：14 能力 + 12 算子，全部要求 callable。"""
    m = _mcp_module()
    tools = []
    for t in TOOLS:
        fn = getattr(m, t["id"], None) if m else None
        loaded = callable(fn)
        tools.append({**t,
                      "loaded": loaded,
                      "error": None if loaded else (
                          _MCP_ERROR or f"mcp_server.{t['id']} 不可调用"),
                      "signature": str(inspect.signature(fn)) if loaded else None})
    ops = _verify_operators()
    return {
        "backend": getattr(m, "_FASTMCP_BACKEND", None) if m else None,
        "n_tools": len(tools), "n_tools_loaded": sum(1 for x in tools if x["loaded"]),
        "tools": tools,
        "n_operators": len(ops), "n_operators_loaded": sum(1 for x in ops if x["loaded"]),
        "operators": ops,
        "all_loaded": all(x["loaded"] for x in tools) and all(x["loaded"] for x in ops),
        "l3_exposed": False,
        "forbidden_keys": sorted(FORBIDDEN_KEYS),
        "opt_in_params": sorted(OPT_IN_PARAMS),
        "source": "candidate/indpensim/v0.1/mcp_server.py（进程内复用，零复制）",
    }


class InvokeError(Exception):
    pass


def _coerce(spec, raw):
    """按声明类型做窄转换；不接受任意对象。"""
    typ = spec["type"]
    if raw is None or raw == "":
        return None
    if typ == "int":
        v = int(raw)
    elif typ == "float":
        v = float(raw)
    elif typ == "bool":
        v = raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes", "on")
    elif typ == "str":
        v = str(raw)
    elif typ == "json":
        v = json.loads(raw) if isinstance(raw, str) else raw
    else:
        raise InvokeError(f"未知参数类型 {typ}")
    if spec["name"] in _CAPS and isinstance(v, (int, float)):
        v = min(v, _CAPS[spec["name"]])
    return v


def invoke(tool_id, args=None, *, opt_in=False, confirm=False):
    """调用一个已装载能力。所有失败都显式返回原因，不静默降级。"""
    t = TOOL_BY_ID.get(tool_id)
    if t is None:
        raise InvokeError(f"未知能力 {tool_id!r}；白名单共 {len(TOOLS)} 项")
    m = _mcp_module()
    fn = getattr(m, tool_id, None) if m else None
    if not callable(fn):
        raise InvokeError(f"能力 {tool_id} 未装载：{_MCP_ERROR or '不可调用'}")

    args = dict(args or {})
    for k in list(args):
        if k in FORBIDDEN_KEYS:
            raise InvokeError(f"参数 {k} 属 L3 候选，平台不暴露：{FORBIDDEN_KEYS[k]}")

    sig = inspect.signature(fn)
    spec_by_name = {p["name"]: p for p in t["params"]}
    kwargs = {}
    for name, param in sig.parameters.items():
        spec = spec_by_name.get(name)
        if name not in args:
            continue
        raw = args.pop(name)
        try:
            v = _coerce(spec, raw) if spec else raw
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvokeError(f"参数 {name} 转换失败：{exc}") from exc
        if v is None:
            continue
        if name in OPT_IN_PARAMS and bool(v) and not opt_in:
            raise InvokeError(f"参数 {name}=True 需显式 opt_in=true（L3 保持 opt-in，不夹带边界变更）")
        kwargs[name] = v
    if args:
        raise InvokeError(f"未识别参数：{sorted(args)}")

    for p in t["params"]:
        if p["required"] and p["name"] not in kwargs:
            raise InvokeError(f"缺少必需参数 {p['name']}")
    if t["cost"] == COST_HEAVY and not confirm:
        raise InvokeError(f"能力 {tool_id} 属重调用，需 confirm=true 显式确认")

    t0 = time.time()
    with LOCK:
        result = fn(**kwargs)
    return {
        "ok": True, "tool": tool_id, "tier": t["tier"], "layer": t["layer"],
        "args": kwargs, "elapsed_s": round(time.time() - t0, 3),
        "opt_in": bool(opt_in), "confirm": bool(confirm),
        "source": t["source"], "result": result,
    }


def evidence():
    """工作台证据面板：全部从 runs/ 既有产物读，平台不重算指标。"""
    def jload(rel):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    fc = jload("runs/r166_final_check.json") or {}
    ab = jload("runs/r166_ab_gate.json") or {}
    vo = jload("runs/r166_v2_optim.json") or {}
    ms = jload("runs/r166_mcp_smoke.json") or {}
    zr = jload("runs/r166_zero_regression.json") or {}
    acc = jload("runs/r156_acceptance.json") or {}
    summary = acc.get("summary", {}) or {}
    return {
        "contract": _contract_version(),
        "final_check": {"verdict": fc.get("verdict"),
                        "n_pass": fc.get("n_pass"), "n_checks": fc.get("n_checks")},
        "ab_gate": {"verdict": ab.get("verdict"), "n_pass": ab.get("n_pass"),
                    "n_checks": ab.get("n_checks")},
        "v2_optim": {"verdict": vo.get("verdict"),
                     "max_abs_delta_pp": (vo.get("grid") or [{}])[-1].get("max_abs_delta_pp"),
                     "note": "V2 全幅 σ 注入多种子样本外失效 ⇒ NO_GO，保持 opt-in、不切默认"},
        "mcp_smoke": {"verdict": ms.get("verdict"), "n_pass": ms.get("n_pass"),
                      "n_checks": ms.get("n_checks")},
        "zero_regression": {"max_abs": zr.get("max_abs_delta"),
                            "rmse_pct": zr.get("rmse_pct"),
                            "within5": zr.get("within5"), "n": zr.get("n")},
        "acceptance": {"n": summary.get("n"),
                       "n_health": summary.get("n_health"),
                       "catastrophic_batches": summary.get("catastrophic_batches"),
                       "degraded_batches": summary.get("degraded_batches"),
                       "n_yield_ok": summary.get("n_yield_ok"),
                       "source": "runs/r156_acceptance.json"},
        "l3": {"state": "未执行 · 保持 opt-in",
               "items": ["R166-1 V1 转默认", "R166-2 V2 转默认",
                         "R166-3 V3 写回黄金参数", "R166-4 双基线并行制度"],
               "basis": "docs/roadmap_next.md §8.8 (a)：需用户二次确认 + 独立基线冻结"},
        "cap": "L2 prototype (conditional)",
    }


def _contract_version():
    """契约版本：头部 + 表体取最大（修 R134 只扫表体导致停在 v1.94 的缺陷）。"""
    import re
    best = None
    p = os.path.join(ROOT, "ENGINE_CONTRACT.md")
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                for pat in (r"[（(]v(\d+)\.(\d+)", r"^\|\s*v(\d+)\.(\d+)\s*\|"):
                    for m in re.finditer(pat, line):
                        v = (int(m.group(1)), int(m.group(2)))
                        if best is None or v > best:
                            best = v
    except OSError:
        pass
    return f"v{best[0]}.{best[1]}" if best else "unknown"
