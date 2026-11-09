# -*- coding: utf-8 -*-
"""平台 v2 —— 仿真计算平台 HTTP 服务。

定位（与 `platform/` 的关系）
---------------------------
`platform/`（R167 冻结，契约 v1.97）是**研发成果看板**：看 86 批回归、通道健康、
算子目录、证据面板。它回答"这轮研发做得怎么样"。

本服务是**仿真计算平台**：配置工况 → 调用引擎 → 看轨迹与指标。
它回答"给我一个工况，引擎算出什么"。研发成果在这里是**佐证**，不是主界面。

不复用 `platform/serve.py` 的理由：R167 契约要求 `/api/simulate` 函数体**逐字未改**
（L0 冻结基线，86 批逐位零回归锚），且它只开放 14 个参数、8 个通道、2h 降采样。
本服务是独立实现，**不修改 platform/ 下任何文件**。

接口
----
GET  /                      → 前端页面
GET  /api2/health           → 引擎就绪、作业队列状态、批次清单
GET  /api2/catalog          → 参数目录（AST 派生，非手写）
GET  /api2/responses        → 扫描响应量定义
GET  /api2/jobs             → 作业列表
GET  /api2/job/<id>         → 单作业状态（?full=1 带回结果）
GET  /api2/sweep/<id>       → 单扫描作业状态
GET  /api2/history          → 运算历史摘要列表（带执行时间，倒序）
GET  /api2/history/<id>     → 单条历史（?full=1 带回完整结果体）
DELETE /api2/history/<id>   → 删除一条留痕
POST /api2/run              → 提交仿真作业 → {job_id}；force=true 绕过缓存真实重算
POST /api2/scan             → 提交扫描作业 → {job_id}
POST /api2/cancel           → 取消作业 → {job_id}
GET  /api2/batch/<n>/v3     → 该批 V3 实测通道（前端叠加对照用）

R168.3：每次**真实**仿真运算完成自动落盘到 runs/sim_history/，
服务重启后历史仍在；点击历史=回放结果（零计算），force 重算=新增一条留痕。

只绑 127.0.0.1：本地工作台，不是对外服务。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLATFORM_V2 = os.path.join(ROOT, "platform_v2")
ENGINE_DIR = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, PLATFORM_V2)

from param_catalog import build_catalog  # noqa: E402
import job_queue as jq  # noqa: E402
import engine_api as ea  # noqa: E402
import history as hist  # noqa: E402
from scan import RESPONSES  # noqa: E402

BUILD = "R168"
CONTRACT_NOTE = "平台 v2 独立实现；platform/ (R167 v1.97) 保持冻结未改"

_CATALOG = None
_CATALOG_LOCK = threading.Lock()


def catalog() -> dict:
    """参数目录缓存（派生一次；源码改了需重启服务 —— 派生层不做热重载，避免半新半旧）。"""
    global _CATALOG
    with _CATALOG_LOCK:
        if _CATALOG is None:
            _CATALOG = build_catalog()
        return _CATALOG


# V3 实测通道 → (V3 列名, 标签, 单位, 是否离线化验)
V3_CHANNELS = [
    ("S", "S", "底物", "g/L", False),
    ("P", "P", "青霉素", "g/L", False),
    ("DO2", "DO2", "溶氧", "mg/L", False),
    ("pH", "pH", "pH", "-", False),
    ("T", "T", "温度", "K", False),
    ("CO2outgas", "CO2outgas", "尾气CO₂", "%", False),
    ("O2", "O2", "尾气O₂", "%", False),
    ("OUR", "OUR", "摄氧速率", "g/min", False),
    ("CER", "CER", "释碳速率", "g/h", False),
    ("NH3", "NH3", "氨氮", "mg/L", False),
    ("vis", "vis", "黏度", "cP", False),
    ("X_offline", "X", "菌丝(化验)", "g/L", True),
    ("P_offline", "P", "青霉素(化验)", "g/L", True),
    ("PAA_offline", "PAA", "前体(化验)", "g/L", True),
    ("NH3_offline", "NH3", "氨氮(化验)", "g/L", True),
    ("Viscosity_offline", "vis", "黏度(化验)", "cP", True),
]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PLATFORM_V2, **kw)

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        qs = {}
        for kv in query.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                qs[k] = v

        try:
            if path == "/api2/health":
                return self._json(200, {
                    "ok": True,
                    "build": BUILD,
                    "note": CONTRACT_NOTE,
                    "batches": ea.golden_batches(),
                    "n_batches": len(ea.golden_batches()),
                    "queue": jq.JOBS.stats(),
                    "sweep_queue": jq.SWEEPS.stats(),
                    "catalog_n": catalog()["n_exposed"],
                    "catalog_rejected": len(catalog()["rejected"]),
                    "history_n": hist.stats()["n"],
                })
            if path == "/api2/catalog":
                return self._json(200, {"ok": True, "catalog": catalog()})
            if path == "/api2/responses":
                return self._json(200, {"ok": True, "responses": [
                    {"key": k, "label": v[0], "unit": v[1]} for k, v in RESPONSES.items()
                ]})
            if path == "/api2/jobs":
                return self._json(200, {"ok": True, "jobs": jq.JOBS.list(),
                                        "sweeps": jq.SWEEPS.list()})
            if path == "/api2/history":
                try:
                    lim = int(qs.get("limit") or 0)
                except ValueError:
                    lim = 0
                return self._json(200, {"ok": True, "records": hist.list_records(lim),
                                        "n": hist.stats()["n"], "dir": hist.history_dir()})
            if path.startswith("/api2/history/"):
                rid = path.split("/")[-1]
                rec = hist.get_record(rid, full=qs.get("full") == "1")
                if rec is None:
                    return self._json(404, {"ok": False, "error": f"历史记录 {rid} 不存在"})
                return self._json(200, {"ok": True, "record": rec})
            if path.startswith("/api2/job/"):
                jid = path.split("/")[-1]
                job = jq.JOBS.get(jid)
                if job is None:
                    return self._json(404, {"ok": False, "error": f"作业 {jid} 不存在"})
                return self._json(200, {"ok": True, "job": job.to_dict(with_result=qs.get("full") == "1")})
            if path.startswith("/api2/sweep/"):
                jid = path.split("/")[-1]
                job = jq.SWEEPS.get(jid)
                if job is None:
                    return self._json(404, {"ok": False, "error": f"扫描作业 {jid} 不存在"})
                return self._json(200, {"ok": True, "job": job.to_dict(with_result=qs.get("full") == "1")})
            if path.startswith("/api2/batch/") and path.endswith("/v3"):
                try:
                    bn = int(path.split("/")[-2])
                except ValueError:
                    return self._json(400, {"ok": False, "error": "批号非法"})
                try:
                    df = ea.load_batch_csv(bn)
                except Exception as exc:  # noqa: BLE001
                    return self._json(404, {"ok": False, "error": str(exc)})
                t = df["time_h"].to_numpy(float)
                out = {"ok": True, "batch": bn, "t": [round(float(x), 2) for x in t], "ch": {}}
                for key, col, _lab, _u, offline in V3_CHANNELS:
                    if col not in df.columns:
                        continue
                    vals = df[col].to_numpy(float)
                    if offline:
                        idx = [i for i in range(len(vals)) if vals[i] == vals[i]]
                        out["ch"][key] = {"col": col, "points": [
                            [round(float(t[i]), 2), round(float(vals[i]), 4)] for i in idx]}
                    else:
                        out["ch"][key] = {"col": col, "values": [
                            None if vals[i] != vals[i] else round(float(vals[i]), 4)
                            for i in range(len(vals))]}
                return self._json(200, out)
            return super().do_GET()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # --------------------------------------------------------------- DELETE
    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api2/history/"):
            rid = path.split("/")[-1]
            if not hist.delete_record(rid):
                return self._json(404, {"ok": False, "error": f"历史记录 {rid} 不存在"})
            return self._json(200, {"ok": True, "deleted": rid, "n": hist.stats()["n"]})
        return self._json(404, {"ok": False, "error": "not found"})

    # --------------------------------------------------------------- POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as exc:  # noqa: BLE001
            return self._json(400, {"ok": False, "error": f"请求体解析失败：{exc}"})

        try:
            if path == "/api2/run":
                rerun_of = payload.get("rerun_of")
                if not isinstance(rerun_of, str) or len(rerun_of) > 80:
                    rerun_of = None
                try:
                    job = jq.submit_sim({
                        "batch": payload.get("batch"),
                        "overrides": payload.get("overrides") or {},
                        "stride": int(payload.get("stride") or 1),
                        "with_metrics": bool(payload.get("with_metrics", True)),
                        "with_balance": bool(payload.get("with_balance", True)),
                        "with_trajectory": bool(payload.get("with_trajectory", True)),
                        "rerun_of": rerun_of,
                    }, force=bool(payload.get("force", False)))
                except ea.EngineError as exc:
                    return self._json(400, exc.to_dict())
                return self._json(200, {"ok": True, "job_id": job.id, "state": job.state})

            if path == "/api2/scan":
                try:
                    job = jq.submit_sweep({
                        "batch": payload.get("batch"),
                        "axes": payload.get("axes") or [],
                        "response": payload.get("response") or "yield_err",
                        "overrides": payload.get("overrides") or {},
                        "stride": int(payload.get("stride") or 12),
                        "max_points": payload.get("max_points"),
                    })
                except ea.EngineError as exc:
                    return self._json(400, exc.to_dict())
                return self._json(200, {"ok": True, "job_id": job.id, "state": job.state})

            if path == "/api2/cancel":
                jid = payload.get("job_id")
                kind = payload.get("kind") or "sim"
                mgr = jq.SWEEPS if kind == "sweep" else jq.JOBS
                try:
                    d = mgr.cancel(jid)
                except ea.EngineError as exc:
                    return self._json(404, exc.to_dict())
                return self._json(200, {"ok": True, "job": d})

            return self._json(404, {"ok": False, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8772)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"仿真计算平台 v2 已启动: http://127.0.0.1:{args.port}  （Ctrl+C 停止）")
    print(f"引擎批次: {len(ea.golden_batches())} 批 · 参数目录: {catalog()['n_exposed']} 键")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
