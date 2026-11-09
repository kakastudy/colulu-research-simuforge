# -*- coding: utf-8 -*-
"""给 `tools/r157_bistab_knob.py` 加「基础参数覆盖」口（`--base-override`）。

用途
----
**崩塌态逃逸实验**：把系统先推进崩塌态（`Y_sP = 0.85 < 跳变位置 0.894344`），
再扫各旋钮，看**有没有任何旋钮能把系统连续地拉回生产态**。
⇒ 若全部无效 ⇒ 崩塌态是一个**吸引子（basin）** ⇒ D-54（葡萄糖闭环）
在这套方程里**永久关闭**，进料可行域的硬约束是**阈值型**而非参数型。

实现
----
在 `_sim_one` 的 job 元组里追加第 5 位 `extra`（dict，覆盖基础参数）；
`_run` 兼容 4/5 元组。
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(ROOT, "tools", "r157_bistab_knob.py")

REPL = [
    # 1) _sim_one 解包
    ('''    batch, knob, value, ph_fix = job
    try:''',
     '''    batch, knob, value, ph_fix, extra = job
    try:'''),
    # 2) 覆盖应用
    ('''        p = dict(build_params(COMBINED[batch]))
        if knob is not None:
            p[KNOB_KEY[knob]] = value''',
     '''        p = dict(build_params(COMBINED[batch]))
        if extra:
            p.update(extra)
        if knob is not None:
            p[KNOB_KEY[knob]] = value'''),
    # 3) _run 兼容 4/5 元组
    ('''    ex = _init_pool(workers)
    return list(ex.map(_sim_one, jobs))''',
     '''    ex = _init_pool(workers)
    jobs = [j if len(j) == 5 else (j[0], j[1], j[2], j[3], None) for j in jobs]
    return list(ex.map(_sim_one, jobs))'''),
    # 4) _dense_scan 签名与调用
    ('''def _dense_scan(batch, knob, a, b, n, ph_fix, workers):''',
     '''def _dense_scan(batch, knob, a, b, n, ph_fix, workers, extra=None):'''),
    ('''    rows = _run([(batch, knob, float(v), ph_fix) for v in pts], workers)''',
     '''    rows = _run([(batch, knob, float(v), ph_fix, extra) for v in pts], workers)'''),
    ('''                rows_d, ys_d, max_adj, n_sign = _dense_scan(
                    b, k, a, bnd, args.refine_n, ph_fix, args.workers)''',
     '''                rows_d, ys_d, max_adj, n_sign = _dense_scan(
                    b, k, a, bnd, args.refine_n, ph_fix, args.workers, extra)'''),
    # 5) _bisect 内的单点调用
    ('''        r = _run([(batch, knob, mid, ph_fix)], workers)[0]''',
     '''        r = _run([(batch, knob, mid, ph_fix, extra)], workers)[0]'''),
    # 6) CLI
    ('''    ap.add_argument("--dense-coarse", type=int, default=0,''',
     '''    ap.add_argument("--base-override", type=str, default="",
                    help="基础参数覆盖，如 'Y_sP=0.85'（崩塌态逃逸实验用）")
    ap.add_argument("--dense-coarse", type=int, default=0,'''),
    # 7) main 里解析 extra
    ('''    ph_fix = int(args.ph_fix)

    all_out = []''',
     '''    ph_fix = int(args.ph_fix)
    extra = {}
    for kv in [x for x in args.base_override.split(",") if x.strip()]:
        k, v = kv.split("=")
        extra[k.strip()] = float(v)
    if extra:
        print("[base-override] %s" % extra)

    all_out = []'''),
    # 8) 粗扫 job 带 extra
    ('''        jobs = [(b, k, v, ph_fix) for k in knobs for v in GRIDS[k]]''',
     '''        jobs = [(b, k, v, ph_fix, extra) for k in knobs for v in GRIDS[k]]'''),
]


def main() -> int:
    t = io.open(TARGET, encoding="utf-8").read()
    missing = []
    for old, new in REPL:
        if old in t:
            t = t.replace(old, new, 1)
        elif new not in t:
            missing.append(old.splitlines()[0][:70])
    io.open(TARGET, "w", encoding="utf-8", newline="").write(t)
    if missing:
        print("[warn] 未命中的锚点（可能已打过补丁）：")
        for m in missing:
            print("   -", m)
    else:
        print("[ok] 全部锚点命中")
    import ast
    ast.parse(io.open(TARGET, encoding="utf-8").read())
    print("[ok] AST 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
