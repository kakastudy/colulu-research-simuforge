# -*- coding: utf-8 -*-
"""仿真计算记录持久化（看板 A/B/B2/C 档运行结果）。

结构：runs/dashboard_results/
  <tier>_<batch:02d>_<hash8>.meta.json  — 参数、指标、时间、崩溃分级（快速表格用）
  <tier>_<batch:02d>_<hash8>.sim.pkl    — 完整轨迹 DataFrame（pickle，~0.4MB/次）

run_key 规则：tier + batch + params_hash（canonical json 的 sha1 前 12 位）。
同 key 重复点击 → 命中缓存（秒开）；B/C 档按 (档位, 批, 维度/目标/迭代) 构 key。
列表可按档位过滤、按时间倒序。
"""
import hashlib
import json
import os

_RUN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                        "runs", "dashboard_results"))

TIERS = {"A": "仿真", "B": "B 档在线估计", "B2": "B 档 stage-2（P_offline 锚定）",
         "C": "C 档反设计寻优", "O": "内部观测（集合平滑器 PH3）"}


def _canonical(d) -> str:
    return json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)


def params_hash(payload: dict) -> str:
    return hashlib.sha1(_canonical(payload).encode("utf-8")).hexdigest()[:12]


def run_key(tier: str, batch_no: int, payload: dict) -> str:
    return f"{tier}_{int(batch_no):02d}_{params_hash(payload)}"


def _paths(key: str):
    return (os.path.join(_RUN_DIR, key + ".meta.json"),
            os.path.join(_RUN_DIR, key + ".sim.pkl"))


def save_run(tier: str, batch_no: int, payload: dict, sim_df=None,
             metrics: dict | None = None, extra: dict | None = None):
    """保存一次运行结果；sim_df 为 None 的档位（B/B2/C 的纯指标结果）不写 pkl。"""
    os.makedirs(_RUN_DIR, exist_ok=True)
    key = run_key(tier, batch_no, payload)
    meta_path, pkl_path = _paths(key)
    meta = {"run_key": key, "tier": tier, "tier_label": TIERS.get(tier, tier),
            "batch": int(batch_no), "payload": payload,
            "metrics": metrics or {}, "extra": extra or {}}
    import datetime
    meta["created"] = datetime.datetime.now().isoformat(timespec="seconds")
    if sim_df is not None:
        sim_df.to_pickle(pkl_path)
        meta["sim_pickle"] = os.path.basename(pkl_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)
    return key


def load_run(key: str):
    """返回 (meta, sim_df or None)；损坏的 pkl 返回 None 轨迹并保留 meta。"""
    meta_path, pkl_path = _paths(key)
    if not os.path.exists(meta_path):
        return None, None
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    sim_df = None
    if meta.get("sim_pickle"):
        pkl = os.path.join(_RUN_DIR, meta["sim_pickle"])
        if os.path.exists(pkl):
            try:
                sim_df = pd_read_pickle(pkl)
            except Exception:
                sim_df = None
    return meta, sim_df


def pd_read_pickle(path):
    import pandas as pd
    return pd.read_pickle(path)


def has_run(tier: str, batch_no: int, payload: dict):
    key = run_key(tier, batch_no, payload)
    meta, _ = load_run(key)
    return key if meta else None


def list_runs(tier: str | None = None, batch_no: int | None = None):
    out = []
    if not os.path.isdir(_RUN_DIR):
        return out
    for fn in sorted(os.listdir(_RUN_DIR)):
        if not fn.endswith(".meta.json"):
            continue
        p = os.path.join(_RUN_DIR, fn)
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        if tier and m.get("tier") != tier:
            continue
        if batch_no is not None and m.get("batch") != int(batch_no):
            continue
        m["_mtime"] = os.path.getmtime(p)
        out.append(m)
    out.sort(key=lambda m: m["_mtime"], reverse=True)
    return out


def delete_run(key: str) -> bool:
    meta_path, pkl_path = _paths(key)
    removed = False
    for p in (meta_path, pkl_path):
        if os.path.exists(p):
            os.remove(p)
            removed = True
    return removed
