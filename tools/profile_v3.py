# -*- coding: utf-8 -*-
"""M0-2 V3 数据集剖析：流式解析、批次切分、落 CSV、对照统计 CSV 验证。

输入: 100_Batches_IndPenSim/Mendeley_data/100_Batches_IndPenSim_V3.csv (~2.5GB)
输出: data/processed/batches/batch_XX.csv (37 通道)
      data/processed/batches_manifest.csv (每批统计 + 验证列)
      data/processed/v3_data_quality.csv (通道级质量统计)
      data/processed/v3_profile_report.json
"""
import csv
import json
import sys
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

H_SAMPLE = 0.2  # 采样间隔 h（与 MATLAB 一致）


def main():
    t0 = time.time()
    # ---- 1) 表头检查：列数、前 37 列名、尾部数字列 ----
    with open(RAW_V3, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        row1 = next(reader)
    print(f"[header] total cols = {len(header)}")
    print(f"[header] first 37 = {header[:37]}")
    print(f"[header] col 37..41 = {header[37:42]}")
    trailing = header[N_NAMED:]
    print(f"[header] trailing cols = {len(trailing)}, head={trailing[:3]}, tail={trailing[-3:]}")
    print(f"[row1] total values = {len(row1)}, trailing non-zero = "
          f"{sum(1 for v in row1[N_NAMED:] if v.strip() not in ('0', '0.0', '0.00', '-0'))}")

    # ---- 2) 流式解析：按 Batch_ref (列 34) 切批 ----
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
    print(f"[parse] rows total = {n_rows_total}, batches = {len(order)}, "
          f"batch numbers = {order[:5]}...{order[-5:]}")

    # ---- 3) 落批 + 统计 + 验证 ----
    stats_csv = pd.read_csv(STATS)
    stats_csv = stats_csv.rename(columns={
        "Batch ref": "batch",
        "Penicllin_harvested_during_batch(kg)": "harvested_during_kg",
        "Penicllin_harvested_end_of_batch (kg)": "end_of_batch_kg",
        "Penicllin_yield_total (kg)": "yield_total_kg",
        "Fault ref(0-NoFault 1-Fault)": "fault_ref",
    })

    manifest_rows = []
    dq_acc = {c: [] for c in CLEAN}
    for b in order:
        df = pd.concat(buffers[b], ignore_index=True)
        df.columns = CLEAN
        t = df["time_h"].to_numpy()
        V_end = float(df["V"].iloc[-1])
        P_end = float(df["P"].iloc[-1])
        harvested = float((df["Fremoved"] * df["P"]).sum()) * H_SAMPLE
        end_of_batch = V_end * P_end
        total = end_of_batch + harvested
        fault = int(df["FaultFlag"].iloc[-1])
        manifest_rows.append({
            "batch": b,
            "n_rows": len(df),
            "t0_h": float(t[0]), "t_end_h": float(t[-1]),
            "V_end_L": V_end, "P_end_g_L": P_end,
            "harvested_during_g": harvested,
            "end_of_batch_g": end_of_batch,
            "yield_total_g": total,
            "fault_flag": fault,
        })
        for c in CLEAN:
            s = df[c].to_numpy()
            dq_acc[c].append((s.size, int(np.isnan(s).sum())))
        df.to_csv(BATCHES_DIR / f"batch_{b:02d}.csv", index=False)

    manifest = pd.DataFrame(manifest_rows)
    # 对照统计 CSV
    mrg = manifest.merge(stats_csv, on="batch", how="left")
    mrg["rel_err_during"] = (mrg["harvested_during_g"] - mrg["harvested_during_kg"] * 1000) / (mrg["harvested_during_kg"] * 1000)
    mrg["rel_err_end"] = (mrg["end_of_batch_g"] - mrg["end_of_batch_kg"] * 1000) / (mrg["end_of_batch_kg"] * 1000)
    mrg["rel_err_total"] = (mrg["yield_total_g"] - mrg["yield_total_kg"] * 1000) / (mrg["yield_total_kg"] * 1000)
    mrg["fault_match"] = (mrg["fault_flag"] == mrg["fault_ref"])
    manifest.to_csv(OUT / "batches_manifest.csv", index=False)
    mrg.to_csv(OUT / "batches_validation.csv", index=False)

    print("\n[validation] rel err (computed vs statistics CSV):")
    for c in ["rel_err_during", "rel_err_end", "rel_err_total"]:
        v = mrg[c].abs()
        print(f"  {c}: max={v.max():.3e} median={v.median():.3e} p95={v.quantile(0.95):.3e}")
    print(f"  fault_match all = {bool(mrg['fault_match'].all())}")

    # ---- 4) 通道级数据质量 ----
    dq_rows = []
    for c in CLEAN:
        sizes = np.array([x[0] for x in dq_acc[c]])
        nans = np.array([x[1] for x in dq_acc[c]])
        dq_rows.append({"channel": c, "total_rows": int(sizes.sum()),
                        "nan_rows": int(nans.sum()),
                        "nan_frac": float(nans.sum() / sizes.sum())})
    dq = pd.DataFrame(dq_rows)
    dq.to_csv(OUT / "v3_data_quality.csv", index=False)
    print("\n[dq] channels with nan_frac > 0.05:")
    print(dq[dq["nan_frac"] > 0.05].to_string(index=False))

    # ---- 5) 报告 ----
    report = {
        "source": str(RAW_V3),
        "header_total_cols": len(header),
        "header_trailing_cols": len(trailing),
        "header_trailing_desc": "Raman 波长分箱数字列（2400..0），数据行为 0",
        "n_batches": len(order),
        "n_rows_total": int(n_rows_total),
        "batches_ok": int(sum(1 for r in manifest_rows if r["n_rows"] > 0)),
        "validation": {
            "rel_err_during_max": float(mrg["rel_err_during"].abs().max()),
            "rel_err_end_max": float(mrg["rel_err_end"].abs().max()),
            "rel_err_total_max": float(mrg["rel_err_total"].abs().max()),
            "fault_match_all": bool(mrg["fault_match"].all()),
        },
        "yield_total_kg_min": float(manifest["yield_total_g"].min() / 1000),
        "yield_total_kg_max": float(manifest["yield_total_g"].max() / 1000),
        "yield_total_kg_mean": float(manifest["yield_total_g"].mean() / 1000),
        "fault_batches": int(manifest["fault_flag"].sum()),
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(OUT / "v3_profile_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n[report] saved:", OUT / "v3_profile_report.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
