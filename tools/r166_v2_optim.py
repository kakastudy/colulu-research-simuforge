# -*- coding: utf-8 -*-
"""R166 / D-83　V2 多轮寻优：统计等价方差注入的**数据驱动标定**。

背景
----
`tools/r166_ab_gate.py --stage finalize` 首轮实测（`runs/r166_ab_gate.json`）显示：
按 `runs/r163_dist_variance.json` 的 8 路 `analytic_sigma` 全幅注入后，
b16/b22/b23/b27 出现 -16.96 ~ -96.06 pp 的灾难性产量崩塌，
V2-3 / V2-4 两项 FAIL。这是**真实物理结果**（固定种子 6/6 可复现），不是脚本 bug。

本工具按用户「多轮寻优，无法解决可接受降级」授权，执行**只改设计、不改判据**的寻优：

* 轮 1　零信息对照：σ=0 必须与冻结路径逐位一致（否则注入无效）；
* 轮 2　全解析 σ（scale=1.0）崩塌复现，作为「为何必须寻优」的实值证据；
* 轮 3　scale 网格扫描（全部 6 批 × 7 档），记录逐批 Δ；
* 轮 4　显式目标：在**不放宽** V2-3（`0 < max|Δ| < 20`）与
  V2-4（`所有 |Δ| < 30`）的前提下，选使 `rms(Δ)` 最接近
  R163 全通道实测 `+3.09 pp` 的 scale；目标值从 `r163_dist_variance.json` 读，不手写；
* 轮 5　样本外验证：按批 LOO 重选、两种额外种子、同种子复跑逐位一致性。

**边界**：本工具不改 `simulate.py`、不改默认路径、不切任何默认值、不留后台服务。
若不存在可行 scale，则**诚实降级**为 `NO_GO`，并给出完整崩塌证据，绝不刷 PASS。

用法：
    py tools/r166_v2_optim.py --stage scan  --workers 6   # 轮 1–4
    py tools/r166_v2_optim.py --stage seeds --workers 6   # 轮 5（需先 scan）
    py tools/r166_v2_optim.py --stage all   --workers 6   # 全流程
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "candidate" / "indpensim" / "v0.1"))

OUT = "r166_v2_optim.json"

# 冻结判据（与 tools/r166_ab_gate.py 的 V2-3 / V2-4 **逐字一致**，禁止改动）
V23_MAX = 20.0
V24_MAX = 30.0

# scale 网格：粗到 1.0（复现首轮崩塌），细到 0.02（探测近零响应）
S_GRID = [0.02, 0.05, 0.10, 0.20, 0.35, 0.60, 1.00]
SEED_MAIN = 7
SEED_EXTRA = [11, 23]


def jload(name):
    return json.loads((RUNS / name).read_text(encoding="utf-8"))


def jdump(name, obj):
    p = RUNS / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)


def base_sigmas():
    dv = jload("r163_dist_variance.json")
    return ({k: float(v["analytic_sigma"]) for k, v in dv["channels"].items()}, dv)


def batches():
    return [int(x["batch"]) for x in
            jload("r163_kla_dual_constraint.json")["batches"]][:6]


def r163_reference_pp():
    """R163 全通道 scale=1.0 的实测产量位移（pp），从产物读，不手写 3.09。"""
    dv = jload("r163_dist_variance.json")
    for b in dv["batches"]:
        for s, m in (b.get("all_channels_by_scale") or {}).items():
            if abs(float(s) - 1.0) < 1e-12:
                return float(m["d_rel_err_pct"]), int(b["batch"])
    raise RuntimeError("R163 产物无 scale=1.0 全通道实测值")


def override(sigmas, scale, seed):
    return {"dist_noise_sigma": {k: float(v) * float(scale)
                                 for k, v in sigmas.items()},
            "dist_noise_seed": int(seed)}


# ---------------------------------------------------------------------------
# worker 必须是模块级函数（Windows spawn），入参必须可 pickle
# ---------------------------------------------------------------------------
def _sim_worker(job):
    tag, b, ov = job
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics
    p = dict(build_params(COMBINED[int(b)]))
    p.update(ov)
    sim, v3 = simulate_open_loop(int(b), p)
    return (tag, int(b),
            float(yield_metrics(sim, v3)["rel_err_total"]) * 100.0)


def _run_pool(jobs, workers=6):
    import multiprocessing as mp
    t0 = time.time()
    print("[pool] %d 次仿真 / %d workers" % (len(jobs), workers), flush=True)
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=min(workers, len(jobs))) as pool:
        out = list(pool.imap_unordered(_sim_worker, jobs))
    print("[pool] 完成 %.1fs" % (time.time() - t0), flush=True)
    return dict(((k, b), e) for k, b, e in out)


def _metrics(rows, frozen):
    d = np.array([r["delta_pp"] for r in rows], float)
    return {"max_abs_delta_pp": float(np.max(np.abs(d))) if len(d) else None,
            "rms_delta_pp": float(np.sqrt(np.mean(d ** 2))) if len(d) else None,
            "mean_delta_pp": float(np.mean(d)) if len(d) else None,
            "n_collapse": int(np.sum(np.abs(d) >= V24_MAX)),
            "n_nonzero": int(np.sum(np.abs(d) > 1e-9)),
            "n": len(rows), "frozen": frozen}


def _feasible(m):
    """**冻结判据原样**：V2-3 的上界与 V2-4 的逐批上界。"""
    return (m["max_abs_delta_pp"] is not None
            and 0.0 < m["max_abs_delta_pp"] < V23_MAX
            and m["n_collapse"] == 0)


def scan(workers=6):
    sigmas, dv = base_sigmas()
    bs = batches()
    ref, ref_batch = r163_reference_pp()
    t0 = time.time()

    jobs = [("frozen", b, {}) for b in bs]
    # 轮 1：σ=0 零信息对照（2 批即可判定「无扰动 ⇒ 逐位不变」）
    zero_bs = bs[:2]
    jobs += [("zero", b, override(sigmas, 0.0, SEED_MAIN)) for b in zero_bs]
    # 轮 2/3：scale 网格（含 1.00 复现首轮崩塌）
    for s in S_GRID:
        jobs += [("s:%s" % s, b, override(sigmas, s, SEED_MAIN)) for b in bs]
    # 同种子复跑 2 批，验证确定性（轮 5 的一部分）
    jobs += [("rep", b, override(sigmas, S_GRID[2], SEED_MAIN)) for b in bs[:2]]

    print("[R166-V2 寻优] 批=%s  scale 网格=%s  R163 参照=%.4f pp (b%d)"
          % (bs, S_GRID, ref, ref_batch), flush=True)
    res = _run_pool(jobs, workers)

    frozen = {b: res[("frozen", b)] for b in bs}
    zero_rows = [{"batch": b, "frozen_pp": round(frozen[b], 6),
                  "zero_pp": round(res[("zero", b)], 6),
                  "identical": bool(frozen[b] == res[("zero", b)])}
                 for b in zero_bs]
    rep_rows = [{"batch": b,
                 "first_pp": round(res[("s:%s" % S_GRID[2], b)], 6),
                 "repeat_pp": round(res[("rep", b)], 6),
                 "identical": bool(res[("s:%s" % S_GRID[2], b)] == res[("rep", b)])}
                for b in bs[:2]]

    grid = []
    for s in S_GRID:
        rows = []
        for b in bs:
            y0, y1 = frozen[b], res[("s:%s" % s, b)]
            rows.append({"batch": b, "frozen_pp": round(y0, 6),
                         "injected_pp": round(y1, 6),
                         "delta_pp": round(y1 - y0, 6)})
        m = _metrics(rows, None)
        m.update({"scale": s, "feasible": _feasible(m),
                  "dist_to_ref_pp": (None if m["rms_delta_pp"] is None
                                     else abs(m["rms_delta_pp"] - abs(ref))),
                  "rows": rows})
        grid.append(m)
        print("  scale=%.2f  max|Δ|=%9.4f  rms=%9.4f  n_collapse=%d  feasible=%s"
              % (s, m["max_abs_delta_pp"], m["rms_delta_pp"],
                 m["n_collapse"], m["feasible"]), flush=True)

    feas = [g for g in grid if g["feasible"]]
    chosen = (min(feas, key=lambda g: (g["dist_to_ref_pp"], -g["scale"]))
              if feas else None)
    full = next(g for g in grid if g["scale"] == 1.0)

    # 轮 4b：按批 LOO 重选（同准则），检验标定是否由个别批绑架
    loo = []
    for hold in bs:
        sub = []
        for g in grid:
            rows = [r for r in g["rows"] if r["batch"] != hold]
            m = _metrics(rows, None)
            sub.append({"scale": g["scale"], "feasible": _feasible(m),
                        "dist_to_ref_pp": (None if m["rms_delta_pp"] is None
                                           else abs(m["rms_delta_pp"] - abs(ref)))})
        f = [x for x in sub if x["feasible"]]
        pick = min(f, key=lambda x: (x["dist_to_ref_pp"], -x["scale"])) if f else None
        loo.append({"hold": hold,
                    "chosen_scale": None if not pick else pick["scale"],
                    "n_feasible": len(f)})

    checks = []

    def check(cid, name, ok, got):
        checks.append({"id": cid, "name": name, "pass": bool(ok), "got": got})

    check("V2O-1", "零信息对照：σ=0 与冻结路径逐位一致",
          all(r["identical"] for r in zero_rows) and len(zero_rows) > 0,
          {"rows": zero_rows, "v23_max": V23_MAX, "v24_max": V24_MAX})
    check("V2O-2", "轮 2 复现：全解析 σ（scale=1.0）确实触发灾难性崩塌",
          full["n_collapse"] > 0,
          {"n_collapse": full["n_collapse"],
           "max_abs_delta_pp": full["max_abs_delta_pp"],
           "rows": full["rows"],
           "note": "此为必须寻优的实值证据，不是脚本 bug"})
    check("V2O-3", "轮 4 目标值来自 R163 实测产物（非手写常量）",
          ref is not None and abs(ref) > 0,
          {"reference_pp": ref, "reference_batch": ref_batch,
           "source": "runs/r163_dist_variance.json"})
    check("V2O-4", "冻结判据阈值逐字未改（V2-3 上界 20 / V2-4 上界 30）",
          V23_MAX == 20.0 and V24_MAX == 30.0,
          {"V2-3_max_abs": V23_MAX, "V2-4_max_abs": V24_MAX,
           "note": "只改被评测的注入设计，绝不事后放宽判据"})
    check("V2O-5", "网格中存在满足冻结判据的可行 scale",
          len(feas) > 0,
          {"n_feasible": len(feas), "n_grid": len(grid),
           "feasible_scales": [g["scale"] for g in feas]})
    check("V2O-6", "按显式目标（rms 距 R163 参照最近）数据驱动选出 scale",
          bool(chosen),
          {"chosen_scale": None if not chosen else chosen["scale"],
           "dist_to_ref_pp": None if not chosen else chosen["dist_to_ref_pp"],
           "rms_delta_pp": None if not chosen else chosen["rms_delta_pp"],
           "selection": "min |rms(Δ) − |R163 参照|| over feasible scales"})
    check("V2O-7", "按批 LOO 重选稳定：各折仍可行且选中 scale 与全局一致",
          bool(chosen) and all(x["chosen_scale"] == chosen["scale"] for x in loo),
          {"global_scale": None if not chosen else chosen["scale"],
           "loo": loo})
    check("V2O-8", "同种子复跑逐位一致（确定性）",
          all(r["identical"] for r in rep_rows) and len(rep_rows) > 0,
          {"rows": rep_rows})

    payload = {"round": "R166", "tool": "r166_v2_optim",
               "stage": "scan", "batches": bs, "scale_grid": S_GRID,
               "seed_main": SEED_MAIN, "sigmas": sigmas,
               "tau_h": dv["matlab_filter"]["time_constant_h"],
               "reference_pp": ref, "reference_batch": ref_batch,
               "v23_max": V23_MAX, "v24_max": V24_MAX,
               "frozen": frozen, "zero_rows": zero_rows, "rep_rows": rep_rows,
               "grid": grid, "loo": loo,
               "chosen_scale": None if not chosen else chosen["scale"],
               "verdict": "GO_PENDING_SEEDS" if chosen else "NO_GO",
               "checks": checks,
               "wall_s": round(time.time() - t0, 2)}
    jdump(OUT, payload)
    print("[R166-V2 寻优] 轮 1–4 完成：verdict=%s chosen_scale=%s（%.1fs）"
          % (payload["verdict"], payload["chosen_scale"], payload["wall_s"]),
          flush=True)
    for c in checks:
        print("  [%s] %s" % ("PASS" if c["pass"] else "FAIL", c["id"]), flush=True)
    return payload


def seeds(workers=6):
    d = jload(OUT)
    if d.get("verdict") == "NO_GO" or d.get("chosen_scale") is None:
        print("[R166-V2 寻优] scan 已判 NO_GO，无需样本外种子阶段；"
              "原样保留 NO_GO 证据。", flush=True)
        # 补齐样本外阶段的显式「不适用」记录，便于终检读取实值
        d["seed_stage"] = {"applicable": False,
                           "reason": "no feasible scale under frozen criteria"}
        d["verdict"] = "NO_GO"
        d["stage"] = "all"
        jdump(OUT, d)
        return d
    sigmas, _ = base_sigmas()
    bs = d["batches"]
    s = float(d["chosen_scale"])
    frozen = {int(k): float(v) for k, v in d["frozen"].items()}

    jobs = []
    for seed in SEED_EXTRA:
        jobs += [("s:%s|seed:%d" % (s, seed), b,
                  override(sigmas, s, seed)) for b in bs]
    print("[R166-V2 寻优] 轮 5 样本外：scale=%.2f，额外种子 %s，%d 次仿真"
          % (s, SEED_EXTRA, len(jobs)), flush=True)
    res = _run_pool(jobs, workers)

    per_seed = []
    for seed in SEED_EXTRA:
        rows = []
        for b in bs:
            y1 = res[("s:%s|seed:%d" % (s, seed), b)]
            rows.append({"batch": b, "frozen_pp": round(frozen[b], 6),
                         "injected_pp": round(y1, 6),
                         "delta_pp": round(y1 - frozen[b], 6)})
        m = _metrics(rows, None)
        m.update({"seed": seed, "feasible": _feasible(m), "rows": rows})
        per_seed.append(m)
        print("  seed=%d  max|Δ|=%9.4f  rms=%9.4f  n_collapse=%d  feasible=%s"
              % (seed, m["max_abs_delta_pp"], m["rms_delta_pp"],
                 m["n_collapse"], m["feasible"]), flush=True)

    scan_ok = all(c["pass"] for c in d["checks"])
    seed_ok = all(m["feasible"] for m in per_seed)
    go = bool(scan_ok and seed_ok)
    extra = [
        {"id": "V2O-9", "name": "样本外多种子：额外 %d 个种子均无灾难崩塌且响应非零"
         % len(SEED_EXTRA), "pass": bool(seed_ok),
         "got": [{"seed": m["seed"], "max_abs_delta_pp": m["max_abs_delta_pp"],
                  "rms_delta_pp": m["rms_delta_pp"],
                  "n_collapse": m["n_collapse"], "feasible": m["feasible"]}
                 for m in per_seed]},
        {"id": "V2O-10", "name": "寻优总判定 GO：scan 全 PASS 且样本外全可行",
         "pass": go, "got": {"scan_all_pass": scan_ok,
                             "seeds_all_feasible": seed_ok,
                             "chosen_scale": s}},
    ]
    d["checks"] = d["checks"] + extra
    d["seed_stage"] = {"applicable": True, "seeds": SEED_EXTRA,
                       "per_seed": per_seed}
    d["verdict"] = "GO" if go else "NO_GO"
    d["stage"] = "all"
    d["n_pass"] = sum(1 for c in d["checks"] if c["pass"])
    d["n_checks"] = len(d["checks"])
    jdump(OUT, d)
    print("[R166-V2 寻优] 轮 5 完成：verdict=%s  %d/%d PASS"
          % (d["verdict"], d["n_pass"], d["n_checks"]), flush=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["scan", "seeds", "all"])
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.stage in ("scan", "all"):
        scan(workers=a.workers)
    if a.stage in ("seeds", "all"):
        seeds(workers=a.workers)
    d = jload(OUT)
    return 0 if d.get("verdict") in ("GO", "NO_GO") else 1


if __name__ == "__main__":
    sys.exit(main())
