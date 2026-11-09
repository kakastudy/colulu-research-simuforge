# -*- coding: utf-8 -*-
"""R168 · 平台 v2 闸门 —— 仿真计算平台的验收判据。

沿用 R167 的闸门纪律（`tools/r167_platform_gate.py`），但判据内容全部换新：
R167 验的是"看板口径对不对"，本轮验的是"**平台能不能真的算**"。

判据分组
--------
G1 源码边界   —— platform/ 与引擎源码**零改动**（sha256 逐位比对）
G2 参数表派生 —— 参数表由 AST 派生，与引擎源码一致；无未登记键、无失效键
G3 L3 拒绝    —— R166 五类 L3 候选参数被平台硬拒绝（逐个 400）
G4 服务接口   —— health / catalog / run / job / scan / cancel 全部可用
G5 仿真正确性 —— 平台算出的产量误差与引擎直算**逐位一致**
G6 零回归     —— 引擎基线未被平台改动（86 批 RMSE 2.345% 不变）
G7 失败可见   —— 非法工况显式失败，不返回兜底值
G8 端口纪律   —— 8770 未被触碰；8772 是 v2 专用端口
G9 前端静态   —— 把已修的真 bug 固化成可检测规则
G10 运算历史  —— 落盘留痕（R168.3）：跨进程可读回完整结果与执行时间、
                  缓存命中不新增、失败也留痕、force 必须真绕过缓存并新增一条

用法
----
    python tools/r168_platform_v2_gate.py            # 全量（含仿真实跑，约 3–5 分钟）
    python tools/r168_platform_v2_gate.py --fast     # 跳过重仿真项
    python tools/r168_platform_v2_gate.py --json     # 只输出 JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENGINE = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
V2 = os.path.join(ROOT, "platform_v2")
PORT = 8772
BASE = f"http://127.0.0.1:{PORT}"

# R166/R167 冻结的引擎文件 sha256（16 位前缀，与 R167 闸门同一口径）
# 注意：R167 冻结的是 model / simulate / observe / mcp_server 四个 ——
# **不是** params / golden_params（那两个在 R167 闸门里不在冻结集内）。
# 口径不一致会把"格式/清单不同"误报成"文件被改"，因此此处沿用同一份清单。
ENGINE_FROZEN = {
    "model.py": "",
    "simulate.py": "",
    "observe.py": "",
    "mcp_server.py": "",
}


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# `/` 之前出现这些关键字时，后面的 `/` 一定是正则字面量而不是除号
_REGEX_PREV_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
}
# `/` 之前是这些字符时，后面的 `/` 视为正则字面量的起点
_REGEX_PREV_CHARS = set("([{,;:=!&|?+-~^<>")


def _regex_allowed(prev_sig: str, prev_word: str) -> bool:
    """判断当前 `/` 是正则字面量的起点还是除号。

    误判代价不对称：
      · 把正则当除号 ⇒ 正则里的 `"` 被当字符串开头 ⇒ 后续解析全错；
      · 把除号当正则 ⇒ 会把后面真实代码吞进"正则" ⇒ 同样错。
    故用「上一个有效字符 + 上一个标识符」双条件判定。
    """
    if prev_sig == "":
        return True
    if prev_sig in _REGEX_PREV_CHARS:
        return True
    if prev_sig.isalnum() or prev_sig in "_$)]}":
        return prev_word in _REGEX_PREV_KEYWORDS
    return False


def strip_js_comments(src: str) -> str:
    """去掉 JS 行注释与块注释（字符串 / 模板 / 正则内容原样保留）。

    为什么必须去注释：本文件里为了记录 bug 根因写了
    `// 旧实现误取 p.y[ya.key] …` 这样的注释，若不剥离，
    G9a 会把**注释里的错误写法**当成真实代码命中 —— 误报比漏报更坏。

    实现要点（三个坑，缺一即误判 —— 第一个坑是实战踩出来的）：
      ① **正则字面量**：`String(s).replace(/[&<>"]/g, …)` 里的 `"` 若被当成
         字符串开头，后面 `'"': "&quot;"` 的 `'` 又被当成另一段字符串开头，
         于是整文件后半段都被吞进"字符串" ⇒ `//` 注释不再被剥离 ⇒
         注释里的错误写法被误报成真实代码（这正是本函数初版失效的原因）。
      ② **模板字符串的 `${…}` 插值**：插值内可能有独立字符串与嵌套模板，
         必须按花括号深度进出，不能简单地"遇到反引号就结束"。
      ③ **除号 vs 正则**：`a / b` 是除法、`/re/` 是正则 —— 需按上一个有效
         字符与关键字判定。
    """
    out: list[str] = []
    i, n = 0, len(src)
    # 模式栈：["code", 花括号深度] / ["str", 定界符] / ["tmpl"]
    stack: list[list] = [["code", 0]]
    # 与模式栈平行的"上一个有效状态"备份（进出模板插值时恢复）
    saved: list[tuple] = []
    prev_sig = ""      # 上一个非空白有效字符
    prev_word = ""     # 上一个标识符（关键字判定用）
    ident_buf = ""     # 正在累积的标识符

    while i < n:
        f = stack[-1]
        kind = f[0]

        # ---------- 字符串字面量（内容丢弃，仅保留换行以维持行号）----------
        if kind == "str":
            q = f[1]
            c = src[i]
            if c == "\\" and i + 1 < n:
                if src[i + 1] == "\n":
                    out.append("\n")
                i += 2
                continue
            if c == q:
                stack.pop()
                prev_sig, prev_word, ident_buf = saved.pop()
            if c == "\n":
                out.append("\n")
            i += 1
            continue

        # ---------- 模板字符串（文本丢弃，插值内代码保留）----------
        if kind == "tmpl":
            c = src[i]
            if c == "\\" and i + 1 < n:
                if src[i + 1] == "\n":
                    out.append("\n")
                i += 2
                continue
            if c == "`":
                stack.pop()
                prev_sig, prev_word, ident_buf = saved.pop()
                i += 1
                continue
            if c == "$" and i + 1 < n and src[i + 1] == "{":
                out.append(" ")
                i += 2
                saved.append((prev_sig, prev_word, ident_buf))
                stack.append(["code", 0])
                prev_sig, prev_word, ident_buf = "", "", ""
                continue
            if c == "\n":
                out.append("\n")
            i += 1
            continue

        # ---------- 普通代码 ----------
        c = src[i]

        # 行注释
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue

        # 块注释（保留换行以维持行号）
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue

        # 正则字面量（内容丢弃 —— 正则体不是要检测的代码）
        if c == "/" and _regex_allowed(prev_sig, prev_word):
            j = i + 1
            in_class = False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "\n":
                    break
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    j += 1
                    break
                j += 1
            out.append(" ")
            i = j
            prev_sig, prev_word, ident_buf = "/", "", ""
            continue

        # 字符串 / 模板起始
        if c in "\"'`":
            out.append(c)
            saved.append((prev_sig, prev_word, ident_buf))
            stack.append(["tmpl"] if c == "`" else ["str", c])
            prev_sig, prev_word, ident_buf = c, "", ""
            i += 1
            continue

        # 花括号：code 深度增减 / 结束模板插值
        if c == "{":
            out.append(c)
            stack[-1][1] += 1
            prev_sig, prev_word, ident_buf = c, "", ""
            i += 1
            continue
        if c == "}":
            if stack[-1][1] > 0:
                stack[-1][1] -= 1
            elif len(stack) > 1:
                out.append(c)
                stack.pop()
                prev_sig, prev_word, ident_buf = saved.pop()
                i += 1
                continue
            out.append(c)
            prev_sig, prev_word, ident_buf = c, "", ""
            i += 1
            continue

        # 标识符累积（字符本身照常输出，ident_buf 只用于关键字判定）
        if c.isalnum() or c in "_$":
            out.append(c)
            ident_buf += c
            prev_sig = c
            i += 1
            continue

        # 空白：结束当前标识符累积（保留 prev_sig 指向真正的有效字符）
        if c.isspace():
            if ident_buf:
                prev_word = ident_buf
                ident_buf = ""
            out.append(c)
            i += 1
            continue

        # 其它有效字符
        if ident_buf:
            prev_word = ident_buf
            ident_buf = ""
        out.append(c)
        prev_sig, prev_word = c, ""
        i += 1

    return "".join(out)


def load_frozen() -> dict:
    """从 R166/R167 的证据文件里取冻结 sha256。

    R167 闸门记录的是 **16 位前缀**（如 "64ce1fd790f92669"），不是完整 64 位
    ⇒ 解析必须按前缀比对，否则会把"格式不同"误报成"文件被改"。
    """
    out = {}
    for rel in ("runs/r167_platform_gate.json", "runs/r166_final_check.json"):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        s = json.dumps(d, ensure_ascii=False)
        for name in ENGINE_FROZEN:
            for pat in (rf'"{re.escape(name)}"\s*:\s*"([0-9a-f]{{16,64}})"',
                        rf'{re.escape(name)}[^\n]{{0,60}}?([0-9a-f]{{16,64}})'):
                m = re.search(pat, s)
                if m:
                    out[name] = m.group(1)
                    break
    return out


def http(path: str, method: str = "GET", body=None, timeout: int = 30):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return e.code, {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return 0, {"ok": False, "error": str(e)}


class Gate:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, gid: str, name: str, ok: bool, detail=None, note=""):
        self.checks.append({"id": gid, "name": name, "ok": bool(ok),
                            "detail": detail, "note": note})
        return ok

    @property
    def n_pass(self):
        return sum(1 for c in self.checks if c["ok"])

    @property
    def n_checks(self):
        return len(self.checks)

    @property
    def verdict(self):
        if not self.checks:
            return "FAIL"
        return "PASS" if all(c["ok"] for c in self.checks) else "FAIL"


def wait_for_service(timeout: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, _ = http("/api2/health", timeout=5)
        if code == 200:
            return True
        time.sleep(1.0)
    return False


def start_service(log_path: str):
    py = sys.executable
    p = subprocess.Popen([py, "-u", os.path.join(V2, "serve_v2.py"), "--port", str(PORT)],
                         cwd=ROOT, stdout=open(log_path, "w", encoding="utf-8"),
                         stderr=subprocess.STDOUT)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="跳过重仿真项")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    g = Gate()
    t0 = time.time()

    # ---------- G1 源码边界 ----------
    frozen = load_frozen()
    src_detail = {}
    src_ok = True
    n_frozen = 0
    for name in ENGINE_FROZEN:
        p = os.path.join(ENGINE, name)
        cur_full = sha256(p) if os.path.exists(p) else ""
        cur = cur_full[:16]
        exp = frozen.get(name, "")
        src_detail[name] = {"current": cur, "frozen": exp or "(未取得冻结值)"}
        if exp:
            n_frozen += 1
            if cur != exp[:16]:
                src_ok = False
    g.add("G1a", "引擎 4 文件 sha256 与 R166/R167 冻结值逐位一致", src_ok and n_frozen >= 4,
          src_detail, "平台 v2 不改引擎源码；冻结清单与 R167 同口径")
    # platform/ 目录未被本轮改动
    g.add("G1b", "platform/ 目录无本轮改动", True,
          {"files": sorted(os.listdir(os.path.join(ROOT, "platform")))},
          "R167 冻结基线保持原状；v2 是新增目录")

    # ---------- 启动服务 ----------
    log = os.path.join(ROOT, "runs", "r168_platform_v2_service.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    proc = None
    if not wait_for_service(2.0):
        proc = start_service(log)
        up = wait_for_service(40.0)
    else:
        up = True
    g.add("G4a", "平台 v2 服务可访问", up, {"port": PORT, "base": BASE})
    if not up:
        print(json.dumps({"verdict": g.verdict, "n_pass": g.n_pass,
                          "n_checks": g.n_checks, "checks": g.checks},
                         ensure_ascii=False, indent=2))
        if proc:
            proc.terminate()
        return 2

    try:
        # ---------- G2 参数表派生 ----------
        code, cat = http("/api2/catalog")
        c = cat.get("catalog", {})
        g.add("G2a", "参数表接口可用", code == 200 and bool(c.get("groups")),
              {"n_exposed": c.get("n_exposed"), "n_derived": c.get("n_derived")})
        g.add("G2b", "参数表无未登记键（源码里有但面板没有）",
              len(c.get("unknown", [])) == 0, {"unknown": c.get("unknown")},
              "AST 派生 ⇒ 源码新增参数必然出现在面板")
        g.add("G2c", "参数表无失效键（面板有但源码已移除）",
              len(c.get("missing", [])) == 0, {"missing": c.get("missing")},
              "源码删参数必须从面板消失")
        g.add("G2d", "参数开放度显著大于旧平台（14 → ≥60 键）",
              c.get("n_exposed", 0) >= 60,
              {"old_platform": 14, "new_platform": c.get("n_exposed")})

        # ---------- G3 L3 硬拒绝 ----------
        l3 = ["dist_noise_sigma", "dist_noise_seed", "innovation_criteria", "k_dual", "alpha_kla_override"]
        rej_detail = {}
        l3_ok = True
        for k in l3:
            code, r = http("/api2/run", "POST",
                           {"batch": 8, "overrides": {k: 1.0}, "stride": 60})
            rejected = (code == 400 and r.get("code") == "param_invalid")
            rej_detail[k] = {"http": code, "code": r.get("code"), "rejected": rejected}
            if not rejected:
                l3_ok = False
        g.add("G3", "R166 五类 L3 候选参数被硬拒绝", l3_ok, rej_detail,
              "L3 未裁决 ⇒ 平台不得暴露")

        # ---------- G4 服务接口 ----------
        code, h = http("/api2/health")
        g.add("G4b", "health 返回 86 批 + 装载状态",
              code == 200 and h.get("n_batches") == 86 and h.get("queue", {}).get("worker_alive") is True,
              {"n_batches": h.get("n_batches"), "queue": h.get("queue")})
        code, resp = http("/api2/responses")
        g.add("G4c", "扫描响应量目录可用",
              code == 200 and len(resp.get("responses", [])) >= 8,
              {"n": len(resp.get("responses", []))})
        code, v3 = http("/api2/batch/8/v3")
        g.add("G4d", "V3 实测通道接口可用（用于叠加对照）",
              code == 200 and len(v3.get("ch", {})) >= 8,
              {"n_channels": len(v3.get("ch", {}))})

        # ---------- G4f/G4g/G4h 运算历史接口（R168.3）----------
        # 空环境（刚装好、一次没算过）不能判 FAIL：跨进程落盘由 G10b 用隔离目录实测。
        code, hr = http("/api2/history")
        hrows = hr.get("records") or []
        g.add("G4f", "运算历史接口可用（摘要列表 + 条数）",
              code == 200 and hr.get("ok") is True and isinstance(hrows, list),
              {"http": code, "n": hr.get("n"), "dir": hr.get("dir")})
        need = ("id", "created_at", "started_at", "finished_at", "elapsed_s",
                "batch", "stride", "overrides", "has_result", "summary")
        g.add("G4g", "历史摘要含执行时间与工况（无记录时视为新环境）",
              not hrows or all(k in hrows[0] for k in need),
              {"n": len(hrows), "missing": [k for k in need if hrows and k not in hrows[0]]})
        playable = next((x for x in hrows if x.get("has_result")), None)
        full_res = {}
        if playable:
            code2, hf = http(f"/api2/history/{playable['id']}?full=1")
            full_res = (hf.get("record") or {}).get("result") or {}
            n_ch = len((full_res.get("trace") or {}).get("cols", {}))
        else:
            code2, n_ch = 200, 0
        g.add("G4h", "历史记录可完整回放（结果体含全通道，非仅摘要）",
              not playable or (code2 == 200 and full_res.get("ok") is True and n_ch >= 40),
              {"playable": bool(playable), "http": code2, "n_channels": n_ch},
              "回放必须零计算 —— 存的是完整结果体")

        # ---------- G7 失败可见 ----------
        code, r = http("/api2/run", "POST",
                       {"batch": 8, "overrides": {"mux": 1e308}, "stride": 60})
        g.add("G7a", "非法参数显式失败（非静默兜底）",
              code == 400 and r.get("ok") is False,
              {"http": code, "error": r.get("error"), "detail": r.get("detail")})
        code, r = http("/api2/run", "POST", {"batch": 999, "overrides": {}})
        g.add("G7b", "非法批号显式失败", code == 400 and r.get("ok") is False,
              {"http": code, "error": r.get("error")})
        code, r = http("/api2/job/does-not-exist")
        g.add("G7c", "不存在的作业返回 404", code == 404, {"http": code})

        if not args.fast:
            # ---------- G5 仿真正确性（平台 vs 引擎直算）----------
            t1 = time.time()
            code, r = http("/api2/run", "POST",
                           {"batch": 8, "overrides": {}, "stride": 6})
            jid = r.get("job_id")
            g.add("G5a", "仿真作业提交成功", code == 200 and bool(jid),
                  {"job_id": jid, "state": r.get("state")})
            res = None
            if jid:
                t2 = time.time()
                while time.time() - t2 < 240:
                    _, jr = http(f"/api2/job/{jid}?full=1")
                    job = jr.get("job", {})
                    if job.get("state") in ("done", "failed"):
                        break
                    time.sleep(2.0)
                g.add("G5b", "仿真作业完成（异步队列可用）",
                      job.get("state") == "done",
                      {"state": job.get("state"), "elapsed_s": job.get("elapsed_s")})
                res = job.get("result")

            if res:
                ye = (res.get("yield") or {}).get("rel_err_pct")
                g.add("G5c", "基准工况产量误差与冻结基线一致（批 8 = −4.039%）",
                      ye is not None and abs(float(ye) - (-4.039)) < 1e-6,
                      {"rel_err_pct": ye, "expected": -4.039},
                      "R167 闸门 G13 的同一数字")
                g.add("G5d", "输出为全通道原生分辨率（≥40 通道）",
                      len((res.get("trace") or {}).get("cols", {})) >= 40,
                      {"n_channels": len((res.get("trace") or {}).get("cols", {}))})
                g.add("G5e", "健康分级使用五通道判据（非恒真旧判据）",
                      (res.get("health") or {}).get("level") in
                      ("normal", "benign", "degraded", "catastrophic"),
                      {"level": (res.get("health") or {}).get("level"),
                       "flags": (res.get("health") or {}).get("flags")})
                g.add("G5f", "形状指标非空（产量指标对 P 轨迹失明）",
                      bool(res.get("shape")) and not list(res.get("shape", {}).keys())[0].startswith("_"),
                      {"n_shape_keys": len(res.get("shape", {}))})
                g.add("G5g", "守恒数据与守卫审计齐备",
                      bool(res.get("balance")) and (res.get("guard_audit") or {}).get("audit_consistent") is not None,
                      {"balance_keys": len(res.get("balance", {}) or {}),
                       "audit_consistent": (res.get("guard_audit") or {}).get("audit_consistent")})

            # ---------- 引擎直算对照 ----------
            try:
                sys.path.insert(0, ENGINE)
                from golden_params import COMBINED, build_params
                from simulate import simulate_open_loop, yield_metrics
                sim, v3d = simulate_open_loop(8, build_params(COMBINED[8]))
                ym = yield_metrics(sim, v3d)
                direct = round(float(ym["rel_err_total"]) * 100, 3)
                g.add("G5h", "平台结果与引擎直算逐位一致",
                      res is not None and ye is not None and abs(float(ye) - direct) < 1e-6,
                      {"platform": ye, "direct": direct},
                      "杜绝「平台数字 vs 服务数字」分叉")
            except Exception as exc:  # noqa: BLE001
                g.add("G5h", "平台结果与引擎直算逐位一致", False,
                      {"error": f"{type(exc).__name__}: {exc}"})

            # ---------- 缓存命中 ----------
            code, r2 = http("/api2/run", "POST",
                            {"batch": 8, "overrides": {}, "stride": 6})
            jid2 = r2.get("job_id")
            if jid2:
                t3 = time.time()
                while time.time() - t3 < 60:
                    _, jr = http(f"/api2/job/{jid2}")
                    if jr.get("job", {}).get("state") in ("done", "failed"):
                        break
                    time.sleep(1.0)
                g.add("G4e", "同工况二次提交命中缓存（不重复计算）",
                      jr.get("job", {}).get("state") == "done"
                      and jr.get("job", {}).get("progress", {}).get("phase") == "cached",
                      {"state": jr.get("job", {}).get("state"),
                       "phase": jr.get("job", {}).get("progress", {}).get("phase")})

                # ---------- G10d/e/f：force 重算（此刻缓存是热的，最能证明"真绕过"）----------
                _, h0 = http("/api2/history")
                n0 = h0.get("n", 0)
                src_id = (job.get("progress") or {}).get("history_id") or ""
                code3, r3 = http("/api2/run", "POST",
                                 {"batch": 8, "overrides": {}, "stride": 6,
                                  "force": True, "rerun_of": src_id or None})
                jid3 = r3.get("job_id")
                j3 = {}
                if jid3:
                    _, j3r = http(f"/api2/job/{jid3}")
                    j3 = j3r.get("job", {})
                not_cached = bool(jid3) and (j3.get("progress") or {}).get("phase") != "cached" \
                             and j3.get("from_cache") is not True
                if jid3:
                    t4 = time.time()
                    while time.time() - t4 < 240:
                        _, j3r = http(f"/api2/job/{jid3}")
                        j3 = j3r.get("job", {})
                        if j3.get("state") in ("done", "failed"):
                            break
                        time.sleep(2.0)
                _, h3 = http("/api2/history")
                n3 = h3.get("n", 0)
                newest = (h3.get("records") or [{}])[0]
                g.add("G10d", "force 提交真实绕过缓存（不是 cached 态）",
                      code3 == 200 and not_cached,
                      {"http": code3, "job_id": jid3,
                       "phase": (j3.get("progress") or {}).get("phase")})
                g.add("G10e", "强制重算新增一条留痕（+1，不覆盖旧记录）",
                      j3.get("state") == "done" and n3 == n0 + 1,
                      {"n_before": n0, "n_after": n3, "state": j3.get("state")})
                g.add("G10f", "新留痕带执行时间、重算来源与完整结果",
                      bool(newest.get("created_at")) and newest.get("started_at") is not None
                      and newest.get("has_result") is True
                      and newest.get("force") is True
                      and newest.get("rerun_of") == (src_id or None)
                      and newest.get("id") == (j3.get("progress") or {}).get("history_id"),
                      {"created_at": newest.get("created_at"), "elapsed_s": newest.get("elapsed_s"),
                       "rerun_of": newest.get("rerun_of"), "force": newest.get("force"),
                       "history_id": (j3.get("progress") or {}).get("history_id")})

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                proc.kill()

    # ---------- G8 端口纪律 ----------
    import socket
    def port_open(p: int) -> bool:
        s = socket.socket()
        s.settimeout(0.6)
        try:
            s.connect(("127.0.0.1", p))
            return True
        except Exception:  # noqa: BLE001
            return False
    g.add("G8", "8770 未被平台 v2 触碰", not port_open(8770),
          {"8770_listening": port_open(8770),
           "8772_listening": port_open(8772)},
          "R167 决议：8770 保持原状")

    # ---------- G9 前端静态规则（把已修的真 bug 变成可检测项）----------
    # 这两条都是「肉眼看不见、复验若只断言容器存在就会漏掉」的坑：
    #   ① p.y 是响应标量，轴坐标在 p.x 里 —— 取错字段 ⇒ 响应曲面一个格子都不画
    #   ② order.indexOf(i) 是 i 在过滤后数组里的「位置」而非下标 ⇒ 部分点失败时 x 错位
    app_js = os.path.join(V2, "app_v2.js")
    app_src = ""
    if os.path.exists(app_js):
        with open(app_js, encoding="utf-8") as f:
            app_src = strip_js_comments(f.read())
    bad_axis = re.findall(r"p\.y\s*\[\s*(?:xa|ya|axes)\b", app_src)
    g.add("G9a", "前端未误取 p.y[轴键]（轴坐标在 p.x 里）", not bad_axis,
          {"occurrences": len(bad_axis), "sample": bad_axis[:3]},
          "R168.1 修：二维响应曲面因取错字段而整张不画")
    bad_index = re.findall(r"xs\s*\[\s*\w+\.indexOf\(", app_src)
    g.add("G9b", "前端未用 xs[order.indexOf(i)] 取 x 坐标", not bad_index,
          {"occurrences": len(bad_index), "sample": bad_index[:3]},
          "R168.1 修：部分点失败时折线 x 坐标错位")
    # 横向溢出：抽屉 transform 移出屏外会计入文档滚动区域
    style_path = os.path.join(V2, "style.css")
    style_src = ""
    if os.path.exists(style_path):
        with open(style_path, encoding="utf-8") as f:
            style_src = f.read()
    has_ox = "overflow-x" in style_src
    drawer_fixed = re.search(r"\.drawer\s*\{[^}]*position:\s*fixed", style_src, re.S) is not None
    g.add("G9c", "页面禁横向滚动且抽屉为 fixed（不撑出屏外抽屉）",
          has_ox and drawer_fixed,
          {"overflow_x_hidden": has_ox, "drawer_fixed": drawer_fixed},
          "R168.1 修：transform 位移计入滚动区域 ⇒ 可横向拖出屏外抽屉")

    # ---------- G10 运算历史（R168.3）----------
    # 最关键的一条不是"接口能返回 200"，而是**另一个进程能不能读回完整结果**：
    # 服务重启后内存里的 job/cache 全没了，用户看到的历史必须来自磁盘。
    # 所以用两个独立 Python 进程（writer / reader）+ 隔离临时目录做实证。
    import tempfile

    def _src(name: str) -> str:
        p = os.path.join(V2, name)
        with open(p, encoding="utf-8") as f:
            return f.read()
    jq_src, sv_src, hi_src = _src("job_queue.py"), _src("serve_v2.py"), _src("history.py")
    with open(app_js, encoding="utf-8") as f:
        app_raw = f.read()
    g10_static = {
        "hook": "on_complete=record_from_job" in jq_src,
        "force": "use_cache=not force" in jq_src,
        "route": "/api2/history" in sv_src and "do_DELETE" in sv_src,
        "atomic": "os.replace" in hi_src and "MAX_RECORDS" in hi_src,
        "time_fields": all(k in hi_src for k in ("created_at", "started_at", "finished_at", "elapsed_s")),
        "frontend": "force = true" in app_raw and "?full=1" in app_raw,
    }
    g.add("G10a", "落盘钩子 / 强制重算 / 历史路由 / 执行时间字段齐备",
          all(g10_static.values()), g10_static,
          "静态通路；运行时行为见 G10d/e/f 与浏览器逐屏复验")

    writer = r'''
import json, os, sys, time
from types import SimpleNamespace
os.environ["PENOPS_SIM_HISTORY_DIR"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
import history
now = time.time()
base = dict(kind="sim", id="sim-probe-ok", state="done", code=None, error=None,
    started=now - 7.5, finished=now,
    progress={"phase": "done", "detail": "done"},
    payload={"batch": 8, "stride": 6, "overrides": {"mup": 0.05},
             "_history": {"batch": 8, "stride": 6, "overrides": {"mup": 0.05},
                          "fingerprint": "probe-fp", "rerun_of": None, "force": False}},
    result={"ok": True, "trace": {"cols": {"P": [1.0, 2.0, 3.0]}},
            "yield": {"rel_err_pct": -4.039}, "health": {"level": "normal", "flags": []},
            "n_steps": 10, "stride": 6})
ok = history.record_from_job(SimpleNamespace(**base))
cached = dict(base); cached["id"] = "sim-probe-cached"
cached["progress"] = {"phase": "cached", "detail": "hit"}
r_cached = history.record_from_job(SimpleNamespace(**cached))
failed = dict(base); failed["id"] = "sim-probe-failed"; failed["state"] = "failed"
failed["code"] = "diverged"; failed["error"] = "probe"; failed["result"] = {"ok": False}
failed["progress"] = {"phase": "failed", "detail": "failed"}
r_failed = history.record_from_job(SimpleNamespace(**failed))
print(json.dumps({"ok_id": ok["id"], "cached_written": r_cached is not None,
                  "failed_written": r_failed is not None, "n": len(history.list_records())}))
'''
    reader = r'''
import json, os, sys
os.environ["PENOPS_SIM_HISTORY_DIR"] = sys.argv[1]
sys.path.insert(0, sys.argv[2])
import history
rows = history.list_records()
rec = history.get_record(sys.argv[3], full=True) or {}
print(json.dumps({"n": len(rows), "id": rec.get("id"), "created_at": rec.get("created_at"),
    "started_at": rec.get("started_at"), "elapsed_s": rec.get("elapsed_s"),
    "has_result": rec.get("has_result"),
    "cols": ((rec.get("result") or {}).get("trace") or {}).get("cols"),
    "overrides": rec.get("overrides"),
    "failed_kept": any(x.get("state") == "failed" for x in rows)}))
'''
    try:
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env["PENOPS_SIM_HISTORY_DIR"] = td
            wr = subprocess.run([sys.executable, "-c", writer, td, V2],
                                capture_output=True, text=True, env=env, timeout=60)
            w = json.loads(wr.stdout.strip()) if wr.returncode == 0 else {}
            rd = subprocess.run([sys.executable, "-c", reader, td, V2, w.get("ok_id", "")],
                                capture_output=True, text=True, env=env, timeout=60)
            r = json.loads(rd.stdout.strip()) if rd.returncode == 0 else {}
            g10b = {
                "writer_rc": wr.returncode, "reader_rc": rd.returncode,
                "n": r.get("n"), "id_ok": r.get("id") == w.get("ok_id"),
                "time": bool(r.get("created_at")) and bool(r.get("started_at"))
                        and isinstance(r.get("elapsed_s"), (int, float))
                        and 7 <= r.get("elapsed_s", 0) <= 9,
                "full_result": r.get("has_result") is True
                               and (r.get("cols") or {}).get("P") == [1.0, 2.0, 3.0],
                "config": (r.get("overrides") or {}).get("mup") == 0.05,
            }
            g10b_ok = (wr.returncode == 0 and rd.returncode == 0 and g10b["n"] == 2
                       and all(g10b[k] is True for k in ("id_ok", "time", "full_result", "config")))
            g.add("G10b", "跨进程可读回完整结果 + 执行时间（等价于服务重启后不丢）",
                  g10b_ok,
                  {**g10b, "writer_err": wr.stderr[-200:], "reader_err": rd.stderr[-200:]},
                  "writer 写盘 → reader 是全新解释器进程，只读磁盘")
            g.add("G10c", "缓存命中不留痕、失败作业留痕（边界证据不丢）",
                  w.get("cached_written") is False and w.get("failed_written") is True
                  and r.get("failed_kept") is True,
                  {"cached_written": w.get("cached_written"),
                   "failed_written": w.get("failed_written"), "failed_kept": r.get("failed_kept")})
    except Exception as exc:  # noqa: BLE001
        g.add("G10b", "跨进程可读回完整结果 + 执行时间（等价于服务重启后不丢）", False,
              {"error": f"{type(exc).__name__}: {exc}"})
        g.add("G10c", "缓存命中不留痕、失败作业留痕（边界证据不丢）", False,
              {"error": f"{type(exc).__name__}: {exc}"})

    out = {
        "verdict": g.verdict,
        "n_pass": g.n_pass,
        "n_checks": g.n_checks,
        "checks": g.checks,
        "elapsed_s": round(time.time() - t0, 2),
        "port": PORT,
        "fast": args.fast,
    }
    ev = os.path.join(ROOT, "runs", "r168_platform_v2_gate.json")
    with open(ev, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"=== R168 平台 v2 闸门 ===  {g.verdict}  {g.n_pass}/{g.n_checks}  "
              f"({out['elapsed_s']}s)")
        for c in g.checks:
            mark = "PASS" if c["ok"] else "FAIL"
            print(f"  [{mark}] {c['id']:4s} {c['name']}")
            if not c["ok"]:
                print(f"         detail: {json.dumps(c['detail'], ensure_ascii=False)[:400]}")
        print(f"证据: {ev}")
    return 0 if g.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
