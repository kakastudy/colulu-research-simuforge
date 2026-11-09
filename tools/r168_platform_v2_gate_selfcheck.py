# -*- coding: utf-8 -*-
"""R168.1 · G9 前端静态规则的**自验证**。

闸门规则本身也要被验证，否则它只是装饰：
  ① 对「当前代码」必须 PASS；
  ② 对「注入了旧 bug 的代码」必须 FAIL（否则规则抓不到它要抓的东西）。

用法：python tools/r168_platform_v2_gate_selfcheck.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from r168_platform_v2_gate import strip_js_comments  # noqa: E402

V2 = os.path.join(ROOT, "platform_v2")

PAT_AXIS = re.compile(r"p\.y\s*\[\s*(?:xa|ya|axes)\b")
PAT_INDEX = re.compile(r"xs\s*\[\s*\w+\.indexOf\(")


def axis_hits(src: str) -> int:
    return len(PAT_AXIS.findall(strip_js_comments(src)))


def index_hits(src: str) -> int:
    return len(PAT_INDEX.findall(strip_js_comments(src)))


def main() -> int:
    with open(os.path.join(V2, "app_v2.js"), encoding="utf-8") as f:
        good = f.read()
    with open(os.path.join(V2, "style.css"), encoding="utf-8") as f:
        css = f.read()

    results = []

    # ① 当前代码必须干净
    results.append(("当前代码 G9a 无命中", axis_hits(good) == 0, axis_hits(good)))
    results.append(("当前代码 G9b 无命中", index_hits(good) == 0, index_hits(good)))

    # ② 注入旧 bug 必须被抓到
    injected_axis = good + "\nconst yi = ya.values.findIndex((v) => Math.abs(v - p.y[ya.key]) < 1e-9);\n"
    results.append(("注入 ① 后 G9a 报警", axis_hits(injected_axis) >= 1, axis_hits(injected_axis)))

    injected_index = good + "\nconst d = pathFrom(order.map((i) => xs[order.indexOf(i)]));\n"
    results.append(("注入 ② 后 G9b 报警", index_hits(injected_index) >= 1, index_hits(injected_index)))

    # ③ 注释里的错误写法不应误报
    comment_only = good + "\n// 说明：旧实现误取 p.y[ya.key] ⇒ 整张网格不画\n"
    results.append(("注释中的写法不误报", axis_hits(comment_only) == 0, axis_hits(comment_only)))

    # ④ 字符串字面量里的写法不应误报
    str_only = good + '\nconst note = "旧写法是 p.y[ya.key]";\n'
    results.append(("字符串中的写法不误报", axis_hits(str_only) == 0, axis_hits(str_only)))

    # ⑤ 回归：正则字面量里含引号（实战触发点）
    #    `replace(/[&<>"]/g, c => ({'"': "&quot;"}[c]))` —— 初版扫描器把正则里的
    #    `"` 当字符串开头，把 `'"'` 的 `'` 又当一段字符串开头 ⇒ 整文件后半段被吞
    #    ⇒ 注释不再剥离 ⇒ 误报。此处构造最小复现，验证新扫描器不再犯同样的错。
    regex_trap = (
        'const esc = (s) => String(s).replace(/[&<>"]/g, '
        '(c) => ({ "&": "&amp;", \'"\': "&quot;" }[c]));\n'
        '// 旧实现误取 p.y[ya.key] ⇒ 整张网格不画\n'
    )
    results.append(("正则字面量含引号时不误报", axis_hits(regex_trap) == 0, axis_hits(regex_trap)))

    # ⑥ 回归：模板字符串插值内的独立字符串 / 嵌套模板
    tmpl_trap = (
        'const t = `a ${x ? \'p.y[ya.key]\' : `b ${y}`} c`;\n'
        '// 注释里也有 p.y[ya.key]\n'
    )
    results.append(("模板插值内不误报", axis_hits(tmpl_trap) == 0, axis_hits(tmpl_trap)))

    # ⑦ 回归：除号不能被误判成正则（否则后面真实代码被吞）
    div_trap = 'const z = a / b / c;\nconst w = "p.y[ya.key]";\n'
    results.append(("除号不误判成正则", axis_hits(div_trap) == 0, axis_hits(div_trap)))

    # ⑤ G9c：抽屉必须是 fixed 且禁横向滚动
    drawer_fixed = re.search(r"\.drawer\s*\{[^}]*position:\s*fixed", css, re.S) is not None
    results.append(("G9c 抽屉为 fixed", drawer_fixed, drawer_fixed))
    results.append(("G9c 禁横向滚动", "overflow-x" in css, "overflow-x" in css))

    ok = True
    print("=== G9 规则自验证 ===")
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}  (实测 {detail})")
        ok = ok and passed
    print("结论:", "规则有效" if ok else "规则无效 —— 必须修正后再用")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
