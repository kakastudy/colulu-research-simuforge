# -*- coding: utf-8 -*-
"""统一返回体与 JSON 清洗。

Python 库调用返回原生 Python 对象（dict / DataFrame / ndarray 都保留），
但 `call(..., envelope=True)` 与 MCP 层必须给出 **JSON 安全** 的返回体：
NaN / Inf 一律转 null, numpy 标量转原生类型，pandas 对象转 records。
不擅自 round —— 数值精度必须和引擎逐位一致。
"""
from __future__ import annotations

import math
import time
from typing import Any

from .errors import OperatorError


def jsonable(obj: Any, *, _depth: int = 0) -> Any:
    """递归转 JSON 可序列化对象；遇到不可识别类型显式报错。"""
    if _depth > 24:
        raise ValueError("jsonable: 嵌套过深（>24），疑似循环引用")
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj

    # numpy（惰性 import，避免 L1 启动即承担 numpy 成本）
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore[assignment]
    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            f = float(obj)
            return None if (math.isnan(f) or math.isinf(f)) else f
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [jsonable(v, _depth=_depth + 1) for v in obj.tolist()]

    try:
        import pandas as pd
    except ImportError:
        pd = None  # type: ignore[assignment]
    if pd is not None:
        if isinstance(obj, pd.DataFrame):
            return [{str(k): jsonable(v, _depth=_depth + 1)
                     for k, v in row.items()}
                    for row in obj.to_dict(orient="records")]
        if isinstance(obj, pd.Series):
            return {str(k): jsonable(v, _depth=_depth + 1) for k, v in obj.to_dict().items()}
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj)

    if isinstance(obj, dict):
        return {str(k): jsonable(v, _depth=_depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v, _depth=_depth + 1) for v in obj]
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {str(k): jsonable(v, _depth=_depth + 1)
                for k, v in vars(obj).items() if not k.startswith("_")}
    raise TypeError(f"jsonable: 不支持的类型 {type(obj).__name__}")


def ok_envelope(name: str, result: Any, *, elapsed_s: float = 0.0,
                level: str = "capability", **meta: Any) -> dict:
    """成功返回体。result 一律经 JSON 清洗。"""
    try:
        body = jsonable(result)
    except (TypeError, ValueError) as exc:
        raise OperatorError("serialization_error",
                            f"能力 {name} 的返回体无法 JSON 化：{exc}") from exc
    return {
        "ok": True,
        "name": name,
        "level": level,
        "elapsed_s": round(elapsed_s, 3),
        **meta,
        "result": body,
    }


def err_envelope(name: str, err: OperatorError, *, elapsed_s: float = 0.0,
                 **meta: Any) -> dict:
    return {"ok": False, "name": name, "elapsed_s": round(elapsed_s, 3),
            **meta, **err.to_dict()}


class Timer:
    def __init__(self):
        self.t0 = time.time()

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0
