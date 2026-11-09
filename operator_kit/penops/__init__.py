# -*- coding: utf-8 -*-
r"""penops —— 工业青霉素发酵罐仿真算子的 L1 Python 库（可 import 直接调用）。

两层封装中的第一层；第二层是同目录下的 `penops_mcp`（MCP 协议适配，**当前未装载**）。

它能做什么
----------
把项目里散落的全部算子收进一个可调用的 Python 包：

    14 个 Agent 能力   A/B/C/D 全档（mcp_server.py 的函数本体，逐字复用）
     4 个 v2 扩展      全量仿真 / 参数扫描 / 参数目录 / 响应量目录
    58 个底层算子      引擎各模块的公开计算函数（含 R167 登记的 12 个）

快速开始
--------
    import sys; sys.path.insert(0, r"<项目根>\operator_kit")   # 或 pip install -e .
    import penops

    penops.solver_info()                          # 零算力自检
    penops.evaluate_batch(batch_no=8)             # A 档产量评估
    penops.call("param_catalog")                  # 统一调用口（带 ok/code/elapsed）
    penops.call("parameter_scan", batch=8, axes=[...], confirm=True)

    penops.status()                               # 14+4+56 项运行时 callable 核验
    penops.operators()                           # 底层算子目录
    penops.capabilities()                        # 能力 + 参数 JSON Schema
    penops.tools()                               # MCP tools/list（与 L2 同源）

    from penops import primitives as P
    sim, v3 = P.get("simulate.simulate_open_loop")(8, params)   # 原生对象可用
    P.invoke("model.state_names")

统一返回体
----------
`call()` / 顶层能力函数默认返回 `{ok, name, level, elapsed_s, result, ...}`；
失败返回 `{ok:False, code, error, detail}`，**不静默降级、不用默认值兜底**。
需要引擎原生对象（DataFrame 等）时传 `_envelope=False`，或直接走 `primitives.get()`。

守卫（沿用用户 2026-11-06 裁决，不夹带边界变更）
------------------------------------------------
* L3 五键（dist_noise_sigma / dist_noise_seed / innovation_criteria /
  k_dual / alpha_kla_override）在任何嵌套层级出现都硬拒绝；
* fallback_chain / health_probe 置 True 需 `_opt_in=True`；
* 重调用（86 批复验 / 集合平滑 / 寻优 / 扫描 / 同化）需 `_confirm=True`；
* n_jobs/maxiter/n_ens/max_terms/stride/max_points 封顶，batch_no ∈ [1,100]。

路径与可搬走性
---------------
默认 `operator_kit/` 位于项目根下。整体搬走后设置环境变量
`PENOPS_ENGINE_ROOT=<项目根绝对路径>` 即可，引擎实现仍从原项目 import。
默认注入 `fastmcp` 替身，因此本库**不依赖任何 MCP SDK**；
`PENOPS_REAL_MCP=1` 可改用真实 SDK（`penops.backend()` 如实报告）。

边界
----
不改 `candidate/` / `platform/` / `platform_v2/` / `data/` 的任何一行；
所有算子实现均从原位置进程内 import，L1 只做装配、校验与返回体包装。
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "call", "invoke_primitive", "status", "operators", "capabilities",
    "capability", "tools", "backend", "primitives", "registry", "guards",
    "OperatorError", "ErrorCode", "__version__",
]

from . import guards, primitives, registry  # noqa: E402
from .client import (  # noqa: E402
    backend, call, capabilities, capability, invoke_primitive,
    operators, status, tools,
)
from .errors import ErrorCode, OperatorError  # noqa: E402


def __getattr__(name: str):
    """`penops.solver_info()` 等顶层能力函数。"""
    from .client import capability
    if name in registry.CAP_BY_ID or name in registry.V2_BY_ID:
        return capability(name)
    raise AttributeError(f"penops 没有属性 {name!r}")
