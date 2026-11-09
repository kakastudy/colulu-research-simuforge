# -*- coding: utf-8 -*-
"""平台 v2 —— 仿真引擎封装层。

这一层是**唯一的**仿真执行入口，平台 v2 的所有接口都经它，
以保证「平台数字」与「引擎数字」不可能分叉（R167 建立的同源原则）。

它做什么
--------
1. 统一装配：批级黄金参数（`build_params(COMBINED[b])`） + 用户工况覆盖
   ⇒ **单一装配口径**，禁止绕过（对齐 ENGINE_CONTRACT 的 build_params 约定）。
2. 执行仿真：`simulate_open_loop`（33 维 ODE + BDF 积分）。
3. 提取结果：
   - 全 41 列轨迹（原生 0.2h 分辨率，不降采样到 2h —— 那是看板的取舍，不是引擎的）
   - 产量指标（`yield_metrics`：harvested + V·P，与 MATLAB `Penicllin_yield_total` 逐位同构）
   - 五通道健康分级（`classify_health`，非恒真的旧 `classify_crash`）
   - 守恒核验（`element_balance`）
   - 轨迹级指标（`trajectory_metrics`）
   - 守卫审计（`sim.attrs['guard_audit']`）
   - 有效域越界告警（`sim.attrs['mv_warnings']`）
4. 失败**显式可见**：分��/越域/参数非法/积分发散各自带原因返回，
   绝不用「看起来正常」的默认值兜底（对齐 I2 失败可见）。

为什么不用 `platform/serve.py` 里那套
-----------------------------------
旧平台的 `/api/simulate` 是 **L0 冻结基线**（R167 契约要求函数体逐字未改），
只开放 14 个参数、只取 8 通道、降到 2h、且同步阻塞（实测 18–84 s）。
本模块是**新平台 v2** 的独立实现，不改动旧平台的任何一行。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENGINE_DIR = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

sys.path.insert(0, os.path.join(ROOT, "platform_v2"))
from param_catalog import build_catalog, validate_overrides  # noqa: E402

# 引擎侧模块（惰性 import，避免服务启动即承担 3.8 s 的 import 成本）
_MODS: dict[str, Any] = {}


def _mod(name: str):
    """惰性 import 引擎模块并缓存。"""
    if name not in _MODS:
        import importlib
        _MODS[name] = importlib.import_module(name)
    return _MODS[name]


def load_batch_csv(batch_no: int) -> pd.DataFrame:
    p = os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch_no:02d}.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(f"批 {batch_no} 的 V3 数据不存在：{p}")
    return pd.read_csv(p)


def golden_batches() -> list[int]:
    gp = _mod("golden_params")
    return [b for b in gp.GOLDEN_ALL if b in gp.COMBINED]


def scenario_fingerprint(batch: int, overrides: dict, extra: dict | None = None) -> str:
    """工况指纹：同一工况 ⇒ 同一结果 ⇒ 可缓存。"""
    payload = json.dumps(
        {"batch": batch, "ov": overrides, "ex": extra or {}},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class EngineError(Exception):
    """带显式原因码的引擎错误（前端据此区分失败类型，不吞异常）。"""

    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"ok": False, "code": self.code, "error": self.message, "detail": self.detail}


def assemble_params(batch: int, overrides: dict) -> tuple[dict, dict]:
    """装配仿真参数。

    返回 (params, report)：
      params  —— 传给 simulate_open_loop 的参数字典
      report  —— {applied, rejected, base, warnings}

    装配口径：
      ① 底座 = build_params(COMBINED[batch]) 的批级黄金覆盖（**唯一装配入口**）
      ② 覆盖 = 用户工况，逐键校验（L3 键硬拒绝 / 未知键拒绝 / 非有限数拒绝）
    """
    gp = _mod("golden_params")
    if batch not in gp.COMBINED:
        raise EngineError(
            "batch_not_in_golden",
            f"批 {batch} 不在黄金集 COMBINED 中，无法作为仿真底座",
            {"available_n": len(gp.COMBINED)},
        )
    base = gp.build_params(gp.COMBINED[batch])
    catalog = build_catalog()
    clean, problems = validate_overrides(overrides or {}, catalog)
    if problems:
        raise EngineError("param_invalid", "工况参数被拒绝", {"problems": problems})

    params = dict(base)
    params.update(clean)
    return params, {
        "applied": clean,
        "rejected": problems,
        "base": {k: v for k, v in gp.COMBINED[batch].items()},
    }


# 轨迹输出列 —— 全量原生分辨率，不降采样
TRACE_COLUMNS = [
    "time_h",
    # 操作量（回放 + 覆盖）
    "Fg", "RPM", "Fs", "Fa", "Fb", "Fc", "Fh", "Fw", "pressure", "Fremoved",
    "Fpaa", "Foil", "NH3_shots",
    # 状态
    "S", "P", "X", "PAA", "NH3", "DO2", "T", "pH", "pH_openloop", "pH_pre",
    "V", "Wt", "Q", "vis", "vis_state",
    # 气体 / 代谢
    "CO2outgas", "CO2d", "OUR", "O2", "CER",
    # 动力学内部量
    "mup", "mux",
    # 菌丝区
    "A0", "A1", "A3", "A4", "A_t1",
]


def _clean_series(vals: np.ndarray) -> list:
    """NaN/Inf ⇒ null（JSON 友好），保留数组长度不塌陷。"""
    out = []
    for v in vals:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            out.append(None)
        else:
            out.append(round(f, 6))
    return out


def _downsample(ts: np.ndarray, factor: int) -> np.ndarray:
    """按因子抽稀（保持首尾点）。factor=1 ⇒ 不抽稀。"""
    if factor <= 1:
        return np.arange(len(ts))
    idx = list(range(0, len(ts), factor))
    if idx[-1] != len(ts) - 1:
        idx.append(len(ts) - 1)
    return np.array(idx, dtype=int)


def run_simulation(
    batch: int,
    overrides: dict | None = None,
    *,
    stride: int = 1,
    with_metrics: bool = True,
    with_balance: bool = True,
    with_trajectory: bool = True,
) -> dict:
    """执行一次仿真并返回结构化结果。

    stride：轨迹抽稀步长（1 = 全量 1149 点原生分辨率）。
    """
    t0 = time.time()
    overrides = overrides or {}
    params, rep = assemble_params(batch, overrides)

    sim_mod = _mod("simulate")
    try:
        sim, v3 = sim_mod.simulate_open_loop(batch, params)
    except Exception as exc:  # noqa: BLE001
        raise EngineError(
            "simulation_failed",
            f"仿真执行失败：{type(exc).__name__}: {exc}",
            {"traceback": traceback.format_exc(limit=6)},
        ) from exc

    elapsed = time.time() - t0
    out: dict[str, Any] = {
        "ok": True,
        "batch": batch,
        "applied": rep["applied"],
        "base": rep["base"],
        "fingerprint": scenario_fingerprint(batch, rep["applied"]),
        "elapsed_s": round(elapsed, 2),
        "n_steps": int(len(sim)),
    }

    # ---- 守卫审计（I2 失败可见）----
    au = sim.attrs.get("guard_audit", {}) or {}
    out["guard_audit"] = {
        "n_steps": au.get("n_steps"),
        "tally": au.get("tally"),
        "tally_first": au.get("tally_first"),
        "ph_nonpos_steps": au.get("ph_nonpos_steps"),
        "ph_max_pre": au.get("ph_max_pre"),
        "n_ph_over7_pre": au.get("n_ph_over7_pre"),
        "audit_consistent": au.get("audit_consistent"),
    }
    # ---- 有效域越界告警（mv_warnings）----
    out["mv_warnings"] = list(sim.attrs.get("mv_warnings", []) or [])
    out["ph_basic_fixed"] = bool(sim.attrs.get("ph_basic_fixed", False))

    # ---- 轨迹（全量原生分辨率）----
    if with_trajectory:
        ts = sim["time_h"].to_numpy(float)
        keep = _downsample(ts, int(stride))
        trace: dict[str, list] = {"t": _clean_series(ts[keep])}
        cols = {}
        for c in TRACE_COLUMNS:
            if c == "time_h" or c not in sim.columns:
                continue
            cols[c] = _clean_series(sim[c].to_numpy(float)[keep])
        trace["cols"] = cols
        out["trace"] = trace
        out["stride"] = int(stride)

    # ---- 指标 ----
    if with_metrics:
        ym = sim_mod.yield_metrics(sim, v3)
        out["yield"] = {
            "sim_g": round(float(ym["total_sim_g"]), 2),
            "v3_g": round(float(ym["total_v3_g"]), 2),
            "rel_err_pct": round(float(ym["rel_err_total"]) * 100, 3),
            "harvested_sim_g": _f(ym.get("harvested_sim_g")),
            # 注意键名是 end_in_vessel_sim_g（不是 in_vessel_sim_g）
            "end_in_vessel_sim_g": _f(ym.get("end_in_vessel_sim_g")),
            "harvested_v3_g": _f(ym.get("harvested_v3_g")),
            "end_in_vessel_v3_g": _f(ym.get("end_in_vessel_v3_g")),
        }
        # 形状指标（R151：产量指标对 P 轨迹失明 ⇒ 必须同时报形状）
        # shape_metrics 返回**嵌套结构** {通道: {标量, 相位:{...}}}，
        # 这里展平成「通道.字段」两级，前端直接渲染。
        try:
            shp = sim_mod.shape_metrics(sim, v3)
            flat: dict[str, Any] = {}
            for ch, d in (shp or {}).items():
                if not isinstance(d, dict):
                    continue
                for k, v in d.items():
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            if isinstance(v2, dict):
                                continue
                            flat[f"{ch}.{k}.{k2}"] = _num_or_none(v2)
                    else:
                        flat[f"{ch}.{k}"] = _num_or_none(v)
            out["shape"] = flat
        except Exception as exc:  # noqa: BLE001
            out["shape"] = {"_error": f"{type(exc).__name__}: {exc}"}

        # 五通道健康分级（非恒真的旧判据）
        # classify_health 返回**单个 dict** {level, flags, channels, evidence, …}，
        # 不是 (level, flags, evidence) 三元组（R167 平台侧曾按三元组解包 → 恒为 unknown）。
        try:
            hs = sim_mod.classify_health(sim, v3, yield_err=float(ym["rel_err_total"]))
            if isinstance(hs, dict):
                out["health"] = {
                    "level": hs.get("level", "unknown"),
                    "flags": list(hs.get("flags") or []),
                    "channels": _jsonable(hs.get("channels") or {}),
                    "evidence": _jsonable(hs.get("evidence") or {}),
                }
            else:  # 兼容三元组形态
                lvl, flags, evidence = hs
                out["health"] = {"level": lvl, "flags": list(flags or []),
                                 "evidence": _jsonable(evidence)}
        except Exception as exc:  # noqa: BLE001
            out["health"] = {"level": "unknown", "flags": [],
                             "evidence": {"error": f"{type(exc).__name__}: {exc}"}}

        # 旧判据：保留但**显式标注其恒真性**（D-38），不作为结论
        try:
            lvl2, reasons2 = sim_mod.classify_crash(
                sim, yield_err=float(ym["rel_err_total"]))
            out["crash_legacy"] = {"level": lvl2, "reasons": list(reasons2 or []),
                                   "caveat": "D-38：旧判据在黄金集上恒真（恒等 0 命中），仅作兼容，不作结论"}
        except Exception:  # noqa: BLE001
            out["crash_legacy"] = None

    # ---- 守恒 ----
    if with_balance:
        try:
            bal = _mod("conservation_metrics").element_balance(v3)
            out["balance"] = _jsonable(bal)
        except Exception as exc:  # noqa: BLE001
            out["balance"] = {"error": f"{type(exc).__name__}: {exc}"}

    # ---- 轨迹级指标 ----
    try:
        tm = _mod("trajectory_metrics").trajectory_metrics(sim, v3, batch_no=batch)
        out["trajectory_metrics"] = _jsonable(tm)
    except Exception as exc:  # noqa: BLE001
        out["trajectory_metrics"] = {"error": f"{type(exc).__name__}: {exc}"}

    return out


def _f(v: Any) -> float | None:
    """浮点清洗：NaN/Inf ⇒ None（JSON 里应是 null，不是 NaN 字面量）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


def _num_or_none(v: Any) -> Any:
    """标量数值清洗；非数值原样返回。"""
    if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
        return v
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 5)


def _jsonable(obj: Any) -> Any:
    """把 numpy / pandas 标量转成 JSON 原生类型。"""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else round(obj, 6)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    return obj


if __name__ == "__main__":  # 自检：跑一批，验证装配与指标链路
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--stride", type=int, default=5)
    a = ap.parse_args()
    t = time.time()
    r = run_simulation(a.batch, {}, stride=a.stride)
    print(json.dumps({
        "ok": r["ok"], "batch": r["batch"], "elapsed_s": r["elapsed_s"],
        "yield": r.get("yield"), "health": (r.get("health") or {}).get("level"),
        "flags": (r.get("health") or {}).get("flags"),
        "trace_cols": len((r.get("trace") or {}).get("cols", {})),
        "n_steps": r["n_steps"],
        "guard": r.get("guard_audit", {}).get("ph_nonpos_steps"),
    }, ensure_ascii=False, indent=2))
