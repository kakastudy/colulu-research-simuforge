"""Render the Canvas 2D process flow diagram to a publication PNG.

Uses the installed Playwright Chromium at device scale factor 2, so a
1200 x 640 logical canvas is exported at >= 2400 px wide (300 dpi at A4 width).
"""
from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "paper" / "pfd.html"
OUT = ROOT / "paper" / "figures" / "fig12_pfd.png"


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--no-sandbox", "--disable-gpu",
                                          "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1500, "height": 950},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
        page.on("console", lambda m: errors.append("console: %s" % m.text)
                if m.type == "error" else None)
        page.goto(HTML.as_uri() + "?static=1", wait_until="load")
        page.wait_for_timeout(500)
        canvas = page.locator("#pfd")
        canvas.screenshot(path=str(OUT))
        # sanity: canvas is not blank
        nonempty = page.evaluate("""() => {
          const c = document.getElementById('pfd');
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          let n = 0;
          for (let i = 0; i < d.length; i += 4000) if (d[i] < 250) n++;
          return {w: c.width, h: c.height, darkSamples: n};
        }""")
        browser.close()
    print("WROTE", OUT, os.path.getsize(OUT), "bytes")
    print("CANVAS", nonempty)
    print("ERRORS", errors)
    if errors or nonempty["darkSamples"] < 50:
        raise SystemExit("PFD render check failed")
    print("PFD_EXPORT_OK")


if __name__ == "__main__":
    main()
