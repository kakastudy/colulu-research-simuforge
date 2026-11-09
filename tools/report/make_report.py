# -*- coding: utf-8 -*-
"""报告构建：report_content.py → report.docx + report.html（双格式，图内嵌）。

按 office-docx 技能约定，用选定的捆绑 Python（含 python-docx）执行。
"""
import base64
import html as _h
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(_ROOT, "runs", "report_assets")
OUT_DOCX = os.path.join(_ROOT, "runs", "report", "IndPenSim_求解器研发报告.docx")
OUT_HTML = os.path.join(_ROOT, "runs", "report", "IndPenSim_求解器研发报告.html")
os.makedirs(os.path.dirname(OUT_DOCX), exist_ok=True)

TITLE = "工业青霉素补料分批发酵罐仿真求解器（仿真算子库）研发报告"
SUBTITLE = "基于 IndPenSim V3 黄金集的 A/B/C 三档算子与 MOP 协议服务化验证"
os_variant = "analysis"

# ============ DOCX ============
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

import report_content

CONTENT = report_content.build_content()

doc = Document()
style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

for s in doc.sections:
    s.left_margin = Inches(0.9)
    s.right_margin = Inches(0.9)
    s.top_margin = Inches(0.9)
    s.bottom_margin = Inches(0.9)


def _zh(run, name="宋体"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def rich_runs(p, text, size, bold_all=False, italic=False, color=None, font="宋体"):
    """把 **加粗** 内联标记转成真实加粗 run。"""
    import re
    segs = re.split(r"\*\*(.+?)\*\*", text)
    for i, seg in enumerate(segs):
        if not seg:
            continue
        r = p.add_run(seg)
        r.font.size = Pt(size)
        r.bold = bold_all or (i % 2 == 1)
        r.italic = italic
        if color:
            r.font.color.rgb = color
        _zh(r, font)


def para(text, size=10.5, bold=False, italic=False, align=None, indent=True,
         color=None, font="宋体"):
    p = doc.add_paragraph()
    if not indent:
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(4)
    else:
        p.paragraph_format.first_line_indent = Pt(21)
    p.paragraph_format.line_spacing = 1.25
    if align is not None:
        p.alignment = align
    if "**" in text:
        rich_runs(p, text, size, bold, italic, color, font)
    else:
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.bold = bold
        r.italic = italic
        if color:
            r.font.color.rgb = color
        _zh(r, font)
    return p


def heading(text, level):
    h = doc.add_heading("", level=level)
    r = h.add_run(text)
    sizes = {0: 18, 1: 14, 2: 12, 3: 11}
    r.font.size = Pt(sizes.get(level, 11))
    r.font.color.rgb = RGBColor(0x1F, 0x3B, 0x63)
    _zh(r, "黑体")
    return h


# 标题块
para(TITLE, size=17, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, font="黑体")
para(SUBTITLE, size=11, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False,
     color=RGBColor(0x44, 0x55, 0x66), font="黑体")
para("版本 v1.0 · 2026-10-27 · 内部工程报告（基于黄金集 V3 的研究成果汇总）",
     size=9, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, color=RGBColor(0x66, 0x66, 0x66))

current_list_style = None
t_idx = 0
for item in CONTENT:
    kind = item[0]
    if kind == "h1":
        heading(item[1], 1)
    elif kind == "h2":
        heading(item[1], 2)
    elif kind == "h3":
        heading(item[1], 3)
    elif kind == "p":
        para(item[1])
    elif kind == "bullet":
        para("· " + item[1], indent=False)
    elif kind == "table":
        t_idx += 1
        caption, headers, rows = item[1], item[2], item[3]
        para(caption, size=9.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, font="黑体")
        tb = doc.add_table(rows=1, cols=len(headers))
        tb.style = "Table Grid"
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j, h in enumerate(headers):
            cell = tb.rows[0].cells[j]
            cell.text = ""
            r = cell.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            _zh(r, "黑体")
        for row in rows:
            cells = tb.add_row().cells
            for j, v in enumerate(row):
                cells[j].text = ""
                r = cells[j].paragraphs[0].add_run(str(v))
                r.font.size = Pt(9)
                _zh(r)
        para("", indent=False)
    elif kind == "fig":
        fname, caption = item[1], item[2]
        fp = os.path.join(ASSETS, fname)
        if os.path.exists(fp):
            doc.add_picture(fp, width=Inches(5.9))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            para(caption, size=9, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER,
                 indent=False, color=RGBColor(0x33, 0x44, 0x55))
        else:
            para(f"[缺失图件: {fname}]", size=9, color=RGBColor(0xAA, 0x33, 0x33))

doc.save(OUT_DOCX)
print("DOCX ->", OUT_DOCX)

# ============ HTML（含内嵌图） ============
def img_b64(fname):
    fp = os.path.join(ASSETS, fname)
    if not os.path.exists(fp):
        return None
    with open(fp, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def slugify(t):
    out, seen = [], 0
    for ch in t:
        if ch.isascii() and (ch.isalnum() or ch == " "):
            out.append(ch.lower())
        elif ch.isascii():
            continue
        else:
            out.append(f"c{seen}")
            seen += 1
    s = "".join(out).replace(" ", "-")
    seen2 = {}
    final = []
    for tok in s.split("-"):
        seen2[tok] = seen2.get(tok, 0) + 1
        final.append(f"{tok}{seen2[tok] if seen2[tok] > 1 else ''}")
    return "s-" + "-".join(x for x in final if x)[:80]


toc, body = [], []
t_idx = 0
for item in CONTENT:
    kind = item[0]
    if kind in ("h1", "h2", "h3"):
        lvl = int(kind[1])
        sid = slugify(item[1])
        if lvl <= 2:
            toc.append((lvl, item[1], sid))
        body.append(f'<h{lvl} id="{sid}">{_h.escape(item[1])}</h{lvl}>')
    elif kind == "p":
        t = item[1]
        parts = _h.escape(t).split("**")
        if len(parts) > 1:
            body.append("<p class=\"body\">" + "".join(
                (f"<b>{seg}</b>" if i % 2 == 1 else seg) for i, seg in enumerate(parts) if seg) + "</p>")
        else:
            body.append(f'<p class="body">{parts[0]}</p>')
    elif kind == "bullet":
        body.append(f'<p class="bullet">· {_h.escape(item[1])}</p>')
    elif kind == "table":
        t_idx += 1
        headers, rows = item[2], item[3]
        thead = "".join(f"<th>{_h.escape(str(h))}</th>" for h in headers)
        trs = "".join("<tr>" + "".join(
            f"<td>{_h.escape(str(v))}</td>" for v in row) + "</tr>" for row in rows)
        body.append(f'<div class="tblwrap"><p class="tcap">{_h.escape(item[1])}</p>'
                    f'<table><thead><tr>{thead}</tr></thead><tbody>{trs}</tbody></table></div>')
    elif kind == "fig":
        b = img_b64(item[1])
        if b:
            body.append(f'<div class="fig"><img src="data:image/png;base64,{b}" '
                        f'alt="{_h.escape(item[2])}"/><p class="fcap">{_h.escape(item[2])}</p></div>')
        else:
            body.append(f'<p class="fcap">[缺失图件: {_h.escape(item[1])}]</p>')

toc_html = "".join(
    f'<li class="t{lvl}"><a href="#{sid}">{_h.escape(txt)}</a></li>' for lvl, txt, sid in toc)

html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{_h.escape(TITLE)}</title>
<style>
  body {{ font-family: "Source Han Serif SC", "Noto Serif CJK SC", "Microsoft YaHei", Georgia, serif;
         max-width: 900px; margin: 0 auto; padding: 32px; color: #222; line-height: 1.75; }}
  h1 {{ color: #173f73; border-bottom: 3px solid #173f73; padding-bottom: 6px; margin-top: 40px; }}
  h2 {{ color: #1f4d8f; border-left: 5px solid #1f4d8f; padding-left: 10px; }}
  h3 {{ color: #235; }}
  .title {{ font-size: 26px; text-align: center; color: #15325b; font-weight: 700; margin-top: 8px; }}
  .subtitle {{ text-align: center; color: #445; font-style: italic; }}
  .meta {{ text-align: center; color: #666; font-size: 13px; }}
  p.body {{ text-indent: 2em; margin: 8px 0; }}
  p.bullet {{ margin: 4px 0 4px 1em; color: #234; }}
  .tblwrap {{ margin: 14px 0; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{ background: #eff4fb; border-top: 2px solid #173f73; border-bottom: 1px solid #173f73;
        padding: 6px 8px; text-align: left; }}
  td {{ border-bottom: 1px solid #c8d4e6; padding: 5px 8px; }}
  tr:last-child td {{ border-bottom: 2px solid #173f73; }}
  .tcap, .fcap {{ text-align: center; font-size: 12.5px; color: #33506f; margin: 4px; }}
  .fig {{ text-align: center; margin: 16px 0; }}
  .fig img {{ max-width: 100%; border: 1px solid #dfe6f1; }}
  .toc {{ background: #f6f8fc; border: 1px solid #dfe6f1; border-radius: 8px; padding: 14px 22px; }}
  .toc h2 {{ border: none; margin: 0 0 8px; }}
  .toc ol {{ list-style: none; margin: 0; padding: 0; }}
  .toc li.t2 {{ padding-left: 22px; }}
  a {{ color: #1f4d8f; text-decoration: none; }}
  @media print {{ .fig img {{ max-height: 100%; }} }}
</style></head><body>
<div class="title">{_h.escape(TITLE)}</div>
<div class="subtitle">{_h.escape(SUBTITLE)}</div>
<div class="meta">版本 v1.0 · 2026-10-27 · 黄金集 IndPenSim V3 · A/B/C 三档算子 · MCP Agent 服务</div>
<div class="toc"><h2>目录</h2><ol>{toc_html}</ol></div>
{chr(10).join(body)}
</body></html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html_doc)
print("HTML ->", OUT_HTML)
