# -*- coding: utf-8 -*-
"""平台本地服务：静态站点 + 仿真 API。

为什么需要它
------------
平台如果只能读 `data.js`，那只是一个报告页。真正的"仿真平台"必须能**当场改参数、
当场出轨迹**。浏览器跑不了 Python，所以用一个零依赖的本地 HTTP 服务把算子库暴露出来。

接口
----
GET  /api/health                  → 引擎就绪状态、可用批次、契约版本、装载摘要
POST /api/simulate                → {batch, overrides:{...}} 返回轨迹 + 产量误差
      body: {"batch": 8, "overrides": {"mux": 0.36, "mup": 0.035, "alpha_kla": 85}}
GET  /api/ops                     → R167：14 个 A/B/C/D 能力 + 12 个算子的**运行时**装载核验
GET  /api/evidence                → R167：工作台证据面板（只读 runs/ 产物，不重算指标）
POST /api/invoke                  → R167：调用已装载能力
      body: {"tool": "evaluate_batch", "args": {"batch_no": 8}, "confirm": false}

R167 / D-65 补充
----------------
- `/api/simulate` 是 **L0 冻结基线**，函数体逐字未改；新增的三个接口全部为 additive。
- 能力**不是复制实现**，而是进程内复用 `mcp_server.py` 的 14 个工具函数本体
  （`platform/ops_registry.py`），故平台与 Agent 服务同源。
- **L3 保持 opt-in**：V1/V2/V3 候选参数在注册表里硬拒绝；`fallback_chain` /
  `health_probe` 须显式 `opt_in=true`；重调用须 `confirm=true`。
- 不重启 8770：本轮升级后的服务另起端口（如 `--port 8771`），8770 保持原状。

启动
----
python platform/serve.py                # http://127.0.0.1:8770（默认，未改动）
python platform/serve.py --port 8771    # R167 升级实例

只绑 127.0.0.1：这是本地工作台，不是对外服务。
"""
import argparse
import json
import os
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLATFORM = os.path.join(ROOT, "platform")
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402

sys.path.insert(0, PLATFORM)
import ops_registry as ops  # noqa: E402  —— R167：A/B/C/D 能力注册表（进程内复用 MCP 工具本体）

# solve_ivp 不是线程安全的用法示范，串行化更稳；R167 起与能力调用共享同一把锁
LOCK = ops.LOCK
BUILD = "R167"

SERIES_CH = [("S", "S"), ("P", "P"), ("X", "X"), ("PAA", "PAA"),
             ("DO2", "DO2"), ("OUR", "OUR"), ("vis", "vis"), ("CER", "CER")]
STEP_H = 2.0

# 允许前端覆盖的键（白名单，防止把内部标志位打进模型）
ALLOWED_OVERRIDES = {
    "mux", "mup", "alpha_kla", "m_s", "m_paa", "vis_scale", "vis_decay_rate",
    "biomass_death_rate", "late_death_rate", "death_recycle",
    "Y_NX", "Y_NP", "mu_h_scale", "q_co2",
}


def load_v3(b):
    return pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))


def simulate(batch, overrides):
    from simulate import simulate_open_loop, yield_metrics, classify_crash

    if batch not in COMBINED:
        raise ValueError(f"批 {batch} 未在 COMBINED 中")
    params = build_params(COMBINED[batch])
    applied = {}
    for k, v in (overrides or {}).items():
        if k not in ALLOWED_OVERRIDES:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(fv):
            continue
        params[k] = fv
        applied[k] = fv

    sim, _ = simulate_open_loop(batch, params)
    v3 = load_v3(batch)
    ym = yield_metrics(sim, v3)
    level, reasons = classify_crash(sim, yield_err=float(ym["rel_err_total"]))

    ts = sim["time_h"].to_numpy(float)
    grid = np.arange(ts[0], ts[-1] + 1e-9, STEP_H)
    series = {"t": [round(float(x), 2) for x in grid], "sim": {}}
    for key, col in SERIES_CH:
        if col in sim.columns:
            series["sim"][key] = [round(float(x), 4) for x in
                                  np.interp(grid, ts, sim[col].to_numpy(float))]

    return {
        "batch": batch,
        "applied": applied,
        "base": {k: v for k, v in COMBINED[batch].items()},
        "yield_err": round(float(ym["rel_err_total"]) * 100, 3),
        "yield_sim": round(float(ym["total_sim_g"]), 2),
        "yield_v3": round(float(ym["total_v3_g"]), 2),
        "crash": level,
        "reasons": reasons,
        "series": series,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PLATFORM, **kw)

    def log_message(self, fmt, *args):  # 静音
        pass

    def _json(self, code, obj):
        # default=str：能力返回体可能含 numpy / Timestamp，显式串行化而非静默丢字段
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/health"):
            st = ops.status()
            return self._json(200, {
                "ok": True,
                "batches": [b for b in GOLDEN_ALL if b in COMBINED],
                "n_batches": len([b for b in GOLDEN_ALL if b in COMBINED]),
                "overridable": sorted(ALLOWED_OVERRIDES),
                # --- R167 additive（旧键一字未改）---
                "build": BUILD,
                "contract": ops.evidence()["contract"],
                "port": self.server.server_address[1],
                "capabilities": st["n_tools_loaded"],
                "capabilities_total": st["n_tools"],
                "operators_loaded": st["n_operators_loaded"],
                "operators_total": st["n_operators"],
                "all_loaded": st["all_loaded"],
                "l3_state": "未执行 · 保持 opt-in",
            })
        if self.path.startswith("/api/ops"):
            return self._json(200, {"ok": True, "status": ops.status()})
        if self.path.startswith("/api/evidence"):
            return self._json(200, {"ok": True, "evidence": ops.evidence()})
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/api/simulate", "/api/invoke"):
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/simulate":
                # L0 冻结基线：函数体逐字未改，仍走原 simulate()
                batch = int(payload.get("batch"))
                with LOCK:
                    res = simulate(batch, payload.get("overrides") or {})
                return self._json(200, {"ok": True, "result": res})
            res = ops.invoke(
                payload.get("tool"),
                payload.get("args") or {},
                opt_in=bool(payload.get("opt_in", False)),
                confirm=bool(payload.get("confirm", False)),
            )
            return self._json(200, res)
        except ops.InvokeError as exc:
            # 显式拒绝：白名单 / L3 参数 / opt-in / confirm / 参数类型
            return self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"平台已启动: http://127.0.0.1:{args.port}  （Ctrl+C 停止）")
    print(f"引擎批次: {len([b for b in GOLDEN_ALL if b in COMBINED])} 批")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
