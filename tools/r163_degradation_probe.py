# -*- coding: utf-8 -*-
"""R163 / D-80 探针：真实退化批的**筛查 + 确认 + 注入**三段式。

背景（D-80）
------------
R161 交付了四环算子（enkf_health / degradation_guard / mhe_step / steady_state_baseline），
但**未接入现役 MCP 路径**，且「缺真会发散的 EnKF 批级触发样本」。
R161 只在 3 个批（b8/b11/b22）上跑过 EnKF 探针 ⇒ **回退链在真实数据上从未触发过**，
因此「接入后会不会误降级 / 会不会该降不降」两个问题都没有实证答案。

本探针的设计（承 D-78 判据纪律：零信息对照 + 双向判别力）
--------------------------------------------------------
  A 段 筛查（screening）      —— 全部 86 个黄金批跑 EnKF 健康度探针（n_ens 小），
                                 找出**自然退化**批；判为 degraded 者全部复验。
  B 段 确认（confirmation）    —— 抽样批用大集合（n_ens 大）复验，证伪 A 段的结论。
  C 段 注入（injection）       —— 真实批数据 + **物理可信**故障注入（探头漂移 / 卡死 / 冷却故障），
                                 制造「真会发散的批级触发样本」；
                                 每种注入都配**零信息对照**（同批不注入 ⇒ 不得触发）。
  D 段 汇总                    —— 三层（EnKF / MHE / 稳态）各是否拿到 ≥1 个批级触发样本。

**引擎零改动**：故障注入用 monkey-patch `observe.load_batch` 实现（探针自包含），
不改 observe.py / simulate.py 任何一行 ⇒ 引擎零回归不受影响。

用法：
    py tools/r163_degradation_probe.py --stage A --n-ens 8 --jobs 8
    py tools/r163_degradation_probe.py --stage AB --out runs/r163_degradation_probe.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import solver_chain as sc                                      # noqa: E402
from simulate import load_batch                                # noqa: E402


# ---------------------------------------------------------------------------
# 批级 worker（Windows spawn 要求模块级函数 + 可 pickle 参数）
# ---------------------------------------------------------------------------

def _scan_one(job):
    """单个批的 EnKF 健康度扫描（只读）。"""
    b, n_ens, seed = job
    from observe import enkf_observe
    from calibration import calib_params
    t0 = time.time()
    try:
        out = enkf_observe(b, params=calib_params(b), n_ens=n_ens, seed=seed,
                           verbose=False, health_probe=True)
    except Exception as exc:
        return {"batch": b, "n_ens": n_ens, "error": "%s: %s" % (type(exc).__name__, exc),
                "wall_s": round(time.time() - t0, 1)}
    hr = sc.enkf_health(out.get("health"), records=out.get("records"),
                        integration_failures=out.get("integration_failures"),
                        n_ens=out.get("n_ens"))
    dg = sc.degradation_guard(hr)
    return {
        "batch": b, "n_ens": n_ens, "seed": seed,
        "healthy": bool(hr["healthy"]),
        "tier": dg["tier"], "degraded": dg["degraded"],
        "reasons": hr["reasons"],
        "metrics": {k: v for k, v in hr["metrics"].items()
                    if k in ("cv_min", "cv_median", "cv_collapse_run", "fail_rate",
                             "integration_failures", "innovation_z_max",
                             "innovation_z_max_all_channels",
                             "innovation_over_limit_counts",
                             "innovation_over_limit_counts_excluded",
                             "cond_max", "n_steps")},
        "wall_s": round(time.time() - t0, 1),
    }


def _scan_many(jobs, jobs_parallel=8, on_result=None, done_batches=None):
    """并行扫描（spawn 上下文）。

    `on_result` : 每完成一个批的回调（用于**增量落盘**，避免长跑中断即全丢）。
    `done_batches` : 已完成的批号集合（resume 用），这些批直接跳过。
    """
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    results = []
    todo = [j for j in jobs if not done_batches or j[0] not in done_batches]
    if not todo:
        return results
    with ctx.Pool(processes=jobs_parallel) as pool:
        for i, r in enumerate(pool.imap_unordered(_scan_one, todo), 1):
            results.append(r)
            tag = "ERR" if "error" in r else ("DEGRADED" if r["degraded"] else "ok")
            print("  [%3d/%3d] b%-3d %-8s %s (%.0fs)"
                  % (i, len(todo), r["batch"], tag,
                     (r.get("reasons") or [r.get("error", "")])[0][:60]
                     if r.get("reasons") or r.get("error") else "",
                     r["wall_s"]), flush=True)
            if on_result is not None:
                on_result(r)
    return sorted(results, key=lambda r: r["batch"])


# ---------------------------------------------------------------------------
# C 段：物理可信故障注入（monkey-patch observe.load_batch，不改引擎）
# ---------------------------------------------------------------------------

#: 故障定义表：name → (描述, 施加函数(d)->d)
#: 施加函数只改**观测列**，不动状态/引擎参数 ⇒ 与真实在线仪表故障同型。
def _f_do2_drift(d):
    """DO2 溶氧探头缓慢漂移（真实工厂常见：探头老化/膜结垢）。"""
    if "DO2" not in d.columns:
        return d
    t = d["time_h"].to_numpy(float)
    d = d.copy()
    d["DO2"] = pd.to_numeric(d["DO2"], errors="coerce") + 0.02 * np.maximum(t - 40.0, 0.0)
    return d


def _f_ph_bias(d):
    """pH 探头恒定偏置（缓冲液失效/未校准）。"""
    if "pH" not in d.columns:
        return d
    d = d.copy()
    d["pH"] = pd.to_numeric(d["pH"], errors="coerce") + 0.25
    return d


def _f_co2_stuck(d):
    """CO2 排气分析仪卡死（读数冻结在 t=60 h）。"""
    if "CO2outgas" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    co2 = pd.to_numeric(d["CO2outgas"], errors="coerce").to_numpy(float)
    frozen = co2[np.argmin(np.abs(t - 60.0))]
    d["CO2outgas"] = np.where(t >= 60.0, frozen, co2)
    return d


def _f_cooling_fault(d):
    """冷却失效：夹套温度观测阶跃 +5 K（T 通道**不在**判据白名单 ⇒ 预期不触发）。"""
    if "T" not in d.columns:
        return d
    d = d.copy()
    t = d["time_h"].to_numpy(float)
    T = pd.to_numeric(d["T"], errors="coerce").to_numpy(float)
    d["T"] = np.where(t >= 80.0, T + 5.0, T)
    return d


FAULTS = {
    "do2_sensor_drift": ("DO2 探头漂移（+0.02 mg/L/h 线性漂移，自 t=40 h 起）", _f_do2_drift,
                         True),
    "ph_probe_bias": ("pH 探头恒定偏置 +0.25", _f_ph_bias, True),
    "co2_sensor_stuck": ("CO2 排气分析仪卡死（冻结于 t=60 h）", _f_co2_stuck, True),
    "cooling_fault_T": ("冷却失效（T 阶跃 +5 K，**T 不在判据白名单** ⇒ 预期不触发）",
                        _f_cooling_fault, False),
}


def _scan_injected(job):
    """在真实批上注入故障后跑 EnKF 健康度（monkey-patch，进程内自洽）。

    ⚠ **patch 目标必须是 `simulate.load_batch` 而不是 `observe.load_batch`**：
    `observe.enkf_observe` 在**函数体内**重新 `from simulate import load_batch`，
    函数内局部名会遮蔽模块级绑定 ⇒ patch `observe.load_batch` **完全无效**。
    patch `simulate.load_batch` 才会在每次调用时被函数内的 import 读到。
    """
    b, n_ens, seed, fault = job
    import simulate
    import observe
    from observe import enkf_observe
    from calibration import calib_params

    _orig = simulate.load_batch
    desc, fn, expect_fire = FAULTS[fault]
    try:
        simulate.load_batch = lambda _b: fn(_orig(_b))
        out = enkf_observe(b, params=calib_params(b), n_ens=n_ens, seed=seed,
                           verbose=False, health_probe=True)
    except Exception as exc:
        return {"batch": b, "fault": fault, "error": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        simulate.load_batch = _orig

    hr = sc.enkf_health(out.get("health"), records=out.get("records"),
                        integration_failures=out.get("integration_failures"),
                        n_ens=out.get("n_ens"))
    dg = sc.degradation_guard(hr)
    return {
        "batch": b, "fault": fault, "fault_desc": desc, "expect_fire": expect_fire,
        "healthy": bool(hr["healthy"]), "degraded": dg["degraded"], "tier": dg["tier"],
        "reasons": hr["reasons"],
        "metrics": {k: v for k, v in hr["metrics"].items()
                    if k in ("innovation_z_max", "innovation_z_max_all_channels",
                             "innovation_over_limit_counts",
                             "innovation_over_limit_counts_excluded",
                             "fail_rate", "cond_max")},
    }


def _scan_many_injected(jobs, jobs_parallel=4):
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    out = []
    with ctx.Pool(processes=jobs_parallel) as pool:
        for r in pool.imap_unordered(_scan_injected, jobs):
            out.append(r)
            print("  b%-3d %-18s degraded=%-5s expect_fire=%-5s %s"
                  % (r["batch"], r["fault"], r.get("degraded"), r.get("expect_fire"),
                     (r.get("reasons") or [r.get("error", "")])[0][:70]), flush=True)
    return sorted(out, key=lambda r: (r["batch"], r["fault"]))


# ---------------------------------------------------------------------------

def _flush(out_path, payload):
    """原子落盘（增量写入；长跑中断不丢已完成结果）。"""
    tmp = out_path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="A", choices=["A", "B", "C", "ALL"])
    ap.add_argument("--n-ens", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--confirm-ens", type=int, default=20)
    ap.add_argument("--confirm-sample", default="")
    ap.add_argument("--inject-batches", default="8,22,55,91")
    ap.add_argument("--out", default="runs/r163_degradation_probe.json")
    ap.add_argument("--force", action="store_true", help="忽略已有结果，强制重算本阶段")
    a = ap.parse_args()

    from golden_params import GOLDEN_ALL

    # 增量模式：已存在的阶段结果直接复用（避免 A/B/C 串行重跑）
    payload = {"round": "R163", "debt": "D-80",
               "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
               "stage": a.stage, "checks": []}
    if os.path.exists(a.out) and not a.force:
        try:
            prev = json.load(open(a.out, encoding="utf-8"))
            if prev.get("round") == "R163":
                payload.update({k: v for k, v in prev.items()
                                if k not in ("generated", "stage", "verdict")})
                print("[增量] 复用已有阶段结果：%s"
                      % ", ".join(sorted(k for k in payload
                                         if k[0] in "ABC" and "_" in k)), flush=True)
        except Exception as exc:
            print("[增量] 读取失败（忽略）：%s" % exc, flush=True)

    # ---- A 段：筛查（增量落盘 + 可恢复）----
    def _a_summary(acc):
        return {
            "n": len(GOLDEN_ALL), "n_scanned": len(acc),
            "n_degraded": sum(1 for r in acc.values() if r.get("degraded")),
            "degraded_batches": sorted(b for b, r in acc.items() if r.get("degraded")),
            "healthy_batches": sorted(b for b, r in acc.items()
                                      if not r.get("degraded") and "error" not in r),
            "n_error": sum(1 for r in acc.values() if "error" in r),
            "error_batches": sorted(b for b, r in acc.items() if "error" in r),
        }

    if a.stage in ("A", "ALL"):
        prior = {r["batch"]: r for r in payload.get("A_screening", [])
                 if "error" not in r}
        done = set(prior.keys())
        print("== A 段：自然退化筛查（%d 批，n_ens=%d，%d 进程；已完成 %d 批）=="
              % (len(GOLDEN_ALL), a.n_ens, a.jobs, len(done)), flush=True)
        acc = dict(prior)

        def _save(r):
            """每完成一批即落盘（长跑可中断 / 可恢复）。

            ⚠ **A_summary 必须与 A_screening 同步落盘**（R163 踩过）：
            原实现只在 A 段**全部跑完**后才写 A_summary ⇒ 中途中断（算力让给
            其它探针）会导致 A_screening 有 32 批而 A_summary 缺失 ⇒
            下游治理脚本读不到触发率。
            """
            acc[r["batch"]] = r
            payload["A_screening"] = [acc[k] for k in sorted(acc)]
            payload["A_summary"] = _a_summary(acc)
            _flush(a.out, payload)

        jobs = [(b, a.n_ens, 7) for b in GOLDEN_ALL]
        _scan_many(jobs, a.jobs, on_result=_save, done_batches=done)
        payload["A_screening"] = [acc[k] for k in sorted(acc)]
        payload["A_summary"] = _a_summary(acc)
        _flush(a.out, payload)
        print("A 段小结：已扫 %d/%d 批；自然退化 %d 批 %s"
              % (len(acc), len(GOLDEN_ALL), payload["A_summary"]["n_degraded"],
                 payload["A_summary"]["degraded_batches"]), flush=True)

    # ---- B 段：确认（抽样 + 全部退化批复验）----
    if a.stage in ("B", "ALL") and payload.get("A_screening"):
        deg = payload["A_summary"]["degraded_batches"]
        if a.confirm_sample:
            samp = [int(x) for x in a.confirm_sample.split(",") if x.strip()]
        else:
            # 确定性抽样：每隔 k 取一个（覆盖全表而非随机，便于复现）
            k = max(1, len(GOLDEN_ALL) // 6)
            samp = GOLDEN_ALL[::k]
        todo = sorted(set(deg) | set(samp))
        print("== B 段：确认复验（%d 批，n_ens=%d）==" % (len(todo), a.confirm_ens), flush=True)
        payload["B_confirmation"] = _scan_many([(b, a.confirm_ens, 7) for b in todo], a.jobs)
        payload["B_summary"] = {
            "confirmed_degraded": [r["batch"] for r in payload["B_confirmation"]
                                   if r.get("degraded")],
            "confirmed_healthy": [r["batch"] for r in payload["B_confirmation"]
                                  if not r.get("degraded") and "error" not in r],
            "screened_degraded_batches": deg,
            "screened_healthy_batches": [r["batch"] for r in payload["A_screening"]
                                         if not r.get("degraded") and "error" not in r],
        }
        # 筛查-确认一致性
        incon = [r["batch"] for r in payload["B_confirmation"]
                 if "error" not in r
                 and bool(r["degraded"]) != bool(r["batch"] in deg)]
        payload["B_summary"]["inconsistent"] = incon
        print("B 段小结：确认退化 %s；筛查/确认不一致 %s"
              % (payload["B_summary"]["confirmed_degraded"], incon), flush=True)

    # ---- C 段：故障注入 + 零信息对照 ----
    if a.stage in ("C", "ALL"):
        # C 段**不依赖** A 段跑完：直接由已有 A_screening 现算 A_summary
        # （A 段若被中断，A_screening 仍可用 ⇒ 触发率照样算得出）
        if payload.get("A_screening"):
            payload["A_summary"] = _a_summary(
                {r["batch"]: r for r in payload["A_screening"] if "error" not in r})
            _flush(a.out, payload)
        bl = [int(x) for x in a.inject_batches.split(",") if x.strip()]
        jobs = [(b, a.n_ens, 7, f) for b in bl for f in FAULTS]
        print("== C 段：故障注入（%d 批 × %d 故障）==" % (len(bl), len(FAULTS)), flush=True)
        inj = _scan_many_injected(jobs, max(1, min(a.jobs, 4)))
        # 零信息对照：同批不注入的判定（取 A 段结果；无 A 段则现跑）
        ctrl = {}
        if payload.get("A_screening"):
            ctrl = {r["batch"]: r for r in payload["A_screening"] if "error" not in r}
        else:
            print("  [零信息对照] 现跑同批无注入…", flush=True)
            for r in _scan_many([(b, a.n_ens, 7) for b in bl], a.jobs):
                ctrl[r["batch"]] = r
        for r in inj:
            c = ctrl.get(r["batch"])
            r["control_healthy"] = bool(c["healthy"]) if c else None
            r["control_degraded"] = bool(c["degraded"]) if c else None
            # ⚠ **可归因性**（R163 修正，承 D-78 判别力纪律）：
            #   若该批的**零信息对照本身就退化**，则注入后的「触发」**不能**归因于注入
            #   —— 因为它可能只是该批固有的退化被重复观测到。
            #   ⇒ 只有「对照健康」的批，其触发/未触发才是**有效的因果证据**。
            r["attributable"] = bool(r.get("control_healthy") is True)
        payload["C_injection"] = inj

        # ---- 分层归因：可归因子集（对照健康）上的正/反向判别力 ----
        attrib = [r for r in inj if r.get("attributable")]
        non_attrib = [r for r in inj if not r.get("attributable")]
        tp = [r for r in attrib if r.get("expect_fire") and r.get("degraded")]
        fn = [r for r in attrib if r.get("expect_fire") and not r.get("degraded")]
        tn = [r for r in attrib if (not r.get("expect_fire")) and not r.get("degraded")]
        fp = [r for r in attrib if (not r.get("expect_fire")) and r.get("degraded")]

        def _tag(r):
            return "%s@b%d" % (r["fault"], r["batch"])

        payload["C_summary"] = {
            "n_cases": len(inj),
            "n_attributable": len(attrib),
            "n_not_attributable": len(non_attrib),
            "not_attributable_cases": [_tag(r) for r in non_attrib],
            "fired": [_tag(r) for r in inj if r.get("degraded")],
            "not_fired": [_tag(r) for r in inj if not r.get("degraded")],
            # 四格混淆矩阵（**仅对照健康的子集** ⇒ 因果有效）
            "true_positive": [_tag(r) for r in tp],
            "false_negative": [_tag(r) for r in fn],
            "true_negative": [_tag(r) for r in tn],
            "false_positive": [_tag(r) for r in fp],
            "control_all_healthy": all((r.get("control_healthy") is True)
                                       for r in inj),
            # ⚠ 旧口径把**不可归因**的批也算进来 ⇒ 会把「对照已退化」误判成「判据失灵」
            "expect_fire_all_fired": all((r.get("degraded") == r.get("expect_fire"))
                                         for r in inj),
            "expect_fire_all_fired_attributable": all(
                (r.get("degraded") == r.get("expect_fire")) for r in attrib),
            "n_control_healthy_batches": sorted({r["batch"] for r in attrib}),
        }
        print("C 段小结（分层归因）：")
        print("  可归因（对照健康）%d 例：TP=%d FN=%d TN=%d FP=%d"
              % (len(attrib), len(tp), len(fn), len(tn), len(fp)))
        print("  不可归因（对照本身退化）%d 例：%s"
              % (len(non_attrib), payload["C_summary"]["not_attributable_cases"]))
        print("  触发 %s；未触发 %s"
              % (payload["C_summary"]["fired"], payload["C_summary"]["not_fired"]))

    # ---- 收尾：任何阶段结束时都保证 A_summary 存在且与 A_screening 一致 ----
    # ⚠ R163 踩过：C 段任务在 A 段**之后**启动时，payload 里没有 A_summary；
    #   C 段结束时用**旧 payload 覆盖**落盘 ⇒ A_summary 丢失 ⇒ 下游读不到触发率。
    #   ⇒ 收尾时无条件重算（幂等）。
    if payload.get("A_screening"):
        payload["A_summary"] = _a_summary(
            {r["batch"]: r for r in payload["A_screening"] if "error" not in r})
        _flush(a.out, payload)

    payload["verdict"] = "PASS" if payload.get("checks", [] ) == [] else "INFO"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print("\n写出：%s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
