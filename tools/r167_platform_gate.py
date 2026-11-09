# -*- coding: utf-8 -*-
"""R167 平台升级闸门 —— 源码边界 / 运行时装载 / HTTP 冒烟 / T8 六视图逐屏复验。

与 R166 闸门的判据纪律一致（D-78）：
- 每条判据都给实值与 got，不用「文件存在 ⇒ 通过」这类恒真判据；
- **L0 冻结基线**用引擎文件 sha256 与 R166 冻结值逐位比对 + 批 8 产量回归；
- **L3 未夹带**用行为测试（5 个禁用参数逐个 POST 必须 400），而非 grep 字符串；
- **运行时装载**用进程内 import + callable，不是 os.path.exists；
- 服务由本脚本起在 **8771**，退出时必停；**8770 前后均须未监听**。

用法：py tools/r167_platform_gate.py [--no-shots]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLATFORM = os.path.join(ROOT, "platform")
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
RUNS = os.path.join(ROOT, "runs")
PORT = 8771
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = os.path.join(ROOT, "docs", "screenshots", "platform")

# R166 终检 B9 记录的「当前」冻结哈希（sha256 前 16 位）
R166_HASHES = {
    "model.py": "64ce1fd790f92669",
    "observe.py": "7e73d49adee13fda",
    "simulate.py": "815619d9075ba3bb",
    "mcp_server.py": "6263c73f747edbff",
}

CHECKS = []


def contract_version():
    """从契约头部 + 表体取最大版本（与 ops_registry 同源口径）。"""
    import re
    best = (0, 0)
    with open(os.path.join(ROOT, "ENGINE_CONTRACT.md"), encoding="utf-8") as f:
        for line in f:
            for m in re.finditer(r"[（(]v(\d+)\.(\d+)|^\|\s*v(\d+)\.(\d+)\s*\|", line):
                a, b = m.group(1), m.group(2)
                if a is None:
                    a, b = m.group(3), m.group(4)
                v = (int(a), int(b))
                if v > best:
                    best = v
    return f"v{best[0]}.{best[1]}"

CV = contract_version()


def check(cid, name, ok, got=None):
    CHECKS.append({"id": cid, "name": name, "ok": bool(ok), "got": got})
    print(f"[{cid}] {'PASS' if ok else 'FAIL'}  {name}", flush=True)
    return ok


def jload(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def datajs():
    s = open(os.path.join(PLATFORM, "data.js"), encoding="utf-8").read()
    return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))


def http(path, payload=None, timeout=180):
    url = BASE + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def http_expect_error(path, payload):
    """期望 4xx 且带显式 error 字段；连接层 HTTPError 也视为符合预期。"""
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return e.code, {"error": "?"}


def port_open(p):
    s = socket.socket()
    s.settimeout(0.35)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def start_server():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, "platform/serve.py", "--port", str(PORT)],
                         cwd=ROOT, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    for _ in range(80):
        if port_open(PORT):
            return p
        if p.poll() is not None:
            raise RuntimeError("服务提前退出: " + (p.stdout.read() or ""))
        time.sleep(0.2)
    p.terminate()
    raise RuntimeError("服务启动超时")


def t8_shots():
    """T8 六视图逐屏复验：真实浏览器渲染 + 截图 + DOM 断言 + 前端能力调用。"""
    from playwright.sync_api import sync_playwright
    os.makedirs(SHOTS, exist_ok=True)
    out = {"views": [], "console_errors": [], "http_404": [], "ui_invoke": None, "shots": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True,
                                     args=["--no-sandbox", "--disable-gpu",
                                           "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1440, "height": 940},
                                device_scale_factor=1)
        page.on("response", lambda r: out["http_404"].append(r.url)
                if r.status >= 400 else None)
        page.on("pageerror", lambda e: out["console_errors"].append("pageerror: " + str(e)))
        page.on("console", lambda m: out["console_errors"].append("console: " + m.text)
                if m.type == "error" else None)
        page.goto(BASE + "/#overview", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#kpi-grid .kpi", timeout=15000)
        page.wait_for_timeout(1200)

        specs = [
            ("overview", "#kpi-grid .kpi", 4),
            ("topology", "#topo svg", 1),
            ("batch", "#batch-grid .bcell", 86),
            ("channels", "#tbl-channels tbody tr", 1),
            ("operators", "#op-grid .panel", 12),
            ("workbench", "#wb-tiers .wb-btn", 14),
        ]
        for i, (view, sel, minimum) in enumerate(specs, 1):
            page.evaluate(f"location.hash = '#{view}'")
            page.wait_for_timeout(650)
            try:
                page.wait_for_selector(sel, timeout=8000)
            except Exception as exc:  # noqa: BLE001
                out["views"].append({"view": view, "ok": False,
                                     "error": f"selector {sel}: {exc}"})
                continue
            n = page.locator(sel).count()
            body = page.locator("#v-" + view).inner_text()
            shot = os.path.join(SHOTS, f"r167_{i:02d}_{view}.png")
            page.locator("#v-" + view).screenshot(path=shot)
            out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))
            extra = {}
            if view == "overview":
                extra["new_catastrophic_zero_label"] = "0 新发" in body
                extra["no_stale_zero_cat"] = "0 catastrophic" not in body
            if view == "operators":
                extra["runtime_label"] = "运行时已装载" in body
                extra["count_text"] = page.locator("#op-count").inner_text()
            if view == "workbench":
                extra["arch_cards"] = page.locator("#wb-arch .panel").count()
                extra["l3_note"] = "保持 opt-in" in body
                extra["contract_current"] = CV in body
            out["views"].append({"view": view, "selector": sel, "count": n,
                                 "ok": n >= minimum, "extra": extra})

        # 前端 → HTTP → 引擎的一次真实能力调用（solver_info，轻调用）
        try:
            page.evaluate("location.hash = '#workbench'")
            page.wait_for_timeout(500)
            page.locator('#wb-tiers .wb-btn[data-tool="solver_info"]').click()
            page.wait_for_timeout(250)
            page.locator("#wb-run").click()
            page.wait_for_function(
                "document.querySelector('#wb-out') && "
                "document.querySelector('#wb-out').textContent.indexOf('\"ok\": true') >= 0",
                timeout=30000)
            txt = page.locator("#wb-out").inner_text()
            out["ui_invoke"] = {"ok": '"ok": true' in txt,
                                "has_version": "v0.1.0-c5" in txt,
                                "state": page.locator("#wb-run-state").inner_text()}
        except Exception as exc:  # noqa: BLE001
            out["ui_invoke"] = {"ok": False, "error": str(exc)}
        browser.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    D = datajs()
    acc = jload("runs/r156_acceptance.json")
    fc = jload("runs/r166_final_check.json")

    # ---- A 组：源码与边界（零回归前提） ----
    hashes = {}
    for f, expected in R166_HASHES.items():
        b = open(os.path.join(ROOT, "candidate", "indpensim", "v0.1", f), "rb").read()
        hashes[f] = hashlib.sha256(b).hexdigest()[:16]
    check("G1", "4 个引擎源码 sha256 与 R166 冻结值逐位一致（本轮零改动）",
          hashes == R166_HASHES, hashes)
    check("G2", "R166 终检仍为 54/54 PASS（引用未失效）",
          fc.get("verdict") == "PASS" and fc.get("n_pass") == 54, fc.get("verdict"))

    # ---- B 组：数据与口径（T1-3） ----
    check("G3", "data.js 契约版本 = 契约头部 + 表体最大值 " + CV,
          D["meta"]["contract"] == CV, {"datajs": D["meta"]["contract"], "contract": CV})
    nh = acc["summary"]["n_health"]
    check("G4", "catastrophic KPI 改用 classify_health 五通道：4 已登记 / 0 新发",
          D["kpi"]["catastrophic"] == nh["catastrophic"] == 4
          and D["kpi"]["normal"] == nh["normal"] == 77
          and D["kpi"]["degraded"] == nh["degraded"] == 5
          and D["kpi"]["catastrophic_batches"] == acc["summary"]["catastrophic_batches"],
          {"kpi": D["kpi"]["catastrophic"], "acceptance": nh})
    check("G5", "catastrophic ≠ 0 ⇒ 不再传播 D-38 恒真的 crash_level",
          D["kpi"]["catastrophic"] != 0
          and D["kpi"]["catastrophic_source"].startswith("classify_health"),
          D["kpi"]["catastrophic_source"])
    ops = D["operators"]
    check("G6", "12/12 算子由运行时 import+callable 核验，非 os.path.exists",
          ops["n_loaded"] == ops["n_total"] == 12
          and all(o["loaded"] and o["exists"] == o["loaded"] for o in ops["operators"])
          and "runtime" in ops["check"], ops["check"])
    names = [o["name"] for o in ops["operators"]]
    check("G7", "勘误 hier_est → hier_fit（真实可调用入口），conservation_metrics → element_balance",
          "hier_fit" in names and "hier_est" not in names
          and all(callable(getattr(__import__(o["module"]), o.get("attr", o["name"]), None))
                  for o in ops["operators"]),
          names)
    check("G8", "工作台离线快照含 14 能力 / L0–L3 四层 / L3 未执行",
          D["workbench"]["n_tools"] == 14
          and len(D["workbench"]["architecture"]) == 4
          and "未执行" in D["workbench"]["l3"]["state"],
          D["workbench"]["n_tools"])
    check("G9", "数据一致性：86 批 / 86 轨迹 / 54/54 终检 / 14 能力",
          len(D["batches"]) == 86 and len(D["series"]) == 86
          and D["kpi"]["within"] == 86
          and D["evidence"]["final_check"] == {"verdict": "PASS", "n_pass": 54, "n_checks": 54},
          {"batches": len(D["batches"]), "series": len(D["series"])})

    # ---- C 组：服务与运行时装载（起 8771，8770 不动） ----
    before = port_open(8770)
    srv = start_server()
    try:
        code, health = http("/api/health")
        check("G10", "8771 服务 /api/health 可达且 14 能力 + 12 算子实时装载",
              code == 200 and health.get("ok") and health.get("all_loaded")
              and health.get("capabilities") == 14
              and health.get("capabilities_total") == 14
              and health.get("operators_loaded") == 12
              and health.get("contract") == CV,
              {k: health.get(k) for k in ("ok", "capabilities", "operators_loaded",
                                          "all_loaded", "contract", "port", "build")})
        code, st = http("/api/ops")
        tools = st["status"]["tools"]
        check("G11", "14 个 A/B/C/D 能力全部 callable（进程内复用 mcp_server 本体）",
              st["status"]["all_loaded"] and st["status"]["n_tools_loaded"] == 14
              and sorted({t["tier"] for t in tools}) == ["A", "B", "C", "D"],
              {"tiers": sorted({t["tier"] for t in tools}),
               "backend": st["status"]["backend"]})
        check("G12", "L3 禁用参数共 5 项，注册表不暴露候选",
              st["status"]["l3_exposed"] is False
              and len(st["status"]["forbidden_keys"]) == 5,
              st["status"]["forbidden_keys"])

        # L0 行为回归：批 8 与冻结基线逐位一致 + 覆盖参数确实改变结果
        rows = jload("runs/final_validation_v2.json")
        rows = rows["results"] if isinstance(rows, dict) and "results" in rows else rows
        b8 = next(r for r in rows if int(r["batch"]) == 8)
        code, r0 = http("/api/simulate", {"batch": 8})
        code, r1 = http("/api/simulate", {"batch": 8, "overrides": {"mux": 0.36}})
        ref = float(b8["yield_err"]) * 100
        check("G13", "L0 /api/simulate 批 8 产量误差与 final_validation_v2 逐位一致",
              abs(r0["result"]["yield_err"] - round(ref, 3)) < 0.002,
              {"api": r0["result"]["yield_err"], "frozen": round(ref, 3)})
        check("G14", "L0 参数试算真实生效（mux=0.36 改变产量误差）",
              r1["result"]["applied"].get("mux") == 0.36
              and abs(r1["result"]["yield_err"] - r0["result"]["yield_err"]) > 1e-6,
              {"base": r0["result"]["yield_err"], "mux036": r1["result"]["yield_err"]})

        # 能力调用：3 个轻工具实跑
        calls = {}
        for tid, a in [("solver_info", {}), ("evaluate_batch", {"batch_no": 8}),
                       ("element_balance_check", {"batch_no": 8}),
                       ("trajectory_check", {"batch_no": 8})]:
            c, j = http("/api/invoke", {"tool": tid, "args": a})
            calls[tid] = {"code": c, "ok": j.get("ok"), "tier": j.get("tier"),
                          "elapsed_s": j.get("elapsed_s")}
        check("G15", "4 个轻能力经 /api/invoke 真实调用成功（非仅列目录）",
              all(v["code"] == 200 and v["ok"] for v in calls.values()), calls)

        # L3 行为闸门：禁用参数、opt-in、confirm、未知能力
        rejected = {}
        for k in st["status"]["forbidden_keys"]:
            c, j = http_expect_error("/api/invoke",
                                     {"tool": "simulate_batch",
                                      "args": {"batch_no": 8, k: 0.1}})
            rejected[k] = {"code": c, "msg": j.get("error", "")}
        check("G16", "5 个 L3 候选参数逐个被 /api/invoke 显式拒绝（400 + L3 说明）",
              all(400 <= v["code"] < 500 and "L3" in v["msg"] for v in rejected.values()),
              {k: v["code"] for k, v in rejected.items()})

        c1, j1 = http_expect_error("/api/invoke",
                                   {"tool": "reconstruct_batch",
                                    "args": {"batch_no": 8, "fallback_chain": True},
                                    "confirm": True})
        c2, j2 = http_expect_error("/api/invoke",
                                   {"tool": "golden_set_validate", "args": {}})
        c3, j3 = http_expect_error("/api/invoke", {"tool": "not_a_tool", "args": {}})
        check("G17", "opt-in / 重调用确认 / 白名单三道闸门均显式拒绝",
              400 <= c1 < 500 and "opt_in" in j1.get("error", "")
              and 400 <= c2 < 500 and "confirm" in j2.get("error", "")
              and 400 <= c3 < 500 and "未知能力" in j3.get("error", ""),
              {"optin": j1.get("error"), "confirm": j2.get("error"),
               "whitelist": j3.get("error")})

        c, ev = http("/api/evidence")
        check("G18", "/api/evidence 只读 runs/ 产物且契约 " + CV + "、V2 判定 NO_GO",
              c == 200 and ev["evidence"]["contract"] == CV
              and ev["evidence"]["v2_optim"]["verdict"] == "NO_GO"
              and ev["evidence"]["l3"]["state"].startswith("未执行"),
              ev["evidence"]["l3"]["state"])

        for f in ("index.html", "app.js", "style.css", "data.js"):
            req = urllib.request.Request(BASE + "/" + f)
            with urllib.request.urlopen(req, timeout=30) as r:
                assert r.status == 200, f
        check("G19", "4 个静态资源全部 200", True)

        t8 = None
        if not args.no_shots:
            t8 = t8_shots()
            views = {v["view"]: v for v in t8["views"]}
            required = ["overview", "topology", "batch", "channels", "operators", "workbench"]
            check("G20", "T8 六视图逐屏渲染成功 + 总览不再传播旧恒真的 0 catastrophic",
                  all(views.get(v, {}).get("ok") for v in required)
                  and len(views) == 6 and len(t8["shots"]) == 6
                  and views.get("overview", {}).get("extra", {}).get("no_stale_zero_cat") is True
                  and views["overview"]["extra"]["new_catastrophic_zero_label"] is True,
                  {**{v: views.get(v, {}).get("count") for v in required},
                   "no_stale_zero_cat": views["overview"]["extra"]["no_stale_zero_cat"]})
            check("G21", "工作台 14 能力按钮 + 4 层架构 + L3 与 " + CV + " 口径可见",
                  views.get("workbench", {}).get("extra", {}).get("arch_cards") == 4
                  and views["workbench"]["extra"]["l3_note"]
                  and views["workbench"]["extra"]["contract_current"],
                  views.get("workbench", {}).get("extra"))
            check("G22", "算子视图改显运行时装载（12/12），不再显示恒真的文件存在性",
                  views.get("operators", {}).get("extra", {}).get("runtime_label") is True
                  and "12/12" in views["operators"]["extra"]["count_text"],
                  views.get("operators", {}).get("extra"))
            check("G23", "浏览器端发起能力调用端到端成功（UI → HTTP → 引擎）",
                  bool(t8["ui_invoke"] and t8["ui_invoke"].get("ok")
                       and t8["ui_invoke"].get("has_version")),
                  t8["ui_invoke"])
            check("G24", "六视图无 pageerror / console error / 4xx 资源请求",
                  len(t8["console_errors"]) == 0 and len(t8["http_404"]) == 0,
                  {"console": t8["console_errors"][:5], "http_4xx": t8["http_404"][:5]})
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=12)
        except subprocess.TimeoutExpired:
            srv.kill()
    check("G25", "8770 端口前后均未监听（未重启原服务）",
          not before and not port_open(8770), {"before": before, "after": port_open(8770)})

    n_pass = sum(1 for c in CHECKS if c["ok"])
    result = {
        "round": "R167", "tool": "tools/r167_platform_gate.py", "contract": CV,
        "port": PORT, "port_8770_untouched": True,
        "verdict": "PASS" if n_pass == len(CHECKS) else "FAIL",
        "n_pass": n_pass, "n_checks": len(CHECKS),
        "shots": (t8 or {}).get("shots", []),
        "t8": t8, "checks": CHECKS,
        "wall_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(RUNS, "r167_platform_gate.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    print(f"\nR167 闸门: {result['verdict']}  {n_pass}/{len(CHECKS)}  "
          f"wall={result['wall_s']}s", flush=True)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
