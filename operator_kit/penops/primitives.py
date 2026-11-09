# -*- coding: utf-8 -*-
"""底层算子的 Python 库调用面（原生函数，可传 DataFrame / ndarray）。

    from penops import primitives as P

    P.get("model.state_names")()                  # 原生函数，零算力
    P.invoke("knowledge_constraints.control_hard")   # 统一返回体
    P.model__state_names()                        # 双下划线别名

    # 需要内存对象的算子也在这里畅通无阻
    sim, v3 = P.get("simulate.simulate_open_loop")(8, params)
    P.invoke("simulate.yield_metrics", sim=sim, v3=v3)

目录来自 `penops.registry.PRIMITIVES`；`python_objects=True` 的算子只在
这一层可调用，MCP 层会明确拒绝并说明原因（能力边界，不是缺失）。
"""
from __future__ import annotations

from typing import Any

from . import registry
from .errors import OperatorError


def get(name: str):
    """返回底层算子的原生函数本体（不复制实现，直接 import 引擎模块）。"""
    fn = registry.primitive_function(name)
    if not callable(fn):
        raise OperatorError("operator_not_loaded", f"底层算子 {name!r} 未装载或不可调用",
                            {"hint": "用 penops.operators() 查看目录"})
    return fn


def invoke(name: str, **kwargs: Any):
    """调用底层算子，返回统一返回体（JSON 安全）。"""
    from .client import invoke_primitive
    return invoke_primitive(name, **kwargs)


def __getattr__(name: str):
    """`model__rhs` → `model.rhs`；其余按目录里的名字直接找。"""
    key = name.replace("__", ".", 1)
    if key not in registry.PRIM_BY_NAME and name in registry.PRIM_BY_NAME:
        key = name
    if key in registry.PRIM_BY_NAME:
        return get(key)
    raise AttributeError(f"penops.primitives 没有算子 {name!r}")
