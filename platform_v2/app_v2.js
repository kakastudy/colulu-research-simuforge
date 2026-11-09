/* ==========================================================================
   平台 v2 — 仿真计算平台 · 前端

   与 platform/app.js 的根本区别：
     旧平台 = 看已完成的东西（86 批回归、通道健康、算子清单）
     本平台 = 驱动引擎算东西（配工况 → 提交 → 轮询 → 读轨迹）

   所有数值都来自服务端**实时调用引擎**，前端不预烘焙任何仿真结果。
   ========================================================================== */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const num = (v, d) => (v === null || v === undefined || Number.isNaN(v)
    ? "—" : Number(v).toFixed(d === undefined ? 2 : d));
  const fmt = (v, d) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: d === undefined ? 2 : d }));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  const API = "/api2";
  const store = {
    get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* file:// 下不可用 */ } },
  };

  const state = {
    view: "bench",
    theme: store.get("ferm-theme-v2", "dark"),
    batches: [],
    catalog: null,
    responses: [],
    overrides: {},          // 当前工况覆盖
    batch: null,
    job: null,              // 当前作业
    jobTimer: null,
    result: null,           // 当前结果
    v3: null,               // 当前批的 V3 实测
    traceCh: ["P", "X", "S"],
    traceMode: "sim",       // sim | both
    chGrpOpen: new Set(),   // 通道分组展开状态（默认全折叠）
    pickerOpen: store.get("ferm-picker-v2", "0") === "1",  // 通道选项面板展开态（默认收起）
    runT0: null,            // 本次仿真开始时刻（进度条用）
    runTimer: null,
    runExpected: null,      // 预计耗时（从历史学习）
    runStride: null,
    history: [],            // 运算历史摘要（倒序，最新在前）
    historyOpen: store.get("ferm-hist-open-v2", "1") === "1",
    historyAll: false,      // 是否展开全部历史
    historyBusy: false,     // 回放请求进行中
    viewSource: null,       // 当前结果的来源：{id, created_at, kind: history|live, rerun_of}
    rerunOf: null,          // 下一次「重新计算」标注重算自哪条历史
    scanAxes: [],
    scanJob: null,
    scanTimer: null,
    scanResult: null,
    presOpen: new Set(["dynamics"]),
  };

  /* ================= 主题 ================= */
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    store.set("ferm-theme-v2", state.theme);
  }
  applyTheme();
  $("#btn-theme").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    applyTheme();
    if (state.result) drawTrace();
  });

  /* ================= tooltip ================= */
  const tip = $("#tip");
  function showTip(html, ev) {
    tip.innerHTML = html;
    tip.dataset.on = "true";
    const r = tip.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  const hideTip = () => { tip.dataset.on = "false"; };

  /* ================= 抽屉 ================= */
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

  /* ================= 视图路由 ================= */
  const VIEWS = [
    { id: "bench", label: "仿真台", icon: '<path d="M4 19V9m5 10V5m5 14v-7m5 7V11"/>' },
    { id: "scan", label: "扫描", icon: '<path d="M3 17l5-6 4 4 4-8 5 6"/><path d="M3 21h18"/>' },
    { id: "presets", label: "工况库", icon: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>' },
    { id: "operators", label: "算子", icon: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>' },
    { id: "engine", label: "引擎", icon: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>' },
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

  function go(id) {
    if (!VIEWS.some((v) => v.id === id)) id = "bench";
    state.view = id;
    $$("#rail .rail-btn").forEach((b) => b.setAttribute("aria-current", String(b.dataset.view === id)));
    VIEWS.forEach((v) => { $("#v-" + v.id).hidden = v.id !== id; });
    closeDrawer();
    if (location.hash !== "#" + id) {
      try { history.replaceState(null, "", "#" + id); } catch (e) { /* file:// 受限 */ }
    }
    const el = $("#v-" + id);
    if (el) { el.style.animation = "none"; void el.offsetWidth; el.style.animation = ""; }
    if (id === "scan") renderScanAxes();
    if (id === "presets") renderPresets();
    if (id === "engine") refreshEngine();
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

  /* ================= 通道元数据 ================= */
  const CH_META = {
    S: { label: "底物", unit: "g/L", grp: "state" },
    P: { label: "青霉素", unit: "g/L", grp: "state" },
    X: { label: "生物量", unit: "g/L", grp: "state" },
    PAA: { label: "前体", unit: "mg/L", grp: "state" },
    NH3: { label: "氨氮", unit: "mg/L", grp: "state" },
    DO2: { label: "溶氧", unit: "mg/L", grp: "state" },
    pH: { label: "pH", unit: "-", grp: "state" },
    pH_openloop: { label: "pH(开环)", unit: "-", grp: "diag" },
    pH_pre: { label: "pH(解算)", unit: "-", grp: "diag" },
    T: { label: "温度", unit: "K", grp: "state" },
    V: { label: "体积", unit: "L", grp: "state" },
    Wt: { label: "重量", unit: "kg", grp: "state" },
    vis: { label: "黏度", unit: "cP", grp: "state" },
    Q: { label: "发热量", unit: "-", grp: "state" },
    CO2d: { label: "溶解CO₂", unit: "g/L", grp: "gas" },
    CO2outgas: { label: "尾气CO₂", unit: "%", grp: "gas" },
    O2: { label: "尾气O₂", unit: "%", grp: "gas" },
    OUR: { label: "摄氧速率", unit: "g/min", grp: "gas" },
    CER: { label: "释碳速率", unit: "g/h", grp: "gas" },
    mux: { label: "比生长速率", unit: "1/h", grp: "kin" },
    mup: { label: "比产物速率", unit: "1/h", grp: "kin" },
    A0: { label: "菌丝区 A0", unit: "g/L", grp: "myc" },
    A1: { label: "菌丝区 A1", unit: "g/L", grp: "myc" },
    A3: { label: "菌丝区 A3", unit: "g/L", grp: "myc" },
    A4: { label: "菌丝区 A4", unit: "g/L", grp: "myc" },
    A_t1: { label: "老化菌丝", unit: "g/L", grp: "myc" },
    Fg: { label: "通气量", unit: "L/h", grp: "op" },
    Fs: { label: "糖补料", unit: "L/h", grp: "op" },
    Foil: { label: "油补料", unit: "L/h", grp: "op" },
    Fpaa: { label: "前体补料", unit: "L/h", grp: "op" },
    Fa: { label: "酸补料", unit: "L/h", grp: "op" },
    Fb: { label: "碱补料", unit: "L/h", grp: "op" },
    Fc: { label: "冷却水", unit: "L/h", grp: "op" },
    Fh: { label: "热水", unit: "L/h", grp: "op" },
    Fw: { label: "补水", unit: "L/h", grp: "op" },
    RPM: { label: "搅拌转速", unit: "RPM", grp: "op" },
    Fremoved: { label: "放罐流量", unit: "L/h", grp: "op" },
    pressure: { label: "罐压", unit: "bar", grp: "op" },
    NH3_shots: { label: "氨补加", unit: "-", grp: "op" },
  };
  const CH_COLOR = {
    P: "var(--accent)", X: "var(--accent-2)", S: "var(--ok)", DO2: "var(--warn)",
    CO2d: "var(--crit)", pH: "#f0997b", T: "#ed93b1", PAA: "#97c459", vis: "#85b7eb",
  };
  const chColor = (k) => CH_COLOR[k] || "var(--dim)";

  /* ================= API ================= */
  async function api(path, opts) {
    const r = await fetch(API + path, opts);
    let j;
    try { j = await r.json(); } catch (e) { throw new Error("响应不是 JSON（服务可能未启动）"); }
    if (!r.ok || j.ok === false) {
      const err = new Error(j.error || ("HTTP " + r.status));
      err.code = j.code; err.payload = j;
      throw err;
    }
    return j;
  }
  const post = (path, body) => api(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

  /* ================= 引导 ================= */
  async function boot() {
    renderRail();
    try {
      const h = await api("/health");
      state.batches = h.batches || [];
      $("#brand-sub").textContent = `青霉素补料分批发酵罐 · ${h.n_batches} 批黄金集`;
      $("#st-build").textContent = "build " + h.build + " · " + h.catalog_n + " 参数键";
      $("#st-dot").className = "dot";
      $("#st-engine").textContent = "engine ready";
      updateQueueNote(h.queue);
    } catch (e) {
      $("#st-dot").className = "dot err";
      $("#st-engine").textContent = "engine unreachable: " + e.message;
      return;
    }
    fillBatchSelects();
    try {
      const c = await api("/catalog");
      state.catalog = c.catalog;
      renderParamGroups();
    } catch (e) {
      console.error("catalog", e);
    }
    try {
      const r = await api("/responses");
      state.responses = r.responses || [];
      $("#scan-response").innerHTML = state.responses
        .map((x) => `<option value="${x.key}">${esc(x.label)}${x.unit ? " (" + x.unit + ")" : ""}</option>`).join("");
      updateRespDesc();
    } catch (e) { /* 非关键 */ }

    renderPresets();
    renderOperators();
    pollJobs();
    setInterval(pollJobs, 4000);
    // 运算历史：启动时加载（服务重启后磁盘记录仍在），低频轮询兼顾多标签页
    refreshHistory();
    setInterval(refreshHistory, 20000);
    applyHistoryFold();

    const hash = location.hash.replace("#", "");
    if (VIEWS.some((v) => v.id === hash)) state.view = hash;
    go(state.view);
  }

  function fillBatchSelects() {
    const opts = state.batches.map((b) => `<option value="${b}">批 #${b}</option>`).join("");
    $("#sel-batch").innerHTML = opts;
    $("#scan-batch").innerHTML = opts;
    // 默认选一批"典型正常批"
    state.batch = state.batches.includes(8) ? 8 : (state.batches[0] || null);
    if (state.batch) { $("#sel-batch").value = state.batch; $("#scan-batch").value = state.batch; }
  }

  /* ================= 参数面板 ================= */
  let prmQuery = "";

  function renderParamGroups() {
    const cat = state.catalog;
    if (!cat) return;
    const q = prmQuery.trim().toLowerCase();
    const host = $("#param-groups");
    const groups = cat.groups.map((g) => {
      // 搜索：按名称 / 键 / 说明 / 分组名过滤
      const params = g.params.filter((p) => {
        if (!q) return true;
        return (p.label || "").toLowerCase().includes(q)
          || (p.key || "").toLowerCase().includes(q)
          || (p.desc || "").toLowerCase().includes(q)
          || (g.label || "").toLowerCase().includes(q);
      });
      return { g, params };
    }).filter((x) => x.params.length);

    if (!groups.length) {
      host.innerHTML = `<div class="tiny muted" style="padding:14px;text-align:center">
        没有匹配「${esc(prmQuery)}」的参数</div>`;
      return;
    }

    host.innerHTML = groups.map(({ g, params }) => {
      const rows = params.map((p) => paramRow(p)).join("");
      const open = q ? true : state.presOpen.has(g.id);
      return `<div class="grp ${open ? "open" : ""}" data-g="${g.id}">
        <div class="grp-h">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" style="color:var(--dim-2)">
            <path d="M9 6l6 6-6 6"/>
          </svg>
          <span class="nm">${esc(g.label)}</span>
          <span class="cnt">${params.length}${params.length !== g.params.length ? "/" + g.params.length : ""}</span>
          <span class="desc">${esc(g.desc)}</span>
        </div>
        <div class="grp-b">${rows}</div>
      </div>`;
    }).join("");

    $$("#param-groups .grp-h").forEach((h) =>
      h.addEventListener("click", () => {
        const g = h.parentElement;
        g.classList.toggle("open");
        const gid = g.dataset.g;
        if (g.classList.contains("open")) state.presOpen.add(gid); else state.presOpen.delete(gid);
      }));

    $$("#param-groups [data-p]").forEach((el) => bindParam(el));
    updateOverrideCount();
  }

  $("#prm-search").addEventListener("input", (e) => {
    prmQuery = e.target.value;
    renderParamGroups();
  });

  function paramRow(p) {
    const k = p.key;
    const v = state.overrides[k];
    const isSet = v !== undefined;
    let ctl;
    if (p.control === "select") {
      const opts = selectOptions(p);
      ctl = `<select class="inp" data-p="${k}" data-ctl="select">${opts}</select>`;
    } else if (p.control === "json") {
      ctl = `<textarea class="inp" data-p="${k}" data-ctl="json" placeholder='{"k": v} 或 [[t,amp],…]'>${isSet ? esc(JSON.stringify(v)) : ""}</textarea>`;
    } else if (p.control === "number") {
      ctl = `<input class="inp" type="number" step="any" data-p="${k}" data-ctl="number" value="${isSet ? esc(v) : ""}" placeholder="${p.default !== null && p.default !== undefined ? esc(p.default) : "默认"}" />`;
    } else {
      const lo = p.low !== null && p.low !== undefined ? p.low : 0;
      const hi = p.high !== null && p.high !== undefined ? p.high : lo + 1;
      const cur = isSet ? v : (p.default !== null && p.default !== undefined ? p.default : lo);
      ctl = `<input type="range" data-p="${k}" data-ctl="slider" min="${lo}" max="${hi}" step="${(hi - lo) / 200}" value="${cur}" />
             <input class="num" data-p="${k}" data-ctl="num" value="${cur}" />`;
    }
    return `<div class="prm ${isSet ? "changed" : ""}" data-row="${k}">
      <div class="prm-h">
        <span class="nm">${esc(p.label)}</span>
        <span class="unit">${esc(p.unit || "")}</span>
        <span class="key">${esc(k)}</span>
      </div>
      <div class="ctl">${ctl}</div>
      <div class="desc">${esc(p.desc || "")}</div>
    </div>`;
  }

  function selectOptions(p) {
    const k = p.key;
    const special = {
      ode_method: ["BDF", "Radau", "LSODA"],
      ph_mode: ["model", "measured"],
      ph_rp_mode: ["net", "prod_only", "all_acid"],
      death_mode: ["0", "1"],
      ph_fix: ["0", "1"],
      x0_force: ["0", "1"],
      ph_hyd_acid: ["0", "1"],
      paa_degrad_inverse_gate: ["0", "1"],
      dist_flag: ["0", "1"],
    };
    let vals = special[k];
    if (!vals) {
      if (k === "fault_type") vals = ["0", "1", "2", "3"];
      else if (p.default !== null && p.default !== undefined) vals = [String(p.default)];
      else vals = ["0"];
    }
    return vals.map((v) => {
      const sel = (state.overrides[k] !== undefined && String(state.overrides[k]) === v) ||
        (state.overrides[k] === undefined && String(p.default) === v);
      return `<option value="${esc(v)}" ${sel ? "selected" : ""}>${esc(v === "0" ? "关/无" : v)}</option>`;
    }).join("");
  }

  function bindParam(el) {
    const k = el.dataset.p;
    const ctl = el.dataset.ctl;
    const ev = ctl === "json" ? "change" : "input";
    el.addEventListener(ev, () => {
      let v = el.value;
      if (v === "") { delete state.overrides[k]; }
      else if (ctl === "slider" || ctl === "num" || ctl === "number") {
        const f = parseFloat(v);
        if (Number.isNaN(f)) return;
        v = f;
        // 联动同一行的滑块/数字框
        $$(`[data-p="${k}"]`).forEach((o) => { if (o !== el && o.type !== "range") o.value = v; });
        if (el.type === "range") {
          const numEl = $$(`[data-p="${k}"]`).find((o) => o.type !== "range");
          if (numEl) numEl.value = v;
        }
      } else if (ctl === "select") {
        v = /^-?\d+$/.test(v) ? parseInt(v, 10) : v;
      } else if (ctl === "json") {
        try { v = JSON.parse(v); } catch (e) {
          el.style.borderColor = "var(--crit)";
          setTimeout(() => { el.style.borderColor = ""; }, 1400);
          return;
        }
      }
      if (v === "" || v === undefined) delete state.overrides[k];
      else state.overrides[k] = v;
      const row = $(`[data-row="${k}"]`);
      if (row) row.classList.toggle("changed", state.overrides[k] !== undefined);
      updateOverrideCount();
      updateFingerprint();
    });
  }

  function updateOverrideCount() {
    const n = Object.keys(state.overrides).length;
    const el = $("#ov-count");
    el.textContent = n + " 项";
    el.className = n ? "tag acc" : "tag mute";
  }

  function updateFingerprint() {
    const keys = Object.keys(state.overrides).sort();
    $("#cfg-fp").textContent = keys.length ? keys.length + " 项覆盖" : "基准工况";
  }

  /* ================= 预设工况 ================= */
  const PRESETS = [
    {
      id: "base", name: "基准工况", desc: "黄金集批级标定参数，不加任何覆盖。作为一切对比的参照系。",
      group: "参照", ov: {},
    },
    {
      id: "dist_tcin", name: "冷却水扰动 +10K", desc: "R12.9：distTcin=+10 可把 CO2d 降到 7.3–7.5 绕过崩溃阈值，副作用是提高生长率。",
      group: "机理", ov: { dist_tcin_asym: 10 }, note: "副作用：μe 上升 ⇒ 产量偏高（反问题批次更严重）",
    },
    {
      id: "ms_low", name: "低维持系数 m_s=0.012", desc: "R12.9.1：降低维持项使残糖积累，可修复「过度产 P」批次，但与 CO2d 正反馈耦合。",
      group: "机理", ov: { m_s: 0.012 }, note: "耦合：低 m_s → S 积累 → 更高 CO2 → 可能崩溃",
    },
    {
      id: "ms_schedule", name: "时变 m_s 调度", desc: "R12.10：早期高 m_s 防 CO2d 崩溃、晚期低 m_s 匹配产量，解耦 m_s–CO2d。",
      group: "机理", ov: { m_s_schedule: [[140, 0.018]] },
    },
    {
      id: "kla_drop", name: "KLa 阶跃降 45%", desc: "R157 模式 kla_step：60–150h 通气能力下降后恢复。预期 DO2↓、残糖↑、产物↓。",
      group: "故障", ov: { fault_type: 1, fault_start: 60, fault_end: 150, fault_magnitude: 0.45 },
    },
    {
      id: "kla_ramp", name: "KLa 渐进衰减", desc: "R157 模式 kla_ramp：60→200h 线性衰减到 −60%，模拟结垢渐进过程。",
      group: "故障", ov: { fault_type: 1, fault_start: 60, fault_end: 200, fault_magnitude: 0.60 },
    },
    {
      id: "feed_hold", name: "补料中断", desc: "R157 模式 feed_hold：100–180h 补料降 90%。注意整批残糖反而升高（恢复期欠消耗）。",
      group: "故障", ov: { fault_type: 3, fault_start: 100, fault_end: 180, fault_magnitude: 0.90 },
    },
    {
      id: "ph_drift", name: "加碱能力漂移", desc: "R157 模式 ph_drift：80–220h 等效持续注酸渐强，pH 缓慢下行。",
      group: "故障", ov: { fault_type: 2, fault_start: 80, fault_end: 220, fault_magnitude: 0.35 },
    },
    {
      id: "fs_scale", name: "进料倍率 Fs×1.05", desc: "R155：进料可行域 < ±1%，且标定点站在墙上。±5% 会触发双稳态崩塌。",
      group: "操作", ov: { mv_scales: { Fs: 1.05 } }, note: "有效域警告：Fs 倍率 >0.97 附近有双稳态分岔（批 8 特异）",
    },
    {
      id: "phfix", name: "pH 链式法则修正", desc: "R156/D-55：修正 pH≥7 basic 分支的数值病态，把 5 批 pH 钳位批的末值从 3.00 拉回 6.6。",
      group: "数值", ov: { ph_fix: 1 }, note: "改变引擎行为 ⇒ 与零回归基线不可比",
    },
    {
      id: "mup_growth", name: "生长耦合产素 α=0.3", desc: "R153：补 Pirt 双相里缺的 α·μ 项，修 60–120h 产素缺口。代价是产量耦合上升。",
      group: "机理", ov: { mu_p_growth: 0.3 }, note: "形状与产量 1:1 耦合：λ=0.3 时 60–120h 从 −6.4% 修到 −3.3%，但产量受损",
    },
    {
      id: "dist_all", name: "8 路时变扰动", desc: "打开 MATLAB 同款低通随机扰动通道（τ=40h）。注意：这是确定性代理，非 MATLAB 逐位复现。",
      group: "机理", ov: { dist_flag: 1 }, note: "MATLAB rng 种子未记录 ⇒ 逐位复现原理上不可达（R162 oq#36）",
    },
  ];

  function renderPresets() {
    const groups = {};
    PRESETS.forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });
    $("#preset-grid").innerHTML = Object.keys(groups).map((g) => `
      <div class="panel">
        <div class="panel-h"><h2>${esc(g)}</h2></div>
        <div class="panel-b" style="display:flex;flex-direction:column;gap:9px">
          ${groups[g].map((p) => `
            <div style="border:1px solid var(--line);border-radius:var(--radius-sm);padding:9px 11px">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <b style="font-size:12px;font-weight:500">${esc(p.name)}</b>
                <div class="spacer"></div>
                <button class="btn sm" data-preset="${p.id}">载入</button>
              </div>
              <div class="tiny muted" style="line-height:1.65">${esc(p.desc)}</div>
              ${p.note ? `<div class="note warn" style="margin-top:7px">${esc(p.note)}</div>` : ""}
              ${Object.keys(p.ov).length ? `<div class="mono tiny" style="margin-top:6px;color:var(--accent)">${esc(JSON.stringify(p.ov))}</div>` : ""}
            </div>`).join("")}
        </div>
      </div>`).join("");

    $$("#preset-grid [data-preset]").forEach((b) =>
      b.addEventListener("click", () => {
        const p = PRESETS.find((x) => x.id === b.dataset.preset);
        state.overrides = JSON.parse(JSON.stringify(p.ov));
        renderParamGroups();
        updateFingerprint();
        go("bench");
        $("#bench-state").textContent = "已载入：" + p.name;
      }));
  }

  $("#sel-preset").innerHTML = `<option value="">— 自定义 —</option>` +
    PRESETS.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#sel-preset").addEventListener("change", (e) => {
    const p = PRESETS.find((x) => x.id === e.target.value);
    if (!p) return;
    state.overrides = JSON.parse(JSON.stringify(p.ov));
    renderParamGroups();
    updateFingerprint();
  });

  $("#btn-clear").addEventListener("click", () => {
    state.overrides = {};
    prmQuery = "";
    $("#prm-search").value = "";
    renderParamGroups(); updateFingerprint();
  });
  $("#btn-reset").addEventListener("click", () => {
    state.overrides = {};
    prmQuery = "";
    $("#prm-search").value = "";
    $("#sel-preset").value = "";
    renderParamGroups(); updateFingerprint();
    $("#bench-state").textContent = "已恢复基准工况";
  });

  /* ================= 运算历史（R168.3） =================
     语义必须分清，否则用户会以为"点一下就又算了 80 秒"：
       · 查看结果  = GET 一条落盘记录 → 直接回放，零计算
       · 重新计算  = POST /run?force=true → 忽略缓存真实重算 → 新增一条留痕
       · 运行仿真  = 常规提交，命中缓存时复用已有结果（不新增留痕）
     每条记录都带执行时间，服务重启后磁盘记录仍在。 */
  const HIST_SHOWN = 6;
  const fmtTime = (s) => String(s || "—").replace("T", " ").slice(0, 19);
  const histNote = (txt, ms) => {
    const el = $("#hist-note");
    if (!el) return;
    el.textContent = txt;
    if (ms) setTimeout(() => {
      el.textContent = "每次真实运算自动留痕 · 点击「查看结果」直接回放，无需重算";
    }, ms);
  };

  function applyHistoryFold() {
    const body = $("#hist-body"), b = $("#btn-hist-toggle");
    if (!body || !b) return;
    body.hidden = !state.historyOpen;
    b.setAttribute("aria-expanded", String(state.historyOpen));
    b.textContent = state.historyOpen ? "收起 ▴" : "展开 ▾";
  }

  async function refreshHistory() {
    try {
      const r = await api("/history");
      state.history = r.records || [];
      renderHistory();
    } catch (e) { /* 服务未就绪时静默，下次轮询再试 */ }
  }

  function histCard(rec) {
    const s = rec.summary || {};
    const active = state.viewSource && state.viewSource.id === rec.id;
    const failed = rec.state !== "done" || !rec.has_result;
    const e = s.yield_err_pct;
    const tone = failed ? "crit" : (e !== null && e !== undefined && Math.abs(e) <= 5 ? "ok" : "warn");
    const nOv = Object.keys(rec.overrides || {}).length;
    const label = failed ? "失败" : (rec.force ? (rec.rerun_of ? "重算" : "强制重算") : "完成");
    return `<div class="hcard ${active ? "active" : ""} ${failed ? "failed" : ""}" data-hid="${esc(rec.id)}">
      <div class="hcard-t"><span class="tm">${esc(fmtTime(rec.created_at))}</span>
        <span class="tag ${tone}">${label}</span></div>
      <div class="hcard-m">批 #${esc(rec.batch ?? "—")} · 抽稀 ${esc(rec.stride ?? "—")}× · ${nOv} 项覆盖 · ${num(rec.elapsed_s, 1)}s</div>
      <div class="hcard-v">${failed
        ? `<span style="color:var(--crit)">${esc(rec.code || rec.error || "运算失败")}</span>`
        : `误差 <b>${num(e, 2)}%</b> · ${esc(s.health_level || "—")} · ${esc(s.n_channels ?? "—")} 通道`}</div>
      ${rec.rerun_of ? `<div class="hcard-x">重算自 …${esc(String(rec.rerun_of).slice(-12))}</div>` : ""}
      <div class="hcard-a">
        ${failed ? '<span class="tiny muted" style="flex:1">无结果可回放</span>'
                 : '<button class="btn sm" data-hview>查看结果</button>'}
        <button class="btn sm" data-hrerun title="按该次工况忽略缓存真实重算一次">重算</button>
        <button class="icon-btn" data-hdel title="删除该条留痕" aria-label="删除">×</button>
      </div>
    </div>`;
  }

  function renderHistory() {
    const n = state.history.length;
    const el = $("#hist-n");
    if (el) { el.textContent = n ? `共 ${n} 次` : "暂无记录"; el.className = n ? "tag acc" : "tag mute"; }
    const list = $("#hist-list");
    if (!list) return;
    if (!n) {
      list.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <div class="ic"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></div>
        <div class="t">还没有运算留痕</div>
        <div class="d">点「运行仿真」算一次，结果会连同执行时间自动存到这里；
          服务重启后记录仍在，之后回看不必重算。</div></div>`;
    } else {
      const shown = state.historyAll ? state.history : state.history.slice(0, HIST_SHOWN);
      list.innerHTML = shown.map(histCard).join("");
    }
    const more = $("#btn-hist-more");
    if (more) {
      more.hidden = n <= HIST_SHOWN || state.historyAll;
      more.textContent = `显示全部 ${n} 条`;
    }
  }

  // 事件委托：重绘卡片后不需要重新绑定
  $("#hist-list").addEventListener("click", (ev) => {
    const card = ev.target.closest(".hcard");
    if (!card) return;
    const id = card.dataset.hid;
    if (ev.target.closest("[data-hdel]")) return deleteHistory(id);
    if (ev.target.closest("[data-hrerun]")) return rerunFromHistory(id);
    if (ev.target.closest("[data-hview]") || !ev.target.closest("button")) return viewHistory(id);
  });
  $("#btn-hist-refresh").addEventListener("click", refreshHistory);
  $("#btn-hist-more").addEventListener("click", () => { state.historyAll = true; renderHistory(); });
  $("#btn-hist-toggle").addEventListener("click", () => {
    state.historyOpen = !state.historyOpen;
    store.set("ferm-hist-open-v2", state.historyOpen ? "1" : "0");
    applyHistoryFold();
  });

  /** 把某次运算的工况回填到左栏 —— 这样「重算」用的确实是那一次的参数。 */
  function applyRecordConfig(rec) {
    const b = Number(rec.batch);
    if (b && state.batches.map(Number).includes(b)) {
      $("#sel-batch").value = String(b);
      state.batch = b;
    }
    if (rec.stride) $("#sel-stride").value = String(rec.stride);
    state.overrides = Object.assign({}, rec.overrides || {});
    renderParamGroups();       // 内部有 catalog 保护，且会刷新覆盖计数
    updateFingerprint();
  }

  /** 查看历史：只读磁盘记录并回放，绝不提交新作业。 */
  async function viewHistory(id) {
    if (state.historyBusy) return;
    state.historyBusy = true;
    histNote("正在读取该次运算的落盘结果…");
    try {
      const r = await api("/history/" + encodeURIComponent(id) + "?full=1");
      const rec = r.record || {};
      if (!rec.has_result || !rec.result || !rec.result.ok) {
        histNote("该次运算失败，没有可回放的结果", 3500);
        return;
      }
      applyRecordConfig(rec);
      state.result = rec.result;
      state.viewSource = { id: rec.id, kind: "history", created_at: rec.created_at,
                           rerun_of: rec.rerun_of };
      state.rerunOf = rec.id;
      renderResult(rec.result);
      loadV3(Number(rec.batch) || state.batch);
      $("#bench-state").textContent = "历史回放 · " + fmtTime(rec.created_at);
      $("#st-dot").className = "dot";
      renderHistory();
      histNote("已回放（零计算）· 如需重新执行请点「重新计算」", 4000);
    } catch (e) {
      histNote("读取失败：" + e.message, 4000);
    } finally {
      state.historyBusy = false;
    }
  }

  async function deleteHistory(id) {
    try {
      await api("/history/" + encodeURIComponent(id), { method: "DELETE" });
      if (state.viewSource && state.viewSource.id === id) state.viewSource = null;
      await refreshHistory();
      histNote("已删除该条留痕", 2500);
    } catch (e) { histNote("删除失败：" + e.message, 4000); }
  }

  async function rerunFromHistory(id) {
    const rec = state.history.find((x) => x.id === id);
    if (!rec) return;
    applyRecordConfig(rec);
    await rerunSim(id);
  }

  /* ================= 运行仿真 ================= */
  $("#btn-run").addEventListener("click", runSim);
  $("#btn-rerun").addEventListener("click", () => rerunSim(
    state.viewSource && state.viewSource.kind === "history" ? state.viewSource.id : null));

  /* ---- 时间进度条：引擎不回报积分进度 ⇒ 用「已用时间 vs 预计时长」逼近 ----
     预计时长从 localStorage 学习（同 stride 的上次实际耗时），无历史用默认值；
     完成后回写实际耗时 ⇒ 越用越准。条到 95% 封顶，超时改文案而不是撒谎到 100%。 */
  function benchExpected(stride) {
    const v = parseFloat(store.get("ferm-exp-" + stride, ""));
    return (v && v >= 3) ? v : (stride >= 12 ? 28 : 48);
  }
  function startBenchProg(stride) {
    state.runT0 = Date.now();
    state.runStride = stride;
    state.runExpected = benchExpected(stride);
    const p = $("#bench-prog");
    if (p) p.hidden = false;
    clearInterval(state.runTimer);
    state.runTimer = setInterval(tickBenchProg, 300);
    tickBenchProg();
  }
  function setBenchProgTag(txt, cls) {
    const tag = $("#bench-prog-tag");
    if (tag) { tag.textContent = txt; tag.className = cls || "tag acc"; }
  }
  function tickBenchProg() {
    if (!state.runT0) return;
    const el = (Date.now() - state.runT0) / 1000;
    const exp = state.runExpected || 45;
    const bar = $("#bench-prog-bar"), txt = $("#bench-prog-txt");
    if (bar) bar.style.width = Math.min(95, 100 * el / exp) + "%";
    if (txt) {
      txt.textContent = el < exp
        ? `已用 ${el.toFixed(0)}s · 预计 ~${Math.round(exp)}s`
        : `已用 ${el.toFixed(0)}s · 较预期慢（首次算该工况属正常）`;
    }
    if (el >= exp) setBenchProgTag("仍在计算", "tag warn");
  }
  function stopBenchProg(okElapsed) {
    clearInterval(state.runTimer);
    state.runTimer = null;
    const p = $("#bench-prog");
    if (p) p.hidden = true;
    // 学习：只学真实算出来的耗时（缓存命中 elapsed≈0 不学）
    if (okElapsed && okElapsed >= 5 && state.runStride) {
      store.set("ferm-exp-" + state.runStride, String(Math.round(okElapsed)));
    }
    state.runT0 = null;
  }

  /** 提交作业。force=true ⇒ 绕过结果缓存，真实重算一次并新增历史留痕。 */
  async function submitSim(force, rerunOf) {
    const batch = parseInt($("#sel-batch").value, 10);
    if (!batch) return false;
    state.batch = batch;
    const btn = $("#btn-run"), rb = $("#btn-rerun");
    btn.disabled = true; rb.disabled = true;
    $("#bench-state").textContent = force ? "提交重算…" : "提交中…";
    try {
      const stride = parseInt($("#sel-stride").value, 10);
      const body = { batch, overrides: state.overrides, stride };
      if (force) { body.force = true; body.rerun_of = rerunOf || null; }
      const r = await post("/run", body);
      state.job = r.job_id;
      state.rerunOf = rerunOf || null;
      $("#bench-state").textContent = (force ? "重算作业 " : "作业 ") + r.job_id;
      startBenchProg(stride);
      pollJob();
      return true;
    } catch (e) {
      $("#bench-state").textContent = (force ? "重算提交失败：" : "提交失败：") + e.message;
      showBenchError(e);
      btn.disabled = false; rb.disabled = false;
      return false;
    }
  }
  // 必须用函数声明：上面的事件绑定在本段代码执行前就要引用它，
  // const 箭头函数有 TDZ，会在页面加载时抛 "Cannot access 'runSim' before initialization"。
  function runSim() { return submitSim(false, null); }
  async function rerunSim(fromId) {
    state.viewSource = null;         // 即将是「实时计算」，旧回放标识先撤掉
    return submitSim(true, fromId || null);
  }

  /** 作业完成后：刷新留痕列表，并把本次结果的来源（执行时间 / 留痕 id）记下来。 */
  async function finishLiveJob(j, cached) {
    state.rerunOf = null;
    await refreshHistory();
    const hid = (j.progress || {}).history_id;
    let rec = hid ? state.history.find((x) => x.id === hid) : null;
    if (cached && !rec) {
      const fp = (state.result || {}).fingerprint;
      rec = fp ? state.history.find((x) => x.fingerprint === fp) : null;
    }
    state.viewSource = rec
      ? { id: rec.id, kind: cached ? "history" : "live", created_at: rec.created_at,
          rerun_of: rec.rerun_of, cached: !!cached }
      : null;
    renderHistory();
  }

  async function pollJob() {
    if (!state.job) return;
    try {
      // 必须带 full=1：作业完成时服务端才回传结果体（否则只有状态）
      const r = await api("/job/" + state.job + "?full=1");
      const j = r.job;
      const st = $("#bench-state");
      if (j.state === "done") {
        clearInterval(state.jobTimer); state.jobTimer = null;
        stopBenchProg(j.elapsed_s);
        $("#btn-run").disabled = false;
        $("#btn-rerun").disabled = false;
        state.result = j.result;
        if (!state.result || !state.result.ok) {
          showBenchError({ message: (j.error || "结果为空"), payload: j.result });
          st.textContent = "失败：结果不可用";
          await finishLiveJob(j, false);
          return;
        }
        const cached = !!j.from_cache;
        st.textContent = (cached ? "完成（复用缓存）· " : "完成 · ") + (j.elapsed_s || 0) + "s";
        $("#st-dot").className = "dot";
        await finishLiveJob(j, cached);
        renderResult(j.result);
        loadV3(batchOf(j));
      } else if (j.state === "failed") {
        clearInterval(state.jobTimer); state.jobTimer = null;
        stopBenchProg(null);
        $("#btn-run").disabled = false;
        $("#btn-rerun").disabled = false;
        st.textContent = "失败：" + (j.code || "");
        $("#st-dot").className = "dot err";
        showBenchError({ message: j.error, payload: { detail: j.result && j.result.detail } });
        await finishLiveJob(j, false);   // 失败也留痕（边界证据）
      } else {
        // 从作业列表点进来的作业没有 runT0 —— 现场起一个进度条
        if (!state.runT0) startBenchProg(parseInt($("#sel-stride").value, 10) || 6);
        setBenchProgTag(j.state === "queued" ? "排队中" : "计算中");
        st.textContent = (j.state === "queued" ? "排队中" : "计算中") +
          (j.progress && j.progress.detail ? " · " + j.progress.detail : "");
        $("#st-dot").className = "dot busy";
        state.jobTimer = setTimeout(pollJob, 1500);
      }
    } catch (e) {
      clearInterval(state.jobTimer); state.jobTimer = null;
      stopBenchProg(null);
      $("#btn-run").disabled = false;
      $("#btn-rerun").disabled = false;
    }
  }

  function batchOf(j) {
    return j.batch || state.batch;
  }

  function showBenchError(e) {
    const detail = e.payload && e.payload.detail;
    let extra = "";
    if (detail && detail.problems) {
      extra = `<div style="margin-top:8px">${detail.problems.map((p) =>
        `<div class="tiny" style="color:var(--crit)">· ${esc(p)}</div>`).join("")}</div>`;
    }
    $("#bench-result").innerHTML = `
      <div class="panel">
        <div class="panel-h"><h2 style="color:var(--crit)">仿真失败</h2></div>
        <div class="panel-b">
          <div class="note crit">${esc(e.message || String(e))}</div>
          ${extra}
          <div class="tiny muted" style="margin-top:9px">
            失败可见（I2）：引擎不返回兜底值，原因逐条列出。
          </div>
        </div>
      </div>`;
  }

  /* ================= 结果渲染 ================= */
  /** 结果来源条：历史回放 / 复用缓存 / 刚算完，必须一眼可分，
      且每条都带「执行运算的时间」—— 否则多份结果摆在一起无法区分。 */
  function sourceBar() {
    const s = state.viewSource;
    const btn = '<button class="btn sm" id="btn-rerun-src" title="忽略缓存，按当前工况真实重算一次">重新计算</button>';
    if (!s) return `<div class="srcbar"><span class="tag mute">本次计算</span>
      <span class="txt">结果来自服务端实时调用引擎</span><div class="spacer"></div>${btn}</div>`;
    const isHist = s.kind === "history";
    return `<div class="srcbar ${isHist ? "replay" : "saved"}">
      <span class="tag ${isHist ? "acc" : "ok"}">${isHist ? (s.cached ? "复用缓存" : "历史回放") : "本次运算已留痕"}</span>
      <span class="txt">执行时间 <b>${esc(fmtTime(s.created_at))}</b>${
        s.rerun_of ? ` · 重算自 …${esc(String(s.rerun_of).slice(-12))}` : ""}</span>
      <div class="spacer"></div>${btn}</div>`;
  }

  function renderResult(r) {
    if (!r || !r.ok) { showBenchError({ message: "结果为空", payload: r }); return; }
    // 展示一份新结果（实时算完或历史回放）时若一个通道都没选，恢复默认可见集合。
    // 否则用户看到的是「未选择任何通道」，会误以为结果没算出来 / 历史没出图
    // —— 与 R168.1「二维曲面画了空壳」是同一类误导。
    if (!state.traceCh.length) {
      const cols = Object.keys((r.trace || {}).cols || {});
      state.traceCh = ["P", "X", "S"].filter((c) => cols[c]);
      if (!state.traceCh.length) state.traceCh = cols.slice(0, 3);
    }
    const y = r.yield || {};
    const h = r.health || {};
    const hl = h.level || "unknown";
    const tone = hl === "normal" || hl === "benign" ? "ok" : (hl === "degraded" ? "warn" : "crit");
    const err = y.rel_err_pct;
    const errTone = Math.abs(err) <= 5 ? "ok" : (Math.abs(err) <= 10 ? "warn" : "crit");

    const au = r.guard_audit || {};
    const warn = (r.mv_warnings || []);
    const nCh = Object.keys((r.trace || {}).cols || {}).length;
    const shapeN = Object.keys(r.shape || {}).length;

    $("#bench-result").innerHTML = `
      ${sourceBar()}
      <div class="grid g-4">
        <div class="kpi ${errTone}">
          <div class="lab">产量相对误差</div>
          <div class="val">${err > 0 ? "+" : ""}${num(err, 2)}<small>%</small></div>
          <div class="foot"><span class="tag ${errTone}">${Math.abs(err) <= 5 ? "±5% 内" : "破线"}</span> 基准 ±5%</div>
        </div>
        <div class="kpi">
          <div class="lab">仿真 / 实测产量</div>
          <div class="val" style="font-size:17px">${fmt(y.sim_g / 1e6, 3)}<small>/ ${fmt(y.v3_g / 1e6, 3)} Mg</small></div>
          <div class="foot">口径 = harvested + V·P</div>
        </div>
        <div class="kpi ${tone}">
          <div class="lab">健康分级（五通道）</div>
          <div class="val" style="font-size:17px">${esc(hl)}</div>
          <div class="foot">${(h.flags || []).length
            ? (h.flags || []).map((f) => `<span class="tag warn">${esc(f)}</span>`).join("")
            : '<span class="tag ok">无病理标记</span>'}</div>
        </div>
        <div class="kpi">
          <div class="lab">耗时 / 采样点</div>
          <div class="val" style="font-size:17px">${num(r.elapsed_s, 1)}<small>s</small></div>
          <div class="foot">${r.n_steps} 步 · 抽稀 ${r.stride}× · ${nCh} 通道</div>
        </div>
      </div>

      ${warn.length ? `<div class="note warn" style="margin-top:var(--gap)">
        <b>有效域告警</b>：${warn.map(esc).join("；")}</div>` : ""}

      ${au.ph_nonpos_steps ? `<div class="note crit" style="margin-top:var(--gap)">
        <b>守卫改写 pH</b> ${au.ph_nonpos_steps} 步（pH_max_pre=${num(au.ph_max_pre, 3)}）。
        守卫钳位会改写动力学 —— mu_h 在 pH 3.0 钳位值下比 6.5 高 8.43 倍，产物会额外水解。</div>` : ""}

      <div class="panel mt">
        <div class="panel-h">
          <h2>状态轨迹</h2>
          <div class="seg" id="seg-mode">
            <button data-m="sim" aria-pressed="true">仅仿真</button>
            <button data-m="both" aria-pressed="false">叠加实测</button>
          </div>
          <div class="spacer"></div>
          <span class="hint" id="trace-count">—</span>
          <button class="btn sm" id="trace-toggle" aria-expanded="${state.pickerOpen}">${state.pickerOpen ? "收起 ▴" : "选项 ▾"}</button>
        </div>
        <div class="panel-b" style="padding-bottom:9px">
          <div id="trace-picker" ${state.pickerOpen ? "" : "hidden"}></div>
        </div>
      </div>

      <div class="panel mt">
        <div class="panel-h">
          <h2>轨迹图</h2>
          <div class="spacer"></div>
          <span class="hint">每个通道独立成图 —— 量纲不同，合并会误导</span>
        </div>
        <div class="panel-b">
          <div class="tcards" id="chart-trace"></div>
        </div>
      </div>

      <div class="panel mt">
        <div class="tabs" id="diag-tabs">
          <button data-tab="shape" aria-selected="true">形状指标<span class="cnt" data-cnt="shape">${shapeN}</span></button>
          <button data-tab="balance" aria-selected="false">守恒与守卫审计<span class="cnt" data-cnt="balance">—</span></button>
          <button data-tab="applied" aria-selected="false">生效参数<span class="cnt" data-cnt="applied">${Object.keys(r.applied || {}).length}</span></button>
          <button data-tab="traj" aria-selected="false">轨迹级指标<span class="cnt" data-cnt="traj">—</span></button>
        </div>
        <div class="tabpane" id="pane-shape"><div class="kv" id="kv-shape"></div></div>
        <div class="tabpane" id="pane-balance" hidden><div class="kv" id="kv-balance"></div></div>
        <div class="tabpane" id="pane-applied" hidden><div class="kv" id="kv-applied"></div></div>
        <div class="tabpane" id="pane-traj" hidden><div class="kv" id="kv-traj"></div></div>
      </div>`;

    $("#btn-rerun-src").addEventListener("click", () => rerunSim(
      state.viewSource && state.viewSource.kind === "history" ? state.viewSource.id : null));

    $$("#seg-mode button").forEach((b) => b.addEventListener("click", () => {
      $$("#seg-mode button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
      state.traceMode = b.dataset.m;
      drawTrace();
    }));

    // 通道选项面板折叠开关（头部保留「已选 X/N」计数，收起时不丢信息）
    $("#trace-toggle").addEventListener("click", () => {
      state.pickerOpen = !state.pickerOpen;
      store.set("ferm-picker-v2", state.pickerOpen ? "1" : "0");
      const pk = $("#trace-picker");
      if (pk) pk.hidden = !state.pickerOpen;
      const b = $("#trace-toggle");
      b.setAttribute("aria-expanded", String(state.pickerOpen));
      b.textContent = state.pickerOpen ? "收起 ▴" : "选项 ▾";
    });

    $$("#diag-tabs button").forEach((b) => b.addEventListener("click", () => {
      const t = b.dataset.tab;
      $$("#diag-tabs button").forEach((o) => o.setAttribute("aria-selected", String(o === t)));
      ["shape", "balance", "applied", "traj"].forEach((k) => {
        const p = $("#pane-" + k);
        if (p) p.hidden = (k !== t);
      });
    }));

    renderTracePicker();
    renderShapeKV(r);
    renderBalanceKV(r);
    renderAppliedKV(r);
    renderTrajKV(r);
    // Tab 计数用真实渲染行数，不用占位符
    ["shape", "balance", "applied", "traj"].forEach((k) => {
      const n = ($( "#pane-" + k + " .kv .r") || []).length;
      const c = $(`#diag-tabs [data-cnt="${k}"]`);
      if (c) c.textContent = n;
    });
    drawTrace();
  }

  /* ---------- 通道选择器：紧凑分组 + 全选/取消全选 ---------- */
  const CH_GROUP_LABEL = {
    state: "状态量", gas: "气体与代谢", myc: "菌丝区", kin: "动力学", op: "操作量", diag: "诊断",
  };
  const CH_GROUP_ORDER = ["state", "gas", "myc", "kin", "diag", "op"];

  function traceGroups() {
    const cols = Object.keys((state.result || {}).trace?.cols || {});
    const g = {};
    cols.forEach((c) => {
      const grp = (CH_META[c] || {}).grp || "op";
      (g[grp] = g[grp] || []).push(c);
    });
    return g;
  }

  function renderTracePicker() {
    const g = traceGroups();
    const host = $("#trace-picker");
    if (!host) return;
    const total = Object.values(g).reduce((a, b) => a + b.length, 0);
    const sel = state.traceCh.length;

    host.innerHTML = `
      <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:8px">
        <button class="btn sm" id="ch-all">全选 ${total}</button>
        <button class="btn sm" id="ch-none">取消全选</button>
        <button class="btn sm" id="ch-inv">反选</button>
        <div class="spacer" style="flex:1"></div>
        <span class="tag ${sel ? "acc" : "mute"}" id="ch-count">已选 ${sel} / ${total}</span>
      </div>
      <div class="chlist">
      ${CH_GROUP_ORDER.filter((k) => g[k]).map((k) => {
        const nSel = g[k].filter((c) => state.traceCh.includes(c)).length;
        const open = state.chGrpOpen.has(k);
        return `<div class="chgrp">
          <div class="chgrp-h" data-grp-toggle="${k}">
            <svg class="arw" aria-expanded="${open}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>
            <span class="nm">${esc(CH_GROUP_LABEL[k] || k)}</span>
            <span class="cnt">${nSel}/${g[k].length}</span>
            <div class="spacer" style="flex:1"></div>
            <button class="btn sm" data-grp-all="${k}">全选</button>
            <button class="btn sm" data-grp-none="${k}">取消</button>
          </div>
          ${open ? `<div class="chgrp-b">
            ${g[k].map((c) => {
              const m = CH_META[c] || { label: c, unit: "" };
              const on = state.traceCh.includes(c);
              return `<button class="chip" data-ch="${c}" aria-pressed="${on}"
                title="${esc(m.label)} · ${esc(m.unit || "")} · ${esc(c)}">
                <span class="sw" style="background:${chColor(c)}"></span>
                ${esc(m.label)}<span class="nm">${esc(c)}</span></button>`;
            }).join("")}
          </div>` : ""}
        </div>`;
      }).join("")}
      </div>`;

    $("#ch-all").addEventListener("click", () => {
      state.traceCh = Object.keys((state.result || {}).trace?.cols || {});
      renderTracePicker(); drawTrace();
    });
    $("#ch-none").addEventListener("click", () => {
      state.traceCh = []; renderTracePicker(); drawTrace();
    });
    $("#ch-inv").addEventListener("click", () => {
      const all = Object.keys((state.result || {}).trace?.cols || {});
      state.traceCh = all.filter((c) => !state.traceCh.includes(c));
      renderTracePicker(); drawTrace();
    });
    $$("[data-grp-toggle]").forEach((el) => el.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;   // 点组内按钮不折叠
      const k = el.dataset.grpToggle;
      if (state.chGrpOpen.has(k)) state.chGrpOpen.delete(k); else state.chGrpOpen.add(k);
      renderTracePicker();
    }));
    $$("[data-grp-all]").forEach((b) => b.addEventListener("click", () => {
      const gk = b.dataset.grpAll;
      (traceGroups()[gk] || []).forEach((c) => { if (!state.traceCh.includes(c)) state.traceCh.push(c); });
      renderTracePicker(); drawTrace();
    }));
    $$("[data-grp-none]").forEach((b) => b.addEventListener("click", () => {
      const gk = b.dataset.grpNone;
      state.traceCh = state.traceCh.filter((c) => !(traceGroups()[gk] || []).includes(c));
      renderTracePicker(); drawTrace();
    }));
    $$("#trace-picker .chip").forEach((b) => b.addEventListener("click", () => {
      const c = b.dataset.ch;
      if (state.traceCh.includes(c)) state.traceCh = state.traceCh.filter((x) => x !== c);
      else state.traceCh.push(c);
      b.setAttribute("aria-pressed", String(state.traceCh.includes(c)));
      const t = Object.keys((state.result || {}).trace?.cols || {}).length;
      const el = $("#ch-count");
      if (el) {
        el.textContent = `已选 ${state.traceCh.length} / ${t}`;
        el.className = "tag " + (state.traceCh.length ? "acc" : "mute");
      }
      drawTrace();
    }));
  }

  function renderShapeKV(r) {
    const s = r.shape || {};
    const rows = Object.entries(s).slice(0, 14);
    $("#kv-shape").innerHTML = rows.length ? rows.map(([k, v]) =>
      `<div class="r"><span class="k">${esc(k)}</span><span class="v">${esc(typeof v === "number" ? num(v, 4) : String(v))}</span></div>`
    ).join("") : `<div class="tiny muted">无形状指标</div>`;
  }

  function renderBalanceKV(r) {
    const b = r.balance || {};
    const au = r.guard_audit || {};
    const rows = [];
    const pick = (obj, keys, prefix) => keys.forEach((k) => {
      if (obj && obj[k] !== undefined && obj[k] !== null) {
        rows.push([prefix + k, typeof obj[k] === "number" ? num(obj[k], 3) : String(obj[k])]);
      }
    });
    pick(b, ["c_balance_pct", "n_balance_pct", "c_closure_pct", "n_closure_pct"], "");
    Object.keys(b).filter((k) => /c_|n_|closure|balance|err/i.test(k) && typeof b[k] === "number").slice(0, 6)
      .forEach((k) => { if (!rows.find((r2) => r2[0] === k)) rows.push([k, num(b[k], 3)]); });
    rows.push(["守卫改写步数", au.ph_nonpos_steps !== undefined ? String(au.ph_nonpos_steps) : "—"]);
    rows.push(["pH 越 7 步数", au.n_ph_over7_pre !== undefined ? String(au.n_ph_over7_pre) : "—"]);
    rows.push(["审计自洽", au.audit_consistent === undefined ? "—" : (au.audit_consistent ? "是" : "否")]);
    $("#kv-balance").innerHTML = rows.length ? rows.map(([k, v]) =>
      `<div class="r"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("")
      : `<div class="tiny muted">无守恒数据</div>`;
  }

  function renderAppliedKV(r) {
    const ap = r.applied || {};
    const base = r.base || {};
    const rows = Object.entries(ap).map(([k, v]) =>
      `<div class="r"><span class="k">${esc(k)}</span><span class="v" style="color:var(--accent)">${esc(JSON.stringify(v))}</span></div>`);
    const brows = Object.entries(base).slice(0, 10).map(([k, v]) =>
      `<div class="r"><span class="k" style="color:var(--dim-2)">${esc(k)} <span style="font-size:9.5px">基准</span></span><span class="v" style="color:var(--dim)">${esc(String(v))}</span></div>`);
    $("#kv-applied").innerHTML =
      (rows.length ? rows.join("") : `<div class="tiny muted">未覆盖任何参数 —— 当前是黄金集基准工况</div>`) +
      (brows.length ? `<div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--line)">
        <div class="tiny muted" style="margin-bottom:4px">批级基准（来自 COMBINED 单一装配口径）· 指纹 ${esc(r.fingerprint || "—")}</div>${brows.join("")}</div>` : "");
  }

  function renderTrajKV(r) {
    const tm = r.trajectory_metrics || {};
    if (tm.error) {
      $("#kv-traj").innerHTML = `<div class="tiny muted">轨迹指标不可用：${esc(tm.error)}</div>`;
      return;
    }
    const rows = [];
    const flat = (o, pre) => {
      Object.entries(o || {}).forEach(([k, v]) => {
        if (v === null || v === undefined) return;
        if (typeof v === "object" && !Array.isArray(v)) flat(v, pre + k + ".");
        else rows.push([pre + k, Array.isArray(v) ? JSON.stringify(v) : (typeof v === "number" ? num(v, 4) : String(v))]);
      });
    };
    flat(tm, "");
    $("#kv-traj").innerHTML = rows.length
      ? rows.map(([k, v]) => `<div class="r"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("")
      : `<div class="tiny muted">本批无轨迹级指标</div>`;
  }

  /* ================= 轨迹图（每通道独立卡片） ================= */
  function drawTrace() {
    const host = $("#chart-trace");
    if (!host || !state.result || !state.result.trace) return;
    const tr = state.result.trace;
    const cols = tr.cols || {};
    const ts = tr.t || [];
    const chans = state.traceCh.filter((c) => cols[c]);
    const el = $("#trace-count");
    if (el) el.textContent = `${chans.length} / ${Object.keys(cols).length} 通道`;

    if (!chans.length) {
      host.innerHTML = `<div class="empty">
        <div class="ic"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg></div>
        <div class="t">未选择任何通道</div>
        <div class="d">在上方「状态轨迹」面板中勾选通道，或点「全选」一次画出全部 ${Object.keys(cols).length} 个通道。</div>
      </div>`;
      return;
    }

    const t0 = ts[0] || 0, t1 = ts[ts.length - 1] || 1;
    host.innerHTML = chans.map((ch) => {
      const meta = CH_META[ch] || { label: ch, unit: "" };
      return `<div class="tcard" data-card="${ch}">
        <div class="tcard-h">
          <span class="sw" style="background:${chColor(ch)}"></span>
          <span class="nm">${esc(meta.label)}</span>
          <span class="unit">${esc(meta.unit || "")}</span>
          <span class="key">${esc(ch)}</span>
          <div class="spacer"></div>
          <span class="stat" data-stat="${ch}"></span>
        </div>
        <div class="tcard-b" data-plot="${ch}"></div>
        <div class="tcard-f">
          <span class="lg" style="color:${chColor(ch)}"><i></i>仿真</span>
          ${state.traceMode === "both" ? `<span class="lg" style="color:var(--warn)"><i class="dash"></i>实测</span>` : ""}
          <span class="lg" style="margin-left:auto" data-axis-lbl="${ch}"></span>
        </div>
      </div>`;
    }).join("");

    // 卡片刚插入 DOM，clientWidth 可能尚未确定 ⇒ 延后一帧再量
    requestAnimationFrame(() => {
      chans.forEach((ch) => drawOne(ch, cols[ch], ts, t0, t1));
    });
  }

  function drawOne(ch, vals, ts, t0, t1) {
    const host = $(`[data-plot="${ch}"]`);
    if (!host) return;
    const meta = CH_META[ch] || { label: ch, unit: "" };
    const w = Math.max(280, host.clientWidth || 320), h = 132;
    const pad = { t: 10, r: 10, b: 20, l: 46 };
    const s = mkSvg(host, w, h);

    const fin = (vals || []).filter((v) => v !== null && v !== undefined);
    if (!fin.length) {
      host.innerHTML = `<div class="tiny muted" style="padding:26px 0;text-align:center">该通道无数值</div>`;
      return;
    }
    let lo = Math.min.apply(null, fin), hi = Math.max.apply(null, fin);
    const last = fin[fin.length - 1];
    if (hi === lo) { hi += Math.abs(hi) * 0.05 + 1e-9; lo -= Math.abs(lo) * 0.05 + 1e-9; }
    const padv = (hi - lo) * 0.12; lo -= padv; hi += padv;

    const sx = scale(t0, t1, pad.l, w - pad.r);
    const sy = scale(lo, hi, h - pad.b, pad.t);

    // 底纹 + 网格
    s.appendChild(svgEl("rect", { x: pad.l, y: pad.t, width: w - pad.r - pad.l, height: h - pad.b - pad.t,
      fill: "color-mix(in srgb, var(--panel-3) 42%, transparent)", rx: 3 }));
    for (let g = 0; g <= 2; g++) {
      const v = lo + (hi - lo) * g / 2;
      const y = sy(v);
      s.appendChild(svgEl("line", { class: "grid-line", x1: pad.l, x2: w - pad.r, y1: y, y2: y }));
      const t = svgEl("text", { x: pad.l - 5, y: y + 3, "text-anchor": "end" });
      t.textContent = Math.abs(v) >= 1000 ? v.toFixed(0) : (Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));
      s.appendChild(t);
    }
    // x 轴刻度
    s.appendChild(svgEl("line", { class: "axis", x1: pad.l, x2: w - pad.r, y1: h - pad.b, y2: h - pad.b }));
    for (let i = 0; i <= 3; i++) {
      const v = t0 + (t1 - t0) * i / 3;
      const t = svgEl("text", { x: sx(v), y: h - pad.b + 12, "text-anchor": "middle" });
      t.textContent = v.toFixed(0) + "h";
      s.appendChild(t);
    }

    // 仿真曲线
    const d = pathFrom(ts, vals, sx, sy);
    s.appendChild(svgEl("path", { d, fill: "none", stroke: chColor(ch), "stroke-width": 1.7, "stroke-linejoin": "round" }));

    // 实测叠加（仅当该通道有 V3 对照）
    let hasV3 = false;
    if (state.traceMode === "both" && state.v3) {
      const vc = (state.v3.ch || {})[ch];
      if (vc) {
        if (vc.values) {
          s.appendChild(svgEl("path", { d: pathFrom(ts, vc.values, sx, sy), fill: "none",
            stroke: "var(--warn)", "stroke-width": 1.2, "stroke-dasharray": "4 3", opacity: .95 }));
          hasV3 = true;
        } else if (vc.points) {
          const px = vc.points.map((p) => p[0]), py = vc.points.map((p) => p[1]);
          s.appendChild(svgEl("path", { d: pathFrom(px, py, sx, sy), fill: "none",
            stroke: "var(--warn)", "stroke-width": 1.4, opacity: .95 }));
          vc.points.forEach((p) => s.appendChild(svgEl("circle", {
            cx: sx(p[0]), cy: sy(p[1]), r: 2, fill: "var(--warn)" })));
          hasV3 = true;
        }
      }
    }

    // 头部统计：末值 + 峰值
    const st = $(`[data-stat="${ch}"]`);
    if (st) {
      const peak = Math.max.apply(null, fin);
      st.innerHTML = `末 <b>${num(last, Math.abs(last) >= 100 ? 1 : 3)}</b> · 峰 <b>${num(peak, Math.abs(peak) >= 100 ? 1 : 3)}</b>`;
    }
    // 底部坐标轴说明
    const al = $(`[data-axis-lbl="${ch}"]`);
    if (al) {
      al.textContent = hasV3 ? `y: ${meta.unit || "-"} · 含实测对照` : `y: ${meta.unit || "-"}`;
      al.style.color = hasV3 ? "var(--warn)" : "";
    }
  }

  async function loadV3(batch) {
    try {
      const r = await api("/batch/" + batch + "/v3");
      state.v3 = r;
      if (state.result) drawTrace();
    } catch (e) { state.v3 = null; }
  }

  /* ================= 作业列表 ================= */
  async function pollJobs() {
    try {
      const r = await api("/jobs");
      const jobs = r.jobs || [];
      updateQueueNote(r);
      if (!jobs.length) {
        $("#job-list").innerHTML = `<div class="tiny muted">暂无作业</div>`;
        return;
      }
      $("#job-list").innerHTML = jobs.slice(0, 12).map((j) => `
        <div class="job ${j.state}" data-job="${esc(j.id)}">
          <span class="st"></span>
          <span class="id">${esc(j.id)}</span>
          <span class="det">${esc(j.batch || "")} · ${esc(j.state)} · ${num(j.elapsed_s, 1)}s</span>
        </div>`).join("");
      $$("#job-list .job").forEach((el) => el.addEventListener("click", () => {
        state.job = el.dataset.job;
        pollJob();
      }));
    } catch (e) { /* 服务未就绪 */ }
  }

  function updateQueueNote(q) {
    if (!q) return;
    const el = $("#queue-note");
    if (el) el.textContent = `排队 ${q.by_state.queued || 0} · 运行 ${q.by_state.running || 0} · 缓存 ${q.cache_n}`;
    $("#st-queue").textContent = `队列 ${(q.by_state.queued || 0) + (q.by_state.running || 0)} · 缓存 ${q.cache_n}`;
  }

  /* ================= 扫描 ================= */

  /* 响应量逐项说明：扫描的意义取决于「响应量选的是什么」——
     同一条曲线，对 yield_err 是验收红线，对 co2d_max 是崩溃阈值观测。 */
  const RESPONSE_DESC = {
    yield_err: "仿真产量相对该批实测产量的偏差（%）。±5% 是项目验收红线 —— 曲线穿出红线即不可行。",
    yield_sim: "仿真绝对产量（g）。看参数对产量的量级影响时用。",
    health: "五通道健康分级的序数（0 正常 → 3 灾难）。看可行域的「安全区」在哪里。",
    co2d_max: "溶解 CO₂ 全程峰值（g/L）。崩溃机理的核心观测通道（阈值 ≈8.0，R12 系结论）。",
    ph_min: "pH 全程最低值。过低 ⇒ 酸化病态 / 产物水解加剧。",
    ph_max: "pH 全程最高值。越 7 ⇒ 触发碱性病态分支（R156 数值病态）。",
    do2_min: "溶氧全程最低值（mg/L）。供氧能力不足的直接证据。",
    p_max: "产物浓度峰值（g/L）。观察工艺上限。",
    x_max: "生物量峰值（g/L）。菌体生长过旺会挤占产物（Pirt 双相竞争）。",
    s_max: "残糖峰值（g/L）。补料 / 消耗失衡的信号。",
  };
  function updateRespDesc() {
    const el = $("#scan-resp-desc");
    if (!el) return;
    const k = $("#scan-response").value;
    el.textContent = RESPONSE_DESC[k] || "";
  }
  $("#scan-response").addEventListener("change", updateRespDesc);

  /* 健康分级 → 绘图色：可行域「安全 / 降级 / 灾难」在图上一眼分层 */
  const healthTone = (h) => h === "catastrophic" ? "var(--crit)"
    : h === "degraded" ? "var(--warn)" : "var(--accent)";

  const AXIS_PRESETS = [
    { key: "mux", label: "比生长速率 μx", from: 0.30, to: 0.50 },
    { key: "mup", label: "比产物速率 μp", from: 0.02, to: 0.08 },
    { key: "m_s", label: "维持系数 m_s", from: 0.005, to: 0.045 },
    { key: "dist_tcin_asym", label: "冷却水温扰动 K", from: -10, to: 20 },
    { key: "alpha_kla", label: "氧传质 αKLa", from: 40, to: 120 },
    { key: "mu_h_scale", label: "水解倍率", from: 0.5, to: 2.5 },
    { key: "biomass_death_rate", label: "生物量衰亡率", from: 0, to: 0.02 },
    { key: "late_death_rate", label: "晚期衰亡率", from: 0, to: 0.02 },
  ];

  function renderScanAxes() {
    const host = $("#scan-axes");
    if (!host) return;
    if (!state.scanAxes.length) state.scanAxes.push({ ...AXIS_PRESETS[0], n: 5 });
    host.innerHTML = state.scanAxes.map((a, i) => `
      <div style="border:1px solid var(--line);border-radius:var(--radius-sm);padding:8px 9px;margin-bottom:7px">
        <select class="inp" data-axis-key="${i}" style="margin-bottom:6px">
          ${AXIS_PRESETS.map((p) => `<option value="${p.key}" ${p.key === a.key ? "selected" : ""}>${esc(p.label)}</option>`).join("")}
        </select>
        <div style="display:flex;gap:6px;align-items:center">
          <input class="inp" type="number" step="any" data-axis-from="${i}" value="${a.from}" style="width:82px" />
          <span class="tiny muted">→</span>
          <input class="inp" type="number" step="any" data-axis-to="${i}" value="${a.to}" style="width:82px" />
          <input class="inp" type="number" data-axis-n="${i}" value="${a.n}" style="width:52px" title="点数" />
          ${state.scanAxes.length > 1 ? `<button class="btn sm danger" data-axis-del="${i}">×</button>` : ""}
        </div>
      </div>`).join("");

    $$("[data-axis-key]").forEach((el) => el.addEventListener("change", () => {
      const i = +el.dataset.axisKey;
      const p = AXIS_PRESETS.find((x) => x.key === el.value);
      state.scanAxes[i] = { ...p, n: state.scanAxes[i].n };
      renderScanAxes();
    }));
    $$("[data-axis-from]").forEach((el) => el.addEventListener("change", () => {
      state.scanAxes[+el.dataset.axisFrom].from = parseFloat(el.value);
    }));
    $$("[data-axis-to]").forEach((el) => el.addEventListener("change", () => {
      state.scanAxes[+el.dataset.axisTo].to = parseFloat(el.value);
    }));
    $$("[data-axis-n]").forEach((el) => el.addEventListener("change", () => {
      state.scanAxes[+el.dataset.axisN].n = clamp(parseInt(el.value, 10) || 5, 2, 24);
    }));
    $$("[data-axis-del]").forEach((el) => el.addEventListener("click", () => {
      state.scanAxes.splice(+el.dataset.axisDel, 1);
      renderScanAxes();
    }));
  }

  $("#btn-add-axis").addEventListener("click", () => {
    if (state.scanAxes.length >= 2) return;
    const used = state.scanAxes.map((a) => a.key);
    const next = AXIS_PRESETS.find((p) => !used.includes(p.key)) || AXIS_PRESETS[0];
    state.scanAxes.push({ ...next, n: 4 });
    renderScanAxes();
  });

  $("#btn-scan").addEventListener("click", runScan);
  $("#btn-scan-csv").addEventListener("click", () => exportScanCsv(state.scanResult));

  async function runScan() {
    const batch = parseInt($("#scan-batch").value, 10);
    const axes = state.scanAxes.map((a) => ({ key: a.key, from: a.from, to: a.to, n: a.n }));
    $("#scan-state").textContent = "提交中…";
    $("#scan-detail").textContent = "作业已提交，等待执行";
    $("#scan-result-panel").hidden = true;
    $("#scan-table-panel").hidden = true;
    $("#scan-prog").style.width = "0%";
    try {
      const r = await post("/scan", {
        batch, axes,
        response: $("#scan-response").value,
        stride: 12,
      });
      state.scanJob = r.job_id;
      pollScan();
    } catch (e) {
      $("#scan-state").textContent = "提交失败";
      $("#scan-detail").innerHTML = `<span style="color:var(--crit)">${esc(e.message)}</span>`;
    }
  }

  async function pollScan() {
    if (!state.scanJob) return;
    try {
      const r = await api("/sweep/" + state.scanJob + "?full=1");
      const j = r.job;
      const p = j.progress || {};
      if (p.total) {
        $("#scan-prog").style.width = (100 * (p.done || 0) / p.total) + "%";
      }
      $("#scan-detail").textContent = p.detail || j.state;
      if (j.state === "done") {
        clearInterval(state.scanTimer); state.scanTimer = null;
        $("#scan-state").textContent = "完成";
        state.scanResult = j.result;
        renderScanResult(j.result);
      } else if (j.state === "failed") {
        clearInterval(state.scanTimer); state.scanTimer = null;
        $("#scan-state").textContent = "失败";
        $("#scan-detail").textContent = j.error || "";
      } else {
        $("#scan-state").textContent = j.state === "queued" ? "排队中" : "扫描中";
        state.scanTimer = setTimeout(pollScan, 2000);
      }
    } catch (e) { clearInterval(state.scanTimer); state.scanTimer = null; }
  }

  function renderScanResult(r) {
    if (!r) return;
    $("#scan-result-panel").hidden = false;
    $("#scan-table-panel").hidden = false;
    $("#scan-chart-title").textContent = r.response_label + " 响应" + (r.response_unit ? " (" + r.response_unit + ")" : "");
    const sm = r.summary || {};
    const axes = r.axes || [];
    const pts = r.points || [];
    const axKeys = axes.map((a) => a.key);
    const okPts = pts.filter((p) => p.ok && p.y !== null && p.y !== undefined);
    const badPts = pts.filter((p) => !(p.ok && p.y !== null && p.y !== undefined));

    // ---- 极值点：yield_err / health 取 |y| 最小（最优），其余取最大（峰值）----
    let best = null;
    const bestLbl = (r.response === "yield_err" || r.response === "health") ? "最优" : "峰值";
    if (okPts.length) {
      best = okPts.reduce((a, b) =>
        (bestLbl === "最优" ? (Math.abs(b.y) < Math.abs(a.y) ? b : a)
                            : (b.y > a.y ? b : a)));
    }

    // ---- 一维形态判定：最大局部斜率 vs 全程平均斜率 ----
    // 阈值型（悬崖）意味着工艺容差窄；平滑型意味着参数可缓调。
    // 本项目关键结论（Fs < ±1%、γ1 悬崖）全是阈值型 —— 这就是扫描的意义。
    let shapeTag = null, threshX = null;
    if (axes.length === 1 && okPts.length >= 3) {
      const gp = pts.map((p, i) => ({ x: xs1(p, i), y: p.y }))
        .filter((o) => o.y !== null && o.y !== undefined && o.x !== null);
      let maxLocal = 0;
      for (let k = 1; k < gp.length; k++) {
        const dx = gp[k].x - gp[k - 1].x, dy = gp[k].y - gp[k - 1].y;
        if (dx > 0) {
          const sl = Math.abs(dy / dx);
          if (sl > maxLocal) { maxLocal = sl; threshX = (gp[k].x + gp[k - 1].x) / 2; }
        }
      }
      const meanSlope = Math.abs((gp[gp.length - 1].y - gp[0].y) / ((gp[gp.length - 1].x - gp[0].x) || 1));
      if (meanSlope > 1e-12) {
        shapeTag = maxLocal >= 3 * meanSlope
          ? { type: "threshold", ratio: maxLocal / meanSlope }
          : { type: "smooth", ratio: maxLocal / meanSlope };
      }
    }

    function xs1(p, i) { return (p.x || {})[axKeys[0]]; }

    // 统计条 —— 成功/失败一眼可见，不允许「空图 = 一切正常」的错觉
    const amp = (sm.y_max !== null && sm.y_max !== undefined && sm.y_min !== null && sm.y_min !== undefined)
      ? sm.y_max - sm.y_min : null;
    const ampRel = (amp !== null && sm.y_median) ? 100 * amp / Math.abs(sm.y_median) : null;
    $("#scan-summary").innerHTML = `<div class="scanstat">
      <span class="s ok">成功 <b>${r.n_ok}</b>/${r.n_total}</span>
      <span class="s ${r.n_failed ? "crit" : "mute"}">失败 <b>${r.n_failed}</b></span>
      <span class="s mute">耗时 <b>${num(r.elapsed_s, 0)}</b>s</span>
      ${sm.y_min !== null && sm.y_min !== undefined ? `<span class="s mute">范围 <b>${num(sm.y_min, 3)}</b> … <b>${num(sm.y_max, 3)}</b></span>` : ""}
      ${amp !== null ? `<span class="s mute">波动 <b>Δ${num(amp, 3)}</b>${ampRel !== null && isFinite(ampRel) ? ` (<b>${num(ampRel, 0)}%</b>)` : ""}</span>` : ""}
      ${sm.y_median !== null && sm.y_median !== undefined ? `<span class="s mute">中位 <b>${num(sm.y_median, 3)}</b></span>` : ""}
      ${shapeTag ? `<span class="s ${shapeTag.type === "threshold" ? "crit" : "ok"}" title="最大局部斜率 / 全程平均斜率 = ${num(shapeTag.ratio, 1)}">形态 <b>${shapeTag.type === "threshold" ? "阈值型 ×" + num(shapeTag.ratio, 1) : "平滑型"}</b></span>` : ""}
    </div>`;

    const host = $("#scan-chart");

    // ---- 全部点失败：不画空坐标系，直接给失败原因清单 ----
    if (!okPts.length) {
      host.innerHTML = `<div class="empty">
        <div class="ic" style="color:var(--crit)"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M12 8v5"/><circle cx="12" cy="16.5" r="1" fill="currentColor" stroke="none"/><path d="M10.3 3.9L2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg></div>
        <div class="t">${r.n_total} 个扫描点全部失败 —— 没有可绘制的响应</div>
        <div class="d">失败原因逐条如下（未参与 min/max 统计，也未被渲染成 0 值）。<br>
          常见原因：参数越出已知有效域、引擎在该工况下发散、响应量不可计算。</div>
        <div class="fails" style="width:100%;max-width:640px;text-align:left">
          ${badPts.map((p) => `<div class="failrow">
            <span class="x">${axKeys.map((k) => esc(k) + "=" + num(p.x[k], 5)).join(" · ")}</span>
            <span class="r">${esc(p.error || "未知原因")}</span>
            <span class="c">${esc(p.code || "")}</span>
          </div>`).join("")}
        </div>
      </div>`;
      renderScanTable(r, axKeys);
      return;
    }

    // ---- 部分失败：图上仍要标出失败点 ----
    if (axes.length === 1) {
      // 一维：折线 + 失败点标记
      const w = host.clientWidth || 700, h = 300;
      const pad = { t: 20, r: 20, b: 38, l: 62 };
      const s = mkSvg(host, w, h);
      const xs = axes[0].values;
      const ys = okPts.map((p) => p.y);
      let lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      if (hi === lo) { hi += 1; lo -= 1; }
      const padv = (hi - lo) * 0.14; lo -= padv; hi += padv;
      const { sx, sy } = axes2(s, { pad, w, h, xd: [xs[0], xs[xs.length - 1]], yd: [lo, hi],
        xlabel: axes[0].key, ylabel: r.response_label });

      // ±5% 参考带（产量误差口径）
      if (r.response === "yield_err") {
        [5, -5].forEach((v) => {
          if (v > lo && v < hi) {
            s.appendChild(svgEl("line", { class: "limit", x1: pad.l, x2: w - pad.r, y1: sy(v), y2: sy(v) }));
            const t = svgEl("text", { x: w - pad.r - 3, y: sy(v) - 4, "text-anchor": "end" });
            t.textContent = (v > 0 ? "+" : "") + v + "% 红线";
            t.setAttribute("style", "fill:var(--crit);font-size:9px");
            s.appendChild(t);
          }
        });
      }

      // 陡变段标注（阈值型）：竖直虚线 + 定位 —— 这就是「可行域边界」的 x 坐标
      if (shapeTag && shapeTag.type === "threshold" && threshX !== null &&
          threshX > xs[0] && threshX < xs[xs.length - 1]) {
        s.appendChild(svgEl("line", { class: "limit", x1: sx(threshX), x2: sx(threshX), y1: pad.t, y2: h - pad.b }));
        const tt = svgEl("text", { x: sx(threshX) + 4, y: pad.t + 9, "text-anchor": "start" });
        tt.textContent = "陡变 ~" + num(threshX, 3);
        tt.setAttribute("style", "fill:var(--crit);font-size:9px");
        s.appendChild(tt);
      }

      // 成功点连线（按 x 顺序，剔除失败点）
      const good = pts.map((p, i) => ({ p, i })).filter((o) => o.p.ok && o.p.y !== null && o.p.y !== undefined);
      const d = pathFrom(good.map((o) => xs[o.i]), good.map((o) => o.p.y), sx, sy);
      s.appendChild(svgEl("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 2 }));

      // 成功点：按健康分级着色 —— 安全区 / 降级带 / 灾难带在图上直接分层
      good.forEach((o) => {
        const x = sx(xs[o.i]), yy = sy(o.p.y);
        const tone = healthTone(o.p.health);
        const c = svgEl("circle", { cx: x, cy: yy, r: 4, fill: tone, stroke: "var(--panel)", "stroke-width": 1.5 });
        c.addEventListener("mousemove", (ev) => showTip(
          `<b>${esc(axes[0].key)} = ${num(xs[o.i], 5)}</b><br>${esc(r.response_label)} = <b>${num(o.p.y, 3)}</b><br>` +
          `健康 <b style="color:${tone}">${esc(o.p.health || "—")}</b> · ${num(o.p.elapsed_s, 0)}s` +
          (o.p.yield_err !== null && o.p.yield_err !== undefined ? `<br>产量误差 ${num(o.p.yield_err, 2)}%` : "") +
          (o.p.co2d_max !== null && o.p.co2d_max !== undefined ? `<br>CO2d 峰 ${num(o.p.co2d_max, 2)} g/L` : "") +
          (o.p.flags && o.p.flags.length ? `<br><span style="color:var(--warn)">${esc(o.p.flags.join(", "))}</span>` : ""), ev));
        c.addEventListener("mouseleave", hideTip);
        s.appendChild(c);
      });

      // 极值点：圆环标注（最优 = |误差|最小 / 峰值 = 响应最大）
      if (best) {
        const bi = pts.indexOf(best);
        if (bi >= 0 && isFinite(sx(xs[bi]))) {
          s.appendChild(svgEl("circle", { cx: sx(xs[bi]), cy: sy(best.y), r: 8.5,
            fill: "none", stroke: "var(--ok)", "stroke-width": 1.6 }));
          const bt = svgEl("text", { x: sx(xs[bi]), y: sy(best.y) - 12, "text-anchor": "middle" });
          bt.textContent = bestLbl + " " + num(best.y, 2);
          bt.setAttribute("style", "fill:var(--ok);font-size:9.5px;font-weight:500");
          s.appendChild(bt);
        }
      }

      // 失败点：标在坐标轴底部（对齐 x 位置）
      badPts.forEach((p) => {
        const i = pts.indexOf(p);
        const x = sx(xs[i]);
        if (!isFinite(x)) return;
        const g = svgEl("g");
        const by = h - pad.b + 3;
        g.appendChild(svgEl("line", { x1: x - 4.5, y1: by, x2: x + 4.5, y2: by + 9, stroke: "var(--crit)", "stroke-width": 1.8 }));
        g.appendChild(svgEl("line", { x1: x - 4.5, y1: by + 9, x2: x + 4.5, y2: by, stroke: "var(--crit)", "stroke-width": 1.8 }));
        g.addEventListener("mousemove", (ev) => showTip(
          `<b>${esc(axes[0].key)} = ${num(xs[i], 5)}</b><br><span style="color:var(--crit)">失败：${esc(p.error || p.code || "")}</span>`, ev));
        g.addEventListener("mouseleave", hideTip);
        s.appendChild(g);
      });

      // 图例
      const lg = svgEl("text", { x: pad.l, y: h - 6, "text-anchor": "start" });
      lg.textContent = (badPts.length
        ? `● 成功点 ${okPts.length}　✕ 失败点 ${badPts.length}（标于轴下）`
        : `● 全部 ${okPts.length} 点成功`) + "　· 按健康分级着色";
      lg.setAttribute("style", "fill:var(--dim-2);font-size:9.5px");
      s.appendChild(lg);
    } else {
      // 二维：热力网格
      const xa = axes[0], ya = axes[1];
      const fin = okPts.map((p) => p.y);
      let lo = Math.min.apply(null, fin), hi = Math.max.apply(null, fin);
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      if (hi === lo) hi += 1;
      const left = 92, right = 18, top = 26, bottom = 44;
      const avail = Math.max(360, host.clientWidth || 900);
      const nX = xa.values.length, nY = ya.values.length;
      const cellW = (avail - left - right) / nX;
      const cellH = clamp(cellW * 0.62, 42, 116);
      const cell = { w: cellW, h: cellH };
      const w = avail;
      const h = top + nY * cellH + bottom;
      const s = mkSvg(host, w, h);
      const t = svgEl("text", { x: left, y: 15, "text-anchor": "start" });
      t.textContent = `${xa.key} →（列） · ${ya.key} ↑（行）`;
      t.setAttribute("style", "fill:var(--dim-2)");
      s.appendChild(t);
      pts.forEach((p) => {
        // 注意：轴坐标在 p.x 里，p.y 是**响应值**（标量）。
        // 旧实现误取 p.y[ya.key] ⇒ 恒为 undefined ⇒ findIndex 恒 -1 ⇒ 整张网格不画。
        const xi = xa.values.findIndex((v) => Math.abs(v - p.x[xa.key]) < 1e-9);
        const yi = ya.values.findIndex((v) => Math.abs(v - p.x[ya.key]) < 1e-9);
        if (xi < 0 || yi < 0) return;
        const x = left + xi * cell.w, y = top + (nY - 1 - yi) * cell.h;
        let fill = "var(--panel-3)";
        if (p.ok && p.y !== null && p.y !== undefined) {
          const t01 = (p.y - lo) / ((hi - lo) || 1);
          fill = `color-mix(in srgb, var(--accent) ${(18 + t01 * 72).toFixed(0)}%, var(--panel-3))`;
        } else {
          fill = "color-mix(in srgb, var(--crit) 55%, var(--panel-3))";
        }
        const rect = svgEl("rect", { x: x + 1, y: y + 1, width: cell.w - 2, height: cell.h - 2, rx: 3, fill, class: "heat-cell" });
        rect.addEventListener("mousemove", (ev) => showTip(
          `<b>${esc(xa.key)}=${num(p.x[xa.key], 5)}</b>, <b>${esc(ya.key)}=${num(p.x[ya.key], 5)}</b><br>` +
          (p.ok ? `${esc(r.response_label)} = <b>${num(p.y, 3)}</b><br>健康 ${esc(p.health || "—")}`
                : `<span style="color:var(--crit)">失败：${esc(p.error || p.code || "")}</span>`), ev));
        rect.addEventListener("mouseleave", hideTip);
        s.appendChild(rect);
        const lbl = svgEl("text", { x: x + cell.w / 2, y: y + cell.h / 2 + 3, "text-anchor": "middle" });
        lbl.textContent = p.ok && p.y !== null && p.y !== undefined ? num(p.y, 1) : "✕";
        lbl.setAttribute("style", "font-size:10px;fill:" + (p.ok ? "var(--text)" : "var(--crit)"));
        s.appendChild(lbl);
      });
      // 极值格高亮：绿色描边 —— 二维的「最优操作角」一目了然
      if (best) {
        const bxi = xa.values.findIndex((v) => Math.abs(v - best.x[xa.key]) < 1e-9);
        const byi = ya.values.findIndex((v) => Math.abs(v - best.x[ya.key]) < 1e-9);
        if (bxi >= 0 && byi >= 0) {
          const bx = left + bxi * cell.w, by = top + (nY - 1 - byi) * cell.h;
          s.appendChild(svgEl("rect", { x: bx + 1.5, y: by + 1.5, width: cell.w - 3, height: cell.h - 3,
            rx: 3, fill: "none", stroke: "var(--ok)", "stroke-width": 2 }));
          const bt = svgEl("text", { x: bx + cell.w / 2, y: by - 4, "text-anchor": "middle" });
          bt.textContent = bestLbl + " " + num(best.y, 2);
          bt.setAttribute("style", "fill:var(--ok);font-size:9.5px;font-weight:500");
          s.appendChild(bt);
        }
      }
      xa.values.forEach((v, i) => {
        const tx = svgEl("text", { x: left + i * cell.w + cell.w / 2, y: top + nY * cellH + 16, "text-anchor": "middle" });
        tx.textContent = num(v, 3); s.appendChild(tx);
      });
      ya.values.forEach((v, i) => {
        const ty = svgEl("text", { x: left - 6, y: top + (nY - 1 - i) * cellH + cellH / 2 + 3, "text-anchor": "end" });
        ty.textContent = num(v, 3); s.appendChild(ty);
      });
      // 色标
      const lg1 = svgEl("text", { x: left, y: h - 10, "text-anchor": "start" });
      lg1.textContent = `低 ${num(lo, 2)}`;
      lg1.setAttribute("style", "fill:var(--dim-2);font-size:9.5px");
      s.appendChild(lg1);
      const lg2 = svgEl("text", { x: left + nX * cell.w, y: h - 10, "text-anchor": "end" });
      lg2.textContent = `高 ${num(hi, 2)}`;
      lg2.setAttribute("style", "fill:var(--dim-2);font-size:9.5px");
      s.appendChild(lg2);
      if (badPts.length) {
        const lg3 = svgEl("text", { x: left + nX * cell.w / 2, y: h - 10, "text-anchor": "middle" });
        lg3.textContent = `✕ ${badPts.length} 个失败点（不参与统计）`;
        lg3.setAttribute("style", "fill:var(--crit);font-size:9.5px");
        s.appendChild(lg3);
      }
    }

    renderScanTable(r, axKeys);
  }

  function renderScanTable(r, axKeys) {
    const pts = r.points || [];
    $("#scan-table").innerHTML =
      `<thead><tr>${axKeys.map((k) => `<th>${esc(k)}</th>`).join("")}<th>${esc(r.response_label)}</th>` +
      `<th title="产量相对误差（每个扫描点都会回传）">误差%</th>` +
      `<th title="该点仿真的 CO2d 全程峰值">CO2d峰</th>` +
      `<th title="该点仿真的 pH 全程最低值">pH低</th>` +
      `<th>健康</th><th>状态</th></tr></thead><tbody>` +
      pts.map((p) => `<tr>${axKeys.map((k) => `<td class="n">${num(p.x[k], 5)}</td>`).join("")}
        <td class="n" style="color:${p.ok ? "var(--text)" : "var(--crit)"}">${p.ok && p.y !== null && p.y !== undefined ? num(p.y, 3) : "失败"}</td>
        <td class="n">${num(p.yield_err, 2)}</td>
        <td class="n">${num(p.co2d_max, 2)}</td>
        <td class="n">${num(p.ph_min, 2)}</td>
        <td>${esc(p.health || "—")}</td>
        <td class="tiny">${p.ok ? esc((p.flags || []).join(",") || "正常") : esc(p.code || "")}</td></tr>`).join("") +
      "</tbody>";
  }

  /* CSV 导出：逐点全字段（轴坐标 + 主响应 + 附带响应 + 健康 + 失败原因），
     带 BOM ⇒ Excel 直接打开不乱码。扫描算一次几十分钟，数据必须能带走。 */
  function exportScanCsv(r) {
    if (!r) return;
    const axKeys = (r.axes || []).map((a) => a.key);
    const head = [...axKeys, r.response, "yield_err_pct", "health", "co2d_max", "ph_min", "ok", "error"];
    const q = (v) => '"' + String(v === null || v === undefined ? "" : v).replace(/"/g, '""') + '"';
    const lines = (r.points || []).map((p) =>
      [...axKeys.map((k) => (p.x || {})[k]), p.y, p.yield_err, p.health || "", p.co2d_max, p.ph_min,
        p.ok ? 1 : 0, q(p.error || "")].join(","));
    const blob = new Blob(["\uFEFF" + head.join(",") + "\n" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `scan_batch${r.batch}_${r.response}_${r.n_total}pts.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 800);
  }

  function axes2(s, o) { return axes(s, o); }

  /* ================= 算子目录 ================= */
  const OP_LAYERS = [
    {
      layer: "仿真引擎", tone: "acc", items: [
        { name: "model.rhs", src: "model.py", desc: "33 维状态 / 105 维参数的机理右端：形态学、产物、底物、供氧、传热耦合。" },
        { name: "integrate_interval", src: "simulate.py", desc: "单采样区间 BDF 积分（rtol 1e-3 / atol 1e-6），对齐 MATLAB ode15s。" },
        { name: "simulate_open_loop", src: "simulate.py", desc: "以 V3 实测被控量序列驱动的开环回放，输出 1149 点全状态轨迹。" },
        { name: "build_params", src: "golden_params.py", desc: "批级覆盖字典 → 仿真参数。唯一装配口径，禁止绕过。" },
      ],
    },
    {
      layer: "验收算子", tone: "ok", items: [
        { name: "yield_metrics", src: "simulate.py", desc: "产量口径：harvested = −Σ(Fremoved·P)·h 与批末 V·P 之和，与 MATLAB 逐位同构。" },
        { name: "classify_health", src: "simulate.py", desc: "五通道健康分级（CO2d / pH 钳位 / pH 越域 / 产物崩塌 / 产量破线）。" },
        { name: "classify_crash", src: "simulate.py", desc: "旧崩溃判据。D-38：黄金集上恒真，仅作兼容，不作结论。" },
        { name: "shape_metrics", src: "simulate.py", desc: "产物形状指标（分相位）。产量指标对 P 轨迹失明，必须同时看形状。" },
        { name: "element_balance", src: "conservation_metrics.py", desc: "批级 C/N 元素平衡闭合度。" },
        { name: "trajectory_metrics", src: "trajectory_metrics.py", desc: "逐点轨迹对照 V3：RMSE / nRMSE / bias / R²（含 4h 化验滞后口径）。" },
      ],
    },
    {
      layer: "软测量求解器", tone: "warn", items: [
        { name: "estimate_batch", src: "soft_sensing.py", desc: "在线通道 54 组合网格反演 (μx, μp, m_s)，发散组合自动置劣解。" },
        { name: "estimate_stage2", src: "stage2_estimator.py", desc: "二阶段以 P_offline 为锚精化 μp —— 崩塌批 5/5 救回的关键。" },
        { name: "reconstruct_batch", src: "observe.py", desc: "集合平滑回溯型状态重构，带置信区间。" },
        { name: "observe_online", src: "observe.py", desc: "降阶 EnKF 在线同化（只读）。" },
      ],
    },
    {
      layer: "寻优求解器", tone: "crit", items: [
        { name: "optimize_feed", src: "optimize.py", desc: "MV 倍率 Nelder-Mead 反设计，带灾难崩溃约束。分钟级。" },
        { name: "advise_control", src: "mcp_server.py", desc: "时间窗 MV 反事实咨询 + T1 操作窗硬约束校验。" },
        { name: "discover_residual", src: "residual_discovery.py", desc: "残差结构发现（SINDy 式），输出候选缺失动力学。" },
      ],
    },
  ];

  function renderOperators() {
    $("#op-layers").innerHTML = OP_LAYERS.map((L) => `
      <div class="panel" style="margin-bottom:var(--gap)">
        <div class="panel-h"><h2>${esc(L.layer)}</h2><div class="spacer"></div><span class="tag ${L.tone}">${L.items.length} 项</span></div>
        <div class="panel-b">
          <div class="grid g-3">
            ${L.items.map((it) => `
              <div style="border:1px solid var(--line);border-radius:var(--radius-sm);padding:9px 11px">
                <div style="display:flex;align-items:center;gap:7px;margin-bottom:4px">
                  <span class="mono" style="font-size:11.5px;color:var(--accent)">${esc(it.name)}</span>
                  <div class="spacer"></div>
                  <span class="tag mute">${esc(it.src)}</span>
                </div>
                <div class="tiny muted" style="line-height:1.65">${esc(it.desc)}</div>
              </div>`).join("")}
          </div>
        </div>
      </div>`).join("");
    $("#op-count").textContent = OP_LAYERS.reduce((a, l) => a + l.items.length, 0) + " 个算子";
  }

  /* ================= 引擎状态 ================= */
  async function refreshEngine() {
    try {
      const h = await api("/health");
      const eng = $("#eng-kpi");
      eng.innerHTML = `
        <div class="kpi ok"><div class="lab">引擎状态</div><div class="val" style="font-size:17px">就绪</div><div class="foot">build ${esc(h.build)}</div></div>
        <div class="kpi"><div class="lab">可调参数</div><div class="val">${h.catalog_n}<small>键</small></div><div class="foot">由引擎源码 AST 派生</div></div>
        <div class="kpi"><div class="lab">L3 拒绝</div><div class="val">${h.catalog_rejected}<small>键</small></div><div class="foot">R166 裁决未切默认</div></div>
        <div class="kpi"><div class="lab">黄金集批次</div><div class="val">${h.n_batches}</div><div class="foot">COMBINED 单一装配源</div></div>`;
      $("#eng-contract").innerHTML = `
        <div><div class="tiny muted">平台版本</div><div class="mono">${esc(h.build)} · 仿真计算平台 v2</div></div>
        <div><div class="tiny muted">与旧平台关系</div><div class="mono">${esc(h.note)}</div></div>
        <div><div class="tiny muted">作业队列</div><div class="mono">排队 ${h.queue.by_state.queued || 0} · 运行 ${h.queue.by_state.running || 0} · 缓存 ${h.queue.cache_n}</div></div>`;

      const cat = state.catalog || (await api("/catalog")).catalog;
      const rows = [];
      cat.groups.forEach((g) => g.params.forEach((p) => rows.push(
        ["参数", g.label, p.key, p.src_default !== null && p.src_default !== undefined ? String(p.src_default) : "—", p.via || "get"]
      )));
      Object.keys(cat.rejected).forEach((k) => rows.push(["L3 拒绝", "—", k, "—", "rejected"]));
      $("#eng-table").innerHTML =
        `<thead><tr><th>类别</th><th>分组</th><th>键</th><th>源码默认</th><th>装配口</th></tr></thead><tbody>` +
        rows.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td class="mono">${esc(r[2])}</td><td class="n">${esc(r[3])}</td><td class="tiny">${esc(r[4])}</td></tr>`).join("") +
        "</tbody>";
    } catch (e) {
      $("#eng-kpi").innerHTML = `<div class="kpi crit"><div class="lab">引擎状态</div><div class="val" style="font-size:15px">不可达</div><div class="foot">${esc(e.message)}</div></div>`;
    }
  }
  $("#btn-refresh-engine").addEventListener("click", refreshEngine);

  /* ================= 启动 ================= */
  addEventListener("hashchange", () => {
    const h = location.hash.replace("#", "");
    if (VIEWS.some((v) => v.id === h) && h !== state.view) go(h);
  });
  boot();
})();
