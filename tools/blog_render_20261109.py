# -*- coding: utf-8 -*-
"""把博客 Markdown 渲染为浅色 HTML 阅读页（图片用相对路径，与 md 同级放置）。"""
from __future__ import annotations

import os

import markdown

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(ROOT, "blog_ai_agent_sim_stack_public_20261109.md")
DST = os.path.join(ROOT, "blog_ai_agent_sim_stack_public_20261109.html")

CSS = """
:root{--ink:#111827;--muted:#5b6b7c;--line:#e5e7eb;--accent:#2563eb;--bg:#fff;}
*{box-sizing:border-box}
body{margin:0;background:#f6f8fb;color:var(--ink);
 font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",system-ui,sans-serif;
 font-size:16.5px;line-height:1.85;-webkit-font-smoothing:antialiased}
.page{max-width:980px;margin:0 auto;background:var(--bg);padding:64px 72px 96px;
 box-shadow:0 1px 3px rgba(15,23,42,.06)}
h1{font-size:34px;line-height:1.3;letter-spacing:-.4px;margin:0 0 6px}
h2{font-size:23px;line-height:1.4;margin:52px 0 14px;padding-top:22px;border-top:1px solid var(--line)}
h2:first-of-type{border-top:0;padding-top:0}
h3{font-size:19px;margin:34px 0 10px}
h4{font-size:16.5px;margin:26px 0 8px;color:#334155}
p{margin:14px 0}
a{color:var(--accent);text-decoration:underline;text-underline-offset:2px;word-break:break-all}
strong{font-weight:700}
blockquote{margin:22px 0;padding:18px 22px;background:#f8fafc;border-left:3px solid var(--accent);
 border-radius:0 8px 8px 0;color:#334155;font-size:15.5px}
blockquote p{margin:8px 0}
table{width:100%;border-collapse:collapse;margin:20px 0;font-size:14.5px}
th,td{border:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top;min-width:92px}
th{background:#f8fafc;font-weight:700;color:#334155}
tr:nth-child(even) td{background:#fcfdff}
code{background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:.9em;
 font-family:Consolas,"SF Mono",Menlo,monospace;color:#0f172a}
img{display:block;max-width:100%;height:auto;margin:26px auto 8px;border:1px solid var(--line);
 border-radius:8px;cursor:zoom-in}
em{color:var(--muted);font-style:normal;font-size:14px;display:block;margin:0 0 26px;line-height:1.75}
hr{border:0;border-top:1px solid var(--line);margin:40px 0}
ol,ul{padding-left:22px}
li{margin:7px 0}
.meta{color:#475569;font-size:17px;font-weight:600;margin:8px 0 30px}
#lb{position:fixed;inset:0;background:rgba(15,23,42,.88);display:none;align-items:center;
 justify-content:center;z-index:99;padding:24px;cursor:zoom-out}
#lb img{max-width:98vw;max-height:96vh;border:0;border-radius:6px;margin:0;cursor:zoom-out}
@media(max-width:760px){.page{padding:34px 20px 56px}h1{font-size:26px}h2{font-size:20px}}
"""

LIGHTBOX = """
<div id="lb"><img alt=""></div>
<script>
document.querySelectorAll('img').forEach(function (im) {
  im.addEventListener('click', function () {
    var lb = document.getElementById('lb');
    lb.querySelector('img').src = im.src;
    lb.style.display = 'flex';
  });
});
document.getElementById('lb').addEventListener('click', function () {
  this.style.display = 'none';
});
</script>
"""


def main():
    text = open(SRC, encoding="utf-8").read()
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip()
    subtitle = ""
    idx = 1
    if len(lines) > 1 and lines[1].startswith("## "):
        subtitle = lines[1].lstrip("# ").strip()
        idx = 2
    body_md = "\n".join(lines[idx:])

    html_body = markdown.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])
    html_body = html_body.replace("<table>", '<div style="overflow-x:auto"><table>')
    html_body = html_body.replace("</table>", "</table></div>")

    page = (
        '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{title}</title><style>{CSS}</style></head>\n"
        '<body><div class="page">\n'
        f"<h1>{title}</h1>\n"
        f'<div class="meta">{subtitle}</div>\n'
        f"{html_body}\n"
        "</div>\n" + LIGHTBOX + "</body></html>"
    )
    open(DST, "w", encoding="utf-8").write(page)
    print("ok", DST, len(page))


if __name__ == "__main__":
    main()
