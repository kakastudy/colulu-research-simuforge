# -*- coding: utf-8 -*-
"""R167 终检（只读、常驻可复跑）—— 闸门 / 治理 / 平台产物 / 边界四类一致性。

    py tools/r167_final_check.py --json
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
CHECKS = []
CV = "v1.97"


def check(cid, name, ok, got=None):
    CHECKS.append({"id": cid, "name": name, "ok": bool(ok), "got": got})
    return ok


def jload(rel):
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def datajs():
    s = text("platform/data.js")
    return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))


def port_open(p):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def main():
    gate = jload("runs/r167_platform_gate.json") or {}
    gov = jload("runs/r167_governance_update.json") or {}
    r166 = jload("runs/r166_final_check.json") or {}
    D = datajs()
    t8 = gate.get("t8") or {}

    # ---- A 闸门 ----
    check("F1", "R167 闸门 25/25 PASS 且含 T8 六视图",
          gate.get("verdict") == "PASS" and gate.get("n_pass") == 25
          and gate.get("n_checks") == 25 and len(gate.get("shots") or []) == 6,
          {"verdict": gate.get("verdict"), "n_pass": gate.get("n_pass"),
           "n_checks": gate.get("n_checks"), "shots": len(gate.get("shots") or [])})
    views = {v["view"]: v for v in t8.get("views", [])}
    check("F2", "T8 六视图全部渲染成功、无 console error / 4xx、前端调用端到端通过",
          len(views) == 6 and all(v.get("ok") for v in views.values())
          and not t8.get("console_errors") and not t8.get("http_404")
          and bool((t8.get("ui_invoke") or {}).get("ok")),
          {"views": {k: v.get("count") for k, v in views.items()},
           "console_errors": t8.get("console_errors"),
           "http_4xx": t8.get("http_404"),
           "ui_invoke": t8.get("ui_invoke")})
    shots = gate.get("shots") or []
    check("F3", "6 张 T8 截图存在且非空（> 10 KB）",
          len(shots) == 6 and all((ROOT / p).exists()
                                  and (ROOT / p).stat().st_size > 10240 for p in shots),
          [((ROOT / p).stat().st_size if (ROOT / p).exists() else 0) for p in shots])

    # ---- B 治理同步 ----
    contract = text("ENGINE_CONTRACT.md")
    check("F4", f"契约升 {CV}：头部 + R167 状态行 + 版本表行三处一致",
          contract.startswith(f"# ENGINE_CONTRACT.md — 求解器引擎批处理契约（{CV}")
          and f"> 状态：**{CV}**（R167" in contract
          and f"| {CV} | R167：" in contract,
          {"header": contract.splitlines()[0][:80]})
    st = text("state.yaml")
    check("F5", "state.yaml：M5→PASS / cap L2 prototype（conditional 解除）/ status_ladder 同步",
          "    M5: PASS" in st and "  level: L2 prototype\n" in st
          and "status_ladder: L2 prototype\n" in st
          and "platform visualization" not in st,
          {"m5": "    M5: PASS" in st, "cap": "  level: L2 prototype\n" in st})
    ledger = text("docs/r157_debt_ledger.md")
    check("F6", "台账 D-65 关闭 + D-92 登记 + 总表行同步",
          "### D-65　" in ledger and "✅ **R167 关闭（治理条件已闭合）**" in ledger
          and "### D-92　R167 仿真计算平台升级" in ledger
          and "| D-65 |" in ledger and "✅ **R167 关闭**" in ledger)
    signoff = text("docs/m5_review_signoff.md")
    check("F7", "签核单 R-17 重评审落地（M5→PASS、cap 条件解除、证据链接）",
          "**R-17**（2026-11-06，R167 平台升级后的" in signoff
          and "`gates.M5`" in signoff and "L2 prototype" in signoff
          and "runs/r167_platform_gate.json" in signoff)
    docs = ["README.md", "tools/INDEX.md", "docs/roadmap_next.md",
            ".workbuddy/memory/2026-11-06.md"]
    marks = ["### R167（2026-11-06）— 仿真计算平台升级",
             "### R167（平台升级 · 算子运行时装载",
             "## 九、R167 执行结果（2026-11-06）",
             "## R167（14:14–）：仿真计算平台升级与算子装载"]
    check("F8", "README / INDEX / 路线图 §8.9 / 工作记忆四处 R167 登记齐全",
          all(m in text(d) for d, m in zip(docs, marks)),
          {d: (m in text(d)) for d, m in zip(docs, marks)})
    check("F9", "治理 apply 无错误、dry-run 幂等记录存在",
          gov.get("mode") == "apply" and gov.get("n_error") == 0
          and gov.get("n_changed", 0) > 0 and gov.get("verdict") == "PASS",
          {k: gov.get(k) for k in ("mode", "n_changed", "n_skip", "n_error")})

    # ---- C 平台产物 ----
    check("F10", f"data.js 契约 {CV} / catastrophic 4 / 12 算子 / 14 能力",
          D["meta"]["contract"] == CV and D["evidence"]["contract"] == CV
          and D["kpi"]["catastrophic"] == 4
          and D["operators"]["n_loaded"] == 12
          and D["workbench"]["n_tools"] == 14 and D["workbench"]["all_loaded"],
          {"contract": D["meta"]["contract"], "catastrophic": D["kpi"]["catastrophic"]})
    serve = text("platform/serve.py")
    check("F11", "serve.py 三 additive 接口齐备且 /api/simulate 仍走 L0 simulate()",
          all(x in serve for x in ('"/api/ops"', '"/api/evidence"', '"/api/invoke"'))
          and "res = simulate(batch, payload.get(\"overrides\") or {})" in serve
          and "import ops_registry as ops" in serve)
    app = text("platform/app.js")
    html = text("platform/index.html")
    check("F12", "前端 6 视图（含 workbench）+ 运行时装载标签 + 工作台 DOM",
          'id: "workbench"' in app and 'id="v-workbench"' in html
          and "运行时已装载" in app and "renderWorkbench" in app
          and "#wb-tiers" in app)
    opssrc = text("platform/ops_registry.py")
    check("F13", "注册表 14 能力 / 5 个 L3 禁用参数 / opt_in+confirm 闸门",
          len(re.findall(r'\{"id":\s*"', opssrc)) == 14
          and len(re.findall(r'^\s+"[a-z_]+":\s*"R166', opssrc, re.M)) == 5
          and "FORBIDDEN_KEYS" in opssrc and "OPT_IN_PARAMS" in opssrc
          and '"l3_exposed": False' in opssrc
          and "COST_HEAVY" in opssrc,
          {"tools": len(re.findall(r'\{"id":\s*"', opssrc)),
           "forbidden": len(re.findall(r'^\s+"[a-z_]+":\s*"R166', opssrc, re.M))})

    # ---- D 边界 ----
    frozen = {"model.py": "64ce1fd790f92669", "observe.py": "7e73d49adee13fda",
              "simulate.py": "815619d9075ba3bb", "mcp_server.py": "6263c73f747edbff"}
    now = {f: hashlib.sha256((ROOT / "candidate/indpensim/v0.1" / f).read_bytes())
           .hexdigest()[:16] for f in frozen}
    check("F14", "引擎 4 文件 sha256 与 R166 冻结值逐位一致（本轮零改动）",
          now == frozen, now)
    check("F15", "R166 终检 54/54 PASS 未被覆盖或失效",
          r166.get("verdict") == "PASS" and r166.get("n_pass") == 54)
    g16 = next((c for c in gate.get("checks", []) if c["id"] == "G16"), {})
    check("F16", "L3 未夹带：平台运行路径不设置候选参数 + 闸门 G16 行为拒绝通过 + GOAL §5 未改",
          "dist_noise_sigma" not in serve
          and "INNOVATION_Z" not in serve
          and "不接实产闭环控制" in text("GOAL.md")
          and g16.get("ok") is True,
          {"G16": g16.get("ok"), "goal5": "不接实产闭环控制" in text("GOAL.md")})
    check("F17", "8770 端口未监听（未重启原服务）", not port_open(8770))
    check("F18", "六视图截图目录与 T8 复验文档、轮次报告齐备",
          (ROOT / "docs/r167_platform_screen_check.md").exists()
          and (ROOT / "docs/r167_round_report.md").exists()
          and (ROOT / "docs/goal_backtrace_check_v5.md").exists())
    leak = []
    for f in ["ENGINE_CONTRACT.md", "state.yaml", "docs/r157_debt_ledger.md",
              "docs/m5_review_signoff.md", "README.md", "tools/INDEX.md",
              "docs/roadmap_next.md", ".workbuddy/memory/2026-11-06.md",
              "docs/r167_round_report.md", "docs/r167_platform_screen_check.md"]:
        # 只认真正的 ${name} 占位符；文档中作为说明文字出现的裸 `${` 不算
        if re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", text(f)):
            leak.append(f)
    check("F19", "治理与报告文本无 ${ 占位符残留", not leak, leak)
    check("F20", "换行风格原样（契约 / state.yaml 为 CRLF，其余 LF）",
          b"\r\n" in (ROOT / "ENGINE_CONTRACT.md").read_bytes()
          and b"\r\n" in (ROOT / "state.yaml").read_bytes()
          and b"\r\n" not in (ROOT / "docs/r167_round_report.md").read_bytes())

    npass = sum(1 for c in CHECKS if c["ok"])
    out = {"round": "R167", "tool": "tools/r167_final_check.py",
           "contract": CV,
           "verdict": "PASS" if npass == len(CHECKS) else "FAIL",
           "n_pass": npass, "n_checks": len(CHECKS), "checks": CHECKS}
    (RUNS / "r167_final_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if "--json" in sys.argv:
        print(json.dumps({k: v for k, v in out.items() if k != "checks"},
                         ensure_ascii=False, indent=1))
    else:
        for c in CHECKS:
            print(f"[{c['id']}] {'PASS' if c['ok'] else 'FAIL'}  {c['name']}")
        print(f"\nR167 终检: {out['verdict']}  {npass}/{len(CHECKS)}")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
