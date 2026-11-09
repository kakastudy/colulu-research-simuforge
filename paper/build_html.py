# -*- coding: utf-8 -*-
"""Build a self-contained, print-ready HTML manuscript from manuscript.md.

- All 19 figures are embedded as base64 PNG.
- Display and inline mathematics are rendered offline with matplotlib mathtext
  to inline SVG (no CDN / no JavaScript maths dependency).
- Figure 12 additionally ships a live, interactive Canvas 2D process flow
  diagram driven by paper/pfd.js (hidden in print, where the static export is used).
"""
from __future__ import annotations

import base64
import io
import os
import re
import sys

import markdown
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PAPER = os.path.join(ROOT, "paper")
_args = sys.argv[1:]
SRC = os.path.abspath(_args[0]) if _args else os.path.join(PAPER, "manuscript.md")
OUT = (os.path.abspath(_args[1]) if len(_args) > 1
       else os.path.join(PAPER, "manuscript.html"))
PFD_JS = os.path.join(PAPER, "pfd.js")

CSS = r"""
:root{
  --ink:#22303C; --blue:#1F4E79; --teal:#16807A; --red:#B03A2E;
  --grey:#6B7A88; --line:#D5DFE8; --soft:#F7FAFC; --band:#EAF2F9;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:#EDF1F5;color:var(--ink);
     font-family:Georgia,"Times New Roman",serif;font-size:10.6pt;line-height:1.58}
.sheet{max-width:212mm;margin:14px auto;background:#fff;padding:20mm 18mm;
       box-shadow:0 8px 34px rgba(31,78,121,.13);border-radius:3px}
h1{font-size:17.5pt;line-height:1.32;color:var(--blue);margin:0 0 14px;
   border-bottom:2px solid var(--blue);padding-bottom:10px;font-weight:700}
h2{font-size:13.4pt;color:var(--blue);margin:1.75em 0 .6em;
   border-bottom:1px solid var(--line);padding-bottom:5px;break-after:avoid}
h3{font-size:11.3pt;color:var(--teal);margin:1.35em 0 .45em;break-after:avoid}
p{margin:.62em 0;text-align:justify;hyphens:auto;orphans:3;widows:3}
strong{color:#16344F}
a{color:var(--blue)}
hr{border:0;border-top:1px solid var(--line);margin:2em 0}
code{font-family:Consolas,"Courier New",monospace;font-size:8.9pt;
     background:#F1F5F8;padding:.5px 3px;border-radius:3px;color:#8A3A2E}
pre{background:var(--soft);border:1px solid var(--line);border-left:3px solid var(--blue);
    border-radius:5px;padding:9px 12px;overflow-x:auto;break-inside:avoid}
pre code{background:none;padding:0;font-size:8.6pt;color:var(--ink)}
blockquote{background:var(--soft);border-left:3px solid var(--blue);
           margin:1.1em 0;padding:10px 16px;break-inside:avoid}
blockquote p{margin:.35em 0}
.reflist p{padding-left:1.55em;text-indent:-1.55em;margin:.34em 0;
           text-align:left;font-size:9pt;line-height:1.46}
.reflist b{color:var(--blue);font-weight:600}
ul,ol{margin:.55em 0 .8em 1.35em;padding:0}
li{margin:.28em 0;text-align:justify}
ol.refs{list-style:none;margin-left:0;counter-reset:refs}
ol.refs>li{position:relative;padding-left:2.15em;margin:.34em 0;text-align:left;
           font-size:9pt;line-height:1.46;break-inside:avoid}
ol.refs>li::before{counter-increment:refs;content:counter(refs) ".";
  position:absolute;left:.1em;top:0;font-weight:600;color:var(--blue);
  font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;margin:1em 0;font-size:8.35pt;
      line-height:1.42;break-inside:avoid}
th,td{border:1px solid #DCE5ED;padding:5px 7px;vertical-align:top;text-align:left}
th{background:var(--band);color:var(--blue);font-weight:700}
tr:nth-child(even) td{background:#FBFCFE}
figure{margin:1.35em 0;text-align:center;break-inside:avoid}
figure img{display:block;max-width:100%;height:auto;margin:0 auto;
           border:1px solid #E3EAF1;border-radius:3px}
figcaption{font-size:8.45pt;line-height:1.52;color:#405568;text-align:left;
           margin-top:8px;padding-left:2px}
figcaption strong{color:var(--blue)}
.eq-block{display:block;text-align:center;margin:1.05em 0;break-inside:avoid}
img.eq-block-img{height:2.05em;max-width:96%;border:0}
img.eq-inline{height:1.08em;vertical-align:-.16em;border:0;display:inline}
.eq-fallback{font-family:Consolas,monospace;background:#FFF4E5;color:#8A3A2E;
             padding:1px 4px;border-radius:3px;font-size:9pt}
.meta{font-size:9pt;color:var(--grey);margin:.25em 0}
.toc{background:var(--soft);border:1px solid var(--line);border-radius:7px;
     padding:12px 18px;margin:16px 0 24px;font-size:9pt;columns:2;column-gap:26px}
.toc a{display:block;break-inside:avoid;color:#34506B;text-decoration:none;padding:1px 0}
.toc a:hover{text-decoration:underline}
.toc b{color:var(--blue);display:block;column-span:all;margin-bottom:6px}
.pfd-live{margin:18px 0 6px;padding:14px;background:var(--soft);
          border:1px solid var(--line);border-radius:9px}
.pfd-live h3{margin:0 0 5px;color:var(--blue)}
.pfd-live p{font-size:9pt;margin:.3em 0;text-align:left}
.pfd-toolbar{display:flex;flex-wrap:wrap;gap:7px;margin:10px 0}
.pfd-toolbar button{border:1px solid var(--line);background:#fff;color:var(--blue);
  border-radius:6px;padding:5px 10px;font-size:9pt;cursor:pointer;
  font-family:"Segoe UI",sans-serif}
.pfd-toolbar button:hover{background:var(--band)}
.pfd-toolbar button.on{background:var(--blue);color:#fff}
.pfd-canvas-shell{position:relative;background:#fff;border:1px solid var(--line);
                  border-radius:7px;padding:5px}
#pfd-paper{display:block;width:100%;aspect-ratio:1200/640}
#pfd-tip{position:absolute;display:none;pointer-events:none;z-index:5;max-width:250px;
  background:var(--ink);color:#fff;padding:7px 9px;border-radius:6px;font-size:9pt;
  line-height:1.45;font-family:"Segoe UI",sans-serif}
.formats{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0}
.formats span{font-size:8.5pt;background:var(--band);color:var(--blue);
  border:1px solid #C9DCEB;border-radius:14px;padding:3px 10px;
  font-family:"Segoe UI",sans-serif}
@page{size:A4;margin:17mm 15mm}
@page pfdland{size:A4 landscape;margin:9mm}
@media print{
  body{background:#fff;font-size:9.6pt}
  .sheet{max-width:none;margin:0;padding:0;box-shadow:none;border-radius:0}
  .toc{margin-bottom:14px}
  .pfd-live{display:none}
  h2{break-after:avoid}
  h3{break-after:avoid}
  figure,table,pre,blockquote{break-inside:avoid}
  a{color:inherit;text-decoration:none}
  figure.pfd-fig{page:pfdland;break-before:page;break-after:page}
  figure.pfd-fig img{width:100%;max-width:none}
  figure.pfd-fig figcaption{font-size:8pt}
}
@media screen and (max-width:760px){
  .sheet{padding:16px;margin:0;border-radius:0}
  .toc{columns:1}
}
"""

MATH_CACHE: dict[tuple[str, bool], str] = {}


def math_html(expr: str, display: bool = False) -> str:
    expr = " ".join(expr.split())
    expr = expr.replace(r"\text{", r"\mathrm{").replace(r"\textit{", r"\mathrm{")
    expr = re.sub(r"\\le(?![A-Za-z])", r"\\leq", expr)
    expr = re.sub(r"\\ge(?![A-Za-z])", r"\\geq", expr)
    key = (expr, display)
    if key in MATH_CACHE:
        return MATH_CACHE[key]
    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, "$" + expr + "$", fontsize=13 if display else 11,
                 color="#22303C")
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.025,
                    transparent=True)
        plt.close(fig)
        svg = buf.getvalue()
        if len(svg) < 250:
            raise ValueError("empty svg")
        b64 = base64.b64encode(svg).decode("ascii")
        cls = "eq-block-img" if display else "eq-inline"
        out = '<img class="%s" src="data:image/svg+xml;base64,%s" alt="equation" />' % (cls, b64)
        if display:
            out = '<div class="eq-block">' + out + "</div>"
    except Exception as exc:  # honest degradation: show the source, never fake a value
        out = '<code class="eq-fallback">%s</code>' % expr.replace("<", "&lt;")
        print("MATH_FALLBACK", expr[:70], str(exc)[:80])
    MATH_CACHE[key] = out
    return out


def protect_math(text: str):
    """Replace display maths with sentinels; render inline maths in the rest."""
    store = []

    def disp(m):
        expr = m.group(1) if m.group(1) is not None else m.group(2)
        store.append(math_html(expr, True))
        return "@@EQ%d@@" % (len(store) - 1)

    text = re.sub(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", disp, text, flags=re.S)

    def inline(m):
        return math_html(m.group(1), False)

    text = re.sub(r"\$([^$]+?)\$", inline, text)
    return text, store


def restore_math(text: str, store):
    for i, html in enumerate(store):
        text = text.replace("@@EQ%d@@" % i, html)
    return text


def figure_html(path: str, caption_md: str) -> str:
    full = os.path.join(PAPER, path)
    with open(full, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    cap = ""
    if caption_md:
        cap = markdown.markdown(caption_md.strip(),
                                extensions=["tables", "sane_lists"])
        cap = re.sub(r"^<p>|</p>$", "", cap.strip())
    # the wide canvas PFD gets its own landscape page in print for legibility
    fig_cls = ' class="pfd-fig"' if path.endswith("fig12_pfd.png") else ""
    return ('<figure%s>\n<img src="data:image/png;base64,%s" alt="%s" />\n'
            '<figcaption>%s</figcaption>\n</figure>' %
            (fig_cls, b64, os.path.basename(path), cap))


def live_pfd_block() -> str:
    return r"""
<div class="pfd-live" id="live-pfd">
  <h3>Interactive process flow diagram &mdash; Canvas 2D</h3>
  <p>This live figure is drawn entirely with the Canvas 2D API (no charting library).
     Hover a unit or a line for its provenance; click to highlight; toggle the control
     loops and the withdrawn channels. The print/PDF rendering uses the static 300 dpi
     export of the same canvas shown as Fig. 12 above.</p>
  <div class="pfd-toolbar">
    <button id="lv-sig" class="on">Control loops: ON</button>
    <button id="lv-wd" class="on">Withdrawn channels: ON</button>
    <button id="lv-anim" class="on">Flow animation: ON</button>
    <button id="lv-png">Export PNG</button>
  </div>
  <div class="pfd-canvas-shell">
    <canvas id="pfd-paper"></canvas>
    <div id="pfd-tip"></div>
  </div>
  <p>Red traces mark certified <code>WITHDRAWN</code> claims; dashed purple traces mark
     certified measurement and control paths. Contract v1.97, 86 in-silico batches.</p>
</div>
"""


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        raw = f.read()
    with open(PFD_JS, "r", encoding="utf-8") as f:
        pfd_js = f.read()

    text, math_store = protect_math(raw)
    paras = re.split(r"\n{2,}", text)
    blocks = []
    i = 0
    while i < len(paras):
        p = paras[i].strip()
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", p)
        if m:
            cap = ""
            if i + 1 < len(paras) and re.match(r"\*\*Fig\.", paras[i + 1].strip()):
                cap = paras[i + 1].strip()
                i += 1
            blocks.append(figure_html(m.group(2), cap))
            if m.group(2).endswith("fig12_pfd.png"):
                blocks.append(live_pfd_block())
        elif p:
            blocks.append(markdown.markdown(p, extensions=[
                "tables", "fenced_code", "sane_lists", "attr_list"]))
        i += 1

    body = "\n\n".join(blocks)
    body = restore_math(body, math_store)

    # the last <ol> in the document is the reference list: give it explicit,
    # aligned numbering (markdown's default list rendering misaligns in print)
    last_ol = body.rfind("<ol>")
    if last_ol != -1:
        body = body[:last_ol] + '<ol class="refs">' + body[last_ol + len("<ol>"):]

    # build a table of contents from the rendered h2 headings
    heads = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)
    if not heads:  # attr_list may not have produced ids; add them
        counter = [0]

        def add_id(m):
            counter[0] += 1
            return '<h2 id="sec%d">%s</h2>' % (counter[0], m.group(1))

        body = re.sub(r"<h2>(.*?)</h2>", add_id, body)
        heads = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)
    toc = ('<nav class="toc"><b>Contents</b>' +
           "".join('<a href="#%s">%s</a>' % (h, re.sub(r"<[^>]+>", "", t))
                   for h, t in heads) + "</nav>")

    # insert the TOC after the running-title / metadata block, before the Abstract
    anchor = "<h2"
    pos = body.find(anchor)
    body = body[:pos] + toc + "\n\n" + body[pos:]

    js_init = r"""
<script>
%s
</script>
<script>
(function(){
  var api = PFD.create(document.getElementById('pfd-paper'), {
    staticMode: false,
    tooltip: document.getElementById('pfd-tip')
  });
  function bind(id, fn, label){
    var b = document.getElementById(id), on = true;
    b.addEventListener('click', function(){
      on = !on; fn(on); b.classList.toggle('on', on);
      b.textContent = label + (on ? ': ON' : ': OFF');
    });
  }
  bind('lv-sig', function(v){ api.toggleSignals(v); }, 'Control loops');
  bind('lv-wd',  function(v){ api.toggleWithdrawn(v); }, 'Withdrawn channels');
  bind('lv-anim',function(v){ api.toggleAnimation(v); }, 'Flow animation');
  document.getElementById('lv-png').addEventListener('click', function(){ api.exportPNG(); });
  window.__pfdApi = api;
  window.__pfdReady = true;
})();
</script>
""" % pfd_js

    # derive document statistics for the format bar from the markdown source
    with open(SRC, "r", encoding="utf-8") as f:
        msrc = f.read()
    n_figs = len(re.findall(r"^!\[", msrc, flags=re.M))
    n_tabs = len(re.findall(r"\*\*Table \d+\.", msrc))
    ref_sec = msrc.split("## References", 1)[1] if "## References" in msrc else ""
    n_refs = len(re.findall(r"^\d+\. ", ref_sec, flags=re.M))
    if not n_refs:
        n_refs = len([b for b in re.split(r"\n\s*\n", ref_sec) if b.strip()])
    m_title = re.match(r"^#\s+([^\n]+)", msrc.strip())
    doc_title = re.sub(r"\*\*", "", m_title.group(1))[:120] if m_title else "Manuscript"

    html = ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>" + doc_title + "</title>\n"
            "<style>\n" + CSS + "\n</style>\n</head>\n<body>\n"
            "<div class=\"sheet\">\n" + body + "\n"
            "<div class=\"formats\"><span>Markdown</span><span>HTML (interactive Canvas)</span>"
            "<span>PDF</span><span>" + str(n_figs) + " figures</span><span>"
            + str(n_tabs) + " tables</span>"
            "<span>" + str(n_refs) + " references</span></div>\n"
            "</div>\n" + js_init + "\n</body>\n</html>\n")

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("WROTE", OUT, os.path.getsize(OUT), "bytes")
    print("paragraph blocks", len(blocks), "headings", len(heads),
          "math expressions", len(MATH_CACHE), "figures", raw.count("!["))
    print("canvas present", "<canvas" in html, "PFD.create", "PFD.create" in html)


if __name__ == "__main__":
    main()
