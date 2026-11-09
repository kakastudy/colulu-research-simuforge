# -*- coding: utf-8 -*-
"""调用守卫 —— 沿用 R167 三闸与用户 2026-11-06 的裁决，不因新封装夹带边界变更。

四道闸
------
1. **L3 五键硬拒绝**（用户上一轮裁决「开放全部已实现键，唯独 L3 五键保持拒绝」）。
   递归检查所有嵌套字典（`params` / `overrides` / `base_overrides` / `candidates` …），
   出现在任何一层都拒绝 —— 只查顶层等于没查。
2. **opt-in**：`fallback_chain` / `health_probe` 置 True 必须显式 `opt_in=True`。
3. **confirm**：`cost=heavy` 的能力（86 批复验 / 集合平滑 / 寻优 / 扫描 / 同化 …）
   必须 `confirm=True`，防止 Agent 误触长任务。
4. **数值上限 + 有效域**：n_jobs/maxiter/n_ens/max_terms/stride/max_points 封顶，
   batch_no ∈ [1,100]；MV 倍率验证域 [0.90,1.25] 只作提示，不静默改写用户值。

所有拒绝都抛 `OperatorError` 带稳定 code 与证据，不用「默认值兜底」蒙混过去。
"""
from __future__ import annotations

import json
import math
from typing import Any

from .errors import ErrorCode, OperatorError
from .registry import (CAP_BY_ID, HEAVY, V2_BY_ID, capability_function,
                       signature_schema)

# 与 platform/ops_registry.py 逐字一致 —— 用户裁决的 L3 五键
FORBIDDEN_KEYS: dict[str, str] = {
    "dist_noise_sigma": "R166/V2：8 路方差注入，多轮寻优判定 NO_GO，保持 opt-in",
    "dist_noise_seed": "R166/V2：方差注入种子，同上",
    "innovation_criteria": "R166/V1：逐通道创新判据，L3 未裁决",
    "k_dual": "R166/V3：alpha_kla 双约束查表，仅评测层，未写回",
    "alpha_kla_override": "R166/V3：写回黄金参数属 L3",
}

OPT_IN_PARAMS = {"fallback_chain", "health_probe"}

CAPS: dict[str, int] = {
    "n_jobs": 6, "maxiter": 25, "n_ens": 50, "max_terms": 8,
    "stride": 200, "max_points": 16,
}

BATCH_MIN, BATCH_MAX = 1, 100
MV_DOMAIN = (0.90, 1.25)


def _scan_forbidden(value: Any, path: str = "$") -> list[str]:
    """递归找 L3 键；返回 ['路径 -> 键: 原因']。"""
    hits: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in FORBIDDEN_KEYS:
                hits.append(f"{path}.{k} -> {k}: {FORBIDDEN_KEYS[k]}")
            hits.extend(_scan_forbidden(v, f"{path}.{k}"))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            hits.extend(_scan_forbidden(v, f"{path}[{i}]"))
    return hits


def _coerce(name: str, spec: dict, raw: Any) -> Any:
    typ = spec.get("type")
    if raw is None:
        return None
    try:
        if typ == "integer":
            v = int(raw)
        elif typ == "number":
            v = float(raw)
        elif typ == "boolean":
            v = raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes", "on")
        elif typ == "string":
            v = str(raw)
        elif typ == "object":
            v = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(v, dict):
                raise ValueError("应为对象/字典")
        elif typ == "array":
            v = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(v, (list, tuple)):
                raise ValueError("应为数组/列表")
        else:
            v = raw
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OperatorError(ErrorCode.PARAM_INVALID,
                            f"参数 {name} 转换失败（期望 {typ or '任意'}）：{exc}") from exc
    if name in CAPS and isinstance(v, (int, float)) and not isinstance(v, bool):
        v = min(v, CAPS[name])
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        raise OperatorError(ErrorCode.PARAM_INVALID,
                            f"参数 {name} 为非有限数（NaN/Inf）", {"value": str(raw)})
    return v


def validate_call(cid: str, args: dict | None, *, opt_in: bool = False,
                  confirm: bool = False) -> dict:
    """校验并清洗一次能力调用的参数，返回可直接 `fn(**clean)` 的关键字参数。"""
    c = CAP_BY_ID.get(cid) or V2_BY_ID.get(cid)
    if c is None:
        raise OperatorError(ErrorCode.UNKNOWN_OPERATOR,
                            f"未知能力 {cid!r}",
                            {"available": sorted(list(CAP_BY_ID) + list(V2_BY_ID))})

    raw = dict(args or {})
    # confirm 是协议层保留字段，剥掉后再交给引擎
    passed_confirm = bool(raw.pop("confirm", False)) or bool(confirm)

    # ① L3 递归硬拒绝（放在最前，任何一层出现都拦下）
    hits = _scan_forbidden(raw)
    if hits:
        raise OperatorError(ErrorCode.PARAM_FORBIDDEN,
                            "工况含 L3 候选参数，按用户裁决保持拒绝",
                            {"hits": hits, "forbidden_keys": sorted(FORBIDDEN_KEYS)})

    fn = capability_function(cid)
    if not callable(fn):
        raise OperatorError(ErrorCode.NOT_LOADED, f"能力 {cid} 的函数体未装载")
    schema = signature_schema(fn)  # 只用反射得到的参数名/类型，不另写清单
    props = schema.get("properties", {})
    required = schema.get("required", [])

    unknown = sorted(set(raw) - set(props))
    if unknown:
        raise OperatorError(ErrorCode.PARAM_INVALID, f"未识别参数：{unknown}",
                            {"allowed": sorted(props)})

    clean: dict[str, Any] = {}
    for name, value in raw.items():
        if name in OPT_IN_PARAMS and bool(value) and not opt_in:
            raise OperatorError(
                ErrorCode.OPT_IN_REQUIRED,
                f"参数 {name}=True 需显式 opt_in=True（L3 保持 opt-in）",
                {"opt_in_params": sorted(OPT_IN_PARAMS)},
            )
        v = _coerce(name, props[name], value)
        if v is not None:
            clean[name] = v

    missing = [k for k in required if k not in clean]
    if missing:
        raise OperatorError(ErrorCode.PARAM_INVALID, f"缺少必需参数：{missing}",
                            {"required": required})

    if "batch_no" in clean:
        b = clean["batch_no"]
        if not isinstance(b, int) or not (BATCH_MIN <= b <= BATCH_MAX):
            raise OperatorError(ErrorCode.BATCH_OUT_OF_RANGE,
                                f"batch_no 必须在 [{BATCH_MIN},{BATCH_MAX}]，实得 {b!r}")
    if "batch" in clean:
        b = clean["batch"]
        if not isinstance(b, int) or not (BATCH_MIN <= b <= BATCH_MAX):
            raise OperatorError(ErrorCode.BATCH_OUT_OF_RANGE,
                                f"batch 必须在 [{BATCH_MIN},{BATCH_MAX}]，实得 {b!r}")

    # axes（扫描）里的 batch 由 payload 顶层控制；max_points 由 CAPS 封顶
    if c["cost"] == HEAVY and not passed_confirm:
        raise OperatorError(
            ErrorCode.CONFIRM_REQUIRED,
            f"能力 {cid} 属重调用（{c['label']}），需显式 confirm=True",
            {"cost": HEAVY, "label": c["label"], "desc": c["desc"]},
        )
    return clean


def validate_primitive(name: str, kwargs: dict | None,
                       *, allow_python_objects: bool = False) -> Any:
    """校验一次底层算子调用：返回函数本体（调用方自行 `fn(**kwargs)`）。"""
    from .registry import PRIM_BY_NAME, primitive_function

    p = PRIM_BY_NAME.get(name)
    if p is None:
        raise OperatorError(ErrorCode.UNKNOWN_OPERATOR,
                            f"未知底层算子 {name!r}",
                            {"hint": "用 list_operators() 查看全部算子"})
    if p["python_objects"] and not allow_python_objects:
        raise OperatorError(
            ErrorCode.PYTHON_OBJECT_REQUIRED,
            f"算子 {name} 需要内存对象（DataFrame / ndarray / 状态向量），MCP 层不接受这类入参",
            {"python_objects": True, "hint": "请在 L1 Python 库中直接调用 primitives.<name>()"},
        )
    hits = _scan_forbidden(kwargs or {})
    if hits:
        raise OperatorError(ErrorCode.PARAM_FORBIDDEN,
                            "算子入参含 L3 候选参数，保持拒绝", {"hits": hits})
    fn = primitive_function(name)
    if not callable(fn):
        raise OperatorError(ErrorCode.NOT_LOADED, f"底层算子 {name} 未装载")
    return fn
