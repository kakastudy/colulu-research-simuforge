/* Interactive process flow diagram (PFD) for the 100,000 L penicillin fed-batch.
 * Pure Canvas 2D, no dependencies. Shared by pfd.html and manuscript.html.
 * Logical coordinate space: 1200 x 640.
 */
(function (global) {
  "use strict";

  var W = 1200, H = 640;
  var C = {
    ink: "#22303C", blue: "#1F4E79", teal: "#16807A", amber: "#C9861B",
    red: "#B03A2E", purple: "#6B4C9A", grey: "#7F8C8D", light: "#EDF2F7",
    line: "#B9C6D2", white: "#FFFFFF", feed: "#1F4E79", gas: "#16807A",
    cool: "#8FA6B8", signal: "#6B4C9A", withdrawn: "#B03A2E"
  };

  var units = [
    { id: "sugar", x: 36, y: 78, w: 148, h: 74, label: "Sugar feed", sub: "glucose / sucrose",
      kind: "tank", color: C.feed, info: "26 process inputs; fed-batch profile, ~230 h" },
    { id: "oil", x: 36, y: 170, w: 148, h: 66, label: "Oil + antifoam", sub: "C source / foam",
      kind: "tank", color: C.feed, info: "carbon-balance input: 1000 x 0.773 g C/L" },
    { id: "paa", x: 36, y: 254, w: 148, h: 66, label: "PAA precursor", sub: "phenylacetic acid",
      kind: "tank", color: C.feed, info: "PAA channel is structurally NOT identifiable" },
    { id: "nh3", x: 36, y: 338, w: 148, h: 66, label: "NH3 / acid / base", sub: "pH + N source",
      kind: "tank", color: C.feed, info: "pH guard clamps; 129 events on batch 91" },
    { id: "air", x: 36, y: 422, w: 148, h: 76, label: "Air + sterile filter", sub: "compressor / sparger",
      kind: "box", color: C.gas, info: "aeration; DO2 cascade with agitation" },
    { id: "cw", x: 36, y: 516, w: 148, h: 60, label: "Cooling water", sub: "jacket loop",
      kind: "box", color: C.cool, info: "temperature control; heat Q state" },

    { id: "reactor", x: 404, y: 118, w: 350, h: 350, label: "R-101 FERMENTER", sub: "100,000 L  |  33-state stiff ODE",
      kind: "reactor", color: C.blue, info: "Penicillium chrysogenum, ~230 h, 37 emitted channels" },

    { id: "offgas", x: 404, y: 26, w: 350, h: 66, label: "Off-gas MS: O2 / CO2", sub: "OUR, CER, RQ",
      kind: "box", color: C.gas, info: "RQ reproduced exactly; simulated OUR/CER ~12% high" },
    { id: "ctrl", x: 820, y: 26, w: 340, h: 66, label: "Supervisory control + evidence gate", sub: "L0 frozen / L1 opt-in / L2 gate / L3 held",
      kind: "box", color: C.purple, info: "14 capabilities, 12 operators; /api/invoke has 4 admission gates" },

    { id: "sens", x: 820, y: 118, w: 340, h: 74, label: "On-line sensors", sub: "DO2, pH, T, P, weight, agitation",
      kind: "box", color: C.teal, info: "0.2 h sampling; non-negativity guards on states 0-30" },
    { id: "soft", x: 820, y: 210, w: 340, h: 74, label: "Soft sensors (5-fold CV)", sub: "X 2.28% | viscosity 5.57% | DO2 11.83%",
      kind: "box", color: C.teal, info: "DELIVERABLE channels; median nRMSE over 86 batches" },
    { id: "raman", x: 820, y: 302, w: 340, h: 74, label: "Raman spectrometer", sub: "WITHDRAWN - no independent information",
      kind: "box", color: C.red, info: "WITHDRAWN: incremental R2 0.0199 -> 0.0092; ~1000x scale mismatch (D-71)" },
    { id: "myc", x: 820, y: 394, w: 340, h: 74, label: "Mycelial compartments A0/A1/A3/A4", sub: "WITHDRAWN - rank(H)=0, nullity=4",
      kind: "box", color: C.red, info: "WITHDRAWN: rank(H_assim)=0, nullity=4; rank(H_report)=1, nullity=3 (D-88)" },
    { id: "harvest", x: 820, y: 486, w: 340, h: 74, label: "Harvest / product mass", sub: "end-of-batch yield gate +/-5%",
      kind: "box", color: C.blue, info: "RMSE 2.3448%, 86/86 within +/-5% (reconstruction consistency)" }
  ];

  // polyline streams: [pts], colour, width, label, dashed?
  var streams = [
    { id: "f1", pts: [[184, 115], [250, 115], [250, 168], [404, 168]], c: C.feed, w: 2.2,
      label: "F1 sugar", info: "substrate feed; S channel is a circular comparison" },
    { id: "f2", pts: [[184, 203], [268, 203], [268, 208], [404, 208]], c: C.feed, w: 2.2,
      label: "F2 oil", info: "oil feed; included in C_in element balance" },
    { id: "f3", pts: [[184, 287], [286, 287], [286, 248], [404, 248]], c: C.feed, w: 2.2,
      label: "F3 PAA", info: "precursor feed; PAA channel NOT identifiable" },
    { id: "f4", pts: [[184, 371], [304, 371], [304, 288], [404, 288]], c: C.feed, w: 2.2,
      label: "F4 NH3", info: "pH control dosing; acid/base split" },
    { id: "a1", pts: [[184, 460], [330, 460], [330, 440], [470, 440], [470, 420]], c: C.gas, w: 2.4,
      label: "A1 sterile air", info: "sparger aeration; kLa nominal 85 +/- 10" },
    { id: "c1", pts: [[184, 546], [360, 546], [360, 430], [404, 430]], c: C.cool, w: 2.0,
      label: "CW supply", info: "jacket cooling; temperature control loop" },
    { id: "c2", pts: [[754, 430], [790, 430], [790, 546], [184, 546]], c: C.cool, w: 1.6,
      label: "", info: "jacket cooling-water return" },
    { id: "g1", pts: [[580, 118], [580, 92]], c: C.gas, w: 2.4,
      label: "off-gas", info: "O2 / CO2 to mass spectrometer; OUR / CER / RQ" },
    { id: "p1", pts: [[754, 400], [790, 400], [790, 523], [820, 523]], c: C.blue, w: 2.6,
      label: "broth", info: "end-of-batch product mass measurement" }
  ];

  // control / information signals (dashed); labelAt keeps annotations in clear space
  var signals = [
    { id: "fb", pts: [[820, 150], [788, 150], [788, 108], [1100, 108], [1100, 92]],
      c: C.signal, label: "certified feedback: DO2 / pH / T", labelAt: [944, 100],
      info: "on-line sensors -> supervisory control; DO2 cascade, pH dosing, temperature" },
    { id: "wd", pts: [[1160, 431], [1172, 431], [1172, 92], [1160, 92]],
      c: C.withdrawn, label: "WITHDRAWN", labelAt: [1010, 294],
      info: "Raman -> PAA and mycelial compartments: no independent information (D-71, D-88)" },
    { id: "wd2", pts: [[1160, 339], [1172, 339]],
      c: C.withdrawn, label: "", labelAt: null, info: "nullity(H) > 0 forces WITHDRAWN" },
    { id: "chain", pts: [[754, 455], [790, 455], [790, 470]],
      c: C.signal, label: "", labelAt: null,
      info: "EnKF -> MHE -> carbon balance -> explicit_failure" }
  ];

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  var FS = 1.22; // global font scale: keeps print-size >= ~5pt at full A4 width
  function text(ctx, s, x, y, size, color, align, bold) {
    ctx.fillStyle = color || C.ink;
    size = Math.round(size * FS * 10) / 10;
    ctx.font = (bold ? "600 " : "") + size + "px 'Segoe UI', 'DejaVu Sans', sans-serif";
    ctx.textAlign = align || "left";
    ctx.textBaseline = "middle";
    ctx.fillText(s, x, y);
  }

  function arrow(ctx, x, y, ang, color, size) {
    ctx.save();
    ctx.translate(x, y); ctx.rotate(ang);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, 0); ctx.lineTo(-size, -size * 0.55); ctx.lineTo(-size, size * 0.55);
    ctx.closePath(); ctx.fill();
    ctx.restore();
  }

  function poly(ctx, pts) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  }

  function drawUnit(ctx, u, hot) {
    ctx.save();
    ctx.shadowColor = "rgba(31,78,121,0.13)";
    ctx.shadowBlur = hot ? 14 : 6;
    ctx.shadowOffsetY = 2;
    var grad = ctx.createLinearGradient(u.x, u.y, u.x, u.y + u.h);
    grad.addColorStop(0, "#FFFFFF");
    grad.addColorStop(1, hot ? "#E3EEF7" : "#F4F8FB");
    rr(ctx, u.x, u.y, u.w, u.h, u.kind === "reactor" ? 26 : 9);
    ctx.fillStyle = grad; ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.lineWidth = hot ? 2.2 : 1.3;
    ctx.strokeStyle = u.color; ctx.stroke();
    // colour bar
    ctx.fillStyle = u.color;
    rr(ctx, u.x, u.y, 5, u.h, 2); ctx.fill();

    if (u.kind === "reactor") {
      // vessel body, liquid level, agitator, baffles, sparger bubbles
      var bx = u.x + 26, by = u.y + 56, bw = u.w - 52, bh = u.h - 92;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(bx, by + 22);
      ctx.quadraticCurveTo(bx, by, bx + 24, by);
      ctx.lineTo(bx + bw - 24, by);
      ctx.quadraticCurveTo(bx + bw, by, bx + bw, by + 22);
      ctx.lineTo(bx + bw, by + bh - 30);
      ctx.quadraticCurveTo(bx + bw, by + bh, bx + bw - 30, by + bh);
      ctx.lineTo(bx + 30, by + bh);
      ctx.quadraticCurveTo(bx, by + bh, bx, by + bh - 30);
      ctx.closePath();
      ctx.clip();
      var lg = ctx.createLinearGradient(0, by + 60, 0, by + bh);
      lg.addColorStop(0, "#EAF3F7"); lg.addColorStop(1, "#B9D9D3");
      ctx.fillStyle = lg; ctx.fillRect(bx, by + 62, bw, bh);
      ctx.strokeStyle = "#16807A"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(bx, by + 62); ctx.lineTo(bx + bw, by + 62); ctx.stroke();
      // bubbles
      for (var i = 0; i < 22; i++) {
        var bxp = bx + 24 + ((i * 47) % (bw - 48));
        var byp = by + bh - 12 - ((i * 31) % (bh - 80));
        ctx.beginPath(); ctx.arc(bxp, byp, 2 + (i % 3), 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(22,128,122,0.42)"; ctx.lineWidth = 0.8; ctx.stroke();
      }
      ctx.restore();
      // agitator shaft + impellers
      var cx = u.x + u.w / 2;
      ctx.strokeStyle = C.blue; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(cx, u.y + 44); ctx.lineTo(cx, u.y + u.h - 60); ctx.stroke();
      [u.y + 210, u.y + 300].forEach(function (yy) {
        ctx.lineWidth = 5; ctx.strokeStyle = C.blue;
        ctx.beginPath(); ctx.moveTo(cx - 46, yy); ctx.lineTo(cx + 46, yy); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx - 46, yy - 8); ctx.lineTo(cx - 46, yy + 8); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx + 46, yy - 8); ctx.lineTo(cx + 46, yy + 8); ctx.stroke();
      });
      // baffles
      ctx.strokeStyle = "rgba(31,78,121,0.35)"; ctx.lineWidth = 2;
      [bx + 16, bx + bw - 16].forEach(function (xx) {
        ctx.beginPath(); ctx.moveTo(xx, by + 78); ctx.lineTo(xx, by + bh - 20); ctx.stroke();
      });
      text(ctx, u.label, u.x + u.w / 2, u.y + 24, 15, u.color, "center", true);
      text(ctx, u.sub, u.x + u.w / 2, u.y + 43, 10, C.grey, "center");
      ctx.fillStyle = "rgba(255,255,255,0.86)";
      ctx.fillRect(u.x + 40, u.y + u.h - 38, u.w - 80, 20);
      text(ctx, "33 states  |  105 parameters  |  26 inputs", cx, u.y + u.h - 28,
           9.5, C.blue, "center");
    } else {
      var cy = u.y + u.h / 2;
      text(ctx, u.label, u.x + 16, cy - (u.h > 60 ? 9 : 0), 11.5, u.color, "left", true);
      if (u.h > 60) text(ctx, u.sub, u.x + 16, cy + 10, 9, C.grey, "left");
    }
    ctx.restore();
  }

  function drawStream(ctx, s, t, hot, showParticles) {
    var pts = s.pts;
    ctx.save();
    ctx.lineWidth = hot ? s.w + 1.8 : s.w;
    ctx.strokeStyle = s.c;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    poly(ctx, pts); ctx.stroke();
    var a = pts[pts.length - 2], b = pts[pts.length - 1];
    arrow(ctx, b[0], b[1], Math.atan2(b[1] - a[1], b[0] - a[0]), s.c, 7);
    if (showParticles) {
      for (var k = 0; k < 3; k++) {
        var seg = 0, total = 0, lens = [];
        for (var i = 1; i < pts.length; i++) {
          var d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
          lens.push(d); total += d;
        }
        var target = ((t * 0.055 + k / 3) % 1) * total;
        var acc = 0;
        for (var j = 0; j < lens.length; j++) {
          if (acc + lens[j] >= target) {
            var f = (target - acc) / lens[j];
            var px = pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f;
            var py = pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f;
            ctx.beginPath(); ctx.arc(px, py, hot ? 3.6 : 2.6, 0, Math.PI * 2);
            ctx.fillStyle = s.c; ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
            break;
          }
          acc += lens[j];
        }
      }
    }
    // label at the first horizontal segment
    var p0 = pts[0], p1 = pts[1];
    if (Math.abs(p0[1] - p1[1]) < 2 && s.label) {
      text(ctx, s.label, (p0[0] + p1[0]) / 2, p0[1] - 9, 8.6, s.c, "center", true);
    }
    ctx.restore();
  }

  function drawSignal(ctx, s, hot) {
    ctx.save();
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = hot ? 2.4 : 1.5;
    ctx.strokeStyle = s.c;
    poly(ctx, s.pts); ctx.stroke();
    ctx.setLineDash([]);
    var a = s.pts[s.pts.length - 2], b = s.pts[s.pts.length - 1];
    arrow(ctx, b[0], b[1], Math.atan2(b[1] - a[1], b[0] - a[0]), s.c, 6);
    if (s.label && s.labelAt) {
      text(ctx, s.label, s.labelAt[0], s.labelAt[1], 8.6, s.c, "left", true);
    }
    ctx.restore();
  }

  function drawLegend(ctx, showWithdrawn) {
    var y = 596, x = 36;
    ctx.font = Math.round(9.2 * FS * 10) / 10 + "px 'Segoe UI', 'DejaVu Sans', sans-serif";
    var items = [
      [C.feed, "material feed"], [C.gas, "air / off-gas"], [C.cool, "cooling water"],
      [C.signal, "certified measurement & control"], [C.withdrawn, "withdrawn / non-identifiable"]
    ];
    items.forEach(function (it) {
      ctx.save();
      if (it[0] === C.signal || it[0] === C.withdrawn) ctx.setLineDash([6, 4]);
      ctx.strokeStyle = it[0]; ctx.lineWidth = 2.4;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 28, y); ctx.stroke();
      ctx.restore();
      text(ctx, it[1], x + 35, y, 9.2, C.ink, "left");
      x += 35 + ctx.measureText(it[1]).width + 30;
    });
    text(ctx, "R-101 = 100,000 L industrial penicillin fed-batch  |  IndPenSim benchmark  |  "
         + "in-silico evidence, no prospective plant validation",
         36, 622, 8.6, C.grey, "left");
  }

  function PFD(canvas, opts) {
    opts = opts || {};
    var ctx = canvas.getContext("2d");
    var staticMode = !!opts.staticMode;
    var showSignals = opts.showSignals !== false;
    var showWithdrawn = opts.showWithdrawn !== false;
    var running = !staticMode;
    var t = 0, hot = null, selected = null, scale = 1;
    var hotspots = [];
    var tip = opts.tooltip || null;

    function resize() {
      var cssW = canvas.clientWidth || W;
      var cssH = canvas.clientHeight || (cssW * H / W);
      var dpr = Math.min(global.devicePixelRatio || 1, 2);
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      scale = cssW / W;
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
    }

    function hit(mx, my) {
      for (var i = hotspots.length - 1; i >= 0; i--) {
        var h = hotspots[i];
        if (mx >= h.x && mx <= h.x + h.w && my >= h.y && my <= h.y + h.h) return h;
      }
      return null;
    }

    function draw() {
      ctx.save();
      ctx.fillStyle = C.white;
      ctx.fillRect(0, 0, W, H);
      // faint process-area bands
      ctx.fillStyle = "#F7FAFC";
      rr(ctx, 20, 14, 196, 578, 12); ctx.fill();
      rr(ctx, 388, 14, 382, 578, 12); ctx.fill();
      rr(ctx, 804, 14, 376, 578, 12); ctx.fill();
      text(ctx, "FEED / UTILITIES", 28, 22, 9, C.grey, "left", true);
      text(ctx, "BIOREACTION", 398, 14, 9, C.grey, "left", true);
      text(ctx, "OBSERVATION & CONTROL", 814, 14, 9, C.grey, "left", true);

      hotspots = [];
      units.forEach(function (u) {
        if (!showWithdrawn && (u.id === "raman" || u.id === "myc")) return;
        drawUnit(ctx, u, hot && hot.id === u.id || selected === u.id);
        hotspots.push({ x: u.x, y: u.y, w: u.w, h: u.h, id: u.id, label: u.label, info: u.info });
      });
      streams.forEach(function (s) {
        drawStream(ctx, s, t, (hot && hot.id === s.id) || selected === s.id, t > 0);
      });
      if (showSignals) {
        signals.forEach(function (s) {
          if (!showWithdrawn && s.c === C.withdrawn) return;
          drawSignal(ctx, s, hot && hot.id === s.id);
          var p = s.pts[0];
          hotspots.push({ x: p[0] - 8, y: p[1] - 8, w: 16, h: 16, id: s.id,
                          label: s.label || "control signal", info: s.info });
          if (s.labelAt) {
            hotspots.push({ x: s.labelAt[0] - 4, y: s.labelAt[1] - 9, w: 200, h: 18,
                            id: s.id, label: s.label, info: s.info });
          }
        });
      }
      streams.forEach(function (s) {
        var p = s.pts[0];
        hotspots.push({ x: p[0] - 9, y: p[1] - 9, w: 18, h: 18, id: s.id,
                        label: s.label || "process stream", info: s.info });
      });
      text(ctx, "Estimator chain:  EnKF -> MHE -> steady-state C balance -> explicit_failure",
           406, 492, 9.6, C.signal, "left", true);
      drawLegend(ctx, showWithdrawn);
      ctx.restore();
    }

    function frame() {
      if (running) t += 1;
      draw();
      if (running) global.requestAnimationFrame(frame);
    }

    function move(ev) {
      var r = canvas.getBoundingClientRect();
      var mx = (ev.clientX - r.left) / scale;
      var my = (ev.clientY - r.top) / scale;
      hot = hit(mx, my);
      if (tip) {
        if (hot) {
          tip.style.display = "block";
          tip.innerHTML = "<strong>" + hot.label + "</strong><br>" + hot.info;
          tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 260) + "px";
          tip.style.top = (ev.clientY - r.top + 14) + "px";
          canvas.style.cursor = "pointer";
        } else {
          tip.style.display = "none";
          canvas.style.cursor = "default";
        }
      }
      if (staticMode) draw();
    }

    canvas.addEventListener("mousemove", move);
    canvas.addEventListener("mouseleave", function () {
      hot = null;
      if (tip) tip.style.display = "none";
      if (staticMode) draw();
    });
    canvas.addEventListener("click", function () {
      selected = hot ? (selected === hot.id ? null : hot.id) : null;
      if (staticMode) draw();
    });
    global.addEventListener("resize", function () { resize(); draw(); });

    resize();
    if (staticMode) { t = 26; draw(); }
    else frame();

    return {
      resize: function () { resize(); draw(); },
      toggleSignals: function (v) { showSignals = v === undefined ? !showSignals : v; draw(); },
      toggleWithdrawn: function (v) { showWithdrawn = v === undefined ? !showWithdrawn : v; draw(); },
      toggleAnimation: function (v) {
        var was = running;
        running = v === undefined ? !running : v;
        if (!was && running) frame();
        else draw();
      },
      exportPNG: function () {
        var a = document.createElement("a");
        a.download = "fig12_pfd.png";
        a.href = canvas.toDataURL("image/png");
        a.click();
      },
      renderStatic: function () { running = false; t = 26; resize(); draw(); }
    };
  }

  global.PFD = { create: PFD, units: units, streams: streams, signals: signals };
})(window);
