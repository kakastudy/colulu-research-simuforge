# -*- coding: utf-8 -*-
"""给已产出的 `runs/r157_bistab_escape.json` 补写 `base_override` 元数据。

背景：R157 收尾时发现 `tools/r157_bistab_knob.py` 的 json 输出**没有记录
`--base-override`**（该 json 是崩塌态逃逸实验的产物，若不记，复核者无法从文件
本身判断它是基线态还是崩塌态跑的 —— 两条判读结论完全不同）。

处理：
  * **工具已修**（`r157_bistab_knob.py` 的 json dump 增加 `base_override` 字段）；
  * 本脚本把**已产出**的 json 补上同一字段，值取自该次运行的日志首行
    `[base-override] {'Y_sP': 0.85}`（可审计：日志留证在 `runs/_r157_bistab_escape.log`）。

幂等：字段已存在则 [skip]。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSONP = os.path.join(HERE, "runs", "r157_bistab_escape.json")
LOGP = os.path.join(HERE, "runs", "_r157_bistab_escape.log")


def main():
    with open(JSONP, "r", encoding="utf-8") as f:
        d = json.load(f)
    if d.get("base_override") is not None:
        print("[skip   ] json 已含 base_override = %s" % d["base_override"])
        return 0

    # 从运行日志首行回读 base-override（可审计来源）
    override = None
    with open(LOGP, "r", encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("[base-override]"):
                override = eval(ln.split("]", 1)[1].strip())  # noqa: S307
                break
    if not override:
        raise SystemExit("[fail] 无法从日志回读 base_override")

    # 保持键序：ph_fix / bisect_rule / base_override / rows
    out = {"ph_fix": d.get("ph_fix"),
           "bisect_rule": d.get("bisect_rule"),
           "base_override": override,
           "rows": d.get("rows")}
    for k in d:
        if k not in out:
            out[k] = d[k]
    with open(JSONP, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("[ok     ] base_override = %s 已补写" % override)

    # 校验
    with open(JSONP, "r", encoding="utf-8") as f:
        d2 = json.load(f)
    assert d2["base_override"] == override
    assert len(d2["rows"]) == len(d["rows"])
    print("[ok] 校验通过；rows n = %d" % len(d2["rows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
