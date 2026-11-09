# -*- coding: utf-8 -*-
"""platform_v2 四个引擎级能力的薄适配层。

只做参数整形 / 默认值裁剪 / 返回体裁剪，**不重新实现任何数值逻辑**：
  - 仿真走 `engine_api.run_simulation`（单一装配口径）
  - 扫描走 `scan.run_sweep`（失败点显式标注，不渲染成 0 值）
  - 参数目录走 `param_catalog.build_catalog`（AST 派生，不手写清单）

对 Agent 的特殊考虑：`run_simulation` 默认 `with_trajectory=False`。
全量轨迹是 1149 点 × 41 列，直接塞进工具返回体会淹没上下文；
需要轨迹的调用方显式打开即可（Python 库无此顾虑）。
"""
from __future__ import annotations

from typing import Any

from ._bootstrap import engine_module
from ._paths import bootstrap_paths, preserved_cwd


def _engine():
    bootstrap_paths()
    with preserved_cwd():
        return engine_module("engine_api")


def run_simulation(
    batch: int,
    overrides: dict | None = None,
    stride: int = 5,
    with_metrics: bool = True,
    with_balance: bool = True,
    with_trajectory: bool = False,
) -> dict:
    """跑一次完整仿真，返回产量/形状/健康/守恒/守卫审计/轨迹级指标。

    batch       : 批号 1–100（须在 golden_params.COMBINED 内）
    overrides   : 工况覆盖字典（逐键校验，L3 五键拒绝）
    stride      : 轨迹抽稀步长（仅 with_trajectory=True 时生效）
    with_trajectory : 是否回传全量轨迹（默认 False，避免返回体过大）
    """
    api = _engine()
    return api.run_simulation(
        int(batch), overrides or {}, stride=int(stride),
        with_metrics=bool(with_metrics), with_balance=bool(with_balance),
        with_trajectory=bool(with_trajectory),
    )


class _SweepJob:
    """`scan.run_sweep` 只需要 payload / cancel_flag / progress 三个字段。"""

    def __init__(self, payload: dict):
        self.payload = payload
        self.cancel_flag = False
        self.progress: dict[str, Any] = {}


def parameter_scan(
    batch: int,
    axes: list[dict],
    response: str = "yield_err",
    overrides: dict | None = None,
    max_points: int = 8,
    stride: int = 12,
) -> dict:
    """一维/二维参数扫描（每个点都是一次完整仿真）。

    axes 形如：
        [{"key": "mux", "values": [0.38, 0.41, 0.44]}]
        或 [{"key": "mux", "from": 0.38, "to": 0.44, "n": 3}]
    最多 2 个轴；max_points 封顶 16（单点 18–84 s，请勿轻易放大）。
    response 可用值见 `list_responses()`。
    """
    bootstrap_paths()
    scan = engine_module("scan")
    job = _SweepJob({
        "batch": int(batch),
        "axes": axes,
        "response": response,
        "overrides": overrides or {},
        "max_points": int(max_points),
        "stride": int(stride),
    })
    with preserved_cwd():
        out = scan.run_sweep(job)
    out["progress_final"] = job.progress
    return out


def param_catalog() -> dict:
    """AST 派生的参数目录：键 / 控件类型 / 有效域 / 分组。零算力。"""
    bootstrap_paths()
    pc = engine_module("param_catalog")
    with preserved_cwd():
        return pc.build_catalog()


def list_responses() -> dict:
    """扫描响应量目录：key / 标签 / 单位。零算力。"""
    bootstrap_paths()
    scan = engine_module("scan")
    return {
        "ok": True,
        "n": len(scan.RESPONSES),
        "responses": [{"key": k, "label": v[0], "unit": v[1]}
                      for k, v in scan.RESPONSES.items()],
        "note": "response 传 key；失败点以 ok=false 显式标注，不参与统计。",
    }
