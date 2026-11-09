# -*- coding: utf-8 -*-
"""平台 v2 —— 参数扫描引擎。

为什么需要它
------------
C 档寻优（`optimize.py` 的 Nelder-Mead）虽然能做反设计，但：
① 分钟级、结果不可视；② 目标单一时看不出**响应曲面**；
③ 找不到「可行域边界」这个真正有用的信息。

而本项目反复撞到的关键结论恰恰是**边界形态**：
  - R149/D-57：`Fs` 可行域 < ±1%，且响应是**硬跳变**（阈值型而非参数型）
  - R155：进料域窄是**标定**问题，不是数值的
  - R149：`γ1` 在 0.985 处悬崖，中段无过渡
这些结论都是扫描出来的。扫描是引擎级的一等能力，应该在平台里直接可用。

扫描口径
--------
1. **单参数扫描**：固定批级基准，逐点改一个参数，记录响应。
2. **双参数扫描**：两个参数的响应曲面（网格）。
3. 响应量可选：`yield_err`（产量相对误差 %）/ `yield_sim` / `health_level`
   / `co2d_max` / `ph_min` / `do2_min` / `p_max`。

失败可见
--------
每个扫描点都独立捕获异常：该点失败就记 `error`，**不中断整个扫描**
（否则一个点崩了整张曲面就没了）。但失败点必须在结果里**显式标注**，
不能被当成「值为 0」渲染 —— 那会让曲面图骗人。

成本控制
--------
扫描是「批量仿真」，单点 18–84 s ⇒ 一次扫描可能几十分钟。
因此：
  - `max_points` 硬上限（默认 24，一维；二维默认 16 = 4×4）
  - 进度实时回传（扫了几个 / 共几个）
  - 取消支持
"""
from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from engine_api import EngineError, assemble_params, _mod

# 响应量定义：key → (标签, 单位, 取值函数)
RESPONSES = {
    "yield_err": ("产量相对误差", "%", lambda m, s: m.get("yield", {}).get("rel_err_pct")),
    "yield_sim": ("仿真产量", "g", lambda m, s: m.get("yield", {}).get("sim_g")),
    "health": ("健康分级", "-", lambda m, s: _health_rank(m.get("health", {}).get("level"))),
    "co2d_max": ("CO2d 峰值", "g/L", lambda m, s: _col_max(s, "CO2d")),
    "ph_min": ("pH 最低", "-", lambda m, s: _col_min(s, "pH")),
    "ph_max": ("pH 最高", "-", lambda m, s: _col_max(s, "pH")),
    "do2_min": ("DO2 最低", "mg/L", lambda m, s: _col_min(s, "DO2")),
    "p_max": ("产物峰值", "g/L", lambda m, s: _col_max(s, "P")),
    "x_max": ("生物量峰值", "g/L", lambda m, s: _col_max(s, "X")),
    "s_max": ("残糖峰值", "g/L", lambda m, s: _col_max(s, "S")),
}

_HEALTH_RANK = {"normal": 0, "benign": 1, "degraded": 2, "catastrophic": 3, "unknown": 4}


def _health_rank(level: str | None) -> int:
    return _HEALTH_RANK.get(str(level), 4)


def _col_max(sim: dict, col: str) -> float | None:
    vals = (sim.get("trace", {}).get("cols", {}) or {}).get(col) or []
    xs = [v for v in vals if v is not None]
    return round(max(xs), 4) if xs else None


def _col_min(sim: dict, col: str) -> float | None:
    vals = (sim.get("trace", {}).get("cols", {}) or {}).get(col) or []
    xs = [v for v in vals if v is not None]
    return round(min(xs), 4) if xs else None


def _parse_axis(spec: dict) -> tuple[str, list[float]]:
    """把 {"key": "mux", "values": [..]} 或 {"key":"mux","from":a,"to":b,"n":k} 解析成 (key, values)。"""
    key = spec.get("key")
    if not key:
        raise EngineError("scan_invalid", "扫描轴缺少 key")
    if spec.get("values"):
        vals = [float(v) for v in spec["values"]]
    elif spec.get("from") is not None and spec.get("to") is not None:
        n = int(spec.get("n", 5))
        if n < 2:
            raise EngineError("scan_invalid", f"扫描轴 {key} 的 n 必须 ≥ 2")
        a, b = float(spec["from"]), float(spec["to"])
        vals = [a + (b - a) * i / (n - 1) for i in range(n)]
    else:
        raise EngineError("scan_invalid", f"扫描轴 {key} 需要 values 或 from/to+n")
    return key, vals


def _numeric_override(key: str, value: float) -> dict:
    """按参数表里的控件类型决定覆盖值的形态（json 型的需包成 dict/list）。"""
    from param_catalog import build_catalog
    cat = build_catalog()
    by_key = {p["key"]: p for g in cat["groups"] for p in g["params"]}
    spec = by_key.get(key)
    if spec is None:
        raise EngineError("param_invalid", f"参数 {key} 不在引擎参数表内")
    ctl = spec["control"]
    if ctl == "json":
        raise EngineError(
            "scan_invalid",
            f"参数 {key} 是结构化类型（{ctl}），不能做数值扫描；请在工况面板里手动配置",
        )
    if ctl == "select":
        return {key: int(value)}
    return {key: float(value)}


def run_sweep(job) -> dict:
    """扫描 runner（由 job_queue 的 Sweep 队列调用）。"""
    from engine_api import run_simulation

    p = job.payload
    batch = int(p.get("batch") or 0)
    axes = p.get("axes") or []
    if not 1 <= len(axes) <= 2:
        raise EngineError("scan_invalid", "扫描支持 1–2 个轴")
    response = str(p.get("response") or "yield_err")
    if response not in RESPONSES:
        raise EngineError("scan_invalid", f"未知响应量 {response}")
    base_overrides = p.get("overrides") or {}

    parsed = [_parse_axis(a) for a in axes]
    for k, _v in parsed:
        if k in ("fault_profile", "mv_scales", "mv_window_scales", "fs_ctl",
                 "fb_limit", "m_s_schedule", "assimilate"):
            raise EngineError("scan_invalid", f"参数 {k} 是结构化类型，不能做数值扫描")

    max_points = int(p.get("max_points") or (24 if len(parsed) == 1 else 16))
    grid = _make_grid(parsed, max_points)
    total = len(grid)
    if total == 0:
        raise EngineError("scan_invalid", "扫描网格为空")

    label, unit, getter = RESPONSES[response]
    t0 = time.time()
    points: list[dict] = []

    for i, combo in enumerate(grid):
        if job.cancel_flag:
            break
        ov = dict(base_overrides)
        try:
            for k, v in combo.items():
                ov.update(_numeric_override(k, v))
            r = run_simulation(batch, ov, stride=int(p.get("stride", 12)),
                               with_metrics=True, with_balance=False, with_trajectory=True)
            val = getter(r, r)
            hl = (r.get("health") or {}).get("level")
            points.append({
                "x": {k: round(float(v), 6) for k, v in combo.items()},
                "y": val,
                "ok": True,
                "yield_err": (r.get("yield") or {}).get("rel_err_pct"),
                "health": hl,
                "flags": list((r.get("health") or {}).get("flags") or []),
                "mv_warnings": list(r.get("mv_warnings") or []),
                "co2d_max": _col_max(r, "CO2d"),
                "ph_min": _col_min(r, "pH"),
                "elapsed_s": r.get("elapsed_s"),
            })
        except EngineError as exc:
            points.append({"x": {k: round(float(v), 6) for k, v in combo.items()},
                           "y": None, "ok": False, "error": exc.message, "code": exc.code})
        except Exception as exc:  # noqa: BLE001
            points.append({"x": {k: round(float(v), 6) for k, v in combo.items()},
                           "y": None, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                           "code": "engine_error"})
        job.progress = {"phase": "running", "detail": f"已扫 {i + 1}/{total} 点",
                        "done": i + 1, "total": total}

    ok_pts = [pt for pt in points if pt["ok"]]
    ys = [pt["y"] for pt in ok_pts if pt["y"] is not None]
    return {
        "ok": True,
        "kind": "sweep",
        "batch": batch,
        "response": response,
        "response_label": label,
        "response_unit": unit,
        "axes": [{"key": k, "values": [round(float(x), 6) for x in v]} for k, v in parsed],
        "base_overrides": base_overrides,
        "points": points,
        "n_total": total,
        "n_ok": len(ok_pts),
        "n_failed": total - len(ok_pts),
        "cancelled": job.cancel_flag,
        "elapsed_s": round(time.time() - t0, 2),
        "summary": {
            "y_min": round(min(ys), 4) if ys else None,
            "y_max": round(max(ys), 4) if ys else None,
            "y_median": round(float(np.median(ys)), 4) if ys else None,
        },
        "note": ("失败点以 ok=false 显式标注，未参与 min/max 统计；"
                 "不得把失败点渲染成 0 值。"),
    }


def _make_grid(parsed: list[tuple[str, list[float]]], max_points: int) -> list[dict]:
    """按轴数生成网格（超上限则提示截断）。"""
    import itertools
    axes = [v for _k, v in parsed]
    total = 1
    for a in axes:
        total *= max(1, len(a))
    if total > max_points:
        # 均匀抽稀到上限（保持首尾）
        keep = np.linspace(0, total - 1, max_points).round().astype(int)
        combos = list(itertools.product(*axes))
        return [dict(zip([k for k, _ in parsed], combos[j])) for j in sorted(set(keep.tolist()))]
    return [dict(zip([k for k, _ in parsed], combo)) for combo in itertools.product(*axes)]


if __name__ == "__main__":  # 自检：mux 粗扫描（3 点）
    import json
    import types
    job = types.SimpleNamespace(
        payload={"batch": 8, "axes": [{"key": "mux", "from": 0.35, "to": 0.47, "n": 3}],
                 "response": "yield_err", "stride": 40, "max_points": 3},
        cancel_flag=False, progress={},
    )
    r = run_sweep(job)
    print(json.dumps({"n": r["n_total"], "ok": r["n_ok"], "failed": r["n_failed"],
                      "summary": r["summary"], "elapsed_s": r["elapsed_s"],
                      "points": [{**pt["x"], "y": pt["y"], "ok": pt["ok"]} for pt in r["points"]]},
                     ensure_ascii=False, indent=2))
