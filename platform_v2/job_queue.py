# -*- coding: utf-8 -*-
"""平台 v2 —— 异步仿真任务队列。

为什么必须有它
--------------
实测单批仿真 **18–84 秒**（33 维 ODE + BDF 积分，1149 个采样步）。
同步 HTTP 会：① 浏览器等待超过默认超时；② 阻塞其他请求；
③ 用户无法知道"是在算还是卡住了"。

所以平台 v2 的仿真一律走**作业队列**：
    POST /api2/job      → 立即返回 job_id（不阻塞）
    GET  /api2/job/<id> → 轮询状态：queued / running / done / failed
    GET  /api2/jobs     → 作业列表（前端可回看历史）

设计要点
--------
1. **状态机显式**：queued → running → done|failed，每态带原因码。
   失败必须带 `code` + `error`，绝不用「空结果」冒充成功。
2. **单并发仿真**：引擎在 Python 层是 CPU 密集 + GIL 争用，
   并发不会提速反而互相拖慢 ⇒ 队列串行执行仿真，
   但**接口层是多线程的**（一个慢仿真不阻塞 health / catalog 查询）。
3. **结果缓存**：同一工况指纹 ⇒ 命中缓存直接返回（省算力，且保证可复现）。
4. **可取消**：running 作业可请求取消（在下一个采样步检查标志）。
5. **有界**：队列上限 + 单作业内存上限，防止误触堆积。

失败可见性（I2）
----------------
引擎侧的三类失败各自映射为显式 code：
    diverged      —— 积分发散 / NaN / 守卫改写状态
    out_of_domain —— 越有效域（mv_warnings 非空）
    param_invalid —— 工况参数被拒
    engine_error  —— 其它引擎异常（带 traceback 摘要）
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections import OrderedDict
from typing import Any, Callable

from engine_api import EngineError, run_simulation, scenario_fingerprint
from history import record_from_job

# 队列上限（防止误触堆积）：同时在跑 1 个 + 排队 8 个
MAX_QUEUED = 8
MAX_JOBS_KEPT = 60          # 内存中保留的作业记录数（FIFO 淘汰）
CACHE_MAX = 24              # 结果缓存条目数


class Job:
    """一个仿真作业。"""

    __slots__ = ("id", "kind", "payload", "state", "created", "started", "finished",
                 "result", "error", "code", "progress", "cancel_flag", "_cached_key")

    def __init__(self, job_id: str, kind: str, payload: dict, cached_key: str | None = None):
        self.id = job_id
        self.kind = kind
        self.payload = payload
        self.state = "queued"
        self.created = time.time()
        self.started = None
        self.finished = None
        self.result: Any = None
        self.error: str | None = None
        self.code: str | None = None
        self.progress = {"phase": "queued", "detail": "等待执行"}
        self.cancel_flag = False
        self._cached_key = cached_key

    def to_dict(self, with_result: bool = False) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "created": round(self.created, 3),
            "started": round(self.started, 3) if self.started else None,
            "finished": round(self.finished, 3) if self.finished else None,
            "elapsed_s": round((self.finished or time.time()) - (self.started or self.created), 2),
            "progress": self.progress,
            "error": self.error,
            "code": self.code,
            "batch": self.payload.get("batch"),
            # 缓存命中不是"一次运算"：前端据此提示"复用了历史结果"，且不写留痕
            "from_cache": self.progress.get("phase") == "cached",
        }
        if with_result and self.result is not None:
            d["result"] = self.result
        return d


class JobManager:
    """作业队列 + 结果缓存。线程安全。"""

    def __init__(self, runner: Callable[[Job], Any], on_complete: Callable[[Job], Any] | None = None):
        self._runner = runner
        self._on_complete = on_complete      # 作业终态回调（落盘留痕等），在锁外执行
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._cache: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._worker = threading.Thread(target=self._loop, daemon=True, name="sim-worker")
        self._worker.start()
        self._seq = 0

    # ---------------- 提交 ----------------
    def submit(self, kind: str, payload: dict, cache_key: str | None = None,
               use_cache: bool = True) -> Job:
        """use_cache=False ⇒ 强制绕过缓存真实重算（"重新计算"按钮走这条）。

        注意：绕过的是"查缓存"，算完仍会写回缓存，下次普通运行依旧可秒回。
        """
        with self._lock:
            self._seq += 1
            jid = f"{kind}-{self._seq:04d}-{uuid.uuid4().hex[:6]}"
            job = Job(jid, kind, payload, cached_key=cache_key)
            if use_cache and cache_key and cache_key in self._cache:
                job.state = "done"
                job.result = self._cache[cache_key]
                job.started = job.finished = time.time()
                job.progress = {"phase": "cached", "detail": "命中结果缓存"}
                self._remember(job)
                return job
            n_queued = sum(1 for j in self._jobs.values() if j.state in ("queued", "running"))
            if n_queued >= MAX_QUEUED:
                raise EngineError(
                    "queue_full",
                    f"仿真队列已满（上限 {MAX_QUEUED}），请稍候或先完成在跑的作业",
                    {"queued": n_queued},
                )
            self._remember(job)
            self._wake.notify()
            return job

    def _remember(self, job: Job) -> None:
        self._jobs[job.id] = job
        while len(self._jobs) > MAX_JOBS_KEPT:
            self._jobs.popitem(last=False)

    # ---------------- 查询 ----------------
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        with self._lock:
            return [j.to_dict() for j in reversed(self._jobs.values())]

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise EngineError("job_not_found", f"作业 {job_id} 不存在")
            if job.state == "queued":
                job.state = "failed"
                job.code = "cancelled"
                job.error = "作业在执行前被取消"
                job.finished = time.time()
                job.progress = {"phase": "cancelled", "detail": "排队中被取消"}
            elif job.state == "running":
                job.cancel_flag = True
                job.progress = {"phase": "cancelling", "detail": "已请求取消，等待当前步结束"}
            return job.to_dict()

    # ---------------- 工作线程 ----------------
    def _loop(self) -> None:
        while True:
            with self._lock:
                while not any(j.state == "queued" for j in self._jobs.values()):
                    self._wake.wait(timeout=1.0)
                    if not self._jobs:
                        continue
                job = next((j for j in self._jobs.values() if j.state == "queued"), None)
                if job is None:
                    continue
                job.state = "running"
                job.started = time.time()
                job.progress = {"phase": "running", "detail": "引擎积分中"}
            try:
                result = self._runner(job)
                with self._lock:
                    if job.cancel_flag:
                        job.state = "failed"
                        job.code = "cancelled"
                        job.error = "作业已取消"
                        job.progress = {"phase": "cancelled", "detail": "取消生效"}
                    else:
                        job.state = "done"
                        job.result = result
                        job.progress = {"phase": "done", "detail": "完成"}
                        if job._cached_key:
                            self._cache[job._cached_key] = result
                            while len(self._cache) > CACHE_MAX:
                                self._cache.popitem(last=False)
            except EngineError as exc:
                with self._lock:
                    job.state = "failed"
                    job.code = exc.code
                    job.error = exc.message
                    job.result = exc.to_dict()
                    job.progress = {"phase": "failed", "detail": exc.message}
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job.state = "failed"
                    job.code = "engine_error"
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.result = {
                        "ok": False, "code": "engine_error", "error": str(exc),
                        "traceback": traceback.format_exc(limit=6),
                    }
                    job.progress = {"phase": "failed", "detail": str(exc)}
            finally:
                with self._lock:
                    job.finished = time.time()
                # 落盘留痕在锁外做：写 JSON 是磁盘 I/O，不能阻塞队列锁。
                # 只有真正跑完的作业会走到这里（缓存命中在 submit() 里直接返回）。
                if self._on_complete:
                    try:
                        self._on_complete(job)
                    except Exception:  # noqa: BLE001
                        # 留痕失败不能把"算成功"变成"作业失败"，但要留日志
                        traceback.print_exc()

    # ---------------- 统计 ----------------
    def stats(self) -> dict:
        with self._lock:
            by_state: dict[str, int] = {}
            for j in self._jobs.values():
                by_state[j.state] = by_state.get(j.state, 0) + 1
            return {
                "n_jobs": len(self._jobs),
                "by_state": by_state,
                "cache_n": len(self._cache),
                "max_queued": MAX_QUEUED,
                "worker_alive": self._worker.is_alive(),
            }


# ---------------------------------------------------------------------------
# 默认 runner：仿真作业
# ---------------------------------------------------------------------------
def sim_runner(job: Job) -> dict:
    p = job.payload
    return run_simulation(
        int(p["batch"]),
        p.get("overrides") or {},
        stride=int(p.get("stride", 1)),
        with_metrics=bool(p.get("with_metrics", True)),
        with_balance=bool(p.get("with_balance", True)),
        with_trajectory=bool(p.get("with_trajectory", True)),
    )


def sweep_runner(job: Job) -> dict:
    """参数扫描作业：委托给 scan 模块。"""
    from scan import run_sweep
    return run_sweep(job)


# 全局管理器（服务启动时创建）
# 仿真作业挂落盘钩子；扫描作业不留痕（扫描是批量试算，结果本身已可导出 CSV）。
JOBS = JobManager(sim_runner, on_complete=record_from_job)
SWEEPS = JobManager(sweep_runner)


def submit_sim(payload: dict, force: bool = False) -> Job:
    """提交仿真作业（自动算缓存指纹）。

    **校验前置**：参数合法性必须在**提交时**判定并直接拒绝（HTTP 400），
    不能拖到后台线程里才失败 —— 否则前端拿到的是"提交成功"，
    几分钟后才看到一条失败信息，且作业队列被无效作业占满。
    （R168 闸门 G3/G7 就是被这一点抓出来的。）
    """
    batch = int(payload.get("batch") or 0)
    overrides = payload.get("overrides") or {}

    # 前置校验：批号 + 参数（含 L3 硬拒绝）
    from engine_api import assemble_params
    assemble_params(batch, overrides)   # 抛 EngineError ⇒ serve 层转 400

    key = scenario_fingerprint(batch, overrides, {"stride": int(payload.get("stride", 1))})
    # 留痕元数据随作业走：`_history` 不参与引擎装配，只供完成钩子写入磁盘。
    payload = dict(payload)
    payload["_history"] = {
        "batch": batch,
        "stride": int(payload.get("stride", 1)),
        "overrides": dict(overrides),
        "fingerprint": key,
        "rerun_of": payload.get("rerun_of"),
        "force": bool(force),
    }
    return JOBS.submit("sim", payload, cache_key=key, use_cache=not force)


def submit_sweep(payload: dict) -> Job:
    """提交扫描作业。扫描结果不缓存（键空间大，且用户多半只跑一次）。

    同样前置校验：轴的键、数值范围、结构化类型不可扫等。
    """
    from scan import _parse_axis
    axes = payload.get("axes") or []
    if not 1 <= len(axes) <= 2:
        raise EngineError("scan_invalid", "扫描支持 1–2 个轴")
    for a in axes:
        _parse_axis(a)
    return SWEEPS.submit("sweep", payload, cache_key=None)


if __name__ == "__main__":  # 自检：提交一次仿真并等待完成
    j = submit_sim({"batch": 8, "overrides": {}, "stride": 10})
    print(f"提交 {j.id} state={j.state}")
    while True:
        j2 = JOBS.get(j.id)
        print(f"  {j2.state:8s} {j2.progress}")
        if j2.state in ("done", "failed"):
            print("error:", j2.error)
            if j2.state == "done":
                r = j2.result
                print("yield:", r["yield"])
                print("health:", r["health"]["level"], r["health"]["flags"])
            break
        time.sleep(3)
