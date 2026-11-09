# -*- coding: utf-8 -*-
"""补一张浅色主题的参数扫描截图（只截结果区，避开左侧含内部编号的说明面板）。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "docs", "blog", "assets")
PORT = 8772
BASE = f"http://127.0.0.1:{PORT}"


def wait_service(timeout=45.0):
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
    proc = None
    if not wait_service(2.0):
        log = os.path.join(ROOT, "runs", "blog_screen_service.log")
        proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(ROOT, "platform_v2", "serve_v2.py"), "--port", str(PORT)],
            cwd=ROOT, stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
        if not wait_service(45.0):
            print("服务启动失败")
            if proc:
                proc.terminate()
            return 2

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            ctx = browser.new_context(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
            ctx.add_init_script("localStorage.setItem('ferm-theme-v2','light')")
            page = ctx.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(1000)
            if page.evaluate("document.documentElement.getAttribute('data-theme')") != "light":
                page.click("#btn-theme")
                page.wait_for_timeout(500)

            page.evaluate("location.hash = '#scan'")
            page.wait_for_timeout(800)
            page.select_option("#scan-batch", "11")
            page.wait_for_timeout(300)

            selects = page.locator("#scan-axes select")
            selects.nth(0).select_option(index=0)
            page.wait_for_timeout(300)
            # 添加第二根轴
            page.click("#btn-add-axis")
            page.wait_for_timeout(500)
            selects = page.locator("#scan-axes select")
            if selects.count() > 1:
                selects.nth(1).select_option(index=1)
                page.wait_for_timeout(400)

            nums = page.locator("#scan-axes input[type=number]")
            vals = ["0.34", "0.46", "2", "0.036", "0.052", "2"]
            for i, v in enumerate(vals):
                if i < nums.count():
                    nums.nth(i).fill(v)
                    nums.nth(i).dispatch_event("change")
                    page.wait_for_timeout(150)

            page.click("#btn-scan")
            t0 = time.time()
            state = ""
            while time.time() - t0 < 420:
                page.wait_for_timeout(3000)
                state = page.locator("#scan-state").inner_text()
                if "完成" in state or "失败" in state:
                    break
            print("scan state:", state)
            page.wait_for_timeout(1800)

            # 只截右侧：进度 + 响应面 + 完整逐点明细
            box = page.evaluate("""(() => {
                const chart = document.querySelector('#scan-chart');
                const table = document.querySelector('#scan-table');
                if (!chart || !table) return null;
                const c = chart.getBoundingClientRect();
                const t = table.getBoundingClientRect();
                const x = Math.max(0, c.x - 24);
                const bottom = t.y + t.height + 26;
                return {x: x, y: 56, w: window.innerWidth - x - 6, h: Math.max(420, bottom - 56)};
            })()""")
            if not box:
                box = {"x": 400, "y": 56, "w": 1190, "h": 780}
            print("clip:", box)
            clip = {"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]}
            page.screenshot(path=os.path.join(OUT, "shot_scan.png"), clip=clip, full_page=True)
            print("ok shot_scan", box)
            browser.close()
    finally:
        if proc:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
