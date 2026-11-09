# Supplementary Information

**Manuscript:** *Falsifiable bioprocess digital twins: an evidence-gated framework tested on 86 industrial-scale penicillin fed-batches*

All numerical tables are machine-generated from the frozen artefacts in `runs/` and are collected in [`supplementary_tables.md`](supplementary_tables.md). All figures are generated from the same JSON files by [`make_figures.py`](make_figures.py) at 300 dpi (PNG) with vector PDF counterparts in `figures/`.

---

## Supplementary Note 1 — Model state vector, parameters and inputs

The port implements `N_STATES = 33` in `candidate/indpensim/v0.1/model.py`. States: S, DO2, O2, P, V, Wt, pH_H, T, Q, viscosity, A_t1, A0, A1, A3, A4, n0…n9, nm, phi0, CO2, CO2d, PAA, NH3, mup, mux. The hyphal-count states n0…n9, nm and phi0 are algebraic quasi-steady variables (`dy = 0`, `model.py` lines 685–697) and are not integrated.

The parameter vector has 105 entries (`params.py`), the input vector 26 (`model.py`, `simulate.py`). Representative nominal values: mux = 0.41, mup = 0.041, alpha_kla = 85, m_s = 0.029, PAA_c = 530000, N_conc_paa = 150000, c_oil = 1000, Y_sx = 1.85, Y_O2_X = 650, X_crit_CO2 = 7.57 g/L, q_co2 = 0.120. Batch-level generating random effects: mux = 0.41 ± 0.025, mup = 0.041 ± 0.0025, alpha_kla = 85 ± 10, PAA_c = 530000 ± 20000. Eight low-pass disturbances use b1 = 0.005, a1 = [1, −0.995] (time constant ≈ 40 h).

Integration: `solve_ivp(method="BDF", rtol=1e-3, atol=1e-6, max_step=0.01 h)`, output sampled at 0.2 h. Guards clamp states 0–30 to 0.001 and DO2 < 2 to 1; an adaptive mux guard activates for k > 65. A pure-numpy RK4 fallback (`integrators.py`, h = 0.001 h) and a `SimRequest`/`SimResult` plugin contract (`contract.py`) exist but are not imported by any active path and are **not** counted as deployed capability.

## Supplementary Note 2 — Why residual-quantile coverage is tautological

Let r_t = y_t − ŷ_t denote residuals on the evaluation window. If the prediction interval is constructed as [q_0.05(r), q_0.95(r)] from the *same* residual sample used for evaluation, then by definition exactly 90% of those residuals lie inside the interval, up to interpolation. Replacing ŷ_t by any constant c merely shifts the residual distribution by a constant; the empirical quantiles shift identically, so the fraction of residuals inside the shifted interval is unchanged. The empirical result confirms the identity to machine precision: 0.899548532731377 for both the fitted and the zero-information predictor, with Δ = 0.0 in all four channels (`runs/r160_i3_coverage_tautology.json`). This is a metric-level instance of leakage in the sense of ref. [12] of the main text. A discriminating interval must derive its width from a quantity *predicted* independently of the realised residual — here μ ± 1.96σ with σ from the predictive model — which separates junk (0.0000) from fitted (0.1072 / 0.3160) predictors.

## Supplementary Note 3 — Five-channel health classifier (pseudo-code)

```
A = max(CO2d) > 7.57                       # legacy classify_crash channel
B = guard_audit.tally['pH_H'] > 0          # pH guard clamping
C = pH_pre_max >= 7.0 or not finite(pH)   # pH excursion
D = drop_sim / drop_meas < 0.6            # product collapse (abs < 0.5 w/o measurement)
E = |yield_err| > 0.05                    # yield breach

if D or E: catastrophic
elif B or C: degraded
elif A: benign
else: normal
```

Empirical distribution: normal 77, benign 0, degraded 5, catastrophic 4. Catastrophic batches [37, 50, 51, 91]; degraded [40, 43, 49, 54, 92]. Flag tallies: pH_clamp 5, pH_over7 9, p_collapse 4. The legacy classifier's guard `if max(CO2d) <= 7.57: return normal` is always true because the observed maximum over 86 batches is 7.194.

**Co-existing conventions (do not merge).** `runs/r156_acceptance.json` retains both the legacy block (n_normal = 86, n_catastrophic = 0) and the corrected `n_health` block. Separately, a *validity* criterion under the default `ph_fix = 0` baseline declares 9 invalid batches [37, 40, 43, 49, 50, 51, 54, 91, 92], of which 5 are true pH clamps [37, 50, 51, 91, 92]. The candidate `ph_fix = 1` path yields 86/86 valid. Validity answers "is this batch admissible for baseline comparison"; health answers "did the model fail". Merging them would recreate the category error the manuscript argues against.

## Supplementary Note 4 — A/B evidence gate definitions

The gate (`tools/r166_ab_gate.py`) is two-sided and threshold-preserving. For V1 it uses 5 zero-information controls and 20 fault injections, derives channel-wise thresholds on a grid with an explicit margin of 1.05, validates by leave-one-out over the control set, and reports a confusion table for both the candidate and the frozen baseline. Selected thresholds: CO2outgas 4.820219494310997, DO2 4.83036999328888, pH 5.041503072387664; O2 is excluded because its injection signal (max|z| 0.0634) cannot be separated from controls (0.0562).

For V2 the frozen caps are max|Δ| ≤ 20 pp (V2-3) and ≤ 30 pp (V2-4) against the reference deviation 3.0878581725122034 pp. The first-pass result (16/18 FAIL, `runs/r166_ab_gate_first_pass.json`) is archived; after adding two evidence checks the final result is 18/20 **NO_GO**, with V2-3 and V2-4 still FAIL. Thresholds were never modified. V3 is confined to the evaluation layer: the `k_dual` lookup is not written back to `golden_params.py`.

## Supplementary Note 5 — Governance spine and evidence index

| Category | Artefact | Content |
|---|---|---|
| Versioned contract | `ENGINE_CONTRACT.md` | v1.0 → v1.97, ~80 version rows; R167 is the newest |
| Debt ledger | `docs/r157_debt_ledger.md` | D-2…D-92, including D-65 closed and D-92 opened in R167 |
| Sign-off | `docs/m5_review_signoff.md` | decisions R-1…R-17 and known boundaries B-1…B-19 |
| State | `state.yaml` | gates, cap level, L3 status, R167 block |
| Per-round reports | `docs/rNNN_round_report.md` | narrative for 167 rounds |
| Per-round evidence | `runs/rNNN_*.json` | machine-readable checks |
| Gates | `tools/rNNN_*_gate.py`, `tools/rNNN_final_check.py` | executable, 54/54 → 25/25 → 20/20 |
| Synchronisation | `tools/rNNN_governance_update.py` | dry-run by default, idempotent, preserves CRLF/LF |

Contract-version parsing was itself a defect: the original parser scanned only the version table body and stalled at v1.94; it now takes the maximum across header and table, which is the single source of truth shared by `/api/health`, `export_data.py` and the evidence panel (all v1.97).

## Supplementary Note 6 — Runtime loading, admission gates and views

Fourteen capabilities by tier — A (6): `solver_info`, `simulate_batch`, `evaluate_batch`, `golden_set_validate`, `trajectory_check`, `element_balance_check`; B (5): `estimate_batch`, `estimate_batch_stage2`, `reconstruct_batch`, `discover_residual`, `observe_online`; C (2): `optimize_feed`, `advise_control`; D (1): `batch_fallback_tier`. They are loaded in-process from `mcp_server.py` function bodies (no duplicated implementation).

Twelve operators verified by `import + callable`: `model.rhs`, `integrate_interval`, `simulate_open_loop`, `yield_metrics`, `classify_crash`, `build_params`, `estimate_batch`, `estimate_stage2`, `optimize_feed`, `hier_fit`, `element_balance`, `trajectory_metrics`. Two naming defects were exposed by runtime verification: `hier_est` (a module; the callable is `hier_fit`) and `conservation_metrics` (a module; the callable is `element_balance`).

`POST /api/invoke` gates: (1) 14-item whitelist; (2) five forbidden L3 keys — `dist_noise_sigma`, `dist_noise_seed`, `innovation_criteria`, `k_dual`, `alpha_kla_override`; (3) `opt_in = true` for `fallback_chain` / `health_probe`; (4) `confirm = true` for six cost-heavy capabilities. Numerical caps: n_jobs ≤ 6, maxiter ≤ 25, n_ens ≤ 50, max_terms ≤ 8, stride ≤ 200. All rejections return an explicit reason with HTTP 400.

Six views with DOM assertion counts: overview 4 KPI cards, topology 1 SVG, batch 86 cells, channels 15 rows, operators 12 panels, workbench 14 capability buttons. Browser hygiene: 0 page errors, 0 console errors, 0 4xx resource requests. Six screenshots at 1440 × 940 are retained in `docs/screenshots/platform/r167_*.png`.

## Supplementary Note 7 — Known boundaries (not unfinished work)

| ID | Boundary | Consequence |
|---|---|---|
| D-38 / D-65 | constant crash classifier; existence-based "loaded" label | replaced by five-channel health and `import + callable` |
| D-53 / D-64 | S and P/PAA structurally non-identifiable | claims withdrawn; no soft-sensor delivery |
| D-54 / D-57 | 99.8–101.5 pp discontinuous control response | runtime closed-loop control ruled out |
| D-70 / D-71 / D-72 | Raman / PAA-PLS carry no independent information | not introduced as delivery components |
| D-78 / D-87 | tautological coverage; 84.38% innovation trigger | argumentation withdrawn; opt-in only |
| D-88 | mycelial compartments rank 0 / nullity 4 | GOAL §2 row 7 reclassified as internal soft-sensing quantity |
| D-89 | 28-batch validation set never held out | no generalisation claim for hierarchical estimates |
| oq#36 | MATLAB `rng('shuffle')` seed not recorded | bit-exact MATLAB reproduction impossible |
| R166 L3 | promotion to default path not executed | V1/V2/V3 remain opt-in |

## Supplementary Note 8 — Environment and reproduction

CPython 3.10.5 (64-bit Windows); pinned in `requirements.txt`: numpy 1.26.4, pandas 2.3.3, scipy 1.15.3, matplotlib 3.8.4, openpyxl 3.1.2, PyYAML 6.0.1, pytest 7.4.3, mcp 1.12.0. `fastmcp` is deliberately absent; D-85 was closed with the official SDK's `mcp.server.fastmcp.FastMCP` compatibility layer.

```
python -m pip install -r requirements.txt
python platform/export_data.py
python tools/r167_platform_gate.py       # starts 127.0.0.1:8771, stops automatically
python tools/r167_final_check.py
python paper/make_figures.py
python paper/make_supplement.py
python paper/check_manuscript.py
```

The platform can be started for interactive inspection with `python platform/serve.py --port 8771`; port 8770 (the historical default) is intentionally left untouched.

## Supplementary figure captions

**Fig. S1.** Channel-level median nRMSE (%) on a log scale comparing the mechanistic A tier with a 5-fold cross-validated B-tier soft sensor over 86 batches. X 24.6 → 2.3; viscosity 19.7 → 5.6; DO2 19.5 → 11.8; P 14.2 → 17.7; PAA 28.2 → 28.7; S 268.6 → 214.6 (model-reference, circular). Classification is carried on the x-axis. Data: `runs/r157_i3_channels.json`.

**Fig. S2.** Runtime capability loading and the six-view platform: 14 tools in four tiers, 12 operators verified by `import + callable`, four admission gates, six views and the additive HTTP surface. Gate 25/25, final check 20/20, contract v1.97, port 8771 (8770 untouched). Data: `runs/r167_platform_gate.json`, `runs/r167_final_check.json`.

**Fig. S3.** Evidence lifecycle over 167 documented rounds, from model port and calibration through metric falsification, identifiability and control limits, the A/B NO_GO decision and runtime loading. Every round emits a JSON evidence file, a round report, a debt-ledger entry and a contract version row; first-pass failures are archived alongside final verdicts.

## Supplementary tables

S-Table A (86-batch anchor), B (channel nRMSE), C (coverage tautology and alternative), D (amplitude sweep), E (seed transfer), F (full-amplitude injection), G (eight disturbance variances), H (health classification), I (G1–G25 and F1–F20 check lists) are provided in [`supplementary_tables.md`](supplementary_tables.md).
