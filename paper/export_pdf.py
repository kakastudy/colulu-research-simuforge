# -*- coding: utf-8 -*-
"""Print the self-contained HTML manuscript to an A4 PDF via headless Chrome.

The interactive Canvas figure is frozen before printing; the PDF shows the
300 dpi static export of the same canvas as Fig. 12.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
_args = sys.argv[1:]
HTML = Path(_args[0]).resolve() if _args else ROOT / "paper" / "manuscript.html"
OUT = (Path(_args[1]).resolve() if len(_args) > 1
       else ROOT / "paper" / "manuscript.pdf")
RUNTITLE = _args[2] if len(_args) > 2 else "Falsifiable bioprocess digital twins"
TAGLINE = _args[3] if len(_args) > 3 else "Evidence-gated framework &middot; in silico"

HEADER = ("<div style=\"width:100%;font-size:7pt;color:#7F8C8D;"
          "font-family:Arial,sans-serif;padding:0 15mm;display:flex;"
          "justify-content:space-between;border-bottom:0.4pt solid #D5DFE8;"
          "padding-bottom:3px\">"
          "<span>" + RUNTITLE + "</span>"
          "<span>" + TAGLINE + "</span>"
          "</div>")
FOOTER = ("<div style=\"width:100%;font-size:7pt;color:#7F8C8D;"
          "font-family:Arial,sans-serif;padding:0 15mm;display:flex;"
          "justify-content:space-between\">"
          "<span>Manuscript &mdash; Markdown / HTML / PDF</span>"
          "<span>Page <span class=\"pageNumber\"></span> of "
          "<span class=\"totalPages\"></span></span></div>")


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--no-sandbox", "--disable-gpu",
                                          "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1200, "height": 1600},
                                  device_scale_factor=1)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
        page.on("console", lambda m: errors.append("console: %s" % m.text)
                if m.type == "error" else None)
        page.goto(HTML.as_uri(), wait_until="load", timeout=120000)
        page.wait_for_function("window.__pfdReady === true", timeout=60000)
        page.evaluate("window.__pfdApi && window.__pfdApi.toggleAnimation(false)")
        page.emulate_media(media="print")
        # allow layout / font / base64 images to settle
        page.wait_for_timeout(700)
        page.pdf(path=str(OUT), format="A4", print_background=True,
                 display_header_footer=True,
                 header_template=HEADER, footer_template=FOOTER,
                 prefer_css_page_size=True)
        dom = page.evaluate("""() => ({
          figures: document.querySelectorAll('figure').length,
          tables: document.querySelectorAll('table').length,
          canvases: document.querySelectorAll('canvas').length,
          mathImgs: document.querySelectorAll('img.eq-inline, img.eq-block-img').length,
          fallbacks: document.querySelectorAll('.eq-fallback').length,
          h2: document.querySelectorAll('h2').length,
          liveHidden: getComputedStyle(document.getElementById('live-pfd')).display
        })""")
        browser.close()

    data = OUT.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page(?![sA-Za-z])", data))
    # Figure count is derived from the source HTML so the exporter works for
    # any manuscript version rather than a hard-coded figure inventory.
    expected_figures = HTML.read_text(encoding="utf-8", errors="ignore").count("<figure")
    print("WROTE", OUT, len(data), "bytes")
    print("DOM", dom)
    print("PDF_PAGES", pages)
    print("EXPECTED_FIGURES", expected_figures)
    print("ERRORS", errors[:6])
    if (errors or pages < 12 or dom["figures"] != expected_figures
            or dom["fallbacks"] != 0):
        raise SystemExit("PDF export check failed")
    print("PDF_EXPORT_OK")


if __name__ == "__main__":
    main()
