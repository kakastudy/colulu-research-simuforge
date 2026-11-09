# -*- coding: utf-8 -*-
"""生成博客第 1 章的全局信息图（单页竖版海报）。

    python tools/blog_infographic_poster.py

输出：docs/blog/assets/fig0_overview.png（2 倍图）
"""
from __future__ import annotations

import os

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "blog", "assets")
OUT_PNG = os.path.join(OUT_DIR, "fig0_overview.png")

HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>
:root{
  --paper:#FAF6EC; --card:#FFFDF6; --tint:#F3EDDF;
  --ink:#1E1B16; --ink2:#4B4438; --mute:#8A8073;
  --line:rgba(30,27,22,.13); --line2:rgba(30,27,22,.26);
  --red:#9B3A2B; --green:#3B5A49;
  --serif:"Noto Serif SC","Songti SC",Georgia,"Times New Roman",serif;
  --sans:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"Consolas","SFMono-Regular","Courier New",monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--paper)}
body{
  width:1240px;font-family:var(--sans);color:var(--ink);
  -webkit-font-smoothing:antialiased;
  font-feature-settings:"tnum" 1,"lnum" 1;
}
.page{width:1240px;padding:58px 64px 46px;position:relative}

/* ---------- 页眉 ---------- */
.top{display:flex;align-items:baseline;justify-content:space-between;
  border-bottom:1px solid var(--line2);padding-bottom:12px}
.top .l{font-size:11.5px;letter-spacing:.34em;color:var(--mute);font-weight:600}
.top .r{font-size:11.5px;letter-spacing:.14em;color:var(--mute)}

.head{margin-top:34px;display:grid;grid-template-columns:1fr 306px;gap:44px;align-items:end}
h1{font-family:var(--serif);font-size:47px;line-height:1.22;font-weight:600;letter-spacing:.005em}
h1 em{font-style:normal;color:var(--red)}
.sub{margin-top:14px;font-family:var(--serif);font-size:17px;color:var(--ink2);letter-spacing:.02em}
.thesis{margin-top:22px;padding-left:14px;border-left:2px solid var(--red);
  font-size:13.6px;line-height:1.95;color:var(--ink2)}
.thesis b{color:var(--ink);font-weight:600}
.headnote{border:1px solid var(--line);background:var(--card);padding:16px 18px}
.headnote .k{font-size:10.5px;letter-spacing:.2em;color:var(--mute);font-weight:700}
.headnote .v{font-family:var(--serif);font-size:15px;line-height:1.7;margin-top:7px;color:var(--ink2)}

/* ---------- 指标带 ---------- */
.metrics{display:grid;grid-template-columns:repeat(4,1fr);margin-top:34px;
  border-top:1px solid var(--line2);border-bottom:1px solid var(--line2)}
.metric{padding:20px 22px 18px;border-left:1px solid var(--line)}
.metric:first-child{border-left:0;padding-left:0}
.metric .n{font-family:var(--serif);font-size:33px;font-weight:600;letter-spacing:-.01em;line-height:1}
.metric .n small{font-size:16px;font-weight:500;margin-left:3px;color:var(--ink2)}
.metric .c{font-size:11.5px;color:var(--mute);margin-top:9px;letter-spacing:.06em}
.metric .d{font-size:12.4px;color:var(--ink2);margin-top:5px;line-height:1.6}

/* ---------- 通用章节头 ---------- */
.sec{margin-top:46px}
.sech{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--line2);padding-bottom:9px}
.sech .no{font-family:var(--serif);font-size:13px;color:var(--red);font-weight:600;letter-spacing:.1em}
.sech h2{font-family:var(--serif);font-size:21px;font-weight:600;letter-spacing:.04em}
.sech .en{margin-left:auto;font-size:10.5px;letter-spacing:.3em;color:var(--mute);font-weight:600}
.sech .cnt{font-size:11.5px;color:var(--mute);letter-spacing:.08em}

/* ---------- 01 过程 ---------- */
.tl{margin-top:4px}
.row{display:grid;grid-template-columns:58px 1fr;gap:0;padding:19px 0 17px;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.rail{position:relative;padding-top:2px}
.rail .rn{font-family:var(--serif);font-size:15px;font-weight:600;color:var(--red);letter-spacing:.06em}
.rail:after{content:'';position:absolute;left:5px;top:23px;bottom:-18px;width:1px;background:rgba(30,27,22,.2)}
.row:last-child .rail:after{display:none}
.body h3{font-family:var(--serif);font-size:16.5px;font-weight:600;letter-spacing:.02em}
.body h3 span{font-family:var(--sans);font-size:11px;color:var(--mute);font-weight:400;letter-spacing:.1em;margin-left:9px}
.body p{margin-top:7px;font-size:13.2px;line-height:1.92;color:var(--ink2)}
.body p b{color:var(--ink);font-weight:600}
.chips{margin-top:9px;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11px;padding:2.5px 9px;border:1px solid var(--line2);color:var(--ink2);letter-spacing:.03em}
.chip.hot{border-color:rgba(155,58,43,.42);color:var(--red)}

/* ---------- 02 方法 ---------- */
.loop{margin-top:22px;display:grid;grid-template-columns:repeat(5,1fr);gap:0}
.node{position:relative;padding:0 14px}
.node:first-child{padding-left:0}
.node:last-child{padding-right:0}
.node .who{font-size:10.5px;letter-spacing:.16em;font-weight:700;color:var(--mute)}
.node .who.hu{color:var(--red)}
.node .t{font-family:var(--serif);font-size:15px;font-weight:600;margin-top:8px;line-height:1.45}
.node .x{font-size:11.9px;color:var(--ink2);margin-top:6px;line-height:1.72}
.node .bar{margin-top:12px;height:2px;background:var(--line2);position:relative}
.node .bar:after{content:'';position:absolute;right:-1px;top:-3.5px;width:9px;height:9px;
  border-top:1.2px solid var(--line2);border-right:1.2px solid var(--line2);transform:rotate(45deg)}
.node:last-child .bar{background:transparent}
.node:last-child .bar:after{display:none}
.loopback{margin-top:16px;border:1px dashed rgba(155,58,43,.36);background:rgba(155,58,43,.035);
  padding:12px 16px;display:flex;align-items:center;gap:12px}
.loopback .ar{font-family:var(--serif);font-size:17px;color:var(--red);line-height:1}
.loopback .tx{font-size:12.6px;color:var(--ink2);line-height:1.75}
.loopback .tx b{color:var(--red);font-weight:600}
.human{margin-top:14px;display:flex;align-items:center;gap:10px;font-size:12.2px;color:var(--ink2)}
.human .tag{font-size:10.5px;letter-spacing:.14em;font-weight:700;color:var(--card);background:var(--red);padding:3px 8px}
.human b{font-weight:600;color:var(--ink)}

/* ---------- 03 约束 ---------- */
.cons{margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line)}
.con{background:var(--paper);padding:18px 20px 17px}
.con .h{display:flex;align-items:baseline;gap:10px}
.con .i{font-family:var(--serif);font-size:12px;color:var(--red);font-weight:600;letter-spacing:.08em}
.con h4{font-family:var(--serif);font-size:15.4px;font-weight:600;letter-spacing:.02em}
.con p{margin-top:8px;font-size:12.4px;line-height:1.85;color:var(--ink2)}
.con p b{color:var(--ink);font-weight:600}
.con .fx{margin-top:9px;font-family:var(--mono);font-size:11.4px;color:var(--green);letter-spacing:.01em}

/* ---------- 04 成果 ---------- */
.res{margin-top:18px}
.rh{display:grid;grid-template-columns:126px 264px 1fr;gap:18px;padding:9px 0;
  font-size:10.5px;letter-spacing:.16em;color:var(--mute);font-weight:700;
  border-bottom:1px solid var(--line2)}
.rr{display:grid;grid-template-columns:126px 264px 1fr;gap:18px;padding:13px 0;
  border-bottom:1px solid var(--line);align-items:baseline}
.rr:last-child{border-bottom:0}
.rr .o{font-family:var(--serif);font-size:14px;font-weight:600}
.rr .o i{display:block;font-family:var(--sans);font-style:normal;font-size:10.5px;color:var(--mute);letter-spacing:.12em;margin-top:3px}
.rr .g{font-size:12.6px;color:var(--ink);line-height:1.75}
.rr .g b{font-family:var(--serif);font-size:14.5px;font-weight:600}
.rr .b{font-size:12.2px;color:var(--mute);line-height:1.75}

/* ---------- 页脚 ---------- */
.foot{margin-top:42px;border-top:1px solid var(--line2);padding-top:20px;
  display:flex;align-items:flex-end;justify-content:space-between;gap:40px}
.foot .q{font-family:var(--serif);font-size:19px;line-height:1.6;letter-spacing:.02em}
.foot .q em{font-style:normal;color:var(--red)}
.foot .r{text-align:right}
.foot .r .u{font-family:var(--mono);font-size:11.6px;color:var(--ink2)}
.foot .r .l{font-size:10.5px;letter-spacing:.18em;color:var(--mute);margin-top:6px}
</style></head>
<body><div class="page">

  <div class="top">
    <div class="l">RESEARCH OVERVIEW</div>
    <div class="r">单案例研究 · 工业规模青霉素补料分批发酵 · 2026</div>
  </div>

  <div class="head">
    <div>
      <h1>AI Agent 原生<br>仿真计算系统</h1>
      <div class="sub">以青霉素反应罐的算子 / 求解器 / 仿真计算平台为例</div>
      <div class="thesis">
        <b>人类没有写一行求解器代码，只做了 6 次裁决。</b>168 轮研发循环里，信息密度最高的产出不是通过项，而是被证伪的判据——它们决定了这套系统能走多远。
      </div>
    </div>
    <div class="headnote">
      <div class="k">VALIDATION SCOPE</div>
      <div class="v">86 批验收 · 12 批反设计口径<br>全部数字可沿三条命令重算</div>
    </div>
  </div>

  <div class="metrics">
    <div class="metric">
      <div class="n">168<small>轮</small></div>
      <div class="c">受约束的研发循环</div>
      <div class="d">每轮都带一次证伪</div>
    </div>
    <div class="metric">
      <div class="n">2.3448<small>%</small></div>
      <div class="c">产量相对误差 RMSE</div>
      <div class="d">从 70.95% 起步</div>
    </div>
    <div class="metric">
      <div class="n">86<small>/86</small></div>
      <div class="c">落入 ±5% 验收带</div>
      <div class="d">最大单批 4.83%</div>
    </div>
    <div class="metric">
      <div class="n">58·18·21</div>
      <div class="c">算子 / 能力 / 接口</div>
      <div class="d">29 项真实调用核验</div>
    </div>
  </div>

  <div class="sec">
    <div class="sech"><span class="no">01</span><h2>研究过程</h2><span class="cnt">四段推进，每段都有一次翻车</span><span class="en">PROCESS</span></div>
    <div class="tl">
      <div class="row">
        <div class="rail"><div class="rn">Ⅰ</div></div>
        <div class="body">
          <h3>底座先立，口径先清 <span>DATA &amp; BASE</span></h3>
          <p>100 个生产批次、37 个通道。动手建模前先清四类口径问题：<b>表头错列 2 列、流量存成负值、单位差一千倍、离线通道 98.2% 为空</b>。这四件事都不是算法问题，但每一件都能让整个迁移静默失败。</p>
          <div class="chips"><span class="chip">33 维方程</span><span class="chip">105 参数</span><span class="chip">26 维输入</span><span class="chip">BDF 刚性积分</span></div>
        </div>
      </div>
      <div class="row">
        <div class="rail"><div class="rn">Ⅱ</div></div>
        <div class="body">
          <h3>把工艺知识拆成可单测的最小单元 <span>OPERATORS</span></h3>
          <p>从 33 维方程里归纳出<b>七族算子与三条不变量</b>，再往上封装：底层只管算，能力层组合成"能做一件事"，接口层暴露给外部调用。核验方式是真实调用而非扫描文件——早期正好栽在"文件存在即认为已装载"上。</p>
          <div class="chips"><span class="chip">58 底层算子</span><span class="chip">18 高层能力</span><span class="chip">21 个工具接口</span><span class="chip hot">29/29 通过</span></div>
        </div>
      </div>
      <div class="row">
        <div class="rail"><div class="rn">Ⅲ</div></div>
        <div class="body">
          <h3>求解器：从"能跑"到"可信" <span>SOLVER</span></h3>
          <p>首次全量跑批 <b>70.95%</b>，12 批崩 9 批。根因不是数值缺陷，而是<b>批次级随机参数</b>——用点值代替分布，崩溃是必然的。六层台阶之后误差落到 2.3448%，其中三次尝试反而让结果变差，正是这三次定位到了耦合项。</p>
          <div class="chips"><span class="chip hot">70.95% → 2.3448%</span><span class="chip">86/86 在 ±5%</span><span class="chip">逐位零回归</span></div>
        </div>
      </div>
      <div class="row">
        <div class="rail"><div class="rn">Ⅳ</div></div>
        <div class="body">
          <h3>平台：从"成果看板"到"计算设备" <span>PLATFORM</span></h3>
          <p>一代回答"研发做得怎么样"，二代回答"能不能当工具用"。判据换了一句话：<b>能不能在不改代码的前提下，把一个新工况跑到可信</b>。于是四件事同时发生——参数面、通道数、时间分辨率、执行模型全部重做。</p>
          <div class="chips"><span class="chip">参数 14 → 97</span><span class="chip">通道 8 → 40</span><span class="chip">分辨率 2h → 0.2h</span><span class="chip">同步 → 异步队列</span></div>
        </div>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sech"><span class="no">02</span><h2>方法：一轮研发的原子结构</h2><span class="cnt">自动化的是产出与验证，不是判断与授权</span><span class="en">METHOD</span></div>
    <div class="loop">
      <div class="node">
        <div class="who hu">人</div>
        <div class="t">目标与红线</div>
        <div class="x">定验收口径：什么算过、什么永远不许碰。判据先于实现</div>
        <div class="bar"></div>
      </div>
      <div class="node">
        <div class="who">AGENT</div>
        <div class="t">候选产出</div>
        <div class="x">代码、脚本、假设。一次只改一件事，便于归因</div>
        <div class="bar"></div>
      </div>
      <div class="node">
        <div class="who">判据</div>
        <div class="t">自动验收</div>
        <div class="x">冻结的指标与阈值。判据不参与讨论，只出结果</div>
        <div class="bar"></div>
      </div>
      <div class="node">
        <div class="who">AGENT</div>
        <div class="t">证伪与回退</div>
        <div class="x">反例优先：先找能推翻自己的样本，再谈改善</div>
        <div class="bar"></div>
      </div>
      <div class="node">
        <div class="who hu">人</div>
        <div class="t">批冻结</div>
        <div class="x">通过才写进基线，且必须附全量回归</div>
        <div class="bar"></div>
      </div>
    </div>
    <div class="loopback">
      <div class="ar">↩</div>
      <div class="tx">未通过 → 回退，并把失败原因写进下一轮约束。<b>判据本身不动</b>：判据也要改，但必须另起一轮、单独证明它错在哪。</div>
    </div>
    <div class="human"><span class="tag">HUMAN</span>全程四个介入点：<b>定判据 · 批冻结 · 裁决冲突 · 授权危险操作</b>；168 轮里人类裁决 6 次。</div>
  </div>

  <div class="sec">
    <div class="sech"><span class="no">03</span><h2>约束：四条不能外包的规则</h2><span class="en">CONSTRAINTS</span></div>
    <div class="cons">
      <div class="con">
        <div class="h"><span class="i">01</span><h4>底座先冻结</h4></div>
        <p>参数与判据冻结之后才允许迭代。任何"改善"都要用<b>全量回归</b>证明自己没有把别的批次弄坏，而不是只看被改的那一批。</p>
        <div class="fx">零回归 max|Δ| = 0.00e+00 · 86 批</div>
      </div>
      <div class="con">
        <div class="h"><span class="i">02</span><h4>判据必须人写</h4></div>
        <p>8 个自建验收仪器里 <b>4 个被证伪</b>：崩溃分类器恒报正常、覆盖率给常数预测器也报 0.8995、相关系数对千倍缩放不变、支配结论因占位值整条撤回。</p>
        <div class="fx">先做零信息对照，再信任何指标</div>
      </div>
      <div class="con">
        <div class="h"><span class="i">03</span><h4>新能力默认关闭</h4></div>
        <p>所有扩展 opt-in，不写回黄金参数；敏感参数在接口层被<b>逐个拒绝</b>，而不是靠调用方自觉。能力增加不等于风险增加。</p>
        <div class="fx">5 类敏感键 → 接口层 400 拒绝</div>
      </div>
      <div class="con">
        <div class="h"><span class="i">04</span><h4>失败必须显式</h4></div>
        <p>NaN / Inf 不静默填 0；越界点标"破线"并<b>退出统计</b>。界面上保留失败点，是因为看得见的失败比藏起来的成功更有价值。</p>
        <div class="fx">宁可少行数据，不留假行数据</div>
      </div>
    </div>
  </div>

  <div class="sec">
    <div class="sech"><span class="no">04</span><h2>成果与边界</h2><span class="cnt">达成与边界同句给出，不分开写</span><span class="en">RESULTS</span></div>
    <div class="res">
      <div class="rh"><div>对象</div><div>达成</div><div>同句必须给出的边界</div></div>
      <div class="rr">
        <div class="o">算子层<i>OPERATORS</i></div>
        <div class="g"><b>58 + 18 + 21</b>，29 项核验全通过</div>
        <div class="b">确定性执行单元，不含判断；判据质量决定其价值</div>
      </div>
      <div class="rr">
        <div class="o">求解器 A<i>正问题</i></div>
        <div class="g"><b>2.3448%</b>，86/86 在 ±5%，逐位零回归</div>
        <div class="b">重建一致性而非前瞻预测；留出批次中位 97.47%，20 批仅 1 批进带</div>
      </div>
      <div class="rr">
        <div class="o">求解器 B<i>观测器</i></div>
        <div class="g">菌量轨迹误差 <b>3.17%</b>，86/86 低于 15%</div>
        <div class="b">产物与前体、菌丝分区量判为结构不可辨识</div>
      </div>
      <div class="rr">
        <div class="o">求解器 C<i>反设计</i></div>
        <div class="g">12 批口径下 <b>12/12</b> 落进 ±5%</div>
        <div class="b">进料可行域窄于 ±1%；修补中段缺口需 30% 量级位移，与域宽差 30 倍</div>
      </div>
      <div class="rr">
        <div class="o">平台<i>两代</i></div>
        <div class="g">看板 <b>25/25</b>，计算平台 <b>18/18</b> 闸门通过</div>
        <div class="b">旧平台原样冻结；闭环数据同化在留出批次上只剩 6/86</div>
      </div>
    </div>
  </div>

  <div class="foot">
    <div class="q">可行性不在"能写代码"，<br>而在<em>"能证伪自己"</em>。</div>
    <div class="r">
      <div class="u">github.com/kakastudy/colulu-research-simuforge</div>
      <div class="l">CODE · DATA · REPRODUCE</div>
    </div>
  </div>

</div></body></html>
"""


def cn_quotes(html: str) -> str:
    """把中文语境里的半角引号换成全角弯引号（属性里不含中文，不会被误伤）。"""
    import re

    return re.sub(r'"([^"<>]*[\u4e00-\u9fa5][^"<>]*)"', r'“\1”', html)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    html_path = os.path.join(OUT_DIR, "_poster_overview.html")
    with open(html_path, "w", encoding="utf-8") as f:
        body = HTML[HTML.index("<body"):]
        head = HTML[:HTML.index("<body")]
        f.write(head + cn_quotes(body))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1240, "height": 1200}, device_scale_factor=2)
        page.goto("file:///" + html_path.replace("\\", "/"))
        page.wait_for_timeout(900)
        h = page.evaluate("document.querySelector('.page').getBoundingClientRect().height")
        page.set_viewport_size({"width": 1240, "height": int(h) + 2})
        page.wait_for_timeout(400)
        page.screenshot(path=OUT_PNG)
        browser.close()

    from PIL import Image

    im = Image.open(OUT_PNG)
    print("ok", OUT_PNG, im.size, "%.0f KB" % (os.path.getsize(OUT_PNG) / 1024))


if __name__ == "__main__":
    main()
