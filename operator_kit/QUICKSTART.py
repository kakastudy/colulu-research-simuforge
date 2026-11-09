# -*- coding: utf-8 -*-
r"""penops 两层封装 —— 可运行的使用说明（代替 README，直接 `python QUICKSTART.py`）。

    python operator_kit/QUICKSTART.py             # 跑 L1 轻调用 + L2 自检
    python operator_kit/QUICKSTART.py --simulate  # 额外跑一次真实 A 档仿真（约 20 s）

两层
----
L1 `penops/`      —— 像普通 Python 库一样 `import penops; penops.evaluate_batch(batch_no=8)`。
                     可用 `pip install -e operator_kit` 安装，或把 operator_kit 加进 sys.path。
L2 `penops_mcp/`  —— MCP 协议适配（stdio JSON-RPC）。**当前未装载**：没有写进
                     `~/.workbuddy/mcp.json`、没有启动常驻服务、没有监听端口。
                     以后要装载，把 `penops_mcp/mcp.json.example` 的 mcpServers 段
                     合并进 `~/.workbuddy/mcp.json` 即可（该示例已按本机路径填好）。

覆盖范围
--------
    14 个 A/B/C/D Agent 能力（mcp_server.py 函数本体，进程内逐字复用）
     4 个 v2 扩展（全量仿真 / 参数扫描 / 参数目录 / 响应量目录）
    58 个底层算子（引擎各模块公开计算函数，含 R167 登记的 12 个）
    = 18 个高层能力 + 58 个底层算子；MCP 默认注册 21 个工具（18 + 3 元工具），
      底层算子经 `list_operators` / `invoke_operator` 两个元工具全量可达。

不变量
------
* 不复制实现：所有数值逻辑都从 `candidate/indpensim/v0.1/` 与 `platform_v2/` 现场 import。
* 不改旧目录一行：`platform/`（L0 冻结基线）/ `platform_v2/` / `candidate/` / `data/` 全部只读。
* 失败显式：统一返回体 `{ok, code, error, detail}`，NaN/Inf → null，绝不静默降级。
* L3 五键保持拒绝；opt-in / confirm / 数值上限四道闸沿用用户 2026-11-06 裁决。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

KIT = os.path.dirname(os.path.abspath(__file__))
if KIT not in sys.path:
    sys.path.insert(0, KIT)


def _show(title: str, obj, limit: int = 420) -> None:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    print(f"\n--- {title} ---\n{s[:limit]}{' …' if len(s) > limit else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true", help="额外跑一次真实 A 档仿真")
    a = ap.parse_args()

    import penops
    from penops import primitives as P

    print(f"penops {penops.__version__} · python {sys.version.split()[0]}")
    s = penops.status()
    print(f"运行时装载：能力 {s['n_capabilities_loaded']}/{s['n_capabilities']} · "
          f"底层算子 {s['n_primitives_loaded']}/{s['n_primitives']} · "
          f"backend={s['backend']['mcp_backend']}")

    # ① 顶层函数（最像普通 Python 库）
    info = penops.solver_info()
    _show("① penops.solver_info()", {"ok": info["ok"],
                                     "name": info["result"]["name"],
                                     "tiers": list(info["result"]["tiers"])})

    # ② 统一调用口（带错误码）
    cat = penops.call("param_catalog")
    _show("② penops.call('param_catalog')", {"ok": cat["ok"],
                                             "n_groups": len(cat["result"]["groups"]),
                                             "derived": cat["result"].get("derived")})

    # ③ 底层算子（原生函数，可传 DataFrame / ndarray）
    names = P.get("model.state_names")()
    _show("③ P.get('model.state_names')()", {"n_states": len(names), "head": names[:5]})

    # ④ 守卫：重调用未确认 ⇒ 显式错误码，不偷偷执行
    blocked = penops.call("golden_set_validate", full=False)
    _show("④ 重调用未确认", {"ok": blocked["ok"], "code": blocked["code"]})

    # ⑤ 真仿真（可选）
    if a.simulate:
        ev = penops.evaluate_batch(batch_no=8)
        _show("⑤ penops.evaluate_batch(batch_no=8)",
              {"ok": ev["ok"], "elapsed_s": ev["elapsed_s"],
               "yield": (ev.get("result") or {}).get("yield"),
               "crash": (ev.get("result") or {}).get("crash")})

    # ⑥ L2：工具清单与 L1 同源
    tools = penops.tools()
    _show("⑥ MCP tools/list（同源派生）",
          {"n_tools": len(tools), "names": [t["name"] for t in tools]})

    print("\nL2 启动方式（本轮不执行）：")
    print(f"  set PYTHONPATH={KIT}")
    print("  python -m penops_mcp --self-check     # 自检")
    print("  python -m penops_mcp                  # stdio 服务，供 Agent 装载后调用")
    return 0 if s["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
