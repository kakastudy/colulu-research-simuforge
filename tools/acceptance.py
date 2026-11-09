# -*- coding: utf-8 -*-
"""R151：验收单入口 —— 一条命令给出 PASS/FAIL，替掉"翻五个脚本对数字"。

背景
----
红线（GOAL.md §4）散落在多个工具里：产量 ±5% 在 `r150_p_shape`、崩溃分级在
`classify_crash`、轨迹在 `trajectory_metrics`、形状在 `r151_shape_accept`。
每次改动都要人工拼一遍，容易漏项（R149 就因为只看了产量而漏掉 pH 峰位）。

本工具把**判据**集中到一处，分两层：
  HARD — GOAL 红线，不达标即 exit 1：产量 86/86 ±5%、catastrophic=0、确定性 max|Δ|=0
  SOFT — 形状判据（D-43），不达标只 WARN（D-42 结项前不阻断），但必须打印并计入台账

用法
----
    python tools/acceptance.py                    # 86 批，含确定性抽检
    python tools/acceptance.py --no-det           # 跳过确定性（省 ~2 批时间）
    python tools/acceptance.py --limit 10         # 冒烟
    python tools/acceptance.py --json runs/xx.json
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r151_shape_accept as shp  # noqa: E402  one() / summarise() / gate_check() 复用

# R155 / D-38 结项：`classify_crash` 首句 `if co2d.max() <= 7.57: return normal`，
# 而 86/86 批 CO2d.max() ≤ 7.194 ⇒ 它在黄金集上**恒真、从未检验过任何东西**。
# 改用 `classify_health()` 的五通道分级（A CO2d / B pH 钳位 / C pH 越域 / D P 崩塌 / E 产量破线）。
# G2 因此从"catastrophic=0"（恒真）改为"没有**新发** catastrophic"：已登记的批是由
# D-36/D-41（守卫钳位改写动力学 + Fb 无限幅）造成的已知后果，不在本轮修复范围内，
# 但它们必须**带名字**列出来，新增一个就 FAIL —— 这样判据才有守门能力。
# R155 实测登记（D 通道改用**相对实测**口径后）：模型比实测多掉 >40% 的 P 有 4 批，
# 且**全部是 pH 钳位批**（b37 0.38 / b50 0.35 / b91 0.43 / b51 0.49，实测末/峰 0.803/0.826/0.375/0.554）。
# 这 4 批是 D-36（钳位改写动力学）的已知后果，不在本轮修复范围；新出现一个就 FAIL。
KNOWN_CATASTROPHIC = frozenset({37, 50, 51, 91})
KNOWN_DEGRADED_MAX = 9   # 与 D-41 的 9 批 invalid 同源（pH 越 7）


def det_check(batches):
    """同批两次跑必须逐位一致。non-determinism 会让所有标定结论失效。"""
    from golden_params import COMBINED, build_params
    import simulate as s

    worst, detail = 0.0, []
    for b in batches:
        p = build_params(COMBINED[b])
        a, _ = s.simulate_open_loop(int(b), p)
        c, _ = s.simulate_open_loop(int(b), p)
        d = float(np.max(np.abs(a.to_numpy(float) - c.to_numpy(float))))
        detail.append({"batch": int(b), "max_abs_delta": d})
        worst = max(worst, d)
    return worst, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all-100", action="store_true")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-det", action="store_true", help="跳过确定性抽检")
    ap.add_argument("--json", type=str, default="")
    ap.add_argument("--candidate-v2", action="store_true",
                    help="R156/D-55 候选基线 v2：pH 链式法则修正 + 5 批 mup 重标（opt-in）")
    ap.add_argument("--reuse", type=str, default="",
                    help="复用已有基线 json 的 rows（如 runs/r151_shape_baseline.json），"
                         "跳过 86 批仿真；判据仍在本地重算。适合快速看判据/写报告")
    args = ap.parse_args()

    if args.batches:
        bs, src = [int(x) for x in args.batches.split(",") if x.strip()], "manual"
    elif args.all_100:
        bs, src = list(range(1, 101)), "all100"
    else:
        bs, src = shp.golden_batches(), "golden86"
    if args.limit:
        bs = bs[: args.limit]

    t0 = time.time()
    if args.reuse:
        blob = json.load(open(args.reuse, encoding="utf-8"))
        rows = blob["rows"]
        bs = [r["batch"] for r in rows]
        src = f"reuse:{os.path.basename(args.reuse)}"
        if args.limit:
            rows, bs = rows[: args.limit], bs[: args.limit]
        print(f"=== 验收（{src}, {len(rows)} 批；跳过仿真，判据本地重算）===", flush=True)
    else:
        print(f"=== 验收（{src}, {len(bs)} 批, workers={args.workers}）===", flush=True)
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            if args.candidate_v2:
                import functools
                _one = functools.partial(shp.one, mode="v2")
            else:
                _one = shp.one
            rows = list(ex.map(_one, bs))
    summ = shp.summarise(rows)
    soft = shp.gate_check(summ)

    n = summ["n"]
    hard = []
    hard.append(("G1 产量 |err|<=5%", f"{summ['n_yield_ok']}/{n}",
                 summ["n_yield_ok"] == n))
    # D-38 已结项（R155）：catastrophic 用五通道健康分级，判据改为"新发=0"（否则恒真）
    cat = list(summ.get("catastrophic_batches", []))
    deg = list(summ.get("degraded_batches", []))
    new_cat = [b for b in cat if b not in KNOWN_CATASTROPHIC]
    # R157 / T1-1：`--reuse` 的 health 恒真修复。
    # 根因：`summarise()` 对**缺失 health 字段**的 rows 静默返回 0 计数，
    # 于是 G2/G2b 在这类数据上恒真通过（旧 json 只有 `crash` 字段，crash 判据 D-38 已判恒真）。
    # 纪律同 D-38：「恒真的判据等于没有判据」⇒ 缺字段时判据**跳过并显式告警**，绝不报 PASS。
    n_health = int(sum(1 for r in rows if r.get("health")))
    health_available = n_health == len(rows)
    if not health_available:
        print(f"\n  [WARN] rows 缺 health 字段（{n_health}/{len(rows)} 行有 health）"
              f" ⇒ G2/G2b 判据**跳过**（不判定 PASS/FAIL）。"
              f"该 json 由 D-38 之前的版本生成；请改用带 health 的基线，"
              f"如 runs/r156_acceptance.json。", flush=True)
    hard.append(("G2 新发 catastrophic=0",
                 (f"{len(new_cat)} 新发（名单 {cat}，已登记 {sorted(KNOWN_CATASTROPHIC)}）"
                  if health_available else "SKIP（rows 无 health 字段，判据不成立）"),
                 len(new_cat) == 0 if health_available else None))
    # 有效域破损（pH 钳位 / pH 越 7）：与 D-41 的 9 批 invalid 同源，不得扩散
    hard.append(("G2b degraded 计数（基线 9）",
                 (f"{len(deg)} <= {KNOWN_DEGRADED_MAX}" if health_available
                  else "SKIP（rows 无 health 字段，判据不成立）"),
                 len(deg) <= KNOWN_DEGRADED_MAX if health_available else None))
    det = None
    if not args.no_det:
        det_bs = [bs[0], bs[len(bs) // 2]] if len(bs) >= 2 else bs
        worst, det = det_check(det_bs)
        hard.append((f"G3 确定性 max|Δ|（抽 b{','.join(str(x['batch']) for x in det)}）",
                     f"{worst:.1e}", worst == 0.0))

    print("\n-- HARD（GOAL 红线）--")
    ok_all = True
    n_skip = 0
    for name, val, ok in hard:
        if ok is None:
            n_skip += 1
            print(f"  [SKIP] {name:38s} {val}")
            continue
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} {val}")
        ok_all &= ok

    print("\n-- SOFT（形状，D-43 草案；D-42 结项前不阻断）--")
    n_soft_fail = 0
    for item in [{"name": a, "value": b, "rule": c, "pass": d} for a, b, c, d in soft]:
        print(f"  [{'PASS' if item['pass'] else 'WARN'}] {item['name']:28s} = "
              f"{item['value']:+.4f}   {item['rule']}")
        n_soft_fail += 0 if item["pass"] else 1

    print(f"\n-- 参考 --")
    print(f"  valid {summ['n_valid']}/{n}   crash(旧): normal {summ['n_normal']}"
          f" / benign {summ['n_benign']} / catastrophic {summ['n_catastrophic']}")
    nh = summ.get("n_health", {})
    if health_available:
        print(f"  health(新): normal {nh.get('normal', 0)} / benign {nh.get('benign', 0)}"
              f" / degraded {nh.get('degraded', 0)} / catastrophic {nh.get('catastrophic', 0)}")
        print(f"  degraded 名单 {deg}")
        print(f"  catastrophic 名单 {cat}   flags {summ.get('health_flags_tally', {})}")
    else:
        print("  health(新): **不可用**（rows 无 health 字段）⇒ G2/G2b 已跳过，"
              "本结论不等于完整验收")
    print(f"  P relRMSE 中位 {summ['p_relrmse']['median']:.4f}  P 60-120 {summ['p_phase_mean']['60-120']:+.4f}"
          f"  产量达标但 P relRMSE>0.20: {summ['n_yield_ok_but_p_bad']}/{n}")
    print(f"  用时 {time.time() - t0:.0f}s")

    if n_skip:
        verdict = ("FAIL" if not ok_all else
                   f"PASS(hard, {n_skip} 判据跳过——不可视为完整验收)")
    else:
        verdict = "PASS" if ok_all and n_soft_fail == 0 else ("PASS(hard)" if ok_all else "FAIL")
    print(f"\n结论：{verdict}" + ("" if n_soft_fail == 0 else f"；{n_soft_fail} 条形状判据未达（soft）"))

    if args.json:
        blob = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": src, "batches": bs,
                "hard": [{"name": a, "value": b,
                          "pass": (None if c is None else bool(c))} for a, b, c in hard],
                "n_skipped": n_skip,
                "soft": [{"name": a, "value": b, "rule": c, "pass": bool(d)}
                         for a, b, c, d in soft],
                "det": det, "summary": summ, "verdict": verdict,
                "rows": rows,   # R155：保存逐批行，使本文件可被 --reuse 复算（否则判据救不回来）
                "elapsed_s": round(time.time() - t0, 1)}
        json.dump(blob, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"written: {args.json}")

    # 退出码：0=全 PASS、1=有 FAIL、2=有判据被跳过（不完整验收，不许当成 PASS）
    sys.exit(0 if (ok_all and n_skip == 0) else (2 if n_skip else 1))


if __name__ == "__main__":
    main()
