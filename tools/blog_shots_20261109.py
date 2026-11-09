# -*- coding: utf-8 -*-
"""公开博客用的平台截图：最新 platform_v2 + 浅色主题 + 正常批次。

与 r168 闸门脚本的区别：
  1. 不覆盖任何参数（闸门脚本为验证"覆盖能进请求"改了 mup，会把批 8 推到双稳态边界）；
  2. 选批 11（黄金集中唯一无争议的正常批），跑一次干净仿真；
  3. 强制浅色主题，与博客的浅色插图统一。

输出 docs/blog/assets/shot_*.png。
"""
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
    os.makedirs(OUT, exist_ok=True)
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
            ctx = browser.new_context(viewport={"width": 1560, "height": 1020}, device_scale_factor=2)
            ctx.add_init_script("localStorage.setItem('ferm-theme-v2','light')")
            page = ctx.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(1200)

            # 主题兜底
            if page.evaluate("document.documentElement.getAttribute('data-theme')") != "light":
                page.click("#btn-theme")
                page.wait_for_timeout(600)

            # 批 11 + 清空所有覆盖
            page.select_option("#sel-batch", "11")
            page.wait_for_timeout(500)
            page.click("#btn-clear")
            page.wait_for_timeout(500)

            # 视图 1：仿真台（配置态）
            page.evaluate("location.hash = '#bench'")
            page.wait_for_timeout(900)
            page.locator("#v-bench").screenshot(path=os.path.join(OUT, "shot_bench.png"))
            print("ok shot_bench")

            # 真实跑一次
            page.click("#btn-run")
            t0 = time.time()
            state = ""
            while time.time() - t0 < 240:
                page.wait_for_timeout(2000)
                state = page.locator("#bench-state").inner_text()
                if "完成" in state or "失败" in state:
                    break
            print("state:", state)
            page.wait_for_timeout(1200)
            page.locator("#bench-result").screenshot(path=os.path.join(OUT, "shot_run.png"))
            print("ok shot_run")

            # 视图 2：叠加实测
            page.locator('#seg-mode button[data-m="both"]').click()
            page.wait_for_timeout(2000)
            page.locator("#v-bench").screenshot(path=os.path.join(OUT, "shot_overlay.png"))
            print("ok shot_overlay")

            # 视图 3：算子
            page.evaluate("location.hash = '#operators'")
            page.wait_for_timeout(900)
            page.locator("#v-operators").screenshot(path=os.path.join(OUT, "shot_ops.png"))
            print("ok shot_ops")

            # 视图 4：引擎状态
            page.evaluate("location.hash = '#engine'")
            page.wait_for_timeout(900)
            page.locator("#v-engine").screenshot(path=os.path.join(OUT, "shot_engine.png"))
            print("ok shot_engine")

            browser.close()
    finally:
        if proc:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
