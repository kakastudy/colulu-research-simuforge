# -*- coding: utf-8 -*-
"""R146 / D-35 第一阶段：pH 偏差的**可辨识性**判定。

问题（D-35）：开环模型 pH 系统性偏酸 0.1–0.25 个单位，而产量标定吸收了该偏差。
本轮不问"怎么修"，先问一个更前置、可证伪的问题：

    **只动 pH 方程自己的 3 个系数（γ1 / γ2 / m_ph），能不能既修好 pH、又不弄坏产量？**

若能 ⇒ D-35 可以只靠 pH 通道重标定关闭，不必全库联合重标定。
若不能 ⇒ 耦合为真，产量参数必须一起动，"联合重标定"从猜测变成必需。

方法（Gauss-Newton，避免盲目 3 参数搜索）：
  1. 基线：按 runs/final_validation_v2.json 的**每批参数**跑 12 批黄金集，
     取 pH_model − pH_meas 残差 r 与产率误差。
  2. 灵敏度：对 ln γ1 / ln γ2 / ln m_ph 各做 +δ 前向差分，得 J（批次×时刻 堆叠）。
  3. 一阶步：解 min‖r + J·Δ‖²（带极小岭正则防奇异），得 Δ。
  4. 线搜索：沿 Δ 以 λ 缩放实跑（λ=0.25…1.5），报 pH RMSE / 平均偏差 / 产率 / 钳位 / 越 7 样点。
     （**不做第二次 Newton**：实测它在 θ1 处把 b36 顶过 pH 7 触发 basic 分支爆破，
       预报 RMSE 0.224 而实跑 0.916——可行域被 D-32 的悬崖截断，不是光滑曲率限制。）

关键点：γ1/γ2/m_ph 在 model.py 中**只出现在 dy[6]**（187-189 行定义、533-548 行使用），
所以它们对产量的唯一影响路径是 pH 反馈。这使"耦合"可被干净地测量，而不是混在参数海里。

用法：
  python tools/r146_ph_ident.py --stage sens      # 只做黄金集灵敏度 + 一阶步
  python tools/r146_ph_ident.py --stage line      # 加沿 Δ1 的阻尼线搜索与可行域边界

（本工具**不改引擎**：θ 只经 `params["gamma1"/"gamma2"/"m_ph"]` 覆盖注入，
 默认不传 ⇒ 逐位不变。R146 未修改任何默认参数。）
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import simulate as sim_mod  # noqa: E402

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]
PH_KEYS = ("gamma1", "gamma2", "m_ph")
DELTA = 0.02          # 对数扰动步长（2%）
RIDGE = 1e-6          # 岭正则（只为防奇异，量级远小于真实灵敏度）
OUT = os.path.join(ROOT, "runs", "r146_ph_ident.json")  # 由 main 按 stage 覆盖


def load_params_map():
    """每批 params dict —— 必须走 SSOT 的 build_params，不能拿 json 里的记录反构造。

    踩坑记录：`runs/final_validation_v2.json` 的 `params` 字段只记录了**该批的显著项**，
    不含 `build_params` 无条件注入的 `dist_flag=1`；按它反构造会跑成 dist_flag=0
    （b8 产率 −7.12% vs 基准 −4.04%），整条结论就落在另一个工况上。
    这里直接调 `golden_params.params_for(b)`，并在 main() 里与冻结基准逐批对账。
    """
    from golden_params import COMBINED, build_params
    return {b: build_params(COMBINED[b]) for b in COMBINED}


def load_frozen_yield():
    """冻结基准的逐批产率误差（用于证明基线口径没跑偏）。"""
    with open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8") as f:
        res = json.load(f)["results"]
    return {int(r["batch"]): float(r["yield_err"]) for r in res}


def run_one(batch, params):
    """跑一批，返回 (pH 残差数组, 时间数组, 产率误差, pH 末值, co2d_max)。

    注意网格错位：sim 从 t=0.4 起记录（首行 0.2 是初值不入记录），v3 从 0.2 起，
    故按 time_h 对齐而非按行号——按行号会整体错一格，把 0.2 h 的系统差摊到全程。
    """
    sim, v3 = sim_mod.simulate_open_loop(int(batch), dict(params))
    t = sim["time_h"].to_numpy(float)
    ph_m = sim["pH"].to_numpy(float)
    _v = {round(float(k), 6): float(v) for k, v in
          zip(v3["time_h"].to_numpy(float), v3["pH"].to_numpy(float))}
    ph_o = np.array([_v.get(round(float(x), 6), np.nan) for x in t], dtype=float)
    msk = np.isfinite(ph_m) & np.isfinite(ph_o) & (t > 0)
    ym = sim_mod.yield_metrics(sim, v3)
    _r = (ph_m - ph_o)[msk]
    _t = t[msk]
    _slope = float(np.polyfit(_t, _r, 1)[0]) * 100.0 if _r.size > 4 else float("nan")
    _th = np.array_split(np.arange(_r.size), 3)
    return {
        "batch": int(batch),
        "t": _t,
        "resid": _r,
        "yield_err": float(ym["rel_err_total"]),
        "ph_end": float(ph_m[-1]),
        "co2d_max": float(sim["CO2d"].max()),
        "ph_model": ph_m[msk],
        "ph_meas": ph_o[msk],
        # 残差结构：常数偏差 a 与每 100 h 的漂移 b。a≠0 ⇒ 可被常数参数吸收；
        # b≠0 ⇒ 缺的是**率**项（每小时的产酸源），常数重标定改不动。
        "resid_mean": float(np.mean(_r)),
        "resid_rmse": float(np.sqrt(np.mean(_r ** 2))),
        "resid_slope_100h": _slope,
        "resid_thirds": [float(np.mean(_r[ix])) for ix in _th if ix.size],
        # 分支/钳位诊断：D-32 的悬崖就在这里显形
        "n_clamp": int(np.sum(ph_m <= 3.05)),
        "n_over7": int(np.sum(ph_m >= 7.0)),
        "ph_min": float(np.min(ph_m)),
        "ph_max": float(np.max(ph_m)),
        "P_end_over_peak": float(sim["P"].iloc[-1] / max(float(sim["P"].max()), 1e-9)),
    }


def _run_task(args):
    batch, params, tag = args
    r = run_one(batch, params)
    r["tag"] = tag
    return r


def summarise(rows, label):
    res = np.concatenate([r["resid"] for r in rows])
    rmse = float(np.sqrt(np.mean(res ** 2)))
    bias = float(np.mean(res))
    yerr = np.array([r["yield_err"] for r in rows])
    within = int(np.sum(np.abs(yerr) <= 0.05))
    print(f"  [{label:14s}] pH RMSE={rmse:.4f}  偏差={bias:+.4f}  "
          f"|产率误差|中位={np.median(np.abs(yerr)):.2%}  ±5%命中={within}/{len(rows)}  "
          f"max|err|={np.max(np.abs(yerr)):.2%}")
    return {"label": label, "ph_rmse": rmse, "ph_bias": bias,
            "yield_abs_med": float(np.median(np.abs(yerr))),
            "within5": within, "n": len(rows),
            "yield_max": float(np.max(np.abs(yerr))),
            "yield_err": {int(r["batch"]): r["yield_err"] for r in rows}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("base", "sens", "line", "g1"), default="line")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--lams", type=str, default="", help="线搜索步长比例，逗号分隔")
    ap.add_argument("--g1s", type=str, default="", help="γ1 标度扫描点，逗号分隔")
    ap.add_argument("--batches", type=str, default="", help="覆盖黄金集，逗号分隔")
    args = ap.parse_args()

    out_path = os.path.join(ROOT, "runs", f"r146_ph_ident_{args.stage}.json")
    pmap = load_params_map()
    batches = [int(x) for x in args.batches.split(",")] if args.batches else GOLDEN
    _par0 = sim_mod.make_params()
    _IDX = {"gamma1": 62, "gamma2": 63, "m_ph": 64}
    base_theta = {k: float(_par0[_IDX[k]]) for k in PH_KEYS}
    print("θ 基线 =", {k: f"{v:.6e}" for k, v in base_theta.items()})

    out = {"theta_base": base_theta, "delta": DELTA, "golden": batches, "stages": {}}

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        # ---- 1. 基线 ----
        print("\n[1] 基线（12 批黄金集）")
        base_rows = list(ex.map(_run_task, [(b, pmap[b], "base") for b in batches]))
        base_sum = summarise(base_rows, "baseline")
        out["stages"]["baseline"] = base_sum
        for r in base_rows:
            print(f"       b{r['batch']:>2d} 偏差={np.mean(r['resid']):+.4f} "
                  f"产率={r['yield_err']:+.2%} pH末={r['ph_end']:.3f}")

        # 口径闸门：基线必须与冻结基准逐批一致，否则后面测的是另一个工况（见 load_params_map 注释）
        frozen = load_frozen_yield()
        dmax = max(abs(r["yield_err"] - frozen[r["batch"]]) for r in base_rows
                   if r["batch"] in frozen)
        print(f"   [口径闸门] 与冻结基准逐批 |Δyield_err| max = {dmax:.3e}")
        if dmax > 1e-9:
            raise SystemExit(f"基线口径与冻结基准不符（max|Δ|={dmax:.3e}）——先修口径再谈灵敏度")
        out["gate"] = {"baseline_vs_frozen_max_abs_delta": dmax}

        # ---- 1a. 只出基线诊断（--stage base）----
        if args.stage == "base":
            out["baseline_diag"] = {
                int(r["batch"]): {"resid_mean": r["resid_mean"],
                                  "resid_rmse": r["resid_rmse"],
                                  "resid_slope_100h": r["resid_slope_100h"],
                                  "resid_thirds": r["resid_thirds"],
                                  "n_clamp": r["n_clamp"], "n_over7": r["n_over7"],
                                  "ph_min": r["ph_min"], "ph_max": r["ph_max"],
                                  "ph_end": r["ph_end"], "yield_err": r["yield_err"],
                                  "P_end_over_peak": r["P_end_over_peak"]}
                for r in base_rows}
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"\n写出 {out_path}")
            return

        # ---- 1b. 逐批 γ1 标定可行性（--stage g1）----
        # 动机：pH 偏差逐批差 80 倍（−0.007 … −0.572），全局重标定不可能同时满足；
        # 那么"逐批一个 γ1 标度"够不够？γ1 是纯产酸增益，物理上对应"每摩尔反应放出多少 H+"，
        # 批间差异（原料批次/菌株状态）本就该落在这里。
        if args.stage == "g1":
            g1s = [float(x) for x in (args.g1s or "0.4,0.55,0.7,0.85,1.0").split(",")]
            print(f"\n[1b] 逐批 γ1 标度扫描 s ∈ {g1s}")
            tasks = [(b, dict(pmap[b], gamma1=base_theta["gamma1"] * s), f"{s:g}")
                     for s in g1s for b in batches]
            rows_g = list(ex.map(_run_task, tasks))
            grid = {}
            for r in rows_g:
                grid.setdefault(r["batch"], {})[r["tag"]] = r
            hdr = "  ".join(f"{'s=' + format(s, 'g'):>16s}" for s in g1s)
            print(f"   {'批':>4s} {hdr}")
            table = {}
            for b in batches:
                g = grid[b]
                cells, best = [], None
                for s in g1s:
                    r = g[f"{s:g}"]
                    bi = float(np.mean(r["resid"]))
                    cells.append(f"{bi:+.3f}/{r['yield_err']:+.1%}")
                    if best is None or abs(bi) < abs(best[1]):
                        best = (s, bi, r["yield_err"], r["n_clamp"], r["n_over7"])
                print(f"   b{b:<3d} " + "  ".join(f"{c:>16s}" for c in cells))
                table[int(b)] = {"bias": {f"{s:g}": float(np.mean(g[f'{s:g}']["resid"]))
                                          for s in g1s},
                                 "yield": {f"{s:g}": g[f'{s:g}']["yield_err"] for s in g1s},
                                 "best_s": best[0], "best_bias": best[1],
                                 "yield_at_best": best[2],
                                 "clamp_at_best": best[3], "over7_at_best": best[4]}
            print("\n   （单元格 = pH 偏差 / 产率误差）")
            vis = [v for v in table.values()
                   if abs(v["best_bias"]) <= 0.05 and abs(v["yield_at_best"]) <= 0.05]
            print(f"   [可行] |偏差|≤0.05 且 |产率|≤5% 的批：{len(vis)}/{len(table)} "
                  f"→ {[b for b, v in table.items() if v in vis]}")
            print(f"   需要的 s：{ {b: v['best_s'] for b, v in table.items()} }")
            out["stages"]["g1"] = {"grid": table, "n_viable": len(vis),
                                   "viable": [b for b, v in table.items() if v in vis]}
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"\n写出 {out_path}")
            return

        # ---- 2. 灵敏度（只用"干净批"）----
        # 为什么筛：被守卫钳位的批（pH 末 3.00x）其 pH 轨迹由钳位决定，对 γ 的响应是
        # 不连续的——实测把它们纳入后三列范数变成 3155/3141/3141、SVD [1.731, .072, .0047]、
        # 条件数 **372**（干净 4 批时是 6.19）。那是钳位在冒充信息，不是可辨识性。
        clean_ids = [r["batch"] for r in base_rows
                     if r["n_clamp"] == 0 and r["n_over7"] == 0]
        dropped = [r["batch"] for r in base_rows if r["batch"] not in clean_ids]
        print(f"\n[2] 灵敏度（对数前向差分 δ={DELTA}）")
        print(f"   用于辨识的干净批 {len(clean_ids)} 个；剔除 {len(dropped)} 个：{dropped}")
        out["clean_ids"] = clean_ids
        out["dropped_ids"] = dropped

        tasks, meta = [], []
        for k in PH_KEYS:
            for b in clean_ids:
                p = dict(pmap[b])
                p[k] = base_theta[k] * np.exp(DELTA)
                tasks.append((b, p, k))
                meta.append((k, b))
        pert_rows = list(ex.map(_run_task, tasks))
        by_tag = {k: {} for k in PH_KEYS}
        for (k, b), r in zip(meta, pert_rows):
            by_tag[k][b] = r

        # 堆叠残差与灵敏度（按批次内时刻对齐，用基线的时间网格做同点差分）
        per_batch = {}
        for r0 in base_rows:
            b = r0["batch"]
            if b not in clean_ids:
                continue
            cols = []
            for k in PH_KEYS:
                rp = by_tag[k][b]
                # 同一批两次运行的网格一致（同输入），直接相减
                assert len(rp["ph_model"]) == len(r0["ph_model"]), f"b{b} 网格不一致"
                cols.append((rp["ph_model"] - r0["ph_model"]) / DELTA)
            per_batch[b] = (r0["resid"], np.column_stack(cols))
        r_vec = np.concatenate([v[0] for v in per_batch.values()])
        J = np.vstack([v[1] for v in per_batch.values()])

        # 列尺度归一（对数参数 ⇒ 灵敏度量级差异大，先标准化再解，避免单纯被大列支配）
        scale = np.linalg.norm(J, axis=0)
        scale[scale == 0] = 1.0
        Jn = J / scale
        U, S, Vt = np.linalg.svd(Jn, full_matrices=False)
        print(f"   奇异值 = {np.round(S, 6)}  条件数 = {S[0]/S[-1]:.3e}")
        print(f"   各列范数 = {dict(zip(PH_KEYS, np.round(scale, 6)))}")

        # 逐批局部可辨识性：平均值斜率 + 该批 3×3 的条件数。若逐批都病态 ⇒ 退化是本征的；
        # 若逐批良性、合并后病态 ⇒ 是"各批需要不同方向"在合并时互相抵消（那才是真发现）。
        print(f"   {'批':>4s} {'偏差':>8s} {'d pH/dlnγ1':>11s} {'d/dlnγ2':>10s} {'d/dlnm_ph':>11s} "
              f"{'批内条件数':>9s}")
        pb_diag = {}
        for b, (rb, Jb) in per_batch.items():
            sb = np.linalg.norm(Jb, axis=0)
            ss = np.linalg.svd(Jb / np.where(sb == 0, 1, sb), compute_uv=False)
            cond_b = float(ss[0] / ss[-1]) if ss[-1] > 0 else float("inf")
            slopes = [float(np.mean(Jb[:, i])) for i in range(3)]
            print(f"   b{b:<3d} {np.mean(rb):>+8.4f} {slopes[0]:>11.5f} {slopes[1]:>10.5f} "
                  f"{slopes[2]:>11.5f} {cond_b:>9.2f}")
            pb_diag[int(b)] = {"resid_mean": float(np.mean(rb)), "slopes": slopes,
                               "cond": cond_b}
        out["per_batch_identifiability"] = pb_diag

        # ---- 3. 一阶步 ----
        A = Jn.T @ Jn + RIDGE * np.eye(3)
        d_std = -np.linalg.solve(A, Jn.T @ r_vec)
        d_log = d_std / scale
        pred_rmse = float(np.sqrt(np.mean((r_vec + J @ d_log) ** 2)))
        print(f"\n[3] Gauss-Newton 一阶步 Δ(lnθ) = {dict(zip(PH_KEYS, np.round(d_log, 4)))}")
        print(f"   预测 pH RMSE: {base_sum['ph_rmse']:.4f} → {pred_rmse:.4f}")

        theta1 = {k: base_theta[k] * np.exp(float(d_log[i])) for i, k in enumerate(PH_KEYS)}
        out["stages"]["gn1"] = {"dlog": d_log.tolist(), "pred_rmse": pred_rmse,
                                "theta": theta1, "sv": S.tolist()}

        if args.stage == "sens":
            # 只走到这里
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"\n写出 {out_path}")
            return

        # ---- 4. 沿安全方向的线搜索（不用第二次 Newton）----
        # 为什么不做第二次 Newton：R146 实测在 θ1 处重算 J 后，GN 步把 b36 的 pH 顶过 7.0
        # （5 个样点，峰 7.194）→ basic 分支爆破 → 守卫钳 3.000 保持 288 样点 → 产率 −41.69%。
        # 预报 0.2241、实跑 0.9159。**可行域被 D-32 的悬崖截断，不是光滑曲率限制**，
        # 故改用沿 Δ1 的阻尼线搜索，把"能走多远"直接测出来。
        print("\n[4] 沿 Δ1 的阻尼线搜索（λ 为步长比例）")
        lams = [float(x) for x in (args.lams or "0.25,0.5,0.75,1.0,1.25,1.5").split(",")]
        tasks = []
        for lam in lams:
            th = {k: base_theta[k] * np.exp(lam * float(d_log[i]))
                  for i, k in enumerate(PH_KEYS)}
            for b in batches:
                tasks.append((b, dict(pmap[b], **th), f"lam{lam:g}"))
        rows_l = list(ex.map(_run_task, tasks))
        by_lam = {}
        for r in rows_l:
            by_lam.setdefault(r["tag"], []).append(r)

        print(f"   {'λ':>5s}  {'pH_RMSE':>8s} {'偏差':>8s}  {'±5%':>6s} {'max|err|':>9s} "
              f"{'钳位样点':>8s} {'≥7样点':>7s} {'max pH':>7s} {'最差批':>10s}")
        table = []
        for lam in lams:
            rs = by_lam[f"lam{lam:g}"]
            s = summarise(rs, f"λ={lam:g}")
            nclamp = sum(r["n_clamp"] for r in rs)
            nover = sum(r["n_over7"] for r in rs)
            phmax = max(r["ph_max"] for r in rs)
            worst = max(rs, key=lambda r: abs(r["yield_err"]))
            print(f"   {lam:>5.2f}  {s['ph_rmse']:>8.4f} {s['ph_bias']:>+8.4f}  "
                  f"{s['within5']:>3d}/{s['n']:<2d} {s['yield_max']:>9.2%} "
                  f"{nclamp:>8d} {nover:>7d} {phmax:>7.3f} "
                  f"b{worst['batch']}{worst['yield_err']:>+7.2%}")
            table.append({"lam": lam, **s, "n_clamp": nclamp, "n_over7": nover,
                          "ph_max": phmax, "worst_batch": int(worst["batch"]),
                          "worst_err": worst["yield_err"],
                          "per_batch_bias": {int(r["batch"]): float(np.mean(r["resid"]))
                                             for r in rs},
                          "per_batch_yield": {int(r["batch"]): r["yield_err"] for r in rs}})
        out["stages"]["line_search"] = table

        # 判据：同时满足 ①无钳位 ②无 ≥7 ③pH 不出实测包络 [5.396, 6.766] 的最大 λ
        env_lo, env_hi = 5.396, 6.766
        safe = [t for t in table
                if t["n_clamp"] == 0 and t["n_over7"] == 0 and t["ph_max"] <= env_hi]
        best = max(safe, key=lambda t: t["lam"]) if safe else None
        print(f"\n   [可行域] 满足无钳位/无≥7/不出包络 [5.396, 6.766] 的最大 λ = "
              f"{best['lam'] if best else 'none'}")
        out["admissible"] = {"env": [env_lo, env_hi],
                             "max_safe_lambda": (best or {}).get("lam"),
                             "table": [{"lam": t["lam"], "ok": bool(t in safe)} for t in table]}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {out_path}")


if __name__ == "__main__":
    main()
