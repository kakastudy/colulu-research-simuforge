# -*- coding: utf-8 -*-
"""L1 Python 库的调用面。

三种用法，按需要选：
    import penops

    # ① 顶层函数（最像普通 Python 库）
    info = penops.solver_info()
    ev   = penops.evaluate_batch(batch_no=8)

    # ② 统一调用口（可编程/可枚举，返回带 ok/code/elapsed 的统一返回体）
    r = penops.call("parameter_scan", batch=8, axes=[...], confirm=True)

    # ③ 底层算子（原生函数，DataFrame / ndarray 可直接传）
    fn = penops.primitives.get("simulate.simulate_open_loop")
    sim, v3 = fn(8, params)
    penops.primitives.invoke("model.state_names")

全部能力、参数、schema 都来自 `registry.py` 这一个真源。
"""
from __future__ import annotations

import functools
import time
from typing import Any

from . import guards, registry
from ._bootstrap import backend_info
from .errors import OperatorError, wrap_exception
from .result import err_envelope, ok_envelope


def call(name: str, *args: Any, _opt_in: bool = False, _confirm: bool = False,
         _envelope: bool = True, **kwargs: Any) -> Any:
    """按名字调用一个已登记能力。

    `_envelope=True`（默认）返回统一返回体 `{ok,name,level,elapsed_s,result}`；
    `_envelope=False` 直接返回引擎原生对象（dict / DataFrame）。
    重调用需 `_confirm=True`；opt-in 开关需 `_opt_in=True`。
    """
    if args:
        raise OperatorError("param_invalid", "能力参数请用关键字传入（与函数签名一致），"
                            f"位置参数不受支持：{args!r}")
    t0 = time.time()
    try:
        clean = guards.validate_call(name, kwargs, opt_in=_opt_in, confirm=_confirm)
        c = registry.CAP_BY_ID.get(name) or registry.V2_BY_ID[name]
        fn = registry.capability_function(name)
        if not callable(fn):
            raise OperatorError("operator_not_loaded", f"能力 {name} 函数体未装载")
        raw = fn(**clean)
        if not _envelope:
            return raw
        return ok_envelope(name, raw, elapsed_s=time.time() - t0,
                           level="capability", tier=c["tier"], layer=c["layer"],
                           args=clean, opt_in=bool(_opt_in), confirm=bool(_confirm))
    except OperatorError as exc:
        if not _envelope:
            raise
        return err_envelope(name, exc, elapsed_s=time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        e = wrap_exception(exc, f"能力 {name}")
        if not _envelope:
            raise e from exc
        return err_envelope(name, e, elapsed_s=time.time() - t0)


def invoke_primitive(name: str, *args: Any, _envelope: bool = True,
                     **kwargs: Any) -> Any:
    """按全限定名调用底层算子（允许传 DataFrame / ndarray 等内存对象）。"""
    if args:
        raise OperatorError("param_invalid", "底层算子请用关键字传参", {"args": repr(args)})
    t0 = time.time()
    try:
        fn = guards.validate_primitive(name, kwargs, allow_python_objects=True)
        raw = fn(**kwargs)
        if not _envelope:
            return raw
        return ok_envelope(name, raw, elapsed_s=time.time() - t0,
                           level="primitive", args=list(kwargs))
    except OperatorError as exc:
        if not _envelope:
            raise
        return err_envelope(name, exc, elapsed_s=time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        e = wrap_exception(exc, f"底层算子 {name}")
        if not _envelope:
            raise e from exc
        return err_envelope(name, e, elapsed_s=time.time() - t0)


def status() -> dict:
    """运行时装载核验（14 能力 + 4 扩展 + 全部底层算子，逐个 import + callable）。"""
    return registry.runtime_status()


def operators(layer: str | None = None, agent_safe_only: bool = False) -> dict:
    """列出底层算子目录。"""
    return registry.list_operators(layer=layer, agent_safe_only=agent_safe_only)


def capabilities() -> list[dict]:
    """列出全部高层能力（含 tier / cost / 描述 / 参数 schema）。"""
    return [{"id": c["id"], "label": c["label"], "tier": c["tier"],
             "layer": c["layer"], "cost": c["cost"], "desc": c["desc"],
             "inputSchema": registry.capability_schema(c["id"])}
            for c in registry.CAPABILITIES + registry.V2_EXTENSIONS]


def tools(profile: str = "capabilities") -> list[dict]:
    """生成 MCP tools/list 的返回体（L2 用的就是它，保证两层清单不分叉）。"""
    return registry.mcp_tools(profile=profile)


def backend() -> dict:
    return backend_info()


def capability(name: str):
    """返回一个可直接调用的能力包装函数（带原函数签名语义的 docstring）。"""
    c = registry.CAP_BY_ID.get(name) or registry.V2_BY_ID.get(name)
    if c is None:
        raise OperatorError("unknown_operator", f"未知能力 {name!r}")

    def _wrapper(*args: Any, **kwargs: Any):
        return call(name, *args, **kwargs)

    _wrapper.__name__ = name
    _wrapper.__qualname__ = name
    _wrapper.__doc__ = (f"{c['label']}（{c['tier']} 档 / {c['cost']}）\n\n{c['desc']}\n\n"
                        f"参数见 penops.capabilities() 的 inputSchema；"
                        f"重调用需 _confirm=True；返回统一返回体。")
    return _wrapper


def __getattr__(name: str):
    """`penops.solver_info()` / `penops.evaluate_batch(batch_no=8)` 的入口。"""
    if name in registry.CAP_BY_ID or name in registry.V2_BY_ID:
        return capability(name)
    raise AttributeError(f"penops 没有属性 {name!r}")
