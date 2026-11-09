# Supplementary Material

**Counterfactual validation of process simulation models: structural failures of single-metric credibility checks in an industrial penicillin fermentation benchmark**

This document collects the implementation detail and the supporting application examples that are deliberately kept out of the main text. The main text is a methodology paper; this supplement records how the demonstration was implemented and how each supplementary experiment can be reproduced. No result in the main text depends on an item appearing only here.

---

## S1. Evidence-gating workflow (condensed)

The demonstration uses a four-stage workflow that separates the authority to run a model from the authority to change what the model relies on. It is an implementation convenience, not a contribution claim; the contribution is the counterfactual diagnostic battery of Section 2.3.

| Stage | Definition | Invariant | Machine-checkable artefact |
|---|---|---|---|
| 0 | Frozen baseline; default path byte-identical | no change to calibrated parameters, integrator, data or regression anchor | four pinned source hashes; maximum regression deviation exactly zero |
| 1 | Opt-in candidates, disabled by default | fully bypassable; never touches stage 0 | explicit bypass flags and a five-name revocation list |
| 2 | Adversarial evidence gate | thresholds frozen; a reject verdict cannot be rewritten as a pass; failures archived | two-sided gate record with retained first-pass failure |
| 3 | Human-gated model update adoption | requires explicit confirmation; not executed in this study | adoption state flag |

Scientific claims are stored as typed records of subject, quantity, evidence, scope and authority. A rejected or withdrawn claim is a valid record with its own evidence, so negative results are first-class outputs. Five parameter names (two disturbance-injection keys, the channel-wise innovation criteria and two golden-parameter override keys) are rejected whenever a candidate attempts to use them.

---

## S2. Five-channel health classifier

The legacy crash classifier begins with a branch that returns `normal` whenever the maximum dissolved CO2 does not exceed 7.57 g/L. Across all 86 batches the maximum is 7.194 g/L, so the first branch always fires (86/86 normal). Batch 91 ends at pH 3.001 with 129 pH-guard clamping events and is still reported normal.

The replacement evaluates five channels per batch:

| Channel | Definition | Severity |
|---|---|---|
| A | dissolved CO2 above 7.57 g/L | benign if alone |
| B | pH-guard clamping events | degraded |
| C | pH excursion beyond 7.0 or non-finite pH | degraded |
| D | product collapse, simulated-to-measured product change below 0.6 | catastrophic |
| E | yield breach beyond +/-5% | catastrophic |

The replacement resolves 77 normal, 0 benign, 5 degraded and 4 catastrophic batches. Flag tallies are 5 pH-clamp, 9 pH-excursion and 4 product-collapse events. A separate validity criterion, which asks whether a batch is admissible for baseline comparison, declares 9 batches invalid. The two criteria are perfectly collinear on this benchmark (phi = 1.0000) because both consume the same pH-guard signal; they are counted once in the evidence inventory.

---

## S3. Runtime loading and interface verification

A deployed capability is counted only if its module imports and its entry symbol is callable; file existence is not evidence. Replacing an existence test with the runtime test exposed two naming defects (a hierarchical estimator whose callable entry point differs from its module name, and an element-balance function registered under its module name), verified 12 of 12 operators and all 14 capabilities.

Four independent admission gates protect capability invocation: a whitelist, the five-name revocation list, an explicit opt-in flag for bypass parameters and an explicit confirmation flag for expensive re-invocations. Numerical caps bound concurrency, iteration and ensemble sizes. All rejections return an explicit reason rather than a silent fallback.

Interface verification used a real browser with document-object-model assertions, console and page-error capture and failed-request monitoring; a capability call was issued end to end from the interface through the service layer to the solver. Six views rendered their expected elements with zero page errors, zero console errors and no failed requests. An integration gate of 25 checks and an independent consistency audit of 20 checks were executed against the frozen artefacts. These are software-verification results and are not used as evidence for any physical or methodological claim in the main text.

---

## S4. Candidate evaluation details (application examples)

Three opt-in candidates were evaluated against a two-sided, pre-registered gate. They are reported here as examples of the workflow; the main text uses only the negative result as methodological evidence.

**V1, channel-wise innovation thresholds.** 25 cases: 5 zero-information controls and 20 injections. Control maxima were 4.59 (CO2 outgassing), 4.60 (dissolved oxygen), 0.06 (oxygen) and 4.80 (pH); injected maxima were 5.34, 7.60, 0.06 and 37.72. Data-driven thresholds with a 1.05 margin selected three channels and excluded oxygen. The confusion table was 10 true positives, 5 false negatives, 4 true negatives and 1 false positive (Youden J = 0.4667); 11 of 20 injections were detected, 0 of 20 controls fired, and leave-one-out calibration succeeded in 5 of 5 folds. All 8 gate checks passed; the candidate remained opt-in.

**V2, eight-path disturbance-variance injection.** At full amplitude the maximum deviation from the frozen baseline was 96.06 percentage points with 3 of 6 yield collapses, reproducible in 6 of 6 repetitions at fixed seed against a reference deviation of 3.09 pp. Frozen caps of 20 and 30 pp were left unchanged. Amplitude optimisation over {0.02, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0} found five feasible scales on the tuning seed; the scale closest to the reference, 0.35 (root-mean-square deviation 2.13 pp), was confirmed by six-fold leave-one-out consistency, giving 8 of 10 optimisation checks passed. The verdict remained NO_GO (18/20). On unseen seed 11 the same scale produced a maximum deviation of 99.85 pp with 2 collapses; on unseen seed 23 it produced 2.13 pp with no collapses. A scale that happens not to collapse on one seed is a seed-specific fit, not a physical calibration.

**V3, dual-constraint oxygen-transfer lookup.** Evaluated on 6 batches excluding 6 known cliff batches; all 6 remained within +/-5%, with 3 improvements, 3 degradations and a maximum deviation of 0.0143 pp. Because 81 of 88 calibrated batches share the nominal coefficient, writing the lookup back would alter the frozen anchor; it was retained as an evaluation-layer result only.

---

## S5. Channel-level soft-sensor matrix (five-fold cross-validation)

Median normalised RMSE over 86 batches for six channels. Channels whose "measurement" is a model reference, or whose states are structurally unobservable, are flagged; a numerical gain on a circular comparison is not treated as evidence.

| Channel | Mechanistic (%) | Cross-validated (%) | Gain (pp) | Verdict |
|---|---|---|---|---|
| Biomass X | 24.5829 | 2.2768 | +22.3062 | deliverable |
| Viscosity | 19.6890 | 5.5736 | +14.1154 | deliverable |
| Dissolved oxygen DO2 | 19.5268 | 11.8344 | +7.6924 | marginal |
| Product P | 14.1919 | 17.6975 | -3.5056 | not identifiable |
| PAA | 28.1973 | 28.7209 | -0.5236 | not identifiable |
| Substrate S | 268.5645 | 214.5867 | +53.9778 | circular comparison |

The product channel additionally retains a 60-120 h deficit (mean -0.0625, median -0.0923) that four independent repair attempts did not close.

---

## S6. Supplementary methodological experiments: reproducible protocols

All experiments are in silico and use only the frozen 33-state ODE engine, the released batch records, the calibrated parameter table and previously recorded response surfaces. No wet-laboratory or prospective plant data are introduced, and the frozen baseline is never modified.

**E1, solver sensitivity.** Eight representative batches (8, 16, 36, 55, 60, 80, 91, 92) are re-integrated with four configurations: BDF at rtol 1e-6 / atol 1e-9, Radau at the same tolerances, LSODA at the same tolerances, and explicit RK45 with max_step 0.01 h. The reference is the frozen default (BDF, rtol 1e-3, atol 1e-6, max_step 0.01 h). Recorded outputs are end-of-batch product deviation, per-channel trajectory NRMSE on t >= 20 h, peak-time shift and CPU time.

**E2, leave-batch-out parameter transfer.** The 86 batches are split into five disjoint folds. For each held-out batch a prior is built only from the calibration vectors of the other folds: either the per-parameter median over nine shared keys, or a complete parameter vector drawn from the training pool. The batch's own input trajectory is used, but its recorded product mass enters only the final error calculation. Four draws are repeated on twelve representative batches to form P5/P95 intervals.

**E3, discontinuity-aware sensitivity.** Apparent finite-difference gradients are recomputed from the frozen 12-step bisection brackets (substrate-setpoint and product-setpoint transitions) and from the 12 x 12 oxygen-transfer response surface. SLSQP and trust-constr are then run offline on the recorded median response curve from five starting values, with the number of runs stagnating at the starting point as the outcome.

**E4, observation-operator rank protocol.** The four mycelial compartment states A0/A1/A3/A4 define a four-column operator. The assimilation operator has 10 channels x 5 time points = 50 one-hot rows, none of which observe a compartment; the reporting operator adds 10 aggregate rows of [1,1,1,1]. Column-normalised singular values, rank, nullity and condition number are computed before and after adding up to four independent compartment-resolved rows, and after adding 50 rows of an already existing type. The six protocol steps are listed in Section 3.3 of the main text.

**E5, discriminative-validity matrix.** Ten criteria are scored on three axes. Control separation is min(1, |M(fitted) - M(zero-information)|) for scalar statistics, 1 - |2q-1| for a detector with trigger rate q, or the fraction of injected defects detected for a loading test. Output entropy is the normalised Shannon entropy of the output distribution. Detection power is Youden J where a confusion table exists, or the defect-detection fraction otherwise.

**E6, parameter uncertainty propagation.** Ten Monte Carlo replicates on six batches apply the nominal batch-level random effects (mux 0.41 +/- 0.025, mup 0.041 +/- 0.0025, alpha_kLa 85 +/- 10) as multiplicative perturbations to each batch's own calibrated vector. A correlation-based elementary-effect proxy ranks the three parameters by their association with the absolute yield deviation.

**E7, physical consistency.** Carbon and nitrogen balances are recomputed from the frozen steady-state census of 13 batches. Carbon budget +/-20%, nitrogen budget +/-35%. Respiratory quotient reproduction from recorded inputs is exact; simulated OUR and CER are approximately 12% high because of overestimated CO2 outgassing and are retained as a declared model bias.

**E8, admission filter.** The E5 matrix is mapped to a two-stage procedure: reject criteria with any zero axis, zero control separation, degenerate dispersion or perfect collinearity; only then admit the survivors into multi-criteria synthesis. Rejected criteria and their re-issue conditions are archived rather than deleted.

---

## S7. Figure and table inventory

The main text carries the process flow diagram, the protocol overview, the six methodological figures (solver sensitivity, discriminative-validity matrix, observation rank, discontinuity, transfer, uncertainty propagation, admission filter and physical consistency) and the extended validation figures (parity, Bland-Altman, violin, ECDF, Q-Q, ACF, radar, heatmap, forest, parallel coordinates, alluvial and mosaic). All figures are supplied as 300 dpi PNG and vector PDF. Tables cover benchmark parameters, criterion diagnostics, transfer results, discontinuity and optimisation statistics, the baseline ladder, distributional diagnostics, candidate gate outcomes and the surviving evidence list.

---

## S8. Numerical conventions

RMSE is computed over batch-level relative yield errors. Normalised RMSE is normalised by the observed channel range and reported as a median over batches and folds; no single aggregate hides channel-level failure. Wilson 95% intervals are reported where coverage is discussed. Symlog scaling in figures is used for display only; all test statistics are computed on untransformed values. Failed checks are reported with the same prominence as passing ones, and no post-hoc threshold relaxation or subgroup searching was performed after seeing results.
