# -*- coding: utf-8 -*-
"""公开博客插图生成：手绘 SVG -> Chromium 2x 截图 -> PNG。

输出 docs/blog/assets/*.png。不读取任何内部治理文件，只读验收结果 JSON 作数据图。
"""
from __future__ import annotations

import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "docs", "blog", "assets")
TMP = os.path.join(OUT, "_src")

INK = "#0F172A"
MUT = "#64748B"
LINE = "#E2E8F0"
BLUE = "#2563EB"
BLUE_BG = "#EFF6FF"
TEAL = "#0F766E"
TEAL_BG = "#F0FDFA"
AMBER = "#B45309"
AMBER_BG = "#FFFBEB"
SLATE = "#334155"
PAPER = "#FFFFFF"

FONT = "'Microsoft YaHei','PingFang SC','Hiragino Sans GB',sans-serif"


def T(x, y, s, size=14, fill=INK, weight=400, anchor="start", op=1.0, ls=0):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}" opacity="{op}" letter-spacing="{ls}">{s}</text>')


def box(x, y, w, h, fill=PAPER, stroke=LINE, r=12, sw=1.2, dash=None, op=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}" opacity="{op}"{d}/>')


def arrow(x1, y1, x2, y2, color=MUT, sw=1.8, dash=None, head=8):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * math.cos(ang), y2 - head * math.sin(ang)
    p1 = (bx - head * 0.5 * math.sin(ang), by + head * 0.5 * math.cos(ang))
    p2 = (bx + head * 0.5 * math.sin(ang), by - head * 0.5 * math.cos(ang))
    return (f'<line x1="{x1}" y1="{y1}" x2="{bx}" y2="{by}" stroke="{color}" stroke-width="{sw}"{d}/>'
            f'<polygon points="{x2},{y2} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{color}"/>')


def wrap(w, h, body, bg=PAPER):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{FONT}"><rect width="{w}" height="{h}" fill="{bg}"/>{body}</svg>')


def head(title, sub, w):
    return (T(56, 62, title, 26, INK, 700) + T(56, 92, sub, 15, MUT, 400)
            + f'<line x1="56" y1="116" x2="{w - 56}" y2="116" stroke="{LINE}" stroke-width="1"/>')


# ---------------------------------------------------------------- 图 1 装置与观测边界
def fig_pfd():
    W, H = 1640, 940
    b = [head("青霉素补料分批发酵罐：装置边界、观测链与时间尺度", "单罐装置级 · 公称 10 万升 · 工作体积 58 m³ · 批长约 230 h", W)]

    # 边界框
    b.append(box(40, 136, 1180, 660, "none", "#94A3B8", 16, 1.4, "8 6"))

    # 左：补料与公用工程
    b.append(T(72, 172, "补料与公用工程", 15, SLATE, 700))
    feeds = ["葡萄糖溶液", "油（消泡/碳源）", "苯乙酸 PAA", "氨水", "酸 / 碱", "冷却水 / 空气"]
    for i, f in enumerate(feeds):
        y = 190 + i * 66
        b.append(box(72, y, 190, 52, "#F8FAFC", LINE, 10))
        b.append(T(167, y + 32, f, 14, SLATE, 500, "middle"))
        b.append(arrow(266, y + 26, 378, y + 26, "#94A3B8", 1.5, "4 3", 7))

    # 夹套
    b.append(box(360, 176, 420, 588, "none", "#CBD5E1", 20, 1.2))
    b.append(T(380, 202, "夹套换热", 12, MUT, 500))

    # 反应器
    b.append(box(384, 214, 372, 522, "#FFFFFF", "#94A3B8", 18, 1.6))
    b.append(T(570, 252, "R-101 发酵罐", 20, INK, 700, "middle"))
    b.append(T(570, 278, "33 维状态 · 105 参数", 13, MUT, 400, "middle"))

    inner = [("菌丝区", "A0 / A1 / A3 / A4"), ("液泡种群", "n0 – n9"), ("溶解氧", "DO₂"), ("溶解 CO₂", "CO2d")]
    for i, (k, v) in enumerate(inner):
        col, row = i % 2, i // 2
        x, y = 412 + col * 174, 304 + row * 86
        b.append(box(x, y, 158, 70, "#F8FAFC", "#E2E8F0", 10))
        b.append(T(x + 79, y + 30, k, 15, SLATE, 700, "middle"))
        b.append(T(x + 79, y + 52, v, 12, MUT, 400, "middle"))

    # 状态条
    states = ["底物 S", "产物 P", "生物量 X", "pH", "温度 T", "体积 V", "OUR / CER", "尾气 CO₂"]
    for i, s in enumerate(states):
        x = 412 + (i % 4) * 86
        y = 496 + (i // 4) * 62
        b.append(box(x, y, 78, 46, BLUE_BG, "#BFDBFE", 8))
        b.append(T(x + 39, y + 29, s, 11, "#1E40AF", 600, "middle"))

    b.append(T(570, 690, "机理：质量 / 能量 / 元素守恒", 13, MUT, 500, "middle"))
    b.append(T(570, 712, "数值：BDF 刚性积分，0.2 h 分段", 13, MUT, 500, "middle"))

    # 观测列
    b.append(T(830, 172, "观测通道", 15, SLATE, 700))
    obs = [
        ("尾气分析 O₂ / CO₂", "→ OUR / CER", "在线 0.2 h", TEAL_BG, "#99F6E4"),
        ("pH · 温度 · 溶氧 · 转速", "→ 状态诊断", "在线 0.2 h", TEAL_BG, "#99F6E4"),
        ("离线化验 P / X / PAA / NH₃", "→ 每 12 h，滞后 4 h", "离线", AMBER_BG, "#FDE68A"),
    ]
    for i, (t1, t2, t3, bg, br) in enumerate(obs):
        y = 190 + i * 108
        b.append(box(830, y, 366, 88, bg, br, 12))
        b.append(T(852, y + 30, t1, 14, INK, 600))
        b.append(T(852, y + 54, t2, 12, MUT, 400))
        b.append(T(1176, y + 68, t3, 12, SLATE, 700, "end"))
        b.append(arrow(792, y + 44, 826, y + 44, "#14B8A6", 1.6, None, 7))

    # 收获
    b.append(box(830, 526, 366, 96, "#FFFFFF", "#94A3B8", 12, 1.4, "6 4"))
    b.append(T(852, 558, "批次末收获", 15, SLATE, 700))
    b.append(T(852, 584, "罐内余量 + 放罐累积", 12, MUT, 400))
    b.append(T(1176, 604, "产量口径", 12, MUT, 400, "end"))
    b.append(arrow(756, 580, 826, 580, "#64748B", 1.6, "6 4", 7))

    # 右侧：下游（范围外）
    b.append(box(1258, 136, 342, 210, "#F8FAFC", LINE, 14, 1.2, "6 4"))
    b.append(T(1284, 176, "下游提取 / 纯化", 16, MUT, 700))
    b.append(T(1284, 206, "不在本次范围", 13, MUT, 400))
    b.append(T(1284, 236, "公用工程管网", 13, MUT, 400))
    b.append(T(1284, 266, "实产 historian / LIMS", 13, MUT, 400))
    b.append(T(1284, 310, "边界外：只作接口预留", 12, "#94A3B8", 400))

    # 右侧：观测频率条
    b.append(box(1258, 372, 342, 424, "#FFFFFF", LINE, 14))
    b.append(T(1284, 408, "三档时间尺度", 15, SLATE, 700))
    rows = [("在线通道", "0.2 h", 0.06, TEAL), ("离线化验", "12 h", 0.42, AMBER), ("批次目标", "230 h", 1.0, BLUE)]
    for i, (name, val, frac, c) in enumerate(rows):
        y = 446 + i * 104
        b.append(T(1284, y, name, 13, INK, 600))
        b.append(T(1576, y, val, 13, c, 700, "end"))
        b.append(box(1284, y + 14, 292, 10, "#F1F5F9", "none", 5))
        b.append(box(1284, y + 14, max(12, 292 * frac), 10, c, "none", 5))
    b.append(T(1284, 758, "慢变量靠趋势，快变量靠在线；", 11, MUT, 400))
    b.append(T(1284, 778, "离线通道缺失时，比速率不可辨识。", 11, MUT, 400))

    # 底部时间轴说明
    b.append(box(40, 820, 1560, 84, "#F8FAFC", LINE, 14))
    b.append(T(72, 852, "基准数据", 13, SLATE, 700))
    b.append(T(72, 880, "100 个生产批次，每批 37 个通道，含 8 类故障注入与 7 路扰动", 13, MUT, 400))
    b.append(T(1000, 852, "验收集", 13, SLATE, 700))
    b.append(T(1000, 880, "86 批（正常批 + 故障批），按批次留出，只增不减", 13, MUT, 400))
    return wrap(W, H, "".join(b))


# ---------------------------------------------------------------- 图 2 三层架构
def fig_arch():
    W, H = 1640, 890
    b = [head("仿真计算系统的三层结构：算子、求解器、平台", "上层调用下层；下层向上层暴露能力，并回写可复核的证据", W)]

    # 人
    b.append(box(56, 140, 1528, 78, BLUE_BG, "#BFDBFE", 14))
    b.append(T(84, 176, "人：目标与边界", 15, "#1E40AF", 700))
    items = ["目标量与用途分级", "红线与操作窗口", "验收口径与分母", "候选提升的授权"]
    for i, it in enumerate(items):
        x = 320 + i * 300
        b.append(box(x, 156, 274, 46, "#FFFFFF", "#BFDBFE", 10))
        b.append(T(x + 137, 185, it, 13, "#1E3A8A", 600, "middle"))

    # 平台层
    b.append(T(56, 262, "平台层", 15, SLATE, 700))
    b.append(T(56, 284, "platform v2", 11, MUT, 400))
    plats = [("仿真台", "配工况 → 求解 → 读 40 通道轨迹"), ("参数扫描", "一维/二维响应面，标出可行域边界"), ("工况库", "预设工况，逐条对应一次验证结论")]
    for i, (t, s) in enumerate(plats):
        x = 200 + i * 356
        b.append(box(x, 240, 330, 86, "#FFFFFF", "#C7D2FE", 12))
        b.append(T(x + 22, 272, t, 16, INK, 700))
        b.append(T(x + 22, 300, s, 12, MUT, 400))
    b.append(box(1278, 240, 306, 86, "#F8FAFC", "#E2E8F0", 12))
    b.append(T(1300, 272, "引擎状态", 16, INK, 700))
    b.append(T(1300, 300, "参数表由源码派生，装载即校验", 12, MUT, 400))

    # 求解器层
    b.append(T(56, 402, "求解器层", 15, SLATE, 700))
    b.append(T(56, 424, "四档能力", 11, MUT, 400))
    solv = [
        ("A 正问题", "给定工况出轨迹", "86 批产量 RMSE 2.34%", BLUE_BG, "#BFDBFE"),
        ("B 逆问题", "由易测量反推难测量", "X 轨迹误差 3.17%", TEAL_BG, "#99F6E4"),
        ("C 反设计", "由目标产量反推操作", "12 批全部落 ±5%", AMBER_BG, "#FDE68A"),
        ("D 诊断治理", "判健康 / 判有效域 / 留证", "五通道分级", "#F8FAFC", "#E2E8F0"),
    ]
    for i, (t, s1, s2, bg, br) in enumerate(solv):
        x = 200 + i * 348
        b.append(box(x, 366, 326, 106, bg, br, 12))
        b.append(T(x + 20, 398, t, 16, INK, 700))
        b.append(T(x + 20, 424, s1, 12, MUT, 400))
        b.append(T(x + 20, 450, s2, 12, SLATE, 600))

    # 算子层
    b.append(T(56, 540, "算子层", 15, SLATE, 700))
    b.append(T(56, 562, "确定性执行", 11, MUT, 400))
    ops = [
        ("58 个底层算子", "七族：装配 / 积分 / 指标 / 健康 / 估计 / 标定 / 寻优", 0),
        ("18 个高层能力", "四档：仿真验收 6 · 逆问题 6 · 反设计 2 · 治理 4", 1),
        ("21 个工具接口", "面向智能体编排：参数 schema + 失败语义", 2),
    ]
    for t, s, i in ops:
        x = 200 + i * 470
        b.append(box(x, 504, 446, 92, "#FFFFFF", "#E2E8F0", 12))
        b.append(T(x + 22, 540, t, 16, INK, 700))
        b.append(T(x + 22, 568, s, 11.5, MUT, 400))

    # 底座
    b.append(box(200, 636, 1384, 128, "#F8FAFC", LINE, 14))
    b.append(T(224, 672, "确定性底座（先研发、后冻结）", 15, SLATE, 700))
    base = [("33 维刚性 ODE", "机理方程"), ("105 个参数", "逐项对照"), ("26 维输入", "含 8 路扰动"),
            ("100 批基准", "37 通道/批"), ("逐位可复现", "零回归锚")]
    for i, (t, s) in enumerate(base):
        x = 224 + i * 272
        b.append(T(x, 716, t, 14, INK, 700))
        b.append(T(x, 740, s, 12, MUT, 400))

    # 箭头：调用向下
    for x in (300, 700, 1100, 1420):
        b.append(arrow(x, 218, x, 238, "#94A3B8", 1.6, None, 7))
    for x in (360, 710, 1060, 1410):
        b.append(arrow(x, 326, x, 364, "#94A3B8", 1.6, None, 7))
    for x in (420, 890, 1360):
        b.append(arrow(x, 472, x, 502, "#94A3B8", 1.6, None, 7))
    b.append(arrow(500, 596, 500, 634, "#94A3B8", 1.6, None, 7))

    b.append(T(56, 812, "约束流向", 12, MUT, 700))
    b.append(T(56, 834, "自上而下是「调用」，自下而上是「能力与证据」；每一次调用都回写逐批结果、判据与失败原因。", 13, SLATE, 400))
    return wrap(W, H, "".join(b))


# ---------------------------------------------------------------- 图 3 研发闭环
def fig_loop():
    W, H = 1640, 420
    b = [head("单轮研发闭环：判据先于实现", "六步一循环，结论四选一：通过 / 返工 / 设上限 / 上报裁决", W)]
    steps = [("定目标", "明确要解决的问题"), ("写判据", "什么算通过，分母是多少"),
             ("做实现", "算子 / 参数 / 接口"), ("全量回归", "逐批逐位比对"),
             ("落证据", "结果与失败原因"), ("裁决", "通过 · 返工 · 设上限 · 上报")]
    for i, (t, s) in enumerate(steps):
        x = 56 + i * 262
        fill = BLUE_BG if i in (1, 3) else "#FFFFFF"
        stroke = "#BFDBFE" if i in (1, 3) else "#E2E8F0"
        b.append(box(x, 150, 226, 96, fill, stroke, 12))
        b.append(T(x + 20, 184, f"{i + 1:02d}", 12, BLUE if i in (1, 3) else MUT, 700))
        b.append(T(x + 20, 210, t, 16, INK, 700))
        b.append(T(x + 20, 232, s, 11.5, MUT, 400))
        if i < 5:
            b.append(arrow(x + 228, 198, x + 258, 198, "#94A3B8", 1.6, None, 7))
    # 回路
    b.append(f'<path d="M 1447 254 L 1447 300 L 169 300 L 169 252" fill="none" stroke="{BLUE}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    b.append(arrow(169, 300, 169, 252, BLUE, 1.6, None, 7))
    b.append(T(808, 330, "返工：改的是实现，不改判据；若判据本身错，先改判据再重跑", 12, BLUE, 500, "middle"))
    b.append(T(56, 372, "冻结的意义：判据一旦冻结，任何「改善」都必须拿全量回归证明自己没有把别的批次弄坏。", 13, SLATE, 400))
    return wrap(W, H, "".join(b))


# ---------------------------------------------------------------- 图 4 校准收敛
def fig_conv():
    W, H = 1440, 720
    b = [head("从 70.95% 到 2.34%：六层校准的收敛过程", "纵轴为产量相对误差 RMSE（%），绿色带为 ±5% 验收线以内", W)]
    pts = [("名义参数", 70.95, "9/12 批崩溃"), ("三维校准", 37.40, "温度通道绕开崩溃阈值"),
           ("维持系数", 32.57, "底物被过度消耗"), ("组合校准", 16.18, "单维调优失效"),
           ("常数改进", 7.28, "进入验收带边缘"), ("时变维持系数", 4.48, "12 批口径达标"),
           ("全量验收集", 2.34, "86 批，全部合格")]
    L, R, Tp, Bt = 120, 1370, 170, 600
    ymax = 75.0
    y = lambda v: Bt - (v / ymax) * (Bt - Tp)

    # 验收带
    b.append(f'<rect x="{L}" y="{y(5)}" width="{R - L}" height="{y(0) - y(5)}" fill="#DCFCE7" opacity="0.75"/>')
    b.append(f'<line x1="{L}" y1="{y(5)}" x2="{R}" y2="{y(5)}" stroke="#16A34A" stroke-width="1.4" stroke-dasharray="6 4"/>')
    b.append(T(R, y(5) - 8, "验收线 5%", 12, "#15803D", 700, "end"))

    # 网格
    for v in (0, 10, 20, 30, 40, 50, 60, 70):
        b.append(f'<line x1="{L}" y1="{y(v)}" x2="{R}" y2="{y(v)}" stroke="{LINE}" stroke-width="1"/>')
        b.append(T(L - 14, y(v) + 4, f"{v}", 12, MUT, 400, "end"))
    b.append(f'<line x1="{L}" y1="{Bt}" x2="{R}" y2="{Bt}" stroke="#94A3B8" stroke-width="1.2"/>')
    b.append(f'<text x="56" y="{(Tp + Bt) / 2}" font-size="13" fill="{MUT}" transform="rotate(-90 56 {(Tp + Bt) / 2})" text-anchor="middle">RMSE (%)</text>')

    n = len(pts)
    step = (R - L - 90) / (n - 1)
    xs = [L + 60 + i * step for i in range(n)]

    # 折线
    d = " ".join(("M" if i == 0 else "L") + f" {xs[i]:.1f} {y(pts[i][1]):.1f}" for i in range(n))
    b.append(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="2.4" stroke-linejoin="round"/>')

    for i, (name, v, note) in enumerate(pts):
        cx, cy = xs[i], y(v)
        last = i == n - 1
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{7 if last else 5}" fill="{PAPER}" stroke="{BLUE}" stroke-width="2.6"/>')
        up = v > 40
        ly = cy - 22 if up else cy + 34
        b.append(T(cx, ly, f"{v:.2f}%", 14, INK if not last else "#15803D", 700, "middle"))
        b.append(T(cx, 660, name, 12, SLATE, 600, "middle"))
        b.append(T(cx, 682, note, 10.5, MUT, 400, "middle"))

    # 大标注
    b.append(box(430, 150, 330, 74, "#FEF2F2", "#FECACA", 10, 1, None))
    b.append(T(452, 180, "起点：参数用点值代替分布", 12.5, "#991B1B", 700))
    b.append(T(452, 204, "崩溃来自机理级联，不是数值缺陷", 11, "#B91C1C", 400))

    b.append(box(1080, 470, 288, 74, "#F0FDF4", "#BBF7D0", 10, 1, None))
    b.append(T(1102, 500, "终点：86 批全部落 ±5%", 12.5, "#166534", 700))
    b.append(T(1102, 524, "最大单批偏差 4.83%", 11, "#15803D", 400))
    return wrap(W, H, "".join(b))


# ---------------------------------------------------------------- 图 5 逐批误差
def fig_batches():
    data = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8"))["results"]
    data.sort(key=lambda r: r["batch"])
    n = len(data)
    W, H = 1600, 760
    b = [head("86 个批次的产量相对误差", "每根柱是一个批次；绿色区间为 ±5% 验收带；琥珀色为故障注入批", W)]
    L, R, mid, half = 90, 1540, 330, 170
    ymax = 6.0
    scale = half / ymax
    bw = (R - L) / n

    # 验收带
    b.append(f'<rect x="{L}" y="{mid - 5 * scale}" width="{R - L}" height="{10 * scale}" fill="#DCFCE7" opacity="0.8"/>')
    for v in (5, -5):
        b.append(f'<line x1="{L}" y1="{mid - v * scale}" x2="{R}" y2="{mid - v * scale}" stroke="#16A34A" stroke-width="1.2" stroke-dasharray="6 4"/>')
    b.append(f'<line x1="{L}" y1="{mid}" x2="{R}" y2="{mid}" stroke="#94A3B8" stroke-width="1"/>')
    b.append(T(L - 12, mid + 4, "0", 11, MUT, 400, "end"))
    b.append(T(L - 12, mid - 5 * scale + 4, "+5", 11, "#15803D", 700, "end"))
    b.append(T(L - 12, mid + 5 * scale + 4, "−5", 11, "#15803D", 700, "end"))

    for i, rec in enumerate(data):
        e = rec["yield_err"] * 100
        h = abs(e) * scale
        x = L + i * bw + bw * 0.14
        y = mid - h if e >= 0 else mid
        color = "#F59E0B" if rec["type"] != "normal" else "#3B82F6"
        b.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.72:.1f}" height="{max(1.2, h):.1f}" fill="{color}" opacity="0.85" rx="1.2"/>')

    # 极值标注（放在柱顶上方，避开 KPI 卡）
    mx = max(data, key=lambda r: abs(r["yield_err"]))
    i = data.index(mx)
    cx = L + i * bw + bw / 2
    ty = mid - mx["yield_err"] * 100 * scale - 12
    b.append(T(min(cx + 90, R - 80), ty - 6, f'{mx["batch"]} 批 {mx["yield_err"]*100:+.2f}%', 11, "#1E40AF", 700, "middle"))

    # x 轴刻度
    for bt in (1, 20, 40, 60, 80, 86):
        i = next((k for k, r in enumerate(data) if r["batch"] == bt), None)
        if i is None:
            continue
        x = L + i * bw + bw / 2
        b.append(f'<line x1="{x:.1f}" y1="{mid + half + 4}" x2="{x:.1f}" y2="{mid + half + 12}" stroke="#CBD5E1" stroke-width="1"/>')
        b.append(T(x, mid + half + 30, str(bt), 11, MUT, 400, "middle"))
    b.append(T(R, mid + half + 30, "批次序号", 11, MUT, 400, "end"))

    # KPI
    cards = [("RMSE", "2.34%", "相对误差均方根"), ("±5% 达标", "86 / 86", "全部批次"), ("最大单批", "4.83%", "仍在验收带内")]
    for i, (k, v, s) in enumerate(cards):
        x = 90 + i * 300
        b.append(box(x, 560, 272, 92, "#F8FAFC", LINE, 12))
        b.append(T(x + 20, 592, k, 12, MUT, 600))
        b.append(T(x + 20, 626, v, 24, INK, 700))
        b.append(T(x + 130, 626, s, 11, MUT, 400))

    b.append(box(1030, 560, 510, 92, "#FFFFFF", LINE, 12))
    b.append(T(1052, 592, "读法说明", 12, MUT, 600))
    b.append(T(1052, 620, "每个批次使用各自的标定参数，这是重建一致性，", 11.5, SLATE, 400))
    b.append(T(1052, 640, "不等于对未见批次的前瞻预测能力。", 11.5, SLATE, 400))
    return wrap(W, H, "".join(b))


FIGURES = {
    "fig1_pfd": fig_pfd,
    "fig2_arch": fig_arch,
    "fig3_loop": fig_loop,
    "fig4_conv": fig_conv,
    "fig5_batches": fig_batches,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True, args=["--force-device-scale-factor=2"])
        page = browser.new_page(device_scale_factor=2)
        for name, fn in FIGURES.items():
            svg = fn()
            html = f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:#fff">{svg}</body>'
            src = os.path.join(TMP, name + ".html")
            open(src, "w", encoding="utf-8").write(html)
            page.set_viewport_size({"width": 1700, "height": 1000})
            page.goto("file:///" + src.replace("\\", "/"))
            el = page.query_selector("svg")
            out = os.path.join(OUT, name + ".png")
            el.screenshot(path=out)
            print("ok", out)
        browser.close()


if __name__ == "__main__":
    main()
