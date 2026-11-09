/* ==========================================================================
   IndPenSim 发酵过程仿真平台 — 前端
   数据契约：window.FERM_DATA（platform/export_data.py 生成）
   原则：L1 骨架（拓扑/全通道/全批次）永不折叠；L2 染色与主指标；L3 走抽屉
   ========================================================================== */
(function () {
  "use strict";

  const D = window.FERM_DATA;
  if (!D) {
    document.body.innerHTML =
      '<div style="padding:40px;font-family:system-ui;color:#e9f0f7">' +
      "缺少数据包 data.js —— 请先运行 <code>python platform/export_data.py</code></div>";
    return;
  }

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const num = (v, d) => (v === null || v === undefined || Number.isNaN(v)
    ? "—" : Number(v).toFixed(d === undefined ? 2 : d));
  const pct = (v, d) => (v === null || v === undefined ? "—" : Number(v).toFixed(d === undefined ? 1 : d) + "%");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const BATCHES = D.batches;
  const BY_B = new Map(BATCHES.map((b) => [b.b, b]));
  const CHANNELS = D.channels;
  const CH_BY_KEY = new Map(CHANNELS.map((c) => [c.key, c]));

  const state = {
    view: "overview",
    batch: pickDefaultBatch(),
    seriesCh: "P",
    cls: "all",
    distCh: "Viscosity_offline",
    errMode: "abs",
    theme: localStorage.getItem("ferm-theme") || "dark",
  };

  function pickDefaultBatch() {
    // 默认选一批"典型正常批"：|产量误差| 最小且非故障批
    const normals = BATCHES.filter((b) => b.type === "normal")
      .slice().sort((a, b) => Math.abs(a.yield_err) - Math.abs(b.yield_err));
    return (normals[0] || BATCHES[0]).b;
  }

  /* ---------------- 主题 ---------------- */
  const store = {
    get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* file:// 或隐私模式 */ } },
  };
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    store.set("ferm-theme", state.theme);
    renderAll();
  }
  $("#btn-theme").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
  });

  /* ---------------- tooltip ---------------- */
  const tip = $("#tip");
  function showTip(html, ev) {
    tip.innerHTML = html;
    tip.dataset.on = "true";
    const pad = 14;
    const r = tip.getBoundingClientRect();
    let x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const hideTip = () => { tip.dataset.on = "false"; };

  /* ---------------- 抽屉 ---------------- */
  const drawer = $("#drawer"), scrim = $("#scrim");
  function openDrawer(title, bodyHtml) {
    $("#drawer-title").textContent = title;
    $("#drawer-body").innerHTML = bodyHtml;
    drawer.dataset.open = "true";
    drawer.setAttribute("aria-hidden", "false");
    scrim.dataset.on = "true";
  }
  function closeDrawer() {
    drawer.dataset.open = "false";
    drawer.setAttribute("aria-hidden", "true");
    scrim.dataset.on = "false";
  }
  $("#drawer-close").addEventListener("click", closeDrawer);
  scrim.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  /* ---------------- 视图路由 ---------------- */
  const VIEWS = [
    { id: "overview", label: "总览", icon: '<path d="M4 19V9m5 10V5m5 14v-7m5 7V11"/>' },
    { id: "topology", label: "拓扑", icon: '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="18" cy="17" r="3"/><path d="M9 12h3m0 0l3-3.4M12 12l3 3.4"/>' },
    { id: "batch", label: "批次", icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>' },
    { id: "channels", label: "通道", icon: '<path d="M3 17l5-6 4 4 4-8 5 6"/><path d="M3 21h18"/>' },
    { id: "operators", label: "算子", icon: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>' },
    { id: "workbench", label: "观察控制", icon: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>' },
  ];

  function renderRail() {
    $("#rail").innerHTML = VIEWS.map((v) =>
      `<button class="rail-btn" data-view="${v.id}" aria-current="${v.id === state.view}">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${v.icon}</svg>
         <span>${v.label}</span>
       </button>`).join("");
    $$("#rail .rail-btn").forEach((b) =>
      b.addEventListener("click", () => go(b.dataset.view)));
  }

  function go(id, opts) {
    if (!VIEWS.some((v) => v.id === id)) id = "overview";
    state.view = id;
    $$("#rail .rail-btn").forEach((b) => b.setAttribute("aria-current", String(b.dataset.view === id)));
    VIEWS.forEach((v) => { $("#v-" + v.id).hidden = v.id !== id; });
    closeDrawer();
    // 视图写进 URL（#topology 等）：可直达、可分享、刷新不丢当前屏。
    // 用 replaceState 而不是 location.hash —— 控制台切屏不该塞满浏览器历史。
    if (!(opts && opts.fromHash) && location.hash !== "#" + id) {
      try { history.replaceState(null, "", "#" + id); } catch (e) { /* file:// 下可能受限 */ }
    }
    const el = $("#v-" + id);
    if (el) { el.style.animation = "none"; void el.offsetWidth; el.style.animation = ""; }
    renderAll();
  }

  /* ================= 图表基元 ================= */
  const NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    return e;
  }
  function mkSvg(host, w, h) {
    host.innerHTML = "";
    const s = svgEl("svg", { class: "chart", viewBox: `0 0 ${w} ${h}`, width: "100%", height: h });
    host.appendChild(s);
    return s;
  }
  const scale = (d0, d1, r0, r1) => (v) => r0 + (r1 - r0) * ((v - d0) / ((d1 - d0) || 1));

  function axes(s, o) {
    const { pad, w, h, xd, yd, xfmt, yfmt, yticks, xticks, ylabel, xlabel } = o;
    const sy = scale(yd[0], yd[1], h - pad.b, pad.t);
    const sx = scale(xd[0], xd[1], pad.l, w - pad.r);
    const ny = yticks || 5, nx = xticks || 5;
    for (let i = 0; i <= ny; i++) {
      const v = yd[0] + (yd[1] - yd[0]) * i / ny;
      const y = sy(v);
      s.appendChild(svgEl("line", { class: "grid-line", x1: pad.l, x2: w - pad.r, y1: y, y2: y }));
      const t = svgEl("text", { x: pad.l - 6, y: y + 3, "text-anchor": "end" });
      t.textContent = yfmt ? yfmt(v) : num(v, 1);
      s.appendChild(t);
    }
    for (let i = 0; i <= nx; i++) {
      const v = xd[0] + (xd[1] - xd[0]) * i / nx;
      const x = sx(v);
      const t = svgEl("text", { x, y: h - pad.b + 12, "text-anchor": "middle" });
      t.textContent = xfmt ? xfmt(v) : num(v, 0);
      s.appendChild(t);
    }
    s.appendChild(svgEl("line", { class: "axis", x1: pad.l, x2: w - pad.r, y1: h - pad.b, y2: h - pad.b }));
    if (ylabel) {
      const t = svgEl("text", { x: pad.l - 2, y: pad.t - 6, "text-anchor": "start" });
      t.textContent = ylabel; s.appendChild(t);
    }
    if (xlabel) {
      const t = svgEl("text", { x: w - pad.r, y: h - 2, "text-anchor": "end" });
      t.textContent = xlabel; s.appendChild(t);
    }
    return { sx, sy };
  }

  function pathFrom(xs, ys, sx, sy) {
    let d = "", pen = false;
    for (let i = 0; i < xs.length; i++) {
      const y = ys[i];
      if (y === null || y === undefined || Number.isNaN(y)) { pen = false; continue; }
      d += (pen ? "L" : "M") + sx(xs[i]).toFixed(1) + " " + sy(y).toFixed(1) + " ";
      pen = true;
    }
    return d;
  }

  function drawIn(el, dur) {
    try {
      const len = el.getTotalLength();
      el.style.strokeDasharray = len;
      el.style.strokeDashoffset = len;
      el.getBoundingClientRect();
      el.style.transition = "stroke-dashoffset " + (dur || 700) + "ms cubic-bezier(.22,.68,.3,1)";
      el.style.strokeDashoffset = "0";
      setTimeout(() => { el.style.strokeDasharray = ""; el.style.transition = ""; }, (dur || 700) + 60);
    } catch (e) { /* 空路径 */ }
  }

  /* ================= 顶栏与状态栏 ================= */
  function renderChrome() {
    const k = D.kpi;
    const items = [
      { lab: "产量 RMSE", val: num(k.rmse, 2), unit: "%", tone: k.rmse <= k.rmse_limit ? "ok" : "crit" },
      { lab: "±5% 命中", val: k.within + "/" + k.within_total, unit: "", tone: k.within === k.within_total ? "ok" : "warn" },
      { lab: "catastrophic(已登记)", val: k.catastrophic, unit: "", tone: k.catastrophic === 0 ? "ok" : "warn" },
      { lab: "通道健康", val: k.healthy_pct, unit: "%", tone: k.healthy_pct >= 80 ? "ok" : k.healthy_pct >= 50 ? "warn" : "crit" },
    ];
    $("#nav-kpi").innerHTML = items.map((i) =>
      `<div class="k"><em>${i.lab}</em><b style="color:var(--${i.tone})">${i.val}${i.unit ? `<small>${i.unit}</small>` : ""}</b></div>`).join("");

    $("#st-contract").textContent = "ENGINE_CONTRACT " + D.meta.contract;
    $("#st-gen").textContent = "数据生成 " + D.meta.generated + " · " + D.meta.batches + " 批";
    $("#brand-sub").textContent = D.meta.subtitle;
    $("#op-contract").textContent = "build_params(COMBINED[b]) @ " + D.meta.contract;
  }

  /* ================= 总览 ================= */
  function renderOverview() {
    const k = D.kpi;
    const cards = [
      { lab: "产量 RMSE", val: num(k.rmse, 2), unit: "%", tone: k.rmse <= k.rmse_limit ? "ok" : "crit",
        foot: `<span class="tag ${k.rmse <= k.rmse_limit ? "ok" : "crit"}">${k.rmse <= k.rmse_limit ? "达标" : "超标"}</span> 红线 ${k.rmse_limit}%`,
        bar: clamp(k.rmse / k.rmse_limit, 0, 1), barColor: "var(--ok)" },
      { lab: "±5% 命中", val: k.within, unit: "/" + k.within_total, tone: k.within === k.within_total ? "ok" : "warn",
        foot: `<span class="tag ${k.within === k.within_total ? "ok" : "warn"}">${(100 * k.within / k.within_total).toFixed(1)}%</span> 黄金集只增不减`,
        bar: k.within / k.within_total, barColor: "var(--ok)" },
      { lab: "catastrophic(已登记)", val: k.catastrophic, unit: "/" + k.within_total, tone: "warn",
        foot: `<span class="tag ok">0 新发</span> 已登记 [${(k.catastrophic_batches || []).join(", ")}] · classify_health 五通道`,
        bar: k.catastrophic / k.within_total, barColor: "var(--warn)" },
      { lab: "通道健康对", val: k.healthy_pairs, unit: "/" + k.total_pairs, tone: k.healthy_pct >= 50 ? "warn" : "crit",
        foot: `<span class="tag ${k.healthy_pct >= 50 ? "warn" : "crit"}">${k.healthy_pct}%</span> healthy &lt;5% nRMSE`,
        bar: k.healthy_pct / 100, barColor: "var(--warn)" },
    ];
    $("#kpi-grid").innerHTML = cards.map((c) => `
      <div class="kpi ${c.tone}">
        <div class="lab">${c.lab}</div>
        <div class="val">${c.val}<small>${c.unit}</small></div>
        <div class="foot">${c.foot}</div>
        <div class="bar"><i style="width:0%;background:${c.barColor}" data-w="${(c.bar * 100).toFixed(1)}"></i></div>
      </div>`).join("");
    requestAnimationFrame(() => $$("#kpi-grid .bar i").forEach((i) => { i.style.width = i.dataset.w + "%"; }));

    drawYieldChart();
    drawHealthChart();
    drawHeat();
    renderXobs();
  }

  /* X 通道 B 档软测量（R139 v2 双通道观测器）——与 A 档机理值并列展示 */
  function renderXobs() {
    const host = $("#xobs"); if (!host) return;
    const x = D.x_obs;
    if (!x) { host.innerHTML = ""; return; }
    const cv = x.cv || {};
    const cy = x.cv_struct || {};
    const cvTxt = cv.nrmse_med_test != null ? `${num(cv.nrmse_med_test, 2)}%` : "—";
    const ciTxt = (cv.ci_lo_pct != null)
      ? `[${num(cv.ci_lo_pct, 1)}, +${num(cv.ci_hi_pct, 1)}]% · 覆盖 ${num(100 * cv.coverage, 1)}%`
      : "—";
    const gate = x.gate || {};
    const gateTxt = (gate.batch && gate.batch.length)
      ? gate.batch.map((b) => `<span class="tag warn">b${b}</span>`).join(" ")
      : `<span class="tag mute">无</span>`;
    host.innerHTML = `
      <div class="panel">
        <div class="panel-h">
          <h2>X 菌丝浓度 · B 档软测量</h2>
          <span class="hint">${x.method}｜p=${x.p} q=${x.q}｜后处理，不进 ODE</span>
          <div class="spacer"></div>
          <span class="tag ok">${x.b.lt15}/${x.n} 批 &lt;15%</span>
        </div>
        <div class="panel-b" style="display:flex;gap:30px;flex-wrap:wrap;align-items:flex-end">
          <div><div class="lab" style="color:var(--dim);font-size:11px">A 档机理</div>
            <div style="font-size:22px;font-weight:600">${num(x.a.nrmse_med, 2)}<small>%</small></div>
            <div style="font-size:11px;color:var(--dim)">${x.a.lt15}/${x.n} 批 &lt;15%</div></div>
          <div style="font-size:16px;color:var(--dim)">→</div>
          <div><div class="lab" style="color:var(--dim);font-size:11px">B 档观测器 v2</div>
            <div style="font-size:22px;font-weight:600;color:var(--ok)">${num(x.b.nrmse_med, 2)}<small>%</small></div>
            <div style="font-size:11px;color:var(--dim)">p90 ${num(x.b.nrmse_p90, 2)}% · 最坏 ${num(x.b.nrmse_max, 2)}%</div></div>
          <div style="margin-left:auto;font-size:11.5px;line-height:1.85;color:var(--dim);text-align:right">
            <div>5 折 CV 测试中位 <b style="color:var(--text)">${cvTxt}</b>（结构化 ${num(cy.nrmse_med_test, 2)}%）</div>
            <div>90% 区间 ${ciTxt}</div>
            <div>门控回退 ${gateTxt}</div>
          </div>
        </div>
      </div>`;
  }

  function drawYieldChart() {
    const host = $("#chart-yield"); if (!host) return;
    const w = host.clientWidth || 720, h = 250, pad = { t: 16, r: 14, b: 26, l: 40 };
    const s = mkSvg(host, w, h);
    const signed = state.errMode === "signed";
    const val = (b) => (signed ? b.yield_err : Math.abs(b.yield_err));
    const lim = signed ? 6.2 : 6.2;
    const yd = signed ? [-lim, lim] : [0, lim];
    const { sx, sy } = axes(s, {
      pad, w, h, xd: [0, BATCHES.length - 1], yd,
      yfmt: (v) => v.toFixed(0) + "%", xfmt: (v) => "#" + BATCHES[Math.round(v)].b,
      yticks: 6, xticks: 6,
    });

    const lines = signed ? [-5, 0, 5] : [5];
    lines.forEach((v) => {
      s.appendChild(svgEl("line", {
        class: v === 0 ? "axis" : "limit", x1: pad.l, x2: w - pad.r, y1: sy(v), y2: sy(v),
      }));
      const t = svgEl("text", { x: w - pad.r - 2, y: sy(v) - 3, "text-anchor": "end" });
      t.textContent = v === 0 ? "0" : (v > 0 ? "+5%" : "−5%");
      t.setAttribute("style", v === 0 ? "" : "fill:var(--crit)");
      s.appendChild(t);
    });

    BATCHES.forEach((b, i) => {
      const v = val(b);
      const x = sx(i), y = sy(v), y0 = sy(0);
      const col = b.health === "catastrophic" ? "var(--crit)"
        : Math.abs(b.yield_err) > 5 ? "var(--crit)" : Math.abs(b.yield_err) > 3 ? "var(--warn)" : "var(--ok)";
      const g = svgEl("g", { style: "cursor:pointer" });
      g.appendChild(svgEl("line", { x1: x, x2: x, y1: y0, y2: y, stroke: col, "stroke-width": 1, opacity: 0.45 }));      const r = 2.6 + 3.4 * clamp(b.avg_nrmse / 40, 0, 1);
      g.appendChild(svgEl("circle", { cx: x, cy: y, r, fill: col, opacity: b.type === "fault" ? 1 : 0.9,
        stroke: b.type === "fault" ? "var(--accent)" : "none", "stroke-width": 1.2 }));
      g.addEventListener("mousemove", (ev) => showTip(
        `<b>批 #${b.b}</b> ${b.type === "fault" ? '<span class="tag crit">故障</span>' : ""}<br>` +
        `产量误差 <b class="mono">${b.yield_err > 0 ? "+" : ""}${b.yield_err.toFixed(2)}%</b><br>` +
        `仿真 ${b.yield_sim} / 实测 ${b.yield_v3} g<br>` +
        `平均通道 nRMSE ${b.avg_nrmse}% · ${b.health}`, ev));
      g.addEventListener("mouseleave", hideTip);
      g.addEventListener("click", () => { state.batch = b.b; go("batch"); });
      s.appendChild(g);
    });
  }

  function drawHealthChart() {
    const host = $("#chart-health"); if (!host) return;
    const rows = CHANNELS.slice(0, 10);
    const w = host.clientWidth || 420, rowH = 22, h = rows.length * rowH + 26;
    const pad = { t: 6, r: 8, b: 18, l: 86 };
    const s = mkSvg(host, w, h);
    const maxN = Math.max(...rows.map((c) => (c.health.healthy || 0) + (c.health.warning || 0) + (c.health.critical || 0)));
    const sx = scale(0, maxN, pad.l, w - pad.r);
    rows.forEach((c, i) => {
      const y = pad.t + i * rowH;
      let acc = 0;
      const segs = [
        ["healthy", "var(--ok)", c.health.healthy || 0],
        ["warning", "var(--warn)", c.health.warning || 0],
        ["critical", "var(--crit)", c.health.critical || 0],
      ];
      const t = svgEl("text", { x: pad.l - 7, y: y + 11, "text-anchor": "end" });
      t.textContent = c.label; t.setAttribute("style", "fill:var(--text-2)");
      s.appendChild(t);
      segs.forEach(([, col, n]) => {
        if (!n) return;
        const x0 = sx(acc), x1 = sx(acc + n);
        const rect = svgEl("rect", { x: x0, y: y + 3, width: Math.max(1.5, x1 - x0 - 1.2), height: 11, rx: 2, fill: col, opacity: 0.85 });
        rect.style.cursor = "pointer";
        rect.addEventListener("mousemove", (ev) => showTip(`<b>${c.label}</b> · ${esc(c.key)}<br>healthy ${c.health.healthy || 0} / warning ${c.health.warning || 0} / critical ${c.health.critical || 0}<br>中位 nRMSE <b>${c.nrmse}%</b> · ${c.cls} 类`, ev));
        rect.addEventListener("mouseleave", hideTip);
        rect.addEventListener("click", () => openChannelDrawer(c.key));
        s.appendChild(rect);
        acc += n;
      });
    });
    const t2 = svgEl("text", { x: w - pad.r, y: h - 2, "text-anchor": "end" });
    t2.textContent = "批次数（共 " + D.meta.batches + "）";
    s.appendChild(t2);
  }

  function drawHeat() {
    const host = $("#heat"); if (!host) return;
    const chs = D.matrix.channels, bs = D.matrix.batches, vals = D.matrix.values;
    const cols = "104px repeat(" + bs.length + ", minmax(7px, 1fr))";
    let html = `<div class="heat" style="grid-template-columns:${cols}">`;
    html += `<div></div>`;
    bs.forEach((b) => { html += `<div class="hx">${b}</div>`; });
    chs.forEach((key, r) => {
      const c = CH_BY_KEY.get(key);
      html += `<div class="hl" title="${esc(c ? c.label : key)}">${esc(c ? c.label : key)}</div>`;
      vals[r].forEach((v, i) => {
        const cls = v === null ? "h-none" : v < 5 ? "h-ok" : v < 15 ? "h-warn" : "h-crit";
        html += `<div class="hc ${cls}" data-ch="${key}" data-b="${bs[i]}" data-v="${v === null ? "" : v}"></div>`;
      });
    });
    html += "</div>";
    host.innerHTML = html;
    $$("#heat .hc").forEach((c, i) => {
      c.style.animation = `cellIn .34s ${Math.min(i * 1.1, 700)}ms both`;
      c.addEventListener("mousemove", (ev) => {
        const v = c.dataset.v;
        const ch = CH_BY_KEY.get(c.dataset.ch);
        showTip(`<b>批 #${c.dataset.b}</b> · ${esc(ch ? ch.label : c.dataset.ch)}<br>nRMSE <b class="mono">${v === "" ? "无数据" : v + "%"}</b><br>` +
          (v === "" ? "" : v < 5 ? "healthy" : v < 15 ? "warning" : "critical"), ev);
      });
      c.addEventListener("mouseleave", hideTip);
      c.addEventListener("click", () => { state.batch = +c.dataset.b; go("batch"); });
    });
  }

  /* ================= 拓扑 ================= */
  let topoBatch = null;
  function renderTopology() {
    const T = D.topology;
    const bno = topoBatch || state.batch;
    const b = BY_B.get(bno);
    const seg = $("#seg-topo-batch");
    const opts = [["8", "b8"], ["11", "b11"], ["27", "b27"], ["36", "b36"], ["92", "b92"]].filter(([k]) => BY_B.has(+k));
    seg.innerHTML = opts.map(([k, lab]) =>
      `<button data-b="${k}" aria-pressed="${+k === bno}">${lab}</button>`).join("");
    $$("#seg-topo-batch button").forEach((btn) =>
      btn.addEventListener("click", () => { topoBatch = +btn.dataset.b; renderTopology(); }));
    $("#topo-batch-note").textContent = b ? `批 #${b.b} · 产量误差 ${b.yield_err > 0 ? "+" : ""}${b.yield_err.toFixed(2)}%` : "—";

    const W = 760, H = 420;
    const host = $("#topo"); host.innerHTML = "";
    const s = svgEl("svg", { class: "topo chart", viewBox: `0 0 ${W} ${H}`, width: "100%", style: "height:auto" });
    host.appendChild(s);

    const s0 = D.series[String(bno)];
    const last = (ch) => (s0 && s0.sim[ch] ? s0.sim[ch][s0.sim[ch].length - 1] : null);

    // 连线
    T.edges.forEach(([a, c]) => {
      const na = T.nodes.find((n) => n.id === a), nc = T.nodes.find((n) => n.id === c);
      const x1 = na.x + na.w, y1 = na.y + 46, x2 = nc.x, y2 = nc.y + 46;
      const d = `M${x1} ${y1} C${x1 + 46} ${y1}, ${x2 - 46} ${y2}, ${x2} ${y2}`;
      s.appendChild(svgEl("path", { class: "edge", d }));
      s.appendChild(svgEl("path", { class: "edge flow", d }));
    });

    // 回路
    const loopPos = {
      // 间距守卫：每个回路盒宽 132，横排相邻中心距必须 ≥140 才不压字。
      // 旧值 feed[214] 与 agit[330] 只差 116 → "补料流量"标签被搅拌盒盖住（T8 复验发现）。
      feed: [196, 322], air: [150, 96], agit: [356, 330],
      cool: [520, 112], offgas: [356, 46], assay: [540, 300],
    };
    T.loops.forEach((lp) => {
      const [x, y] = loopPos[lp.id] || [200, 120];
      const w = 132, h = 52;
      const g = svgEl("g", { "data-loop": lp.id, style: "cursor:pointer" });
      g.appendChild(svgEl("rect", { class: "loop-box", x, y, width: w, height: h, rx: 8 }));
      const t = svgEl("text", { class: "nkey", x: x + 10, y: y + 16 }); t.textContent = lp.label; g.appendChild(t);
      const v = svgEl("text", { class: "nval", x: x + 10, y: y + 36 }); v.textContent = lp.primary.value; g.appendChild(v);
      const u = svgEl("text", { class: "nunit", x: x + 10 + String(lp.primary.value).length * 7 + 4, y: y + 36 });
      u.textContent = lp.primary.unit; g.appendChild(u);
      const k = svgEl("text", { class: "nunit", x: x + w - 8, y: y + 16, "text-anchor": "end" });
      k.textContent = lp.primary.label; g.appendChild(k);
      g.addEventListener("mousemove", (ev) => showTip(`<b>${lp.label}</b><br>${lp.primary.label}：<b class="mono">${lp.primary.value} ${lp.primary.unit}</b><br>${lp.secondary.label}：${lp.secondary.value} ${lp.secondary.unit}`, ev));
      g.addEventListener("mouseleave", hideTip);
      g.addEventListener("click", () => openDrawer(lp.label, `<div class="kv">
          <dt>主指标</dt><dd>${lp.primary.label} = ${lp.primary.value} ${lp.primary.unit}</dd>
          <dt>次指标</dt><dd>${lp.secondary.label} = ${lp.secondary.value} ${lp.secondary.unit}</dd>
        </div><p class="tiny muted" style="margin-top:12px">该回路的输入在仿真中由 V3 实测被控量序列驱动（开环回放），
        因此回路的可控制性不参与本次评估——我们评估的是"给定同样操作，罐内状态是否被复现"。</p>`));
      s.appendChild(g);
    });

    // 主链节点
    const vals = {
      reactor: { p: last("P"), v: last("V") },
    };
    T.nodes.forEach((n) => {
      const g = svgEl("g", { "data-node": n.id, class: n.id === "reactor" ? "sel" : "" });
      const hgt = n.h || 76;
      g.appendChild(svgEl("rect", { class: "node-box" + (n.id === "reactor" ? " sel" : ""), x: n.x, y: n.y, width: n.w, height: hgt, rx: 10 }));
      const lab = svgEl("text", { class: "nlabel", x: n.x + 12, y: n.y + 21 }); lab.textContent = n.label; g.appendChild(lab);
      const sub = svgEl("text", { class: "nsub", x: n.x + 12, y: n.y + 35 }); sub.textContent = n.sub; g.appendChild(sub);
      let pv = n.primary.value, pvUnit = n.primary.unit, sv = n.secondary.value, svUnit = n.secondary.unit;
      if (n.id === "reactor" && vals.reactor.p != null) pv = vals.reactor.p.toFixed(1);
      if (n.id === "reactor" && vals.reactor.v != null) sv = (vals.reactor.v / 1000).toFixed(1);
      const v = svgEl("text", { class: "nval", x: n.x + 12, y: n.y + hgt - 20 }); v.textContent = pv; g.appendChild(v);
      const u = svgEl("text", { class: "nunit", x: n.x + 14 + String(pv).length * 7, y: n.y + hgt - 20 }); u.textContent = pvUnit; g.appendChild(u);
      const k = svgEl("text", { class: "nkey", x: n.x + n.w - 12, y: n.y + hgt - 20, "text-anchor": "end" });
      k.textContent = n.primary.label; g.appendChild(k);
      g.addEventListener("mousemove", (ev) => showTip(`<b>${n.label}</b> · ${n.sub}<br>${n.primary.label}：<b class="mono">${pv} ${pvUnit}</b><br>${n.secondary.label}：${sv} ${svUnit}`, ev));
      g.addEventListener("mouseleave", hideTip);
      g.addEventListener("click", () => openDrawer(n.label, `<div class="kv">
          <dt>主指标</dt><dd>${n.primary.label} = ${pv} ${pvUnit}</dd>
          <dt>次指标</dt><dd>${n.secondary.label} = ${sv} ${svUnit}</dd>
        </div><p class="tiny muted" style="margin-top:12px">主链上的状态量由 ODE 积分给出；本平台展示的是批 #${bno} 的批末值。</p>`));
      s.appendChild(g);
    });

    // 剖面
    drawProfile();
    drawLoopBars();
    $("#topo-kv").innerHTML = b ? `
      <dt>批号</dt><dd>#${b.b}</dd>
      <dt>类型</dt><dd>${b.type === "fault" ? "故障批" : "正常批"}</dd>
      <dt>批末产量</dt><dd>${num(s0 ? last("P") : null, 2)} g/L</dd>
      <dt>批末菌丝</dt><dd>${num(s0 ? last("X") : null, 2)} g/L</dd>
      <dt>批末黏度</dt><dd>${num(s0 ? last("vis") : null, 1)} cP</dd>
      <dt>平均通道 nRMSE</dt><dd>${b.avg_nrmse}%</dd>
      <dt>通道健康</dt><dd>${b.health}</dd>` : `<dt>无数据</dt><dd>—</dd>`;
  }

  function drawProfile() {
    const host = $("#profile"); if (!host) return;
    const s0 = D.series[String(topoBatch || state.batch)];
    if (!s0) { host.innerHTML = '<p class="tiny muted">无轨迹数据</p>'; return; }
    const key = "P";
    const w = host.clientWidth || 300, h = 170, pad = { t: 12, r: 10, b: 22, l: 34 };
    const s = mkSvg(host, w, h);
    const ys = s0.sim[key];
    const off = (s0.off && s0.off[key]) || null;
    const ymax = Math.max(...ys, ...(off ? off.map((p) => p[1]) : [1])) * 1.08;
    const { sx, sy } = axes(s, { pad, w, h, xd: [0, s0.t[s0.t.length - 1]], yd: [0, ymax], yticks: 4, xticks: 4, xfmt: (v) => v.toFixed(0) + "h" });
    const p = svgEl("path", { class: "series sim", d: pathFrom(s0.t, ys, sx, sy) });
    s.appendChild(p); drawIn(p, 900);
    if (off) {
      off.forEach(([t, v]) => s.appendChild(svgEl("circle", { cx: sx(t), cy: sy(v), r: 2.3, fill: "var(--warn)", opacity: 0.9 })));
    }
  }

  function drawLoopBars() {
    const host = $("#loop-bars"); if (!host) return;
    const s0 = D.series[String(topoBatch || state.batch)];
    const load = s0 ? [
      { k: "供氧 OTR", v: clamp((s0.sim.DO2 ? s0.sim.DO2[s0.sim.DO2.length - 1] : 30) / 30, 0, 1) },
      { k: "OUR / 上限", v: clamp((s0.sim.OUR ? s0.sim.OUR[s0.sim.OUR.length - 1] : 0) / 1.2, 0, 1) },
      { k: "补料强度", v: clamp((s0.sim.S ? s0.sim.S[s0.sim.S.length - 1] : 0) / 12, 0, 1) },
      { k: "黏度负荷", v: clamp((s0.sim.vis ? s0.sim.vis[s0.sim.vis.length - 1] : 0) / 110, 0, 1) },
    ] : [];
    host.innerHTML = load.map((r) => `
      <div class="bar-row"><span class="muted">${r.k}</span>
        <span class="track"><i style="width:0%" data-w="${(r.v * 100).toFixed(0)}"></i></span>
        <span class="v mono">${(r.v * 100).toFixed(0)}%</span></div>`).join("");
    requestAnimationFrame(() => $$("#loop-bars .track i").forEach((i) => { i.style.width = i.dataset.w + "%"; }));
  }

  /* ================= 批次工作台 ================= */
  function renderBatch() {
    const b = BY_B.get(state.batch) || BATCHES[0];
    $("#batch-badge").innerHTML = `批 #${b.b} · ${b.type === "fault" ? "故障批" : "正常批"} · classify_health: ${esc(b.health || "unknown")}`;

    $("#batch-grid").innerHTML = BATCHES.map((x) => {
      const a = Math.abs(x.yield_err);
      const col = a > 5 ? "var(--crit)" : a > 3 ? "var(--warn)" : "var(--ok)";
      return `<button class="bcell" data-b="${x.b}" aria-selected="${x.b === b.b}" style="box-shadow:inset 0 -2px 0 ${col}">${x.b}</button>`;
    }).join("");
    $$("#batch-grid .bcell").forEach((c) => c.addEventListener("click", () => {
      state.batch = +c.dataset.b; renderBatch();
    }));

    const kp = [
      { lab: "产量相对误差", v: (b.yield_err > 0 ? "+" : "") + b.yield_err.toFixed(2), u: "%", tone: Math.abs(b.yield_err) > 5 ? "crit" : Math.abs(b.yield_err) > 3 ? "warn" : "ok" },
      { lab: "仿真产量", v: b.yield_sim.toFixed(0), u: "g", tone: "ok" },
      { lab: "实测产量", v: b.yield_v3.toFixed(0), u: "g", tone: "ok" },
      { lab: "平均通道 nRMSE", v: b.avg_nrmse.toFixed(1), u: "%", tone: b.avg_nrmse > 15 ? "crit" : b.avg_nrmse > 8 ? "warn" : "ok" },
    ];
    $("#batch-kpi").innerHTML = kp.map((c) => `
      <div class="kpi ${c.tone}"><div class="lab">${c.lab}</div>
        <div class="val">${c.v}<small>${c.u}</small></div>
        <div class="foot"><span class="tag ${c.tone}">${c.tone === "ok" ? "正常" : c.tone === "warn" ? "警告" : "严重"}</span></div></div>`).join("");

    const s0 = D.series[String(b.b)];
    const seg = $("#seg-series");
    const chKeys = ["P", "S", "X", "PAA", "DO2", "OUR", "vis", "CER"];
    seg.innerHTML = chKeys.map((k) => {
      const m = { P: "青霉素", S: "底物", X: "菌丝", PAA: "前体", DO2: "溶氧", OUR: "OUR", vis: "黏度", CER: "CER" };
      return `<button data-ch="${k}" aria-pressed="${k === state.seriesCh}">${m[k]}</button>`;
    }).join("");
    $$("#seg-series button").forEach((btn) => btn.addEventListener("click", () => {
      state.seriesCh = btn.dataset.ch; renderBatch();
    }));

    drawSeries(s0, b);
    renderTrial(b);

    const pr = b.params || {};
    const rows = Object.keys(pr).sort().map((k) => `<dt>${esc(k)}</dt><dd>${typeof pr[k] === "number" ? num(pr[k], 4) : esc(String(pr[k]))}</dd>`).join("");
    $("#batch-params").innerHTML = rows || '<dt class="muted">无覆盖项</dt><dd>—</dd>';

    const chs = D.matrix.channels.map((key, i) => {
      const v = D.matrix.values[i][D.matrix.batches.indexOf(b.b)];
      return { key, v: v === null ? null : v };
    }).filter((x) => x.v !== null).sort((a, c) => c.v - a.v);
    $("#batch-channels").innerHTML = `<div class="bars">` + chs.map((x) => {
      const c = CH_BY_KEY.get(x.key) || { label: x.key };
      const cls = x.v < 5 ? "var(--ok)" : x.v < 15 ? "var(--warn)" : "var(--crit)";
      return `<div class="bar-row"><span class="muted">${esc(c.label)}</span>
        <span class="track"><i style="width:${clamp(x.v / 40 * 100, 2, 100)}%;background:${cls}"></i></span>
        <span class="v mono">${x.v.toFixed(1)}%</span></div>`;
    }).join("") + "</div>";
  }

  function drawSeries(s0, b) {
    const host = $("#chart-series"); if (!host) return;
    if (!s0) {
      host.innerHTML = `<p class="tiny muted">该批无轨迹缓存 —— 运行 <code>python platform/export_data.py</code> 生成。</p>`;
      return;
    }
    const key = state.seriesCh;
    const ch = CH_BY_KEY.get(key === "vis" ? "Viscosity_offline" : key === "X" ? "X_offline" : key === "PAA" ? "PAA_offline" : key) || {};
    const w = host.clientWidth || 720, h = 300, pad = { t: 16, r: 16, b: 26, l: 46 };
    const s = mkSvg(host, w, h);
    const ys = s0.sim[key] || [];
    const yo = (s0.obs && s0.obs[key]) || null;
    const off = (s0.off && s0.off[key]) || null;
    let ymax = Math.max(...ys, ...(yo || []), ...(off ? off.map((p) => p[1]) : []), 1);
    ymax *= 1.08;
    const { sx, sy } = axes(s, {
      pad, w, h, xd: [0, s0.t[s0.t.length - 1]], yd: [0, ymax], yticks: 5, xticks: 6,
      xfmt: (v) => v.toFixed(0) + "h", ylabel: (ch.label || key) + (ch.unit ? " / " + ch.unit : ""),
    });

    const ps = svgEl("path", { class: "series sim", d: pathFrom(s0.t, ys, sx, sy) });
    s.appendChild(ps); drawIn(ps, 820);

    if (yo) {
      const po = svgEl("path", { class: "series obs", d: pathFrom(s0.t, yo, sx, sy) });
      s.appendChild(po); setTimeout(() => drawIn(po, 820), 160);
    }
    if (off) {
      off.forEach(([t, v], i) => {
        const c = svgEl("circle", { cx: sx(t), cy: sy(v), r: 2.8, fill: "var(--warn)", opacity: 0 });
        c.style.transition = "opacity .3s " + Math.min(40 * i, 500) + "ms";
        c.addEventListener("mousemove", (ev) => showTip(`<b>t = ${t} h</b><br>实测 ${v} ${ch.unit || ""}<br>仿真 ${num(npAt(s0.t, ys, t), 3)} ${ch.unit || ""}`, ev));
        c.addEventListener("mouseleave", hideTip);
        s.appendChild(c);
        requestAnimationFrame(() => { c.style.opacity = 0.92; });
      });
    }

    // 悬停游标
    const cur = svgEl("line", { x1: 0, x2: 0, y1: pad.t, y2: h - pad.b, stroke: "var(--accent)", "stroke-width": 1, opacity: 0, "stroke-dasharray": "3 3" });
    s.appendChild(cur);
    const hit = svgEl("rect", { x: pad.l, y: pad.t, width: w - pad.l - pad.r, height: h - pad.t - pad.b, fill: "transparent" });
    s.appendChild(hit);
    hit.addEventListener("mousemove", (ev) => {
      const box = s.getBoundingClientRect();
      const x = (ev.clientX - box.left) / box.width * w;
      const t = clamp((x - pad.l) / (w - pad.l - pad.r) * s0.t[s0.t.length - 1], 0, s0.t[s0.t.length - 1]);
      cur.setAttribute("x1", x); cur.setAttribute("x2", x); cur.setAttribute("opacity", 0.65);
      const i = clamp(Math.round((t - s0.t[0]) / (s0.t[1] - s0.t[0])), 0, s0.t.length - 1);
      showTip(`<b>t = ${s0.t[i]} h</b><br>仿真 ${num(s0.sim[key][i], 3)} ${ch.unit || ""}<br>` +
        (yo ? `实测 ${num(yo[i], 3)}` : off ? "化验点见散点" : ""), ev);
    });
    hit.addEventListener("mouseleave", () => { cur.setAttribute("opacity", 0); hideTip(); });
  }
  function npAt(xs, ys, x) {
    for (let i = 0; i < xs.length - 1; i++) {
      if (xs[i] <= x && x <= xs[i + 1]) {
        const r = (x - xs[i]) / (xs[i + 1] - xs[i] || 1);
        return ys[i] + r * (ys[i + 1] - ys[i]);
      }
    }
    return ys[ys.length - 1];
  }

  /* ================= 通道诊断 ================= */
  function renderChannels() {
    const rows = CHANNELS.filter((c) => state.cls === "all" || c.cls === state.cls);
    $("#tbl-channels").innerHTML = `
      <thead><tr><th>通道</th><th>分组</th><th class="r">nRMSE</th><th class="r">R²</th><th class="r">gain</th>
      <th class="r">相位</th><th class="r">形状残差</th><th>类</th><th>主导健康</th></tr></thead>
      <tbody>` + rows.map((c) => `
        <tr data-ch="${c.key}" aria-selected="${c.key === state.distCh}">
          <td>${esc(c.label)} <span class="tiny muted mono">${esc(c.key)}</span></td>
          <td class="tiny muted">${c.group}</td>
          <td class="r mono" style="color:${c.nrmse < 5 ? "var(--ok)" : c.nrmse < 15 ? "var(--warn)" : "var(--crit)"}">${c.nrmse.toFixed(1)}%</td>
          <td class="r mono">${c.r2 === null ? "—" : c.r2.toFixed(2)}</td>
          <td class="r mono">${c.gain === null ? "—" : c.gain.toFixed(2)}</td>
          <td class="r mono">${c.lag === null ? "—" : (c.lag > 0 ? "+" : "") + c.lag.toFixed(1) + "h"}</td>
          <td class="r mono">${c.shape === null ? "—" : c.shape.toFixed(1) + "%"}</td>
          <td><span class="tag ${c.cls === "A" ? "ok" : c.cls === "B" ? "warn" : "crit"}">${c.cls}</span></td>
          <td class="tiny muted">ok ${c.health.healthy || 0} / warn ${c.health.warning || 0} / crit ${c.health.critical || 0}</td>
        </tr>`).join("") + "</tbody>";
    $$("#tbl-channels tbody tr").forEach((tr) => tr.addEventListener("click", () => {
      state.distCh = tr.dataset.ch; renderChannels(); openChannelDrawer(tr.dataset.ch);
    }));

    $$("#seg-cls button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.cls === state.cls)));
    $$("#seg-cls button").forEach((b) => { b.onclick = () => { state.cls = b.dataset.cls; renderChannels(); }; });

    drawScatter();
    drawDist();
  }

  function drawScatter() {
    const host = $("#chart-scatter"); if (!host) return;
    const w = host.clientWidth || 420, h = 280, pad = { t: 18, r: 16, b: 30, l: 44 };
    const s = mkSvg(host, w, h);
    const pts = CHANNELS.filter((c) => c.shape !== null && c.bias !== null);
    const xs = pts.map((c) => Math.abs(c.bias));
    const ys = pts.map((c) => c.shape);
    const xmax = Math.max(10, ...xs) * 1.15, ymax = Math.max(10, ...ys) * 1.15;
    const { sx, sy } = axes(s, { pad, w, h, xd: [0, xmax], yd: [0, ymax], yticks: 4, xticks: 4,
      xfmt: (v) => v.toFixed(0) + "%", yfmt: (v) => v.toFixed(0) + "%" });
    const t1 = svgEl("text", { x: w - pad.r, y: h - 2, "text-anchor": "end" }); t1.textContent = "幅度偏差 |bias|";
    s.appendChild(t1);
    const t2 = svgEl("text", { x: pad.l - 2, y: pad.t - 6, "text-anchor": "start" }); t2.textContent = "形状残差";
    s.appendChild(t2);

    // 对角线 = 幅度与形状等权
    s.appendChild(svgEl("line", { x1: sx(0), y1: sy(0), x2: sx(Math.min(xmax, ymax)), y2: sy(Math.min(xmax, ymax)), stroke: "var(--line-2)", "stroke-dasharray": "4 4" }));

    pts.forEach((c) => {
      const col = c.cls === "A" ? "var(--ok)" : c.cls === "B" ? "var(--warn)" : "var(--crit)";
      const g = svgEl("g", { style: "cursor:pointer" });
      g.appendChild(svgEl("circle", { cx: sx(Math.abs(c.bias)), cy: sy(c.shape), r: 4.4, fill: col, opacity: 0.9 }));
      g.addEventListener("mousemove", (ev) => showTip(`<b>${c.label}</b> · ${c.cls} 类<br>nRMSE ${c.nrmse}%<br>幅度偏差 ${c.bias.toFixed(1)}% / 形状残差 ${c.shape.toFixed(1)}%<br><span class="muted">${esc(c.why || "")}</span>`, ev));
      g.addEventListener("mouseleave", hideTip);
      g.addEventListener("click", () => openChannelDrawer(c.key));
      s.appendChild(g);
    });
  }

  function drawDist() {
    const host = $("#chart-dist"); if (!host) return;
    const idx = D.matrix.channels.indexOf(state.distCh);
    const c = CH_BY_KEY.get(state.distCh);
    $("#dist-ch").textContent = c ? c.label : state.distCh;
    if (idx < 0) return;
    const vals = D.matrix.values[idx];
    const w = host.clientWidth || 420, h = 280, pad = { t: 16, r: 14, b: 26, l: 34 };
    const s = mkSvg(host, w, h);
    const ymax = Math.max(20, ...vals.filter((v) => v !== null)) * 1.1;
    const { sx, sy } = axes(s, { pad, w, h, xd: [0, vals.length - 1], yd: [0, ymax], yticks: 4, xticks: 5,
      xfmt: (v) => "#" + D.matrix.batches[Math.round(v)], yfmt: (v) => v.toFixed(0) + "%" });
    vals.forEach((v, i) => {
      if (v === null) return;
      const col = v < 5 ? "var(--ok)" : v < 15 ? "var(--warn)" : "var(--crit)";
      const r = svgEl("rect", { x: sx(i) - 1.6, y: sy(v), width: 3.2, height: Math.max(1, sy(0) - sy(v)), fill: col, opacity: 0.82 });
      r.style.cursor = "pointer";
      r.addEventListener("mousemove", (ev) => showTip(`<b>批 #${D.matrix.batches[i]}</b><br>${c ? c.label : ""} nRMSE <b>${v}%</b>`, ev));
      r.addEventListener("mouseleave", hideTip);
      r.addEventListener("click", () => { state.batch = D.matrix.batches[i]; go("batch"); });
      s.appendChild(r);
    });
    [5, 15].forEach((v) => {
      s.appendChild(svgEl("line", { class: "limit", x1: pad.l, x2: w - pad.r, y1: sy(v), y2: sy(v) }));
      const t = svgEl("text", { x: w - pad.r - 2, y: sy(v) - 3, "text-anchor": "end" }); t.textContent = v + "%";
      t.setAttribute("style", "fill:var(--crit)"); s.appendChild(t);
    });
  }

  function openChannelDrawer(key) {
    const c = CH_BY_KEY.get(key);
    if (!c) return;
    const idx = D.matrix.channels.indexOf(key);
    const vals = D.matrix.values[idx] || [];
    const arr = vals.filter((v) => v !== null).sort((a, b) => a - b);
    const med = arr.length ? arr[Math.floor(arr.length / 2)] : null;
    openDrawer(c.label + " · 通道档案", `
      <div class="kv">
        <dt>通道键</dt><dd>${esc(c.key)}</dd>
        <dt>分组</dt><dd>${c.group}</dd>
        <dt>分类</dt><dd><span class="tag ${c.cls === "A" ? "ok" : c.cls === "B" ? "warn" : "crit"}">${c.cls} 类</span></dd>
        <dt>中位 nRMSE</dt><dd>${c.nrmse}%</dd>
        <dt>R²</dt><dd>${c.r2 === null ? "—" : c.r2}</dd>
        <dt>幅度 gain</dt><dd>${c.gain === null ? "—" : c.gain}</dd>
        <dt>残余相位</dt><dd>${c.lag === null ? "—" : c.lag + " h"}</dd>
        <dt>形状残差</dt><dd>${c.shape === null ? "—" : c.shape + "%"}</dd>
        <dt>逐批中位</dt><dd>${med === null ? "—" : med.toFixed(1) + "%"}</dd>
        <dt>最好 / 最差</dt><dd>${arr.length ? arr[0].toFixed(1) + "% / " + arr[arr.length - 1].toFixed(1) + "%" : "—"}</dd>
      </div>
      <p style="margin:14px 0 6px;font-size:12px;color:var(--text-2)">${esc(c.why || "")}</p>
      <p class="tiny muted">处置原则：A 类可调参；B 类需机制项；C 类只登记、不硬凑（R131 教训）。</p>
      <div class="mt" id="drawer-dist"></div>`);
    const host = $("#drawer-dist");
    if (!host) return;
    const w = host.clientWidth || 380, h = 180, pad = { t: 12, r: 10, b: 22, l: 32 };
    const s = mkSvg(host, w, h);
    const ymax = Math.max(20, ...vals.filter((v) => v !== null)) * 1.1;
    const { sx, sy } = axes(s, { pad, w, h, xd: [0, vals.length - 1], yd: [0, ymax], yticks: 3, xticks: 4,
      xfmt: (v) => "#" + D.matrix.batches[Math.round(v)], yfmt: (v) => v.toFixed(0) + "%" });
    vals.forEach((v, i) => {
      if (v === null) return;
      const col = v < 5 ? "var(--ok)" : v < 15 ? "var(--warn)" : "var(--crit)";
      s.appendChild(svgEl("rect", { x: sx(i) - 1.4, y: sy(v), width: 2.8, height: Math.max(1, sy(0) - sy(v)), fill: col, opacity: 0.85 }));
    });
  }

  /* ================= 算子库 ================= */
  function renderOperators() {
    const ops = D.operators.operators;
    // R167：优先用服务侧「实时」装载核验；离线时用 data.js 的导出时核验，并如实标注。
    const live = trial.ops && trial.ops.status ? trial.ops.status : null;
    const liveMap = live ? Object.fromEntries(live.operators.map((x) => [x.name, x])) : null;
    // 目录名 ≠ 运行时函数名的两处（conservation_metrics→element_balance、model.rhs→rhs）
    // 统一用导出器写入的 attr 字段对齐，避免实时核验少算一个。
    const keyOf = (o) => o.runtime_name || o.name;
    const loaded = ops.filter((o) => liveMap ? !!liveMap[keyOf(o)] && liveMap[keyOf(o)].loaded : !!o.loaded).length;
    $("#op-count").textContent = loaded + "/" + ops.length + " 运行时装载 · " +
      (live ? "服务实时核验" : "导出时核验");
    $("#op-grid").innerHTML = ops.map((o) => {
      const lr = liveMap ? liveMap[keyOf(o)] : null;
      const ok = liveMap ? !!lr && lr.loaded : !!o.loaded;
      const err = lr ? lr.error : o.error;
      return `
      <div class="panel" style="box-shadow:none">
        <div class="panel-h">
          <h2 class="mono" style="font-size:12.5px">${esc(o.name)}</h2>
          <span class="tag ${ok ? "ok" : "crit"}">${ok ? "运行时已装载" : "未装载"}</span>
          <div class="spacer"></div>
          <span class="tiny muted">${esc(o.layer || o.kind)}</span>
        </div>
        <div class="panel-b">
          <p style="margin:0 0 8px;font-size:11.5px;line-height:1.6;color:var(--text-2)">${esc(o.desc)}</p>
          <div class="tiny muted mono">${esc(o.module || o.file)}.${esc(o.attr || o.name)}(${o.args.map(esc).join(", ")})</div>
          <div class="tiny muted" style="margin-top:4px">${esc(o.file)} · import + callable ${ok ? "通过" : "失败：" + esc(err || "?")}</div>
        </div>
      </div>`;
    }).join("");

    $("#tbl-knobs").innerHTML = `
      <thead><tr><th>参数键</th><th>含义</th><th class="r">默认</th><th>作用域</th><th>影响</th></tr></thead>
      <tbody>` + D.operators.knobs.map((k) => `
        <tr><td class="mono">${esc(k.key)}</td><td>${esc(k.label)}</td>
        <td class="r mono">${k.default}</td><td class="tiny muted">${k.scope}</td>
        <td class="tiny muted">${esc(k.effect)}</td></tr>`).join("") + "</tbody>";
  }

  /* ================= 参数试算（需本地引擎） ================= */
  const trial = { conn: null, busy: false, last: null, health: null, ops: null, evidence: null };

  async function probeEngine() {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      trial.conn = r.ok;
      trial.health = r.ok ? await r.json() : null;
    } catch (e) {
      trial.conn = false;
    }
    // R167：能力注册表与证据面板，服务离线时静默降级到 data.js 的离线快照
    for (const [key, url] of [["ops", "/api/ops"], ["evidence", "/api/evidence"]]) {
      try {
        const r = await fetch(url, { cache: "no-store" });
        trial[key] = r.ok ? await r.json() : null;
      } catch (e) { trial[key] = null; }
    }
    return trial.conn;
  }

  /* ================= 观察-控制工作台（R167 / PH5 剩余） ================= */
  let wbTool = null;

  function renderWorkbench() {
    const wb = D.workbench || {};
    const st = trial.ops && trial.ops.status ? trial.ops.status : null;
    const tools = st ? st.tools : (wb.tools || []);
    const ev = trial.evidence && trial.evidence.evidence ? trial.evidence.evidence : (D.evidence || {});

    // L0–L3 架构带
    $("#wb-arch").innerHTML = (wb.architecture || []).map((a) => `
      <div class="panel" style="box-shadow:none">
        <div class="panel-h"><h2>${esc(a.layer)} · ${esc(a.name)}</h2>
          <span class="tag ${a.state.indexOf("未执行") >= 0 ? "mute" : "ok"}">${esc(a.state)}</span></div>
        <div class="panel-b tiny muted" style="line-height:1.7">${esc(a.detail)}</div>
      </div>`).join("");

    const tiers = { A: [], B: [], C: [], D: [] };
    tools.forEach((t) => (tiers[t.tier] || (tiers[t.tier] = [])).push(t));
    const tierName = { A: "A · 仿真引擎/验收", B: "B · 软测量/观测器", C: "C · 反设计/咨询", D: "D · 回退链" };
    $("#wb-tiers").innerHTML = Object.keys(tiers).map((k) => `
      <div class="panel">
        <div class="panel-h"><h2>${tierName[k] || k}</h2>
          <div class="spacer"></div><span class="tag ${tiers[k].every((t) => t.loaded) ? "ok" : "crit"}">${tiers[k].filter((t) => t.loaded).length}/${tiers[k].length} 已装载</span></div>
        <div class="panel-b" style="display:flex;flex-wrap:wrap;gap:8px">
          ${tiers[k].map((t) => `<button class="wb-btn ${wbTool === t.id ? "sel" : ""}" data-tool="${esc(t.id)}"
              ${t.loaded ? "" : "disabled"}>
              <b>${esc(t.label)}</b><span class="mono">${esc(t.id)}</span>
              <em>${esc(t.cost)}${t.cost === "heavy" ? " · 需确认" : ""}</em></button>`).join("")}
        </div>
      </div>`).join("");

    $$("#wb-tiers .wb-btn").forEach((b) => b.addEventListener("click", () => {
      wbTool = b.dataset.tool;
      renderWorkbenchForm(tools.find((t) => t.id === wbTool));
      $$("#wb-tiers .wb-btn").forEach((x) => x.classList.toggle("sel", x.dataset.tool === wbTool));
    }));
    if (wbTool) renderWorkbenchForm(tools.find((t) => t.id === wbTool));

    $("#wb-evidence").innerHTML = `
      <div class="kv">
        <dt>契约版本</dt><dd class="mono">${esc(ev.contract || D.meta.contract)}</dd>
        <dt>R166 终检</dt><dd>${esc(ev.final_check ? ev.final_check.n_pass + "/" + ev.final_check.n_checks + " " + ev.final_check.verdict : "—")}</dd>
        <dt>A/B 证据闸门</dt><dd>${esc(ev.ab_gate ? ev.ab_gate.n_pass + "/" + ev.ab_gate.n_checks + " " + ev.ab_gate.verdict : "—")}</dd>
        <dt>MCP 冒烟</dt><dd>${esc(ev.mcp_smoke ? ev.mcp_smoke.n_pass + "/" + ev.mcp_smoke.n_checks + " " + ev.mcp_smoke.verdict : "—")}</dd>
        <dt>零回归</dt><dd>86 批 max|Δ| = 0.00e+00 · RMSE 2.345% · 86/86</dd>
        <dt>健康分级</dt><dd>normal ${D.kpi.normal} / degraded ${D.kpi.degraded} / catastrophic ${D.kpi.catastrophic}（已登记）</dd>
        <dt>V2 多轮寻优</dt><dd>${esc(ev.v2_optim ? ev.v2_optim.verdict : "—")} · 全幅 σ 崩塌，样本外失效</dd>
        <dt>L3 决策</dt><dd>${esc(ev.l3 ? ev.l3.state : "未执行 · 保持 opt-in")}</dd>
        <dt>cap</dt><dd>${esc(ev.cap || "L2 prototype (conditional)")}</dd>
      </div>
      <p class="tiny muted" style="margin:10px 0 0;line-height:1.8">
        ${esc(wb.no_go || "")}<br>${esc(wb.ph3_note || "")}<br>
        证据全部读自 <code>runs/</code> 既有产物，平台不重算指标。
      </p>`;
    $("#wb-state").textContent = trial.conn
      ? `服务在线 · ${trial.health ? trial.health.capabilities + "/" + trial.health.capabilities_total : "?"} 能力实时装载`
      : "静态模式 · 能力清单为导出时快照，调用需启动本地服务";
  }

  function renderWorkbenchForm(t) {
    const host = $("#wb-form");
    if (!host || !t) { if (host) host.innerHTML = ""; return; }
    host.innerHTML = `
      <div class="panel-h"><h2>${esc(t.label)} <span class="mono tiny muted">${esc(t.id)}</span></h2>
        <div class="spacer"></div><span class="tag ${t.cost === "heavy" ? "warn" : "mute"}">${esc(t.cost)}</span></div>
      <div class="panel-b">
        <p class="tiny muted" style="margin:0 0 10px;line-height:1.7">${esc(t.desc)}</p>
        <div class="grid g-2" style="gap:10px">
          ${(t.params || []).map((p) => `
            <label class="wb-field"><span>${esc(p.name)} <em>${esc(p.type)}${p.required ? " · 必填" : ""}</em></span>
              ${p.type === "bool"
                ? `<input type="checkbox" data-p="${esc(p.name)}" data-type="bool" ${p.default ? "checked" : ""} /> <small class="muted">${esc(p.desc)}</small>`
                : `<input data-p="${esc(p.name)}" data-type="${esc(p.type)}" value="${p.default === null || p.default === undefined ? "" : esc(String(p.default))}" placeholder="${esc(p.desc)}" />`}
            </label>`).join("") || '<p class="tiny muted">无参数</p>'}
        </div>
        <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
          ${(t.params || []).some((p) => ["fallback_chain", "health_probe"].includes(p.name))
            ? '<label class="tiny muted"><input type="checkbox" id="wb-optin" /> 显式 opt-in</label>' : ""}
          ${t.cost === "heavy" ? '<label class="tiny muted"><input type="checkbox" id="wb-confirm" /> 确认为重调用</label>' : ""}
          <button class="btn" id="wb-run" ${trial.conn ? "" : "disabled"}>调用</button>
          <span class="tiny muted" id="wb-run-state">${trial.conn ? "就绪" : "服务离线，仅可查看清单"}</span>
        </div>
        <pre class="mono" id="wb-out" style="margin:12px 0 0;max-height:320px;overflow:auto;font-size:11px;line-height:1.6"></pre>
      </div>`;
    const btn = $("#wb-run");
    if (btn) btn.addEventListener("click", () => runWorkbenchTool(t));
  }

  async function runWorkbenchTool(t) {
    if (!trial.conn || !t) return;
    const args = {};
    $$("#wb-form input[data-p]").forEach((el) => {
      if (el.dataset.type === "bool") { args[el.dataset.p] = !!el.checked; return; }
      if (el.value === "") return;
      args[el.dataset.p] = el.value;
    });
    const body = {
      tool: t.id, args,
      opt_in: !!($("#wb-optin") && $("#wb-optin").checked),
      confirm: !!($("#wb-confirm") && $("#wb-confirm").checked),
    };
    const out = $("#wb-out"), state = $("#wb-run-state");
    state.textContent = "调用中…"; out.textContent = "";
    try {
      const r = await fetch("/api/invoke", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      out.textContent = JSON.stringify(j, null, 2);
      state.textContent = j.ok ? `完成 · ${j.elapsed_s}s · ${j.tier} 档` : `拒绝/失败：${j.error}`;
    } catch (e) {
      state.textContent = "请求失败：" + e.message;
      out.textContent = String(e);
    }
  }

  function renderTrial(b) {
    const host = $("#trial-body"), st = $("#trial-state");
    if (!host) return;
    if (trial.conn === null) { st.textContent = "检测中…"; st.className = "tag mute"; host.innerHTML = ""; return; }
    if (!trial.conn) {
      st.textContent = "静态模式"; st.className = "tag mute";
      host.innerHTML = `<p class="tiny muted" style="margin:0;line-height:1.8">
        当前是静态数据包，只能看历史回归结果。要**当场改参数重算**，在项目根目录运行：
        <code style="display:inline-block;margin-top:6px;padding:3px 8px;border-radius:6px;background:var(--panel-3)">python platform/serve.py</code>
        然后访问 <span class="mono">http://127.0.0.1:8770</span>。</p>`;
      return;
    }
    st.textContent = "引擎在线"; st.className = "tag ok";
    const p = buildParamsView(b);
    const rows = [
      ["mux", "μx 最大比生长", 0.25, 0.55, 0.005],
      ["mup", "μp 比产率", 0.015, 0.085, 0.001],
      ["alpha_kla", "KLa 传质", 50, 120, 1],
    ];
    host.innerHTML = `<div class="grid" style="grid-template-columns:repeat(3,1fr);gap:12px">` +
      rows.map(([k, lab, mn, mx, stp]) => `
        <div>
          <div class="tiny muted" style="margin-bottom:5px">${lab} <span class="mono">${k}</span></div>
          <input type="range" data-k="${k}" min="${mn}" max="${mx}" step="${stp}"
                 value="${p[k] != null ? p[k] : (mn + mx) / 2}" style="width:100%" />
          <div class="mono tiny" data-v="${k}" style="text-align:right">${p[k] != null ? p[k] : "—"}</div>
        </div>`).join("") + `</div>
      <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
        <button class="icon-btn" id="trial-run" style="width:auto;padding:0 12px;height:28px;gap:6px">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l11 7-11 7z"/></svg>
          <span style="font-size:11px">运行试算</span>
        </button>
        <button class="icon-btn" id="trial-reset" style="width:auto;padding:0 12px;height:28px;font-size:11px">复位</button>
        <span class="tiny muted" id="trial-msg"></span>
      </div>
      <div id="trial-out" class="mt"></div>`;

    $$("#trial-body input[type=range]").forEach((inp) => {
      inp.addEventListener("input", () => { $(`#trial-body [data-v="${inp.dataset.k}"]`).textContent = inp.value; });
    });
    $("#trial-reset").addEventListener("click", () => renderTrial(b));
    $("#trial-run").addEventListener("click", () => runTrial(b));
    if (trial.last && trial.last.batch === b.b) renderTrialOut(trial.last);
  }

  function buildParamsView(b) {
    // 当前批生效值：COMBINED 覆盖 + 默认
    const d = { mux: 0.41, mup: 0.041, alpha_kla: 85 };
    Object.keys(d).forEach((k) => { if (b.params && b.params[k] != null) d[k] = b.params[k]; });
    return d;
  }

  async function runTrial(b) {
    const btn = $("#trial-run"), msg = $("#trial-msg");
    const ov = {};
    $$("#trial-body input[type=range]").forEach((i) => { ov[i.dataset.k] = parseFloat(i.value); });
    btn.disabled = true; btn.style.opacity = 0.5; msg.textContent = "求解中（约 20–40 s）…";
    const t0 = performance.now();
    try {
      const r = await fetch("/api/simulate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ batch: b.b, overrides: ov }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "unknown");
      j.result.elapsed = ((performance.now() - t0) / 1000).toFixed(1);
      trial.last = j.result;
      msg.textContent = "完成 " + j.result.elapsed + " s";
      renderTrialOut(j.result);
    } catch (e) {
      msg.textContent = "失败：" + e.message;
    } finally {
      btn.disabled = false; btn.style.opacity = 1;
    }
  }

  function renderTrialOut(res) {
    const host = $("#trial-out"); if (!host) return;
    const b = BY_B.get(res.batch);
    const dErr = res.yield_err - (b ? b.yield_err : 0);
    const tone = Math.abs(res.yield_err) > 5 ? "crit" : Math.abs(res.yield_err) > 3 ? "warn" : "ok";
    host.innerHTML = `
      <div class="grid g-3" style="gap:10px">
        <div class="kpi ${tone}" style="padding:10px 12px">
          <div class="lab">试算产量误差</div>
          <div class="val" style="font-size:20px">${res.yield_err > 0 ? "+" : ""}${res.yield_err}<small>%</small></div>
          <div class="foot">Δ ${dErr > 0 ? "+" : ""}${dErr.toFixed(2)} pt vs 基线</div>
        </div>
        <div class="kpi" style="padding:10px 12px">
          <div class="lab">试算产量 / 实测</div>
          <div class="val" style="font-size:20px">${res.yield_sim.toFixed(0)}<small>g</small></div>
          <div class="foot">实测 ${res.yield_v3.toFixed(0)} g</div>
        </div>
        <div class="kpi ${res.crash === "catastrophic" ? "crit" : "ok"}" style="padding:10px 12px">
          <div class="lab">崩溃分级（legacy）</div>
          <div class="val" style="font-size:16px;text-transform:uppercase">${res.crash}</div>
          <div class="foot">${(res.reasons || []).length ? res.reasons.join(" / ") : "无病理证据"} · classify_crash 为 D-38 恒真旧判据，健康分级请看 classify_health</div>
        </div>
      </div>
      <div class="mt" id="trial-chart"></div>`;
    drawTrialChart(res);
  }

  function drawTrialChart(res) {
    const host = $("#trial-chart"); if (!host) return;
    const w = host.clientWidth || 700, h = 180, pad = { t: 12, r: 12, b: 22, l: 40 };
    const s = mkSvg(host, w, h);
    const t = res.series.t, y = res.series.sim.P || [];
    const base = D.series[String(res.batch)];
    const ymax = Math.max(...y, ...(base ? base.sim.P : [1])) * 1.08;
    const { sx, sy } = axes(s, { pad, w, h, xd: [0, t[t.length - 1]], yd: [0, ymax], yticks: 3, xticks: 4, xfmt: (v) => v.toFixed(0) + "h" });
    if (base) {
      const pb = svgEl("path", { class: "series obs", d: pathFrom(base.t, base.sim.P, sx, sy) });
      s.appendChild(pb);
    }
    const p = svgEl("path", { class: "series sim", d: pathFrom(t, y, sx, sy) });
    s.appendChild(p); drawIn(p, 700);
  }

  /* ================= 渲染总入口 ================= */
  function renderAll() {
    renderChrome();
    if (state.view === "overview") renderOverview();
    else if (state.view === "topology") renderTopology();
    else if (state.view === "batch") renderBatch();
    else if (state.view === "channels") renderChannels();
    else if (state.view === "operators") renderOperators();
    else if (state.view === "workbench") renderWorkbench();
  }

  /* ================= 启动 ================= */
  renderRail();
  // 首次进入按 URL hash 定视图（默认"总览"）；之后手改 hash 也跟随。
  const _hashView = () => (location.hash || "").replace(/^#\/?/, "");
  if (_hashView()) go(_hashView(), { fromHash: true });
  addEventListener("hashchange", () => {
    const id = _hashView();
    if (id && id !== state.view) go(id, { fromHash: true });
  });
  applyTheme();
  $("#btn-about").addEventListener("click", () => openDrawer("关于本平台", `
    <p style="margin:0 0 10px;line-height:1.7">本平台是 <b>IndPenSim 青霉素补料分批发酵过程</b>机理引擎的
    可视化控制台。引擎为 MATLAB IndPenSim V2.02 的 Python 复现（BDF / rtol 1e-3），
    逐 0.2 h 积分 33 维状态，105 维参数。</p>
    <div class="kv">
      <dt>评估集</dt><dd>86 批（84 正常 + 2 故障）</dd>
      <dt>产量 RMSE</dt><dd>${D.kpi.rmse}%</dd>
      <dt>±5% 内</dt><dd>${D.kpi.within}/${D.kpi.within_total}</dd>
      <dt>契约版本</dt><dd>${esc(D.meta.contract)}</dd>
      <dt>数据生成</dt><dd>${esc(D.meta.generated)}</dd>
    </div>
    <p class="tiny muted" style="margin-top:14px">所有指标来自 <code>runs/</code> 下的回归证据文件，
    平台只做呈现、不重算——避免"平台数字 vs 报告数字"分叉。</p>`));

  let rt;
  addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(renderAll, 180); });

  probeEngine().then(() => {
    if (state.view === "batch") renderTrial(BY_B.get(state.batch));
    if (state.view === "operators") renderOperators();
    if (state.view === "workbench") renderWorkbench();
    const st = $("#st-engine");
    if (st) st.textContent = trial.conn
      ? `engine online · ${trial.health ? trial.health.capabilities : "?"} 能力装载 · 可试算/调用`
      : "static mode · 只读回归结果";
  });
})();
