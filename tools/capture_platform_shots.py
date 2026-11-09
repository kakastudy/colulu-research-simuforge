"""用 Playwright + 系统 Chrome 抓取仿真平台各视图截图（用于信息图）。"""
import os, time
from playwright.sync_api import sync_playwright

OUT = r"C:\Users\liuli\Desktop\AI4S\青霉素反应罐\docs\screenshots"
os.makedirs(OUT, exist_ok=True)
URL = "http://127.0.0.1:8770/"
LAUNCH_ARGS = ["--no-sandbox","--disable-gpu","--disable-dev-shm-usage","--disable-setuid-sandbox"]

def log(*a): print("[cap]", *a, flush=True)

def shot_view(page, name, view_id):
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(250)
    path = os.path.join(OUT, name)
    page.locator("#v-" + view_id).screenshot(path=path)
    log("saved", name, os.path.getsize(path), "bytes")

def shot_shell(page, name):
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(250)
    path = os.path.join(OUT, name)
    page.screenshot(path=path)   # 视口级：平台外壳（顶栏+左轨+主区首屏）
    log("saved", name, os.path.getsize(path), "bytes")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=LAUNCH_ARGS)
    page = b.new_page(viewport={"width": 1380, "height": 920}, device_scale_factor=1.5)
    page.goto(URL, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1800)
    page.wait_for_selector("#kpi-grid .kpi", timeout=10000)
    log("overview rendered")

    shot_shell(page, "00_shell.png")
    shot_view(page, "01_overview.png", "overview")

    page.click('[data-view="topology"]'); page.wait_for_selector("#topo svg", timeout=10000)
    shot_view(page, "02_topology.png", "topology")

    page.click('[data-view="batch"]'); page.wait_for_selector("#batch-grid .bcell", timeout=10000)
    page.wait_for_timeout(900)
    shot_view(page, "03_batch_grid.png", "batch")

    page.click('#batch-grid .bcell[data-b="8"]')
    page.wait_for_selector("#chart-series svg", timeout=10000); page.wait_for_timeout(1300)
    shot_view(page, "04_batch_trajectory.png", "batch")

    try:
        page.wait_for_selector("#trial-run", timeout=6000)
        page.click("#trial-run")
        page.wait_for_selector("#trial-chart svg", timeout=15000); page.wait_for_timeout(900)
        shot_view(page, "05_batch_trial.png", "batch")
    except Exception as e:
        log("trial skip", e)

    page.click('[data-view="channels"]')
    page.wait_for_selector("#tbl-channels tr", timeout=10000)
    page.wait_for_selector("#chart-dist svg", timeout=10000)
    shot_view(page, "06_channels.png", "channels")

    page.click('[data-view="operators"]')
    page.wait_for_selector("#op-grid .op-card", timeout=10000)
    shot_view(page, "07_operators.png", "operators")

    b.close()
log("DONE")
