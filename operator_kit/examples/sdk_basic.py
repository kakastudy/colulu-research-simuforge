# -*- coding: utf-8 -*-
"""L1 Python 库示例：从一次仿真到形状/健康/守恒的完整证据链。

运行：
    set PYTHONPATH=<operator_kit>
    python examples/sdk_basic.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import penops  # noqa: E402
from penops import primitives as P  # noqa: E402


def main() -> None:
    print("== 0. 装载自检 ==")
    st = penops.status()
    print(f"   能力 {st['n_capabilities_loaded']}/{st['n_capabilities']} · "
          f"算子 {st['n_primitives_loaded']}/{st['n_primitives']} · ok={st['ok']}")

    print("== 1. 零算力查询 ==")
    print("   参数目录分组数:", len(penops.call("param_catalog")["result"]["groups"]))
    print("   响应量:", [r["key"] for r in penops.call("list_responses")["result"]["responses"]])

    print("== 2. 一次完整仿真（v2 单一装配口径） ==")
    r = penops.run_simulation(batch=8, stride=12, with_trajectory=False)
    res = r["result"]
    print(f"   ok={r['ok']} elapsed={r['elapsed_s']}s · yield_err={res['yield']['rel_err_pct']}% "
          f"· health={res['health']['level']} · steps={res['n_steps']}")

    print("== 3. 底层算子直接用（DataFrame / ndarray 可传） ==")
    sim, v3 = P.get("simulate.simulate_open_loop")(8, {})
    ym = P.get("simulate.yield_metrics")(sim, v3)
    print(f"   sim 列数={len(sim.columns)} · 收获量={float(ym['total_sim_g']):.1f} g")

    print("== 4. 被拒的调用会给出原因码，不静默 ==")
    for name, kw in [("golden_set_validate", {"full": False}),
                     ("evaluate_batch", {"batch_no": 8, "params": {"k_dual": 1.0}}),
                     ("observe_online", {"batch_no": 8, "health_probe": True})]:
        out = penops.call(name, **kw)
        print(f"   {name:20s} → {out['code']}: {out['error'][:60]}")


if __name__ == "__main__":
    main()
