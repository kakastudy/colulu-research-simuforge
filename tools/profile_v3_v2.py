# -*- coding: utf-8 -*-
"""M0-2b V3 数据集剖析 v2：修正 harvested 符号、单位口径、终末收获标志。

关键发现（v1 验证失败后定位）：
1. Fremoved 通道存负值出流（-4000 L/h 放罐），harvested = -sum(Fremoved*P)*h
2. 统计 CSV 表头标 (kg) 但数值实为克级（1.0664e6 g = 1066 kg，工业合理）
3. 统计 CSV end_of_batch = 终末收获量（非 V3 末行 V*P）；V3 CSV 90 批不含终末收获段
4. 表头 PAT_ref 通道名含逗号被拆 3 列 → 表头与数据错位 2 列（用位置取前 37 列规避）
"""
import csv
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_V3 = ROOT / "100_Batches_IndPenSim" / "Mendeley_data" / "100_Batches_IndPenSim_V3.csv"
STATS = ROOT / "100_Batches_IndPenSim" / "Mendeley_data" / "100_Batches_IndPenSim_Statistics.csv"
OUT = ROOT / "data" / "processed"
BATCHES_DIR = OUT / "batches"
BATCHES_DIR.mkdir(parents=True, exist_ok=True)

N_NAMED = 37
CLEAN = [
    "time_h", "Fg", "RPM", "Fs", "Fa", "Fb", "Fc", "Fh", "Fw", "pressure",
    "Fremoved", "S", "DO2", "P", "V", "Wt", "pH", "T", "Q", "CO2outgas",
    "Fpaa", "PAA_offline", "Foil", "NH3_offline", "OUR", "O2", "P_offline",
    "X_offline", "CER", "NH3_shots", "Viscosity_offline", "Fault_ref",
    "Control_ref", "PAT_ref", "Batch_ref", "BatchID", "FaultFlag",
]
H_SAMPLE = 0.2


def main():
    t0 = time.time()
    buffers = {}
    order = []
    reader = pd.read_csv(
        RAW_V3, header=0, usecols=list(range(N_NAMED)),
        chunksize=20000, dtype=float, na_values=["NaN", "nan", "NA", ""],
    )
    n_rows_total = 0
    for chunk in reader:
        n_rows_total += len(chunk)
        br = chunk.iloc[:, 34].to_numpy()
        for b in np.unique(br):
            b = int(b)
            sel = chunk[br == b]
            if b not in buffers:
                buffers[b] = [sel]
                order.append(b)
            else:
                buffers[b].append(sel)

    stats_csv = pd.read_csv(STATS).rename(columns={
        "Batch ref": "batch",
        "Penicllin_harvested_during_batch(kg)": "harvested_during_g",
        "Penicllin_harvested_end_of_batch (kg)": "end_harvest_g",
        "Penicllin_yield_total (kg)": "yield_total_g",
        "Fault ref(0-NoFault 1-Fault)": "fault_ref",
    })
    # 统计值实为克级（表头 kg 标错）；yield_total = harvested_during + end_harvest
    # 注：stats 的 yield_total 公式 = end + harvested（与 MATLAB 源码 - 号不一致）

    manifest_rows = []
    dq_acc = {c: [] for c in CLEAN}
    for b in order:
        df = pd.concat(buffers[b], ignore_index=True)
        df.columns = CLEAN
        t = df["time_h"].to_numpy()
        V_end = float(df["V"].iloc[-1])
        P_end = float(df["P"].iloc[-1])
        # Fremoved 为负值出流 → harvested = -sum(Fremoved*P)*h
        harvested = float(-(df["Fremoved"] * df["P"]).sum()) * H_SAMPLE
        end_in_vessel = V_end * P_end
        total_in_vessel = end_in_vessel + harvested  # 罐内总量 = 末态 + 贯流收获
        last_fr = float(df["Fremoved"].iloc[-1])
        has_final_harvest = last_fr != 0
        fault = int(df["FaultFlag"].iloc[-1])
        manifest_rows.append({
            "batch": b,
            "n_rows": len(df),
            "t0_h": float(t[0]), "t_end_h": float(t[-1]),
            "V_end_L": V_end, "P_end_g_L": P_end,
            "harvested_during_g": harvested,
            "end_in_vessel_g": end_in_vessel,
            "total_in_vessel_g": total_in_vessel,
            "has_final_harvest": int(has_final_harvest),
            "fault_flag": fault,
        })
        for c in CLEAN:
            s = df[c].to_numpy()
            dq_acc[c].append((s.size, int(np.isnan(s).sum())))
        df.to_csv(BATCHES_DIR / f"batch_{b:02d}.csv", index=False)

    manifest = pd.DataFrame(manifest_rows)
    # 统计列名与 manifest 冲突 → 先重命名再合并
    stats_renamed = stats_csv.rename(columns={
        "harvested_during_g": "stats_harvested_g",
        "end_harvest_g": "stats_end_harvest_g",
        "yield_total_g": "stats_yield_total_g",
    })
    mrg = manifest.merge(stats_renamed, on="batch", how="left")
    mrg["rel_err_harvested"] = (mrg["harvested_during_g"] - mrg["stats_harvested_g"]) / mrg["stats_harvested_g"]
    mrg["rel_err_end_in_vessel"] = (mrg["end_in_vessel_g"] - mrg["stats_end_harvest_g"]) / mrg["stats_end_harvest_g"]
    mrg["rel_err_total"] = (mrg["total_in_vessel_g"] - mrg["stats_yield_total_g"]) / mrg["stats_yield_total_g"]
    mrg["fault_match"] = (mrg["fault_flag"] == mrg["fault_ref"])
    manifest.to_csv(OUT / "batches_manifest.csv", index=False)
    mrg.to_csv(OUT / "batches_validation.csv", index=False)

    print("=== validation (corrected) ===")
    for c in ["rel_err_harvested", "rel_err_end_in_vessel", "rel_err_total"]:
        v = mrg[c].abs()
        print(f"  {c}: max={v.max():.3e} median={v.median():.3e} p95={v.quantile(0.95):.3e}")
    print(f"  fault_match all = {bool(mrg['fault_match'].all())}")
    print(f"  batches with final harvest in CSV = {int(mrg['has_final_harvest'].sum())}")

    # 数据质量
    dq_rows = []
    for c in CLEAN:
        sizes = np.array([x[0] for x in dq_acc[c]])
        nans = np.array([x[1] for x in dq_acc[c]])
        dq_rows.append({"channel": c, "total_rows": int(sizes.sum()),
                        "nan_rows": int(nans.sum()),
                        "nan_frac": float(nans.sum() / sizes.sum())})
    dq = pd.DataFrame(dq_rows)
    dq.to_csv(OUT / "v3_data_quality.csv", index=False)

    report = {
        "source": str(RAW_V3),
        "header_anomaly": "PAT_ref 通道名含逗号被拆 3 列 → 表头 2239 列与数据 2237 值错位 2 列；用位置取前 37 列规避",
        "n_batches": len(order),
        "n_rows_total": int(n_rows_total),
        "validation": {
            "harvested_during_rel_err_max": float(mrg["rel_err_harvested"].abs().max()),
            "harvested_during_rel_err_p95": float(mrg["rel_err_harvested"].abs().quantile(0.95)),
            "end_in_vessel_rel_err_max": float(mrg["rel_err_end_in_vessel"].abs().max()),
            "total_rel_err_max": float(mrg["rel_err_total"].abs().max()),
            "fault_match_all": bool(mrg["fault_match"].all()),
        },
        "stats_csv_findings": [
            "表头标 (kg) 但数值实为克级（1.0664e6 g = 1066 kg 工业合理；若按 kg 则 1066 t 不可能）",
            "end_of_batch 列实为终末收获量，非 V3 末行 V*P；V3 CSV 90 批不含终末收获段（10 批含）",
            "yield_total = harvested_during + end_harvest（与 MATLAB 源码 end - harvested 公式不一致）",
        ],
        "yield_total_g_min": float(manifest["total_in_vessel_g"].min()),
        "yield_total_g_max": float(manifest["total_in_vessel_g"].max()),
        "yield_total_g_mean": float(manifest["total_in_vessel_g"].mean()),
        "fault_batches": int(manifest["fault_flag"].sum()),
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(OUT / "v3_profile_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n[report] saved")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
