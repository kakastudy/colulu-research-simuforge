# -*- coding: utf-8 -*-
"""平台 v2 —— 仿真运算历史的落盘留痕。

为什么需要它
------------
`job_queue.py` 的结果只在**进程内存**里（`MAX_JOBS_KEPT=60`，`CACHE_MAX=24`），
服务一重启就全部消失。用户每回打开平台都得重算一遍 20–80 秒的仿真。

本模块把**每一次真实运算**的结果写到磁盘，带执行时间：
    runs/sim_history/index.json          摘要索引（倒序，最新在前）
    runs/sim_history/sim-<时间>-<id>.json   单条完整记录（含结果体）

设计要点
--------
1. **只有真实算过的才算"一次运算"**：命中结果缓存的作业不写新记录
   （它没有执行运算，只是复用了上次的结果）。`force` 重算则是真实运算，会新增一条。
2. **失败也留痕**：发散 / 越域的点是有价值的边界证据，存错误码与原因，
   但 `has_result=false`，前端不提供"查看结果"。
3. **完整结果体**：存的是 `run_simulation()` 的原始返回（40 通道轨迹 + 全部指标），
   所以回看一次历史 = 完整渲染结果，**无需再调引擎**。
4. **执行时间显式**：`started_at` / `finished_at` / `created_at`（ISO 本地时间带时区）
   + `elapsed_s`。索引里也有，前端列卡片不必逐条打开大文件。
5. **原子写 + 有界**：临时文件 + `os.replace`；超过 `MAX_RECORDS` 淘汰最旧，
   避免无限堆积。索引损坏时从单条记录文件重建，不丢用户数据。

`PENOPS_SIM_HISTORY_DIR` 可覆盖目录（测试隔离用）。
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import threading
import time
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DIR = os.path.join(ROOT, "runs", "sim_history")
MAX_RECORDS = 120
_INDEX_NAME = "index.json"
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_LOCK = threading.RLock()


def history_dir() -> str:
    return os.environ.get("PENOPS_SIM_HISTORY_DIR") or DEFAULT_DIR


def _index_path() -> str:
    return os.path.join(history_dir(), _INDEX_NAME)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return _dt.datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")


def _clean(obj):
    """JSON 化：NaN/Inf → None（JSON 标准没有 NaN），numpy 标量 → Python 标量。"""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "item"):          # numpy scalar / 0-d array
        try:
            return _clean(obj.item())
        except Exception:  # noqa: BLE001
            return str(obj)
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    return str(obj)


def _atomic_write(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_clean(obj), f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    os.replace(tmp, path)


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _meta_of(full: dict) -> dict:
    """从完整记录里剥出索引摘要（不含体积最大的 result）。"""
    return {k: v for k, v in full.items() if k != "result"}


def _load_index() -> list[dict]:
    """读索引；损坏/不存在时扫描目录重建（不删任何记录文件）。"""
    os.makedirs(history_dir(), exist_ok=True)
    d = _read_json(_index_path())
    if isinstance(d, dict) and isinstance(d.get("records"), list):
        return d["records"]
    recovered = []
    for fn in sorted(os.listdir(history_dir())):
        if not fn.endswith(".json") or fn == _INDEX_NAME or fn.endswith(".tmp"):
            continue
        full = _read_json(os.path.join(history_dir(), fn))
        if isinstance(full, dict) and full.get("id"):
            recovered.append(_meta_of(full))
    recovered.sort(key=lambda x: x.get("created_ts") or 0, reverse=True)
    if recovered:
        _atomic_write(_index_path(), {"version": 1, "records": recovered})
    return recovered


def _write_index(records: list[dict]) -> None:
    _atomic_write(_index_path(), {"version": 1, "records": records})


def _summary(result: dict | None) -> dict:
    """给列表卡片用的关键数值摘要（避免打开大文件）。"""
    r = result if isinstance(result, dict) else {}
    y = r.get("yield") or {}
    h = r.get("health") or {}
    tr = r.get("trace") or {}
    return {
        "yield_err_pct": y.get("rel_err_pct"),
        "sim_g": y.get("sim_g"),
        "v3_g": y.get("v3_g"),
        "health_level": h.get("level"),
        "health_flags": list(h.get("flags") or []),
        "n_steps": r.get("n_steps"),
        "n_channels": len(tr.get("cols") or {}),
        "stride": r.get("stride"),
        "mv_warnings": list(r.get("mv_warnings") or []),
    }


def record_from_job(job) -> dict | None:
    """作业完成钩子：`JobManager(on_complete=...)` 调用。

    返回写入的摘要 dict；若这次提交命中缓存、或不是仿真作业，则返回 None（不留痕）。
    写完后把新记录 id 塞进 `job.progress`，前端轮询 `/job/<id>` 就能知道"这次算的结果
    存成了哪一条历史"，不用靠时间戳猜。
    """
    if getattr(job, "kind", None) != "sim":
        return None
    progress = getattr(job, "progress", None) or {}
    if progress.get("phase") == "cached":
        return None                      # 没有真实执行 ⇒ 不是"一次运算"

    payload = getattr(job, "payload", None) or {}
    meta_in = payload.get("_history") or {}
    finished = getattr(job, "finished", None) or time.time()
    started = getattr(job, "started", None) or finished
    state = getattr(job, "state", "done")
    result = getattr(job, "result", None)
    ok = state == "done" and isinstance(result, dict) and result.get("ok") is True

    stamp = _dt.datetime.fromtimestamp(finished).astimezone()
    rid = "sim-" + stamp.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    full = {
        "id": rid,
        "created_ts": round(finished, 3),
        "created_at": _iso(finished),      # 执行完成时间（列表主显示）
        "started_at": _iso(started),
        "finished_at": _iso(finished),
        "elapsed_s": round(max(0.0, finished - started), 2),
        "batch": meta_in.get("batch") or payload.get("batch"),
        "stride": meta_in.get("stride") or payload.get("stride") or 1,
        "overrides": dict(meta_in.get("overrides") or payload.get("overrides") or {}),
        "fingerprint": meta_in.get("fingerprint"),
        "job_id": getattr(job, "id", None),
        "state": state,
        "code": getattr(job, "code", None),
        "error": getattr(job, "error", None),
        "rerun_of": meta_in.get("rerun_of"),
        "force": bool(meta_in.get("force")),
        "summary": _summary(result if ok else None),
        "has_result": ok,
        "result": _clean(result) if ok else None,
    }
    meta = _meta_of(full)
    meta["size_bytes"] = 0

    with _LOCK:
        d = history_dir()
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, rid + ".json")
        _atomic_write(fp, full)
        meta["size_bytes"] = os.path.getsize(fp)
        records = _load_index()
        # 幂等：同一个 job 被重复回调时不产生两条
        records = [x for x in records if x.get("job_id") != full["job_id"] or not full["job_id"]]
        records.insert(0, meta)
        while len(records) > MAX_RECORDS:
            old = records.pop()
            old_path = os.path.join(d, str(old.get("id", "")) + ".json")
            if _ID_RE.match(str(old.get("id", ""))) and os.path.isfile(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        _write_index(records)

    progress["history_id"] = rid
    return meta


# ---------------------------------------------------------------------------
# 查询 / 删除（供 HTTP 层调用）
# ---------------------------------------------------------------------------
def list_records(limit: int | None = None) -> list[dict]:
    with _LOCK:
        rows = list(_load_index())
    if limit and limit > 0:
        rows = rows[:limit]
    return rows


def get_record(rid: str, full: bool = False) -> dict | None:
    if not _ID_RE.match(str(rid or "")):
        return None
    with _LOCK:
        rec = _read_json(os.path.join(history_dir(), rid + ".json"))
    if not isinstance(rec, dict):
        return None
    if not full:
        return _meta_of(rec)
    return rec


def delete_record(rid: str) -> bool:
    if not _ID_RE.match(str(rid or "")):
        return False
    with _LOCK:
        fp = os.path.join(history_dir(), rid + ".json")
        existed = os.path.isfile(fp)
        if existed:
            os.remove(fp)
        records = [x for x in _load_index() if x.get("id") != rid]
        _write_index(records)
        return existed


def stats() -> dict:
    with _LOCK:
        rows = _load_index()
        return {"n": len(rows), "dir": history_dir(), "max": MAX_RECORDS,
                "latest_at": rows[0].get("created_at") if rows else None}


if __name__ == "__main__":  # 自检：写一条合成记录 → 重新读 → 删除
    import tempfile
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as td:
        os.environ["PENOPS_SIM_HISTORY_DIR"] = td
        fake = SimpleNamespace(
            kind="sim", id="sim-test-0001", state="done", result={"ok": True},
            code=None, error=None, started=time.time() - 12.3, finished=time.time(),
            progress={"phase": "done", "detail": "完成"},
            payload={"batch": 8, "stride": 6, "overrides": {},
                     "_history": {"batch": 8, "stride": 6, "overrides": {},
                                  "fingerprint": "abc", "rerun_of": None, "force": False}},
        )
        m = record_from_job(fake)
        print("写入:", m["id"], m["created_at"], "phase→", fake.progress)
        print("列表:", len(list_records()), "跨实例重读:", get_record(m["id"], True)["result"])
        print("删除:", delete_record(m["id"]), "剩余:", len(list_records()))
