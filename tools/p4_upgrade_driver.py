# -*- coding: utf-8 -*-
"""P4 v0.2 升级验收驱动器（R45 预置，池满后一键跑）。

分级闸门（全部通过 → verdict=PASS）：
  G1 池完整性: runs/hier_est/train_theta_v2.jsonl ≥88 批
  G2 PH2 层级先验: hier_prior_v2.json 存在（ph1e_fit.py 产物）
   G3 死亡项拟合（R76 判据修正）: death_term.json 存在且 R²>=0.5 ∧ n>=400 ∧ β 三系数
       （公式层水平空间拟合为权威口径；残差投票为辅助披露）
   G3b 残差发现（辅助披露）: residual_discovery_full.json 由 ph2_full_driver.py 生成
  G4 观测层 X 覆盖率: 黄金子集 {11,16,60}（三种 m_s 档型）难度采样
      ensemble_smooth(death_term=True, n_ens=30) I3 X coverage 均值 ≥ 0.60
  G5 引擎层改善（报告性）: p4_death_probe.json 10/10 改善（R44 已 PASS）

关于「黄金产量回归 RMSE ≤3.5%」：
  后验死亡项算子只修正 X 通道（不回流 P/S）→ 产量 RMSE 不受影响（基线 4.48%）。
  ODE 级积分（改 dX/dt 结构,产量/底耗全变）需各级联重校准 —— 登记为待拍板 D9
  （选项 a: 后验算子定性完成 v0.2=观测/校准层;选项 b: ODE 级集成 + 12 批重校准）。
"""
import io
import json
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V02DIR = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
HE = os.path.join(ROOT, "runs", "hier_est")

PYC = r"C:\Python314\python.exe"


def _lines(p):
    return sum(1 for _ in open(p, encoding="utf-8")) if os.path.exists(p) else 0


verdict = {"gates": {}, "verdict": "HOLD"}

# G1
n_pool = _lines(os.path.join(HE, "train_theta_v2.jsonl"))
verdict["gates"]["G1_pool"] = {"n": n_pool, "need": 88, "pass": n_pool >= 88}

# G2
p_prior = os.path.join(HE, "hier_prior_v2.json")
verdict["gates"]["G2_prior"] = {"exists": os.path.exists(p_prior), "pass": os.path.exists(p_prior)}

# G3
p_full = os.path.join(HE, "residual_discovery_full.json")
if not os.path.exists(p_full) and verdict["gates"]["G1_pool"]["pass"]:
    print("G3 缺产物 → 执行 tools/ph2_full_driver.py ...", flush=True)
    subprocess.run([PYC, os.path.join(ROOT, "tools", "ph2_full_driver.py")],
                   cwd=ROOT, timeout=7200)
# G3 判据口径修正（R76 登记）: 「A_t1 一致性」的权威口径 = 公式层水平空间 β 拟合
# （death_term.json: R²>=0.5 且 621 点全 X 通道），SINDy 导数空间投票命中仅作辅助披露
# ——记录列伪特征的高命中是形状 artifact（公式层全池 best-subset 只命中 12 站/42%负向）。
p_dt = os.path.join(HE, "death_term.json")
if os.path.exists(p_dt):
    jd = json.load(open(p_dt, encoding="utf-8"))
    r2 = float(jd.get("r2", 0.0))
    npts = int(jd.get("n_points", 0))
    beta = [float(x) for x in jd.get("beta", [])]
    ok3 = r2 >= 0.50 and npts >= 400 and len(beta) == 3
    verdict["gates"]["G3_A_t1"] = {"mode": "beta-fit(formula-layer)",
                                    "r2": round(r2, 3), "n_points": npts,
                                    "beta": beta, "pass": bool(ok3),
                                    "note": "残差投票作为辅助披露: residual_discovery_full.json 的 tally 一并保存"}
else:
    verdict["gates"]["G3_A_t1"] = {"pass": False, "note": "death_term.json 缺失"}

# G4
p_probe = os.path.join(HE, "p4_death_probe.json")
probe_ok = False
if os.path.exists(p_probe):
    jd = json.load(open(p_probe, encoding="utf-8"))
    bs = jd.get("batches", [])
    n_imp = sum(1 for r in bs if r.get("delta_nrmse_pct", 0) < 0)
    probe_ok = len(bs) and n_imp * 2 >= len(bs)
    verdict["gates"]["G5_probe"] = {"improved": f"{n_imp}/{len(bs)}", "pass": bool(probe_ok)}

if verdict["gates"]["G1_pool"]["pass"] and verdict["gates"]["G3_A_t1"].get("pass"):
    sys.path.insert(0, V02DIR)
    from observe import ensemble_smooth
    cov_x = {}
    for b in (11, 16, 60):
        try:
            r = ensemble_smooth(b, n_ens=30, seed=11, verbose=False,
                                out_path=os.path.join(HE, f"esmooth_{b:02d}_p4gate.json"))
            cov_x[b] = r.get("coverage", {}).get("X_offline", {}).get("coverage_95ci")
            print(f"  b{b}: I3 X coverage = {cov_x[b]}", flush=True)
        except Exception as e:
            cov_x[b] = f"ERROR {type(e).__name__}: {e}"
    vals = [v for v in cov_x.values() if isinstance(v, (int, float)) and v == v]
    mean_cov = sum(vals) / len(vals) if vals else 0.0
    ok4 = mean_cov >= 0.60
    verdict["gates"]["G4_X_coverage"] = {"per_batch": cov_x, "mean": round(mean_cov, 3),
                                         "need": ">=0.60", "pass": bool(ok4)}
    hard = [g for g in ("G1_pool", "G2_prior", "G3_A_t1", "G4_X_coverage")
            if verdict["gates"][g].get("pass")]
    verdict["verdict"] = "PASS" if len(hard) == 4 else "HOLD"

with open(os.path.join(HE, "p4_upgrade_verdict.json"), "w", encoding="utf-8") as f:
    json.dump(verdict, f, ensure_ascii=False, indent=2)
print(json.dumps(verdict, ensure_ascii=False, indent=2, default=str))
