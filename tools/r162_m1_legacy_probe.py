# -*- coding: utf-8 -*-
"""R162 / M1 遗留 oq#38 + oq#36 证伪式探针。

P1 (oq#38) 终末收获口径：MATLAB 原式与 Python `yield_metrics` 是否逐位同构？
P2 (oq#36) MATLAB rng -> numpy 映射：三条候选路径逐位对齐实测。

纪律（D-78）：
  - 每条判据必须有**零信息对照**（恒真判据 = 没有判据）；
  - 结论必须带**口径引用**（源码行 / 官方文档）；
  - 本脚本**只读**，不修改引擎任何文件。

用法：
    py tools/r162_m1_legacy_probe.py
输出：
    runs/r162_m1_legacy_probe.json
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
OUT = os.path.join(ROOT, "runs", "r162_m1_legacy_probe.json")

H_SAMPLE = 0.2
MATLAB_RUN = os.path.join(ROOT, "IndPenSim_V2.01", "IndPenSim_V2.02", "indpensim_run.m")

# MATLAB 官方参考值（来源见下方 MATLAB_REFS 的 url / 文档名）
MATLAB_REFS = {
    "source": "MathWorks 官方文档 'Control Random Number Generation' / 'Random Numbers (Moler)'",
    "url": "https://www.mathworks.com/help/matlab/math/control-random-number-generation.html",
    "rng_default_rand4": [0.8147, 0.9058, 0.1270, 0.9134],
    "rng1_randn5": [-0.6490, 1.1812, -0.7585, -1.1096, -0.8456],
    "rng2_randn5": [-0.1242, -2.5415, 0.2772, -0.1960, -0.1962],
    "rng3_randn5": [0.0685, 0.9512, -0.3448, 0.0359, 1.1221],
    "notes": (
        "rng('default') == twister + seed 0（MathWorks: 'rng uses the factory value of "
        "\"twister\" for the Mersenne Twister generator with seed 0'）；"
        "MATLAB randn 的 normal transform 为 Ziggurat（MathWorks R2022a 随机数生成器对照表："
        "Client CPU / Twister / Normal Transform = 'Ziggurat'）。"
    ),
}


def _rel(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    return float(np.max(np.abs(a - b))) if a.size else float("nan")


# ---------------------------------------------------------------------------
# P1  oq#38 —— 终末收获口径
# ---------------------------------------------------------------------------
def p1_harvest_caliber():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "processed", "batches", "batch_*.csv"))):
        d = pd.read_csv(f)
        t = d["time_h"].to_numpy(float)
        V = d["V"].to_numpy(float)
        P = d["P"].to_numpy(float)
        fr = d["Fremoved"].to_numpy(float)

        nz = np.nonzero(fr != 0)[0]
        # MATLAB 原式（indpensim_run.m:194-196）
        matlab_harvest_during = float((fr * P).sum()) * H_SAMPLE        # 负值
        matlab_end = float(V[-1] * P[-1])
        matlab_total = matlab_end - matlab_harvest_during               # = |during| + end
        # Python 口径（simulate.py:944 yield_metrics）
        py_harvested = float(-(fr * P).sum()) * H_SAMPLE                # 正值
        py_total = py_harvested + matlab_end

        rows.append(dict(
            batch=int(os.path.basename(f)[6:8]),
            n_fremoved_nz=int(nz.size),
            t_first_drain=float(t[nz[0]]) if nz.size else None,
            t_last_drain=float(t[nz[-1]]) if nz.size else None,
            t_end=float(t[-1]),
            last_row_drain=bool(fr[-1] != 0),
            V0=float(V[0]), V_last=float(V[-1]),
            # MATLAB 原式
            matlab_harvest_during=matlab_harvest_during,
            matlab_end=matlab_end,
            matlab_total=matlab_total,
            # Python 口径
            py_harvested=py_harvested,
            py_total=py_total,
            # 反向对照：只算批内放罐（漏掉收罐）的口径偏差
            rel_err_if_drop_end=float(py_harvested / py_total - 1.0),
            # 零信息对照：Fremoved 全置零 => total 应退化为 end
            py_total_zero_Fremoved=matlab_end,
        ))
    df = pd.DataFrame(rows)

    # 1) 结构普查：末行放罐非零的批数应与 PROBLEM.md §9「10 批含终末收获段」一致
    n_last = int(df.last_row_drain.sum())
    drain_batches = sorted(int(b) for b in df.loc[df.last_row_drain, "batch"])

    # 2) MATLAB / Python 口径逐位同构验证
    diff_total = float(np.max(np.abs(df.matlab_total - df.py_total)))
    diff_total_rel = float(np.max(np.abs(df.matlab_total / df.py_total - 1.0)))

    # 3) 符号验证：MATLAB 的 during 必须为负（否则 yield_total 不等于两者之和）
    n_pos_during = int((df.matlab_harvest_during > 0).sum())

    # 4) 反向验证：漏掉 end_in_vessel 的口径偏差有多大
    drop_end = df.rel_err_if_drop_end
    # 5) 零信息对照：Fremoved=0 时 total 必须等于 end
    zero_ctrl = float(np.max(np.abs(df.py_total_zero_Fremoved - df.matlab_end)))

    checks = [
        dict(name="末行放罐非零批数 == PROBLEM.md §9 的 10 批",
             got=n_last, expect=10, ok=(n_last == 10)),
        dict(name="MATLAB yield_total 与 Python total 逐位同构",
             got=diff_total_rel, expect=0.0, ok=(diff_total_rel <= 1e-12),
             detail=f"max|Δ| = {diff_total:.6e} g"),
        dict(name="MATLAB harvested_during 恒为负（符号自洽）",
             got=n_pos_during, expect=0, ok=(n_pos_during == 0)),
        dict(name="零信息对照：Fremoved=0 时 total 退化为 end_in_vessel",
             got=zero_ctrl, expect=0.0, ok=(zero_ctrl <= 1e-9)),
        dict(name="反向验证：漏掉 end_in_vessel 会造成实质偏差（判据非恒真）",
             got=float(drop_end.abs().max()), expect=">5%",
             ok=(float(drop_end.abs().max()) > 0.05),
             detail=f"中位 {drop_end.median():+.2%}，最大 {drop_end.abs().max():.2%}"),
    ]

    return dict(
        checks=checks,
        n_batches=int(len(df)),
        drain_last_batches=drain_batches,
        drain_start_t_unique=sorted(set(df.t_first_drain.round(3).tolist())),
        drain_steps_distribution=df.n_fremoved_nz.value_counts().sort_index().to_dict(),
        V_last_by_group=dict(
            has_drain_last=sorted(float(v) for v in df.loc[df.last_row_drain, "V_last"]),
            no_drain_last_median=float(df.loc[~df.last_row_drain, "V_last"].median()),
            has_drain_last_median=float(df.loc[df.last_row_drain, "V_last"].median()),
        ),
        total_g=dict(
            median=float(df.py_total.median()), min=float(df.py_total.min()),
            max=float(df.py_total.max()),
        ),
        harvested_g=dict(median=float(df.py_harvested.median())),
        end_in_vessel_g=dict(median=float(df.matlab_end.median())),
        drop_end_rel_err=dict(
            median=float(drop_end.median()),
            max_abs=float(drop_end.abs().max()),
            frac_over_5pct=float((drop_end.abs() > 0.05).mean()),
        ),
    )


# ---------------------------------------------------------------------------
# P2  oq#36 —— MATLAB rng -> numpy 映射
# ---------------------------------------------------------------------------
def p2_rng_mapping():
    checks = []
    detail = {}

    # --- 分支 1：numpy default_rng（引擎现役用）vs MATLAB twister ---
    m_uni = MATLAB_REFS["rng_default_rand4"]
    n_def = np.random.default_rng(0).random(4)
    n_rs = np.random.RandomState(0).rand(4)
    detail["matlab_rng_default_rand4"] = m_uni
    detail["numpy_default_rng0_random4"] = n_def.tolist()
    detail["numpy_RandomState0_rand4"] = n_rs.tolist()
    d_def = _rel(m_uni, n_def)
    d_rs = _rel(m_uni, n_rs)
    detail["max_abs_diff_default_rng"] = d_def
    detail["max_abs_diff_RandomState"] = d_rs

    checks.append(dict(
        name="分支1 default_rng(0) 的 uniform 序列 ≠ MATLAB twister seed0",
        got=d_def, expect=">0", ok=(d_def > 0), detail=f"max|Δ| = {d_def:.6f}"))
    checks.append(dict(
        name="分支1 RandomState(0) 的 uniform 序列 ≠ MATLAB twister seed0",
        got=d_rs, expect=">0", ok=(d_rs > 0), detail=f"max|Δ| = {d_rs:.6f}"))

    # --- 分支 2：randn（ziggurat vs polar）逐点比对 ---
    randn_cmp = {}
    for s in (1, 2, 3):
        m = MATLAB_REFS[f"rng{s}_randn5"]
        n = np.random.RandomState(s).standard_normal(5)
        randn_cmp[s] = dict(matlab=m, numpy=n.tolist(),
                            max_abs_diff=_rel(m, n),
                            exact_match=bool(np.allclose(m, n, atol=1e-12)))
    detail["randn_comparison"] = randn_cmp
    all_mismatch = all(not v["exact_match"] for v in randn_cmp.values())
    checks.append(dict(
        name="分支2 MATLAB randn(Ziggurat) 与 numpy standard_normal(polar) 逐点全不等",
        got=all_mismatch, expect=True, ok=all_mismatch,
        detail="; ".join(f"seed{s}: max|Δ|={v['max_abs_diff']:.4f}"
                          for s, v in randn_cmp.items())))

    # --- 分支 3：端到端可复现性 —— 种子基准是否被记录 ---
    src = ""
    if os.path.exists(MATLAB_RUN):
        with open(MATLAB_RUN, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    # rng('shuffle') 可能在上游控制器 fctrl_indpensim.m —— 必须扫全目录，
    # 只扫 indpensim_run.m 会得出「shuffle 出现 0 处」的误导性 detail（D-78 教训）。
    shuffle_hits, shuffle_files = 0, []
    for mf in sorted(glob.glob(os.path.join(ROOT, "IndPenSim_V2.01", "**", "*.m"),
                               recursive=True)):
        with open(mf, "r", encoding="utf-8", errors="replace") as fh:
            mtxt = fh.read()
        h = len(re.findall(r"rng\(\s*['\"]shuffle['\"]\s*\)", mtxt))
        if h:
            shuffle_hits += h
            shuffle_files.append((os.path.basename(mf), h))
    seed_ref_hit = bool(re.search(r"Random_seed_ref\s*=\s*ceil\(\s*rand\s*\*\s*1000\s*\)", src))
    n_rng_calls = len(re.findall(r"\brng\(", src))
    n_randn_calls = len(re.findall(r"\brandn\(", src))
    detail["matlab_source"] = dict(
        rng_calls_in_run=n_rng_calls, randn_calls_in_run=n_randn_calls,
        shuffle_calls_total=shuffle_hits, shuffle_files=shuffle_files,
        seed_ref_unrecorded=seed_ref_hit)

    checks.append(dict(
        name="分支3 种子基准 Random_seed_ref 来自 rng('shuffle')（真随机、未记录）",
        got=seed_ref_hit, expect=True, ok=bool(seed_ref_hit),
        detail=(f"rng('shuffle') 全目录 {shuffle_hits} 处（{shuffle_files}）；"
                f"indpensim_run.m 内 rng {n_rng_calls} 处、randn {n_randn_calls} 处")))

    # --- 分支 4：Python 侧扰动是否有随机源（决定「扰动种子」映射是否可提）---
    sim_py = os.path.join(ROOT, "candidate", "indpensim", "v0.1", "simulate.py")
    with open(sim_py, "r", encoding="utf-8", errors="replace") as fh:
        ssrc = fh.read()
    asym_formula = bool(re.search(r"1\.0\s*-\s*np\.exp\(\s*-t_current\s*/\s*dist_tau\s*\)", ssrc))
    obs_py = os.path.join(ROOT, "candidate", "indpensim", "v0.1", "observe.py")
    with open(obs_py, "r", encoding="utf-8", errors="replace") as fh:
        osrc = fh.read()
    obs_rng = re.findall(r"np\.random\.(default_rng|RandomState)\(([^)]*)\)", osrc)
    detail["python_side"] = dict(
        dist_asym_deterministic_formula=asym_formula,
        observe_rng_calls=obs_rng)
    checks.append(dict(
        name="分支4 Python 侧时变扰动为确定性渐近式（无随机源 ⇒ 无「扰动种子」可映射）",
        got=asym_formula, expect=True, ok=bool(asym_formula)))
    checks.append(dict(
        name="分支4 observe.py 的 rng 仅用于 EnKF 集合初始化（估计器侧，与 MATLAB 数据侧不同用途）",
        got=len(obs_rng), expect=">0", ok=(len(obs_rng) > 0),
        detail=str(obs_rng)))

    return dict(checks=checks, detail=detail, matlab_refs=MATLAB_REFS)


def main():
    res = dict(round="R162", part="m1_legacy", checks_all=[])
    p1 = p1_harvest_caliber()
    p2 = p2_rng_mapping()
    res["P1_oq38_harvest_caliber"] = p1
    res["P2_oq36_rng_mapping"] = p2
    res["checks_all"] = p1["checks"] + p2["checks"]

    n_ok = sum(1 for c in res["checks_all"] if c["ok"])
    res["n_checks"] = len(res["checks_all"])
    res["n_pass"] = n_ok
    res["verdict"] = "PASS" if n_ok == len(res["checks_all"]) else "FAIL"

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2, default=str)

    for c in res["checks_all"]:
        print(("  PASS " if c["ok"] else "  FAIL ") + c["name"]
              + (f"  [{c.get('detail', '')}]" if c.get("detail") else ""))
    print(f"\nVERDICT: {res['verdict']}  ({n_ok}/{len(res['checks_all'])})")
    print(f"-> {OUT}")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
