# -*- coding: utf-8 -*-
"""R168 · 平台 v2 浏览器逐屏复验（T8 同型）。

沿用 R167 的 T8 做法：真实 Chromium 渲染 → 逐屏截图 → DOM 断言 →
**前端发起一次真实仿真**（验证 UI → HTTP → 引擎 全链路）。

与 R167 的差别：R167 验的是"看板数字对不对"，本轮验的是
"**界面能不能真的驱动引擎算**"——包括参数面板改值、运行、轨迹渲染。

用法
----
    python tools/r168_platform_v2_screen.py
    python tools/r168_platform_v2_screen.py --keep   # 不自动停服务
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SHOTS = os.path.join(ROOT, "docs", "screenshots", "platform_v2")
PORT = 8772
BASE = f"http://127.0.0.1:{PORT}"


def wait_service(timeout=40.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(BASE + "/api2/health", timeout=4) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    os.makedirs(SHOTS, exist_ok=True)
    proc = None
    if not wait_service(2.0):
        log = os.path.join(ROOT, "runs", "r168_screen_service.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(ROOT, "platform_v2", "serve_v2.py"),
             "--port", str(PORT)],
            cwd=ROOT, stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        if not wait_service(40.0):
            print("服务启动失败")
            if proc:
                proc.terminate()
            return 2

    out = {"views": [], "console_errors": [], "http_4xx": [], "run": None,
           "shots": [], "base": BASE}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright 未安装")
        if proc:
            proc.terminate()
        return 2

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True,
                                     args=["--no-sandbox", "--disable-gpu",
                                           "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1500, "height": 1000},
                                device_scale_factor=1)
        page.on("response", lambda r: out["http_4xx"].append(f"{r.status} {r.url}")
                if r.status >= 400 else None)
        page.on("pageerror", lambda e: out["console_errors"].append("pageerror: " + str(e)))
        page.on("console", lambda m: out["console_errors"].append("console: " + m.text)
                if m.type == "error" else None)

        page.goto(BASE + "/#bench", wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("#param-groups .grp", timeout=20000)
        except Exception as exc:  # noqa: BLE001
            out["fatal"] = f"参数面板未渲染：{exc}"
            browser.close()
            if proc and not args.keep:
                proc.terminate()
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 2

        specs = [
            ("bench", "#param-groups .grp", 9, "参数分组"),
            ("scan", "#scan-axes select", 1, "扫描轴"),
            ("presets", "#preset-grid .panel", 4, "工况库分组"),
            ("operators", "#op-layers .panel", 4, "算子分层"),
            ("engine", "#eng-kpi .kpi", 4, "引擎状态卡"),
        ]
        for i, (view, sel, minimum, label) in enumerate(specs, 1):
            page.evaluate(f"location.hash = '#{view}'")
            page.wait_for_timeout(900)
            try:
                page.wait_for_selector(sel, timeout=10000)
            except Exception as exc:  # noqa: BLE001
                out["views"].append({"view": view, "ok": False,
                                     "error": f"selector {sel}: {exc}"})
                continue
            n = page.locator(sel).count()
            shot = os.path.join(SHOTS, f"r168_{i:02d}_{view}.png")
            page.locator("#v-" + view).screenshot(path=shot)
            out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))
            out["views"].append({"view": view, "ok": n >= minimum, "n": n,
                                 "min": minimum, "label": label})

        # ---- 关键：前端真实发起一次仿真 ----
        page.evaluate("location.hash = '#bench'")
        page.wait_for_timeout(600)
        # 改一个参数（µp），验证覆盖能进入请求
        num_inp = page.locator('[data-ctl="num"][data-p="mup"]')
        if num_inp.count():
            num_inp.first.fill("0.05")
            num_inp.first.dispatch_event("input")
            page.wait_for_timeout(400)
        ov_count = page.locator("#ov-count").inner_text()

        page.click("#btn-run")
        # 进度条：提交成功后应出现「时间条」（缓存秒完成时可能一闪而过，不强判）
        prog_seen = False
        prog_txt = ""
        for _ in range(6):
            page.wait_for_timeout(400)
            prog_seen = page.evaluate("!document.querySelector('#bench-prog').hidden")
            if prog_seen:
                prog_txt = page.locator("#bench-prog-txt").inner_text()
                break
        # 等作业完成（最长 200s）
        t0 = time.time()
        state_txt = ""
        while time.time() - t0 < 220:
            page.wait_for_timeout(2500)
            state_txt = page.locator("#bench-state").inner_text()
            if "完成" in state_txt or "失败" in state_txt:
                break
        body = page.locator("#bench-result").inner_text()
        shot = os.path.join(SHOTS, "r168_06_bench_run.png")
        page.locator("#bench-result").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))
        out["run"] = {
            "override_count": ov_count,
            "state_text": state_txt,
            "progress_bar_seen": prog_seen,
            "progress_text": prog_txt,
            "has_kpi": page.locator("#bench-result .kpi").count() >= 4,
            # 轨迹改为「每通道一张卡片」⇒ 卡片数 = 已选通道数
            "n_cards": page.locator("#chart-trace .tcard").count(),
            "n_card_svgs": page.locator("#chart-trace .tcard svg").count(),
            "n_card_paths": page.locator("#chart-trace .tcard svg path").count(),
            "has_shape": "形状指标" in body,
            "has_guard": "守恒与守卫审计" in body,
            "has_traj_tab": "轨迹级指标" in body,
            "n_tabs": page.locator("#diag-tabs button").count(),
        }
        out["run"]["ok"] = (out["run"]["has_kpi"]
                            and out["run"]["n_cards"] >= 1
                            and out["run"]["n_card_svgs"] >= 1
                            and out["run"]["n_card_paths"] >= 1
                            and out["run"]["n_tabs"] == 4
                            and (prog_seen or "完成" in state_txt)
                            and "完成" in state_txt)

        # ---- 通道选项面板折叠（R168.2：默认收起，头部保留计数）----
        picker_default_hidden = page.evaluate(
            "document.querySelector('#trace-picker').hidden")
        page.click("#trace-toggle")
        page.wait_for_timeout(300)
        picker_open = page.evaluate(
            "!document.querySelector('#trace-picker').hidden")
        toggle_txt = page.locator("#trace-toggle").inner_text()
        out["picker"] = {"default_hidden": bool(picker_default_hidden),
                         "open_after_toggle": bool(picker_open),
                         "toggle_text": toggle_txt}
        out["picker"]["ok"] = bool(picker_default_hidden) and picker_open

        # ---- 通道全选 / 取消全选 ----
        n_all = page.evaluate("Object.keys(window.__v2cols||{}).length")
        page.click("#ch-all")
        page.wait_for_timeout(900)
        n_sel = page.locator("#chart-trace .tcard").count()
        page.click("#ch-none")
        page.wait_for_timeout(600)
        n_none = page.locator("#chart-trace .tcard").count()
        page.click("#ch-inv")
        page.wait_for_timeout(700)
        n_inv = page.locator("#chart-trace .tcard").count()
        out["select_all"] = {"after_all": n_sel, "after_none": n_none, "after_inv": n_inv,
                              "ok": n_none == 0 and n_sel >= n_inv and n_inv > 0}
        # 恢复 3 个通道：R168.1 起分组默认折叠 ⇒ chip 不在 DOM，必须先展开分组。
        # 不展开的话这里会静默地一个都没点到，后面所有"轨迹卡片数"断言都会失真。
        page.click("#ch-none")
        page.wait_for_timeout(300)
        for k in ("state", "gas", "myc", "kin", "diag", "op"):
            h = page.locator(f'[data-grp-toggle="{k}"]')
            if h.count():
                h.first.click()
                page.wait_for_timeout(90)
        for c in ("P", "X", "S"):
            el = page.locator(f'#trace-picker .chip[data-ch="{c}"]')
            if el.count():
                el.first.click()
                page.wait_for_timeout(120)
        page.wait_for_timeout(700)
        out["select_all"]["restored"] = page.locator("#chart-trace .tcard").count()
        out["select_all"]["ok"] = out["select_all"]["ok"] and out["select_all"]["restored"] >= 1
        # 收起选项面板（折叠闭环）
        page.click("#trace-toggle")
        page.wait_for_timeout(250)
        out["picker"]["closed_again"] = page.evaluate(
            "document.querySelector('#trace-picker').hidden")
        out["picker"]["ok"] = out["picker"]["ok"] and bool(out["picker"]["closed_again"])

        # ---- 诊断 Tab 切换 ----
        tab_ok = {}
        for t in ("balance", "applied", "traj", "shape"):
            page.click(f'#diag-tabs button[data-tab="{t}"]')
            page.wait_for_timeout(280)
            vis = page.evaluate(f"""(() => {{
                const p = document.querySelector('#pane-{t}');
                if (!p) return false;
                return !p.hidden && p.getBoundingClientRect().height > 10;
            }})()""")
            rows = page.evaluate(f"document.querySelector('#pane-{t}').querySelectorAll('.kv .r').length")
            tab_ok[t] = bool(vis) and rows > 0
        out["tabs"] = {"detail": tab_ok, "ok": all(tab_ok.values())}
        shot = os.path.join(SHOTS, "r168_08_bench_tabs.png")
        page.locator("#bench-result").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))

        # ---- 叠加实测模式 ----
        page.locator('#seg-mode button[data-m="both"]').click()
        page.wait_for_timeout(1500)
        shot = os.path.join(SHOTS, "r168_07_bench_overlay.png")
        page.locator("#v-bench").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))
        out["overlay_paths"] = page.locator("#chart-trace .tcard svg path").count()

        # ================================================================
        # 二维扫描 —— R168 抓到的真 bug：
        #   轴坐标误取 p.y[ya.key]（p.y 是响应标量）⇒ findIndex 恒 -1
        #   ⇒ 9 个点全被跳过 ⇒ 响应曲面**一个格子都没画**，界面表现为「空的」。
        #   断言必须检查「数据标记数」，不能只查 svg 存在。
        # ================================================================
        page.evaluate("location.hash = '#scan'")
        page.wait_for_timeout(900)
        page.click("#btn-add-axis")
        page.wait_for_timeout(400)
        page.fill("[data-axis-from='0']", "0.38"); page.dispatch_event("[data-axis-from='0']", "change")
        page.fill("[data-axis-to='0']", "0.46");   page.dispatch_event("[data-axis-to='0']", "change")
        page.fill("[data-axis-n='0']", "2");       page.dispatch_event("[data-axis-n='0']", "change")
        page.select_option("[data-axis-key='1']", "mup"); page.wait_for_timeout(400)
        page.fill("[data-axis-from='1']", "0.038"); page.dispatch_event("[data-axis-from='1']", "change")
        page.fill("[data-axis-to='1']", "0.044");   page.dispatch_event("[data-axis-to='1']", "change")
        page.fill("[data-axis-n='1']", "2");        page.dispatch_event("[data-axis-n='1']", "change")
        page.click("#btn-scan")
        t0 = time.time()
        scan_state = ""
        while time.time() - t0 < 400:
            page.wait_for_timeout(3000)
            scan_state = page.locator("#scan-state").inner_text().strip()
            if scan_state in ("完成", "失败"):
                break
        n_cells = page.locator("#scan-chart rect.heat-cell").count()
        n_labels = page.locator("#scan-chart text").count()
        scan_rows = page.locator("#scan-table tbody tr").count()
        n_best = page.locator("#scan-chart rect[stroke='var(--ok)']").count()
        resp_desc = page.locator("#scan-resp-desc").inner_text().strip()
        has_explainer = page.locator("#v-scan").inner_text().find("扫描解决什么问题") >= 0
        out["scan2d"] = {
            "state": scan_state,
            "heat_cells": n_cells,
            "texts": n_labels,
            "table_rows": scan_rows,
            "best_highlight": n_best,
            "resp_desc_len": len(resp_desc),
            "has_explainer": has_explainer,
            "csv_btn": page.locator("#btn-scan-csv").count(),
            "summary": page.locator("#scan-summary").inner_text(),
        }
        out["scan2d"]["ok"] = (scan_state == "完成" and n_cells >= 4 and scan_rows >= 4
                               and n_best >= 1 and len(resp_desc) > 10
                               and has_explainer and out["scan2d"]["csv_btn"] == 1)
        shot = os.path.join(SHOTS, "r168_09_scan_2d.png")
        page.locator("#v-scan").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))

        # ---- 全失败扫描：必须显示失败原因清单，不能是空图 ----
        page.fill("[data-axis-from='0']", "2.0");  page.dispatch_event("[data-axis-from='0']", "change")
        page.fill("[data-axis-to='0']", "2.5");    page.dispatch_event("[data-axis-to='0']", "change")
        page.fill("[data-axis-n='0']", "2");       page.dispatch_event("[data-axis-n='0']", "change")
        page.click("#btn-scan")
        t0 = time.time()
        scan_state2 = ""
        while time.time() - t0 < 300:
            page.wait_for_timeout(3000)
            scan_state2 = page.locator("#scan-state").inner_text().strip()
            if scan_state2 in ("完成", "失败"):
                break
        n_failrows = page.locator("#scan-chart .failrow").count()
        has_empty = page.locator("#scan-chart .empty").count() >= 1
        out["scan_fail"] = {
            "state": scan_state2,
            "fail_rows": n_failrows,
            "has_empty_state": has_empty,
            "summary": page.locator("#scan-summary").inner_text(),
        }
        out["scan_fail"]["ok"] = (scan_state2 == "完成" and n_failrows >= 1 and has_empty)
        shot = os.path.join(SHOTS, "r168_10_scan_allfail.png")
        page.locator("#v-scan").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))

        # ================================================================
        # R168.3 运算历史 —— 用户诉求：历次结果留存（带执行时间）、回看不重算、
        # 且仍可重新执行。断言必须落在「是否真的提交了计算」上，不能只看面板在不在。
        # ================================================================
        page.evaluate("location.hash = '#bench'")
        page.wait_for_timeout(900)
        run_posts = []
        page.on("request", lambda q: run_posts.append(q.url)
                if q.method == "POST" and "/api2/run" in q.url else None)

        def hist_n():
            with urllib.request.urlopen(BASE + "/api2/history", timeout=8) as resp:
                return json.load(resp)["n"]

        n0 = hist_n()
        n_cards = page.locator("#hist-list .hcard").count()
        panel_txt = page.locator("#hist-panel").inner_text()
        has_exec_time = bool(re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", panel_txt))
        hist_fold_default = page.evaluate("!document.querySelector('#hist-body').hidden")
        page.click("#btn-hist-toggle")
        page.wait_for_timeout(250)
        hist_fold_closed = page.evaluate("document.querySelector('#hist-body').hidden")
        page.click("#btn-hist-toggle")
        page.wait_for_timeout(250)

        view_btn = page.locator("#hist-list .hcard [data-hview]").first
        if view_btn.count():
            view_btn.click()
            page.wait_for_timeout(1600)
        src_loc = page.locator("#bench-result .srcbar")
        src_txt = src_loc.inner_text() if src_loc.count() else ""
        replay_kpi = page.locator("#bench-result .kpi").count()
        replay_cards = page.locator("#chart-trace .tcard").count()
        zero_calc = len(run_posts) == 0          # 回放期间不能有任何计算提交
        shot = os.path.join(SHOTS, "r168_11_history_replay.png")
        page.locator("#v-bench").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))

        # 重新计算：抽稀 12× 缩短等待；force 必须真实提交一次运算并新增留痕
        page.select_option("#sel-stride", "12")
        page.click("#btn-rerun")
        t0 = time.time()
        rerun_state = ""
        while time.time() - t0 < 260:
            page.wait_for_timeout(2500)
            rerun_state = page.locator("#bench-state").inner_text()
            if "完成" in rerun_state or "失败" in rerun_state:
                break
        n1 = hist_n()
        new_card = page.locator("#hist-list .hcard").first
        new_txt = new_card.inner_text() if new_card.count() else ""
        src2_loc = page.locator("#bench-result .srcbar")
        src2_txt = src2_loc.inner_text() if src2_loc.count() else ""
        out["history"] = {
            "n_before": n0, "n_after_rerun": n1, "dom_cards": n_cards,
            "has_exec_time": has_exec_time,
            "fold_default_open": bool(hist_fold_default),
            "fold_closed_after_toggle": bool(hist_fold_closed),
            "replay_source": src_txt,
            "replay_kpi": replay_kpi, "replay_cards": replay_cards,
            "replay_run_posts": 0 if zero_calc else len(run_posts),
            "rerun_state": rerun_state, "rerun_run_posts": len(run_posts),
            "new_card": new_txt.replace("\n", " | ")[:180],
            "source_after_rerun": src2_txt,
        }
        out["history"]["ok"] = (
            n_cards >= 1 and has_exec_time
            and bool(hist_fold_default) and bool(hist_fold_closed)
            and zero_calc and "历史回放" in src_txt and "执行时间" in src_txt
            and replay_kpi >= 4 and replay_cards >= 1
            and "完成" in rerun_state and n1 == n0 + 1
            and "重算" in new_txt and "本次运算已留痕" in src2_txt
            and len(run_posts) == 1)
        shot = os.path.join(SHOTS, "r168_12_history_rerun.png")
        page.locator("#v-bench").screenshot(path=shot)
        out["shots"].append(os.path.relpath(shot, ROOT).replace("\\", "/"))

        browser.close()

    if proc and not args.keep:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()

    ev = os.path.join(ROOT, "runs", "r168_platform_v2_screen.json")
    with open(ev, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"=== R168 平台 v2 逐屏复验 ===")
    for v in out["views"]:
        print(f"  [{'PASS' if v.get('ok') else 'FAIL'}] {v['view']:9s} "
              f"{v.get('label','')}: {v.get('n')} (≥{v.get('min')})")
    r = out.get("run") or {}
    print(f"  [{'PASS' if r.get('ok') else 'FAIL'}] 仿真实跑   "
          f"state={r.get('state_text')} · 卡片 {r.get('n_cards')} · 曲线 {r.get('n_card_paths')} 条 · "
          f"时间条={'见' if r.get('progress_bar_seen') else '未见(可能缓存)'}")
    pk = out.get("picker") or {}
    print(f"  [{'PASS' if pk.get('ok') else 'FAIL'}] 选项折叠   "
          f"默认收起={pk.get('default_hidden')} 展开={pk.get('open_after_toggle')} 再收起={pk.get('closed_again')}")
    sa = out.get("select_all") or {}
    print(f"  [{'PASS' if sa.get('ok') else 'FAIL'}] 通道全选   "
          f"全选={sa.get('after_all')} 取消={sa.get('after_none')} 反选={sa.get('after_inv')} "
          f"恢复={sa.get('restored')}")
    tb = out.get("tabs") or {}
    print(f"  [{'PASS' if tb.get('ok') else 'FAIL'}] 诊断 Tab   {tb.get('detail')}")
    s2 = out.get("scan2d") or {}
    print(f"  [{'PASS' if s2.get('ok') else 'FAIL'}] 二维扫描   "
          f"格子={s2.get('heat_cells')} 明细={s2.get('table_rows')} 行 · 最优格={s2.get('best_highlight')} · "
          f"说明={s2.get('resp_desc_len')}字 · 解释面板={s2.get('has_explainer')} · CSV={s2.get('csv_btn')} · {s2.get('summary')}")
    sf = out.get("scan_fail") or {}
    print(f"  [{'PASS' if sf.get('ok') else 'FAIL'}] 全失败提示 失败行={sf.get('fail_rows')} "
          f"· {sf.get('summary')}")
    hs = out.get("history") or {}
    print(f"  [{'PASS' if hs.get('ok') else 'FAIL'}] 运算历史   "
          f"留痕 {hs.get('n_before')}→{hs.get('n_after_rerun')} · 回放计算提交={hs.get('replay_run_posts')} · "
          f"重算计算提交={hs.get('rerun_run_posts')} · 执行时间={hs.get('has_exec_time')} · "
          f"折叠={hs.get('fold_default_open')}/{hs.get('fold_closed_after_toggle')}")
    print(f"  console errors: {len(out['console_errors'])} · 4xx: {len(out['http_4xx'])}")
    for e in out["console_errors"][:5]:
        print(f"    ! {e[:160]}")
    for e in out["http_4xx"][:5]:
        print(f"    ! {e[:160]}")
    print(f"证据: {ev}")
    ok = (all(v.get("ok") for v in out["views"]) and r.get("ok")
          and sa.get("ok") and tb.get("ok") and s2.get("ok") and sf.get("ok")
          and pk.get("ok") and hs.get("ok")
          and not out["console_errors"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
