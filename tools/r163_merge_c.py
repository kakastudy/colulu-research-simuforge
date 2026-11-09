# -*- coding: utf-8 -*-
"""R163 C 段产物合并（幂等、数据驱动）。

把**健康批注入**（因果可归因）与**混合批注入**（含不可归因样本）合并为一个主产物，
并重算 `A_summary` / `C_summary`（分层归因口径）。

为什么需要合并
--------------
C 段第一轮跑的是 `8,22,55,91`：其中 b55/b91 本身就是自然退化批
⇒ 其「注入后触发」**不能**归因于注入（对照已退化，触发是重复观测到固有退化）。
第二轮改在**健康批**（8/11/15/22/23）上跑 ⇒ 20 例全部可归因，
这才是有效的因果证据（真阳性/假阴性/真阴性/假阳性四格）。

用法：
    py tools/r163_merge_c.py
"""
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN = os.path.join(ROOT, "runs", "r163_degradation_probe.json")
HEALTHY = os.path.join(ROOT, "runs", "r163_degradation_probe_healthy.json")
MIXED = os.path.join(ROOT, "runs", "r163_degradation_probe_mixed.json")


def jload(p):
    if not os.path.exists(p):
        return {}
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def a_summary(rows):
    acc = {r["batch"]: r for r in rows if "error" not in r}
    return {
        "n": 86, "n_scanned": len(acc),
        "n_degraded": sum(1 for r in acc.values() if r.get("degraded")),
        "degraded_batches": sorted(b for b, r in acc.items() if r.get("degraded")),
        "healthy_batches": sorted(b for b, r in acc.items()
                                  if not r.get("degraded") and "error" not in r),
        "n_error": sum(1 for r in acc.values() if "error" in r),
        "error_batches": sorted(b for b, r in acc.items() if "error" in r),
    }


def c_summary(inj):
    attrib = [r for r in inj if r.get("attributable")]
    non = [r for r in inj if not r.get("attributable")]
    tp = [r for r in attrib if r.get("expect_fire") and r.get("degraded")]
    fn = [r for r in attrib if r.get("expect_fire") and not r.get("degraded")]
    tn = [r for r in attrib if (not r.get("expect_fire")) and not r.get("degraded")]
    fp = [r for r in attrib if (not r.get("expect_fire")) and r.get("degraded")]

    def tag(r):
        return "%s@b%d" % (r["fault"], r["batch"])

    # 逐故障的检出率（仅可归因子集）
    per_fault = {}
    for r in attrib:
        d = per_fault.setdefault(r["fault"], {"expect_fire": bool(r["expect_fire"]),
                                              "n": 0, "fired": 0, "cases": []})
        d["n"] += 1
        d["fired"] += 1 if r.get("degraded") else 0
        d["cases"].append(tag(r))
    for k, v in per_fault.items():
        v["detection_rate"] = (float(v["fired"]) / v["n"]) if v["n"] else float("nan")

    return {
        "n_cases": len(inj),
        "n_attributable": len(attrib),
        "n_not_attributable": len(non),
        "not_attributable_cases": [tag(r) for r in non],
        "fired": [tag(r) for r in inj if r.get("degraded")],
        "not_fired": [tag(r) for r in inj if not r.get("degraded")],
        "true_positive": [tag(r) for r in tp],
        "false_negative": [tag(r) for r in fn],
        "true_negative": [tag(r) for r in tn],
        "false_positive": [tag(r) for r in fp],
        "per_fault": per_fault,
        "control_all_healthy": all((r.get("control_healthy") is True) for r in inj),
        "expect_fire_all_fired": all((r.get("degraded") == r.get("expect_fire"))
                                     for r in inj),
        "expect_fire_all_fired_attributable": all(
            (r.get("degraded") == r.get("expect_fire")) for r in attrib),
        "n_control_healthy_batches": sorted({r["batch"] for r in attrib}),
    }


def main():
    main_d = jload(MAIN)
    h_d = jload(HEALTHY)
    m_d = jload(MIXED)

    # A 段：取健康批产物里的（它含 A_summary），否则用主产物
    a_rows = h_d.get("A_screening") or main_d.get("A_screening") or []
    main_d["A_screening"] = a_rows
    main_d["A_summary"] = a_summary(a_rows)

    # C 段：健康批（可归因）为主 + 混合批里 b55/b91 的不可归因样本作补充
    inj = []
    seen = set()
    for r in h_d.get("C_injection", []):
        r["attributable"] = bool(r.get("control_healthy") is True)
        k = (r["batch"], r["fault"])
        if k not in seen:
            inj.append(r)
            seen.add(k)
    for r in m_d.get("C_injection", []):
        k = (r["batch"], r["fault"])
        if k in seen:
            continue
        r["attributable"] = bool(r.get("control_healthy") is True)
        inj.append(r)
        seen.add(k)
    inj.sort(key=lambda r: (r["batch"], r["fault"]))
    main_d["C_injection"] = inj
    main_d["C_summary"] = c_summary(inj)

    main_d["merged_from"] = {
        "healthy": os.path.relpath(HEALTHY, ROOT),
        "mixed": os.path.relpath(MIXED, ROOT) if os.path.exists(MIXED) else None,
    }

    tmp = MAIN + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(main_d, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, MAIN)

    cs = main_d["C_summary"]
    print("== 合并完成 ==")
    print("  A 段：%d 批，退化 %d 批（%.2f%%）"
          % (main_d["A_summary"]["n_scanned"], main_d["A_summary"]["n_degraded"],
             100.0 * main_d["A_summary"]["n_degraded"] / max(1, main_d["A_summary"]["n_scanned"])))
    print("  C 段：%d 例（可归因 %d / 不可归因 %d）"
          % (cs["n_cases"], cs["n_attributable"], cs["n_not_attributable"]))
    print("  四格（可归因子集）：TP=%d FN=%d TN=%d FP=%d"
          % (len(cs["true_positive"]), len(cs["false_negative"]),
             len(cs["true_negative"]), len(cs["false_positive"])))
    for f, v in sorted(cs["per_fault"].items()):
        print("    %-20s expect_fire=%-5s 检出 %d/%d  案例 %s"
              % (f, v["expect_fire"], v["fired"], v["n"], v["cases"]))
    print("写出：%s" % os.path.relpath(MAIN, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
