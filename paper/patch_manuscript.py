# -*- coding: utf-8 -*-
"""Apply the R168 enhancement patch to manuscript.md.

Adds: counterfactual instrument certificates, an evidence type system,
realisation-path invariance testing, extended baselines and distributional
diagnostics, epistemic boundary certificates, ten new figures and five new
tables.  Every numeric value is copied from paper/extended_stats.json, which
is itself derived from runs/.  The pre-patch manuscript is archived as
paper/manuscript_v1.md so the previous version remains auditable.
"""
from __future__ import annotations

import os
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MS = os.path.join(ROOT, "paper", "manuscript.md")
ARCHIVE = os.path.join(ROOT, "paper", "manuscript_v1.md")


def rep_once(t, old, new):
    assert t.count(old) == 1, "anchor not unique (%d): %r" % (t.count(old), old[:70])
    return t.replace(old, new, 1)


def splice(t, a, b, new):
    i = t.index(a) + len(a)
    j = t.index(b, i)
    return t[:i] + new + t[j:]


def before(t, marker, new):
    return rep_once(t, marker, new.rstrip() + "\n\n" + marker)


# ----------------------------------------------------------------------
NEW_ABSTRACT = r"""Digital twins for bioprocesses are judged by predictive accuracy, yet the
*instruments that certify them* are rarely tested for falsifiability. A metric that returns
a favourable value for every model, including a zero-information model, certifies nothing.
We introduce counterfactual instrument auditing: every acceptance statistic, classifier and
deployment check is issued a machine-signed **falsifiability certificate** recording its
control separation, output entropy and detection power, and is quarantined if any axis is
zero. Claims themselves are typed objects <subject, quantity, evidence, scope, authority>;
evaluation compiles a candidate, an adversarial gate type-checks it, and promotion to the
default path requires a human signature that was deliberately never given. On an in-silico
benchmark of 100 fed-batch penicillin fermentations (IndPenSim, 100,000 L, ~230 h), we
ported the 33-state model to Python, calibrated 86 batches and froze a byte-identical
baseline (end-of-batch yield RMSE 2.3448%, 86/86 within +/-5%, max|Delta| = 0.00e+00).
Extended validation places this number in context: against leave-one-out mean, persistence
and zero predictors the frozen twin reduces RMSE by 96.82%, 97.46% and 97.66%, and by
88.8% on a scale-robust median-normalised error (2.22% versus 26.31%). Errors are
unbiased (mean -0.0662%, sign test p = 0.590), approximately normal (Shapiro-Wilk p =
0.182), serially unstructured (lag-1 r = 0.058, runs p = 0.696) and in agreement with the
record (Bland-Altman limits -4.69% / +4.55%). Of eight acceptance instruments, four were
invalidated: a coverage statistic identical (0.899548532731377) for fitted and
zero-information predictors, a crash classifier returning 86/86 `normal`, an innovation
test flagging 84.38%, and a file-existence loading test. Replacements resolved 77 normal,
5 degraded and 4 catastrophic batches. We further show that health and validity criteria,
though conceptually distinct, are perfectly collinear here (phi = 1.0) because both
consume the same pH-guard signal, and therefore cannot be counted as independent
corroboration. **Epistemic boundary certificates** convert unidentifiable states
(rank 0 / nullity 4) and discontinuous control responses (99.8-101.5 pp jumps) into typed
`WITHDRAWN` outputs. A **realisation-path invariance test** rejects eight-path disturbance
variance injection: full amplitude caused 3/6 collapses (96.06 pp), and a scale of 0.35
tuned on seed 7 collapsed to 99.85 pp on unseen seed 11, yielding 18/20 NO_GO with
thresholds unchanged. A Canvas-rendered process flow diagram and a runtime-verified
six-view platform (14 capabilities, 12 operators, gate 25/25, final check 20/20, contract
v1.97) make the evidence executable. All evidence is in silico; each batch uses its own
calibrated parameters, so 2.3448% is reconstruction consistency, not prospective
prediction, and no opt-in candidate was promoted to the default path."""

NEW_CONTRIB = r"""The contributions are sixfold:

1. **Counterfactual auditing of the certification apparatus.** We define a falsifiability
certificate with three machine-computable axes - control separation, output entropy and
detection power - and issue it for eight acceptance instruments from frozen JSON evidence.
Four are invalidated as tautological, constant, saturated or existence-only; four are
certified. This moves V&V from "validate the model" to "validate every device that
produces a claim", including the dashboard.

2. **An evidence type system for scientific claims.** We model a claim as a typed record
<*subject*, *quantity*, *evidence*, *scope*, *authority*> and implement the four-layer
architecture as a compilation pipeline: L0 is a frozen symbol table, L1 compiles
bypassable candidates, L2 is an adversarial type check with pre-registered thresholds,
and L3 is a human-signed linker action. Five forbidden keys constitute an explicit
ambient-authority revocation list. `WITHDRAWN` is a valid output type, not a failure.

3. **A systematic falsification of three acceptance instruments, plus a fourth
independence finding.** Using zero-information controls, constant-detector tests and
trigger-rate audits, we show that a residual-quantile coverage metric, a crash classifier
and a global innovation threshold are respectively tautological, constant and
near-constant. We then show that the replacement health classifier and the batch-validity
criterion, although answering different questions, are perfectly collinear (phi = 1.0)
because they share a pH-guard signal - so two apparently independent checks are one
piece of evidence.

4. **Epistemic boundary certificates.** Structural results are promoted from prose to
typed artefacts: whenever nullity(H) > 0, the corresponding delivery claim is marked
`WITHDRAWN` regardless of fit quality. Mycelial compartment states (rank 0 / nullity 4),
substrate/product/PAA channels, the simulated Raman channel and runtime continuous
control (99.8-101.5 pp discontinuous response) become certified boundaries of the
twin rather than unfinished work.

5. **A realisation-path invariance test and a pre-registered negative result.** For any
stochastic augmentation we require invariance to disturbance *realisations* across at
least two unseen seeds, not merely monotone amplitude behaviour. Eight-path variance
injection at full amplitude caused 3/6 catastrophic collapses (96.06 pp); a scale of
0.35 tuned on seed 7 appeared feasible but failed on unseen seed 11 (99.85 pp) while
succeeding on seed 23 (2.13 pp). We declare 18/20 **NO_GO**, retain the failing
first-pass evidence and leave thresholds untouched.

6. **Extended baseline validation and executable evidence.** Seven historical calibration
stages, five reference predictors with explicitly stated information sets, parity and
Bland-Altman agreement, distributional diagnostics, a 12 x 12 alpha_kLa response surface,
a five-family gate matrix, 147 evidence JSON files and an interactive Canvas 2D process
flow diagram make every headline number comparable and re-derivable."""

SEC_2_5 = r"""### 2.5 Information-theoretic auditing and claim typing

Information theory supplies the vocabulary for asking whether an instrument carries any
information at all [34]: a statistic whose output distribution is degenerate has zero
entropy and cannot discriminate between a model and no model. Method-comparison
statistics add a complementary warning that *association is not agreement* [35] - a
correlation of 0.996 between simulated and recorded yield says little about bias or
limits of agreement. Distributional diagnostics [36-38] are standard practice in
statistics but are seldom applied to the validation instruments of a digital twin.

A second connection is to protection and capability-based systems [39]. In a computer
system, being able to compute a result and being authorised to change what the system
relies on are distinct privileges; conflating them produces exactly the class of
incident that least-authority designs prevent. We argue that scientific claims need the
same separation: running a candidate, evaluating it, and promoting it to the default
production path are three different acts with different authority requirements. Treating a
claim as a typed object makes a negative result a well-typed output rather than an
embarrassment, and makes promotion an explicit linker decision. To our knowledge this
compilation metaphor has not previously been operationalised as an executable,
threshold-preserving gate in a bioprocess digital twin."""

FIG12_BLOCK = r"""![Fig. 12](figures/fig12_pfd.png)

**Fig. 12 | Process flow diagram of the 100,000 L penicillin fed-batch (interactive Canvas
2D).** Six feed and utility trains - sugar, oil/antifoam, PAA precursor, NH3 / acid / base,
sterile air and cooling water - enter the stirred aerated reactor R-101 (33-state stiff
ODE, BDF, 0.2 h on-line sampling, 12 h off-line assays with 98.2% missingness). Off-gas
mass spectrometry supplies OUR, CER and RQ; on-line sensors feed DO2, pH and temperature
loops. Dashed purple traces are certified measurement and control paths, including the
explicit-degradation chain EnKF -> MHE -> steady-state carbon balance -> `explicit_failure`.
Red boxes and traces mark **withdrawn** channels: the simulated Raman spectrometer
(incremental R2 0.0199 -> 0.0092) and the four mycelial compartments (rank 0 / nullity 4).
The supervisory layer implements L0/L1/L2/L3. Rendered natively in Canvas 2D at
1200 x 640 logical units by `paper/pfd.js`, exported at 2508 x 1338 px by headless Chrome
(`paper/export_pfd.py`), and available as an interactive HTML figure with hover provenance
and togglable control/withdrawn layers (`paper/pfd.html`). Sources: `model.py`,
`solver_chain.py`, `runs/r165_mycelium_identifiability.json`, `runs/r167_platform_gate.json`."""

SEC_3_NEW = r"""### 3.13 Falsifiability certificates: the audit as a type check

Let $M$ be an acceptance instrument, $p$ a fitted predictor and $p_0$ a
zero-information control. We attach to $M$ a certificate

$$FC(M) = \langle \Delta,\ \hat{H},\ J,\ \text{verdict},\ \text{evidence} \rangle$$

where $\Delta = \min(1, |M(p) - M(p_0)|)$ for scalar statistics, $\Delta = 1 - |2q-1|$
for a binary detector with trigger rate $q$, and $\Delta$ is the fraction of deliberately
injected defects detected for a loading test; $\hat{H} = -\sum_k \pi_k \log \pi_k /
\log K$ is the normalised Shannon entropy [34] of the output distribution over $K$
categories (zero for a constant output); and $J = \mathrm{TPR} - \mathrm{FPR}$ wherever a
confusion table exists. The verdict is one of `CERTIFIED`, `TAUTOLOGICAL`, `CONSTANT` and
`SATURATED`. An instrument is quarantined if $\Delta = 0$, $\hat{H} = 0$, or $J \le 0$
where applicable, and a named replacement must be recorded. Certificates are issued by
`paper/make_extended_stats.py` from frozen artefacts and written to
`paper/extended_stats.json`; no axis weight or threshold is chosen after seeing results.
The three axes are deliberately reported separately rather than collapsed into a single
score: a composite index would introduce exactly the arbitrary degree of freedom that
this work argues against.

### 3.14 An evidence type system for scientific claims

We model every scientific claim as a typed record

$$\text{Claim} = \langle \textit{subject},\ \textit{quantity},\ \textit{evidence},\
\textit{scope},\ \textit{authority} \rangle.$$

The four layers become a compilation pipeline. L0 is a frozen symbol table: the default
simulation path is pinned by four SHA-256 values and never rewritten. L1 compiles
candidate code into isolated, fully bypassable namespaces but does not link it into the
default path. L2 is a type check: a candidate is admissible only with zero-information and
injection controls, two-sided criteria, frozen thresholds, leave-one-out consistency, a
confusion table and at least two unseen stochastic seeds. L3 is a human-signed linker
action that was **not executed** in this study. The five `FORBIDDEN_KEYS` in
`platform/ops_registry.py` (`dist_noise_sigma`, `dist_noise_seed`,
`innovation_criteria`, `k_dual`, `alpha_kla_override`) constitute an explicit
ambient-authority revocation list [39]; each is rejected at `/api/invoke` with HTTP 400.
`WITHDRAWN` is a valid claim type carrying its own evidence, so a negative result is a
first-class output of the system rather than an omitted section of a report.

### 3.15 Extended baseline ladder and distributional diagnostics

We evaluated five reference estimators against the same 86 recorded yields and report
their **information sets** explicitly, because they are not like-for-like methods: the
naive predictors see only recorded yields, whereas L0 additionally sees batch inputs,
per-batch calibrated `COMBINED` parameters and the 33-state ODE. The estimators are the
frozen L0 reconstruction, a leave-one-out batch-mean predictor, an in-sample global-mean
predictor, a persistence (previous-batch) predictor and a zero predictor. Because the
recorded product mass spans 0.54-4.56 x 10^6 g, relative error is unstable for the two
lowest-yield batches; we therefore also report a scale-robust error,
$\mathrm{RMSE}_{\mathrm{med}} = 100\,\sqrt{\overline{(\hat y - y)^2}} /
\mathrm{median}(y)$.

Agreement was assessed by a parity plot and a Bland-Altman difference plot [35], the
empirical CDF, a normal Q-Q plot with the Shapiro-Wilk statistic [36], lag-1 to lag-10
autocorrelation with a Wald-Wolfowitz runs test [37], an exact sign test, a Wilson 95%
interval [20] for the within-band proportion, and a Mann-Whitney comparison [38] of
normal versus fault batches (84 versus 2, severely underpowered). In accordance with
Section 3.12 we do not report bootstrap intervals. A seven-stage historical calibration
ladder parsed from `docs/round_summary_202610.md` is presented alongside, but is kept
visually and numerically separate from the 86-batch anchor because it uses a 12-batch
protocol. A 12 x 12 alpha_kLa response surface (12 batches x 12 values from 30 to 140)
was reconstructed from `runs/r162_kla_sensitivity.json`.

### 3.16 Realisation-path invariance test

For a stochastic augmentation $c$ with disturbance realisation $\xi_s$ indexed by seed
$s$, we define

$$T(c) = \max_{s \in S_{\text{unseen}}} \max_{b \in B} |\Delta(c, s, b)|.$$

A candidate passes only if the zero-information control is byte-identical to L0, if
$T(c)$ stays below the frozen caps for **every** unseen seed, and if leave-one-out
consistency holds on the tuning seed. This separates amplitude dependence (a property of
the noise scale) from path dependence (a property of the particular disturbance
realisation crossing a basin boundary in a bistable batch). Tuning the scale until a
single-seed collapse disappears is a seed-specific fit, not a physical calibration.

### 3.17 Figure production and three-format delivery

All figures are regenerated from `runs/` evidence at 300 dpi as PNG with vector PDF
counterparts (`paper/make_figures.py`, `paper/make_figures_v2.py`). The process flow
diagram is drawn in native Canvas 2D (`paper/pfd.js`) and exported by headless Chrome.
The manuscript is delivered in three synchronised formats: Markdown (`manuscript.md`),
a self-contained styled HTML with the interactive Canvas figure (`manuscript.html`), and
a print-quality PDF generated from that HTML (`manuscript.pdf`). A machine-readable
consistency check (`paper/check_manuscript.py`) verifies that headline numbers, figure
files, reference numbering and honesty declarations agree across all formats.

"""

SEC_4_NEW = r"""### 4.8 Extended baseline validation: a ladder, five reference predictors and agreement

![Fig. 7](figures/fig7_baselines.png)

**Fig. 7 | Extended baseline validation.** (a) Seven historical calibration stages from
the 12-batch protocol (70.95% -> 4.48% RMSE), shown separately from the 86-batch frozen
anchor (2.3448%) because the protocols differ. (b) Five reference predictors under two
error normalisations; information sets differ and are listed in Table 7. (c) Parity of
recorded and simulated product mass (r = 0.996367, R2 = 0.992747) with the +/-5% band.
(d) Bland-Altman agreement: bias -0.0662%, limits -4.6871% / +4.5547%, no
magnitude-dependent trend. Data: `runs/final_validation_v2.json`,
`runs/r148_validity_gate.json`, `paper/extended_stats.json`.

**Table 7. Baseline ladder with explicit information sets.**

| Estimator | Information set | n | RMSE (%) | RMSE / median yield (%) | within +/-5% |
|---|---|---|---|---|---|
| **L0 frozen mechanistic reconstruction** | batch inputs + per-batch `COMBINED` + 33-state ODE | 86 | **2.3448** | **2.2205** | **86/86** |
| Leave-one-out batch-mean predictor | other 85 recorded yields; held-out batch excluded | 86 | 73.6679 | 26.3103 | 11/86 |
| In-sample global-mean predictor | all 86 recorded yields (optimistic constant) | 86 | 72.8113 | 26.0044 | 11/86 |
| Persistence (previous batch) | recorded yield of the immediately preceding batch | 85 | 92.3806 | 38.2620 | 14/85 |
| Zero predictor | none | 86 | 100.0000 | 96.1811 | 0/86 |

Relative to the leave-one-out mean, persistence and zero predictors, L0 reduces RMSE by
**96.82%, 97.46% and 97.66%** respectively. These differences are large but must not be
over-interpreted: the naive predictors forecast a yield series, whereas L0 reconstructs
each batch from its own inputs and calibrated parameters. Their role is to establish that
the target series is far from trivially predictable and that the frozen anchor is not an
artefact of a low-variance target. The scale-robust column removes the amplification
caused by the two lowest-yield batches (0.54 x 10^6 g and 0.74 x 10^6 g against a median
of 3.24 x 10^6 g); L0 still improves by 88.8% over the leave-one-out mean on that scale.

Seven historical stages show how the 12-batch protocol reached 4.48% from a 70.95%
nominal start (37.40%, 37.72%, 32.57%, 16.18%, 7.28%, 4.48%); extending the evaluation
set to 86 batches produced 2.3448%. Because the batch count and calibration scope
changed, these numbers are **not** a single learning curve and Fig. 7a marks the protocol
boundary explicitly.

### 4.9 Distributional diagnostics and parameter-response surfaces

![Fig. 8](figures/fig8_distribution.png)

**Fig. 8 | Distributional diagnostics of the frozen-baseline error (n = 86).** (a) Violin
and box plots by health class; (b) empirical CDF and histogram with the +/-5% band;
(c) normal Q-Q plot with Shapiro-Wilk W = 0.9793, p = 0.1824; (d) lag-1 to lag-10
autocorrelation with 95% white-noise bounds. All statistics are computed on
untransformed errors. Data: `runs/final_validation_v2.json`,
`runs/r156_acceptance.json`, `paper/extended_stats.json`.

**Table 8. Distributional diagnostics of the 86 signed yield errors.**

| Statistic | Value | Interpretation |
|---|---|---|
| Mean / median | -0.0662% / -0.0744% | no material systematic bias |
| SD / MAD / IQR | 2.3576% / 1.4967% / 3.0034 pp | tight, symmetric spread |
| Range | -4.8144% to +4.8290% | entirely inside the pre-registered band |
| Skew / excess kurtosis | 0.0960 / -0.4767 | near-Gaussian, slightly platykurtic |
| Shapiro-Wilk W (p) | 0.9793 (0.1824) | normality not rejected |
| Q-Q correlation / KS p | 0.9925 / 0.7348 | consistent with normality |
| Sign test | 40+ / 46-, p = 0.5900 | no directional bias |
| Lag-1 autocorrelation | 0.0579 | no serial dependence in batch order |
| Wald-Wolfowitz runs | 42 observed vs 43.79 expected, p = 0.6962 | no ordering artefact |
| Wilson 95% CI for 86/86 | [0.9572, 1.0000] | honest finite-sample bound on the pass rate |
| Normal (84) vs fault (2) RMSE | 2.3365% vs 2.6696% | Mann-Whitney p = 0.1073, underpowered |

![Fig. 11](figures/fig11_multibaseline.png)

**Fig. 11 | Multi-baseline fingerprints and a parameter-response surface.**
(a) Parallel coordinates of the five reference predictors on four normalised
capability axes; (b) radar comparison; (c) 12 x 12 alpha_kLa response surface of
end-of-batch yield error, showing contiguous collapsed and feasible regions rather
than a smooth gradient. The interior optimum is k* = 78.15 +/- 8.94 (11 batches),
close to the nominal 85 +/- 10. Data: `paper/extended_stats.json`,
`runs/r162_kla_sensitivity.json`.

### 4.10 Certifying the certification instruments

![Fig. 9](figures/fig9_certificates.png)

**Fig. 9 | Auditing the auditors.** (a) Eight acceptance instruments scored on three
machine-checkable axes; (b) radar fingerprints of two degenerate, one saturated and one
certified instrument; (c) confusion matrix of the channel-wise detector
(TP10 / FN5 / TN4 / FP1; Youden J = 0.4667). Data: `paper/extended_stats.json`,
`runs/r160_i3_coverage_tautology.json`, `runs/r166_ab_gate.json`.

**Table 9. Falsifiability certificates issued for eight acceptance instruments.**

| ID | Instrument | Control separation | Output entropy | Detection power | Verdict |
|---|---|---|---|---|---|
| M1 | Residual-quantile interval coverage | 0.0000 | 0.0000 | 0.0000 | **TAUTOLOGICAL** |
| M2 | Legacy `classify_crash` | 0.0000 | 0.0000 | 0.0000 | **CONSTANT** |
| M3 | Global innovation threshold (z > 5) | 0.3125 | 0.6253 | 0.0000 | **SATURATED** |
| M4 | Five-channel `classify_health` | 0.2093 | 0.3705 | 1.0000 | CERTIFIED |
| M5 | Channel-wise LOO-calibrated innovation (V1) | 1.0000 | 0.9000 | 0.4667 | CERTIFIED (opt-in) |
| M6 | mu +/- 1.96 sigma interval coverage | 0.1072 | 1.0000 | 0.1072 | CERTIFIED (width only) |
| M7 | File-existence loading test | 0.0000 | 0.0000 | 0.0000 | **TAUTOLOGICAL** |
| M8 | Runtime `import + callable` loading test | 1.0000 | 1.0000 | 1.0000 | CERTIFIED |

Four of eight instruments were invalidated. Note that M3 has non-zero entropy and
non-zero control separation yet zero detection power: a detector that fires on 84.38% of
normal data is *informative about nothing*, which a single entropy number alone would
miss. This is why the certificate reports three axes rather than one aggregate. M6 is
certified only for interval **width**; coverage itself remains withdrawn as calibration
evidence. M8 detects both naming defects (`hier_est` -> `hier_fit`,
`conservation_metrics` -> `element_balance`) that M7 reported as "loaded".

### 4.11 Epistemic boundary certificates and criterion independence

![Fig. S6](figures/figS6_epistemic_sankey.png)

**Fig. S6 | Negative results as first-class typed outputs (supplementary).**
(a) Alluvial diagram from ten candidate claims through four adversarial audits to three
certified statuses; (b) boundary matrix (C = certified, P = partial/conditional,
F = failed or withdrawn). Whenever nullity(H) > 0, `WITHDRAWN` is forced regardless of
fit quality. Data: `runs/r165_mycelium_identifiability.json`,
`runs/r157_i3_channels.json`, `docs/r157_debt_ledger.md`.

![Fig. S7](figures/figS7_governance.png)

**Fig. S7 | Structural boundaries and criterion independence (supplementary).**
(a) Four-batch x ten-scale bistable response surface; (b) carbon-balance error of the
third-ring steady-state census (12/13 credible, +/-20% budget); (c) health-versus-validity
mosaic. Data: `runs/r154_bistable.json`, `runs/r161_fallback_chain_probe.json`,
`runs/r156_acceptance.json`, `runs/r148_validity_gate.json`.

**Table 10. Health-versus-validity cross-tabulation.**

| | valid | invalid | total |
|---|---|---|---|
| normal | 77 | 0 | 77 |
| degraded | 0 | 5 | 5 |
| catastrophic | 0 | 4 | 4 |
| total | 77 | 9 | 86 |

Collapsing to (normal / flagged) x (valid / invalid) gives [[77, 0], [0, 9]] and
**phi = 1.0000**. The two criteria are perfectly collinear because both consume the same
pH-guard clamping and pH > 7 signals. They answer different questions - "is this batch
admissible for baseline comparison" versus "did the model fail" - but on this benchmark
they are **not independent evidence**. Reporting both as corroborating checks would
re-create the category error this paper argues against. We therefore count them as one
piece of evidence and state the collinearity explicitly.

### 4.12 Executable evidence inventory and the realisation-path invariance test

![Fig. 10](figures/fig10_evidence_matrix.png)

**Fig. 10 | Executable evidence.** (a) Five-family gate matrix (teal PASS, red FAIL, grey
not applicable) with the two retained A/B failures and two optimisation failures;
(b) paired channel-level effect sizes with 5-fold CV and mechanistic endpoints;
(c) realisation-path invariance test with the frozen 20 pp / 30 pp caps; (d) durable
evidence inventory on a log scale. Data: `runs/r166_ab_gate.json`,
`runs/r166_v2_optim.json`, `runs/r167_platform_gate.json`,
`runs/r167_final_check.json`, `paper/extended_stats.json`.

![Fig. S4](figures/figS4_channel_heatmap.png)

**Fig. S4 | Channel-level fidelity detail (supplementary).** (a) Six-channel metric
matrix; (b) mechanistic A tier versus 5-fold CV median nRMSE on a log scale;
(c) per-channel effect sizes, with substrate S labelled as a circular comparison.
Data: `runs/r157_i3_channels.json`.

![Fig. S5](figures/figS5_injection_heatmap.png)

**Fig. S5 | Disturbance-variance injection (supplementary).** (a) Seven-scale x six-batch
deviation heatmap on tuning seed 7; (b) the same scale 0.35 on two unseen seeds
(seed 11 collapses on batches 22 and 27); (c) frozen-cap feasibility matrix (5/7
feasible on the tuning seed, LOO chose 0.35 in 6/6 folds). Data:
`runs/r166_v2_optim.json`, `runs/r166_ab_gate.json`.

**Table 11. Executable evidence inventory and gate outcomes.**

| Artefact family | Result | Source |
|---|---|---|
| Integration gate G1-G25 | 25/25 PASS | `runs/r167_platform_gate.json` |
| Final consistency F1-F20 | 20/20 PASS | `runs/r167_final_check.json` |
| Two-sided A/B gate | 18/20 NO_GO (V2-3, V2-4 fail) | `runs/r166_ab_gate.json` |
| Amplitude optimisation V2O-1...10 | 8/10 (V2O-9, V2O-10 fail) | `runs/r166_v2_optim.json` |
| R166 final check | 54/54 PASS | `runs/r166_final_check.json` |
| First-pass A/B (archived, not deleted) | 16/18 FAIL | `runs/r166_ab_gate_first_pass.json` |
| Evidence JSON files | 147 | `runs/` |
| Successive v1.x contract rows | 98 (v1.0-v1.97) | `ENGINE_CONTRACT.md` |
| Debt-ledger IDs | 53 distinct IDs, D-2...D-92 | `docs/r157_debt_ledger.md` |
| Round reports | 36 (programme numbered R1-R167) | `docs/rNNN_round_report.md` |
| Sign-off records | 17 (R-1...R-17) | `docs/m5_review_signoff.md` |
| Browser screenshots | 6 | `docs/screenshots/platform/r167_*.png` |

The realisation-path invariance test (Section 3.16) is decisive for V2. At the chosen
scale 0.35 the maximum deviation was 3.697 pp on tuning seed 7 and 2.128 pp on unseen
seed 23, but **99.852 pp with two collapses** on unseen seed 11; full amplitude reached
96.059 pp with 3/6 collapses. $T(c) = 99.852$ pp exceeds both frozen caps, so the
candidate fails on path dependence even though it is feasible at low amplitude and on
two of three seeds. No post-hoc cap relaxation was applied.

"""

SEC_5_NEW = r"""### 5.7 What is genuinely new, and what is only an analogy

We separate the methodological claims from the implementation so that neither is
overstated. **Implemented and executable**: machine-issued falsifiability certificates
for eight instruments; a typed claim record whose `WITHDRAWN` status is produced by a
rank test; capability-gated compilation with five forbidden keys and a human-gated
linker; a realisation-path invariance test with two unseen seeds; parity, agreement,
distributional and response-surface diagnostics derived from frozen artefacts; and a
Canvas-rendered, interactive process flow diagram whose red traces encode withdrawn
channels. **Analogy, not a new theory of computation**: the mapping from claims to typed
records and from promotion to linking is borrowed from protection systems [39]; it is
useful because it makes the authority boundary explicit and testable, not because
scientific claims are literally programs. **Deliberately not claimed**: a composite
falsifiability score (we report three axes separately), a proof that our certificate
schema is complete, prospective plant validation, or bit-level reproduction of the
original MATLAB simulator.

The most transferable idea is that **a green dashboard is a hypothesis, not a
certificate**. The four invalidated instruments were all cheap, quantitative,
internally consistent and completely uninformative. Replacing them required no new
physics - only a counterfactual control and the discipline to keep the failing result.

### 5.8 How to falsify this paper

A framework that demands falsifiability should specify how it can itself be refuted.
Four experiments would do so. (i) Apply the certificate battery to a second, independent
process with genuinely held-out batches; if zero instruments are invalidated there, our
claim that tautological metrics are a systemic risk is weakened. (ii) Add
compartment-resolved measurements (e.g. image-based morphology) so that nullity(H)
falls; if compartment states then become estimable, our `WITHDRAWN` certificates were
correctly conditional on H and must be reissued. (iii) Collect prospectively measured
plant data and test whether the L0 anchor transfers without per-batch calibration; we
predict it will not, which is precisely why we do not claim predictive accuracy.
(iv) Re-run `tools/r167_platform_gate.py` and `paper/check_manuscript.py` against the
deposited bundle; if the 25/25 gate or the numerical cross-checks fail, the executable
evidence claim is false. We regard (iii) as the most important and the most likely to
change the conclusions.

> **Box 2. Minimal falsifiability certificate schema (machine-issued)**
>
> ```
> FC(M) = {
>   id, instrument,
>   control_separation : [0,1],   # |M(fitted) - M(zero-info)|, or defect-detection rate
>   output_degeneracy  : [0,1],   # normalised Shannon entropy of the output distribution
>   detection_power    : [0,1],   # Youden J, or defect-detection rate
>   verdict            : CERTIFIED | TAUTOLOGICAL | CONSTANT | SATURATED,
>   evidence           : immutable artefact path
> }
> ```
>
> Quarantine rule: `control_separation == 0` OR `output_degeneracy == 0` OR (a confusion
> table exists AND `detection_power <= 0`). A quarantined instrument must name a
> replacement; the failing certificate is retained in the archive. Certificates are
> regenerated from `runs/` by `paper/make_extended_stats.py` and are never edited by hand.

"""

SEC_6_ADD = r"""**Naive baselines are not like-for-like competitors.** The five reference predictors in
Table 7 have strictly less information than L0, and Section 4.8 reports them to bound the
difficulty of the target series, not to rank methods. The 96.82-97.66% reductions must be
read with the information-set column.

**Distributional tests are underpowered for fault batches.** Only two of 86 batches carry
a `fault` label, so the Mann-Whitney comparison (p = 0.1073) is reported for completeness
and cannot support a claim about fault-specific behaviour.

**Two criteria are not independent.** The health classifier and the validity criterion are
perfectly collinear on this dataset (phi = 1.0). They are counted once, not twice, in the
evidence inventory.

**The certificate schema is a minimal instrument, not a complete theory.** Three axes
detect degeneracy, saturation and lack of contrast; they do not detect every possible
form of metric leakage. We report them separately to avoid hiding a failure behind an
aggregate score.

**The process flow diagram is schematic.** Fig. 12 is a Canvas-rendered teaching and
evidence map of the benchmark, not a piping and instrumentation diagram, a control
narrative or a GMP document.

**The HTML/PDF delivery is a rendering of the same manuscript.** It adds no experimental
evidence; all three formats are generated from `manuscript.md` and the same frozen
artefacts, and any discrepancy between them is a rendering defect, not a new result.

"""

NEW_CONCLUSION = r"""We asked which claims about a bioprocess digital twin survive once the unfalsifiable
ones are removed. The answer required auditing not only the model but the entire
claim-producing apparatus. On an 86-batch industrial-scale penicillin simulation
benchmark, a frozen baseline achieved 2.3448% yield RMSE with 86/86 batches within +/-5%
and byte-identical regression - a number that extended validation places in context
(2.22% of median yield, unbiased and serially unstructured errors, Bland-Altman limits
-4.69% / +4.55%) while making clear that it measures reconstruction consistency, not
prospective prediction.

Four of eight acceptance instruments were then invalidated by counterfactual
certificates, and a fifth finding showed that two apparently independent criteria are
perfectly collinear because they share a pH-guard signal. We issued epistemic boundary
certificates for structurally unidentifiable states and discontinuous control, closed the
gradient path for continuous regulation, and produced a pre-registered NO_GO for
disturbance-variance injection when a tuned scale failed a realisation-path invariance
test on an unseen seed. The surviving evidence is smaller but defensible: cross-validated
biomass and viscosity soft sensors, a five-channel health assessment that resolves
77/5/4 batches, an explicit-failure estimator chain, 147 machine-readable evidence
files, and a runtime-verified platform with 14 capabilities and 12 operators.

The general lesson is that credibility in scientific digital twins is a property of the
*evidence apparatus*, not of the headline error. Accuracy is necessary; falsifiability is
what makes it meaningful; authority to promote a change is a separate decision altogether.
We propose a four-layer architecture, machine-issued instrument certificates, typed
epistemic boundaries, a nine-item transferable checklist and a governance spine that
preserves negative results as first-class artefacts. Future work should test the
framework on a second independent process and, ultimately, on prospectively collected
plant data with compartment-resolved measurements - the two additions that would
genuinely change the observation operator and the scope of every claim in this paper.

"""

NEW_REFS = r"""
34. Shannon CE. A mathematical theory of communication. *Bell System Technical Journal*. 1948;27(3):379-423; 27(4):623-656.
35. Bland JM, Altman DG. Statistical methods for assessing agreement between two methods of clinical measurement. *The Lancet*. 1986;327(8476):307-310. doi:10.1016/S0140-6736(86)90837-8.
36. Shapiro SS, Wilk MB. An analysis of variance test for normality (complete samples). *Biometrika*. 1965;52(3-4):591-611. doi:10.1093/biomet/52.3-4.591.
37. Wald A, Wolfowitz J. On a test whether two samples are from the same population. *Annals of Mathematical Statistics*. 1940;11(2):147-162.
38. Mann HB, Whitney DR. On a test of whether one of two random variables is stochastically larger than the other. *Annals of Mathematical Statistics*. 1947;18(1):50-60.
39. Saltzer JH, Schroeder MD. The protection of information in computer systems. *Proceedings of the IEEE*. 1975;63(9):1278-1308.
"""

REPRO_OLD = r"""python -m pip install -r requirements.txt
python platform/export_data.py
python tools/r167_platform_gate.py       # starts 8771, stops automatically
python tools/r167_final_check.py
python paper/make_figures.py
```"""

REPRO_NEW = r"""python -m pip install -r requirements.txt
python platform/export_data.py
python tools/r167_platform_gate.py       # starts 8771, stops automatically
python tools/r167_final_check.py
python paper/make_extended_stats.py      # derive extended_stats.json from runs/
python paper/make_figures.py             # Figures 1-6, S1-S3
python paper/make_figures_v2.py          # Figures 7-11, S4-S7
python paper/export_pfd.py               # Canvas 2D -> figures/fig12_pfd.png
python paper/build_html.py               # manuscript.md -> manuscript.html
python paper/export_pdf.py               # manuscript.html -> manuscript.pdf
python paper/check_manuscript.py         # cross-format consistency check
```

The manuscript is distributed in three synchronised formats under `paper/`:
`manuscript.md` (source), `manuscript.html` (self-contained styled HTML with the
interactive Canvas 2D process flow diagram, also available standalone as `pfd.html`)
and `manuscript.pdf` (A4 print rendering of the same HTML). The pre-enhancement draft is
retained as `manuscript_v1.md` so that the revision itself is auditable."""


def main():
    with open(MS, "r", encoding="utf-8") as f:
        t = f.read()
    if not os.path.exists(ARCHIVE):
        shutil.copy2(MS, ARCHIVE)

    t = splice(t, "## Abstract\n\n", "\n\n**Keywords:**", NEW_ABSTRACT)
    t = splice(t, "The contributions are fourfold:\n\n",
               "\nAll experiments reported here are", NEW_CONTRIB)
    t = before(t, "---\n\n## 3. Materials and methods", SEC_2_5)
    t = before(t, "### 3.2 Mechanistic model and numerical solution", FIG12_BLOCK)
    t = before(t, "---\n\n## 4. Results", SEC_3_NEW)
    t = before(t, "---\n\n## 5. Discussion", SEC_4_NEW)
    t = before(t, "---\n\n## 6. Limitations", SEC_5_NEW)
    t = before(t, "---\n\n## 7. Conclusion", SEC_6_ADD)
    t = splice(t, "## 7. Conclusion\n\n", "\n---\n\n## Declarations", NEW_CONCLUSION)
    t = rep_once(t, REPRO_OLD, REPRO_NEW)
    t = t.rstrip() + "\n" + NEW_REFS.strip() + "\n"

    # Precision corrections discovered during the evidence inventory
    t = rep_once(t,
                 "a debt ledger with 92 numbered findings (D-2\u2026D-92)",
                 "a debt ledger with 53 distinct numbered findings (D-2\u2026D-92)")
    t = rep_once(t,
                 "a versioned engine contract (v1.97 at the time of writing)",
                 "a versioned engine contract (98 successive v1.x rows, v1.0-v1.97)")
    t = rep_once(t,
                 "a complete audit of a 167-round research programme on the IndPenSim benchmark",
                 "a complete audit of a research programme numbered R1-R167 (36 archived round reports) on the IndPenSim benchmark")
    t = rep_once(t,
                 "**Fig. S3 | Evidence lifecycle across 167 documented rounds (supplementary).**",
                 "**Fig. S3 | Evidence lifecycle across a programme numbered R1-R167 (36 archived round reports; supplementary).**")
    t = rep_once(t,
                 "**Running title:** Evidence-gated bioprocess digital twins",
                 "**Running title:** Counterfactual auditing of bioprocess digital twins")
    t = rep_once(t,
                 "**Keywords:** digital twin; model credibility; verification and validation; structural identifiability; tautological metrics; negative results; penicillin fermentation; reproducible simulation; evidence governance",
                 "**Keywords:** digital twin; falsifiability certificate; counterfactual instrument audit; evidence type system; epistemic boundary certificate; realisation-path invariance; structural identifiability; verification and validation; negative results; penicillin fermentation; reproducible simulation")
    t = rep_once(t,
                 "Figures are generated by `paper/make_figures.py` from those JSON files at 300 dpi.",
                 "Figures are generated by `paper/make_figures.py`, `paper/make_figures_v2.py` and `paper/export_pfd.py` from those JSON files at 300 dpi; the interactive process flow diagram is drawn in native Canvas 2D by `paper/pfd.js`.")
    t = rep_once(t,
                 "**Article type:** Original research article",
                 "**Article type:** Original research article (methods and systems paper)\n\n**Formats:** Markdown / self-contained HTML / A4 PDF, synchronised from this source")
    with open(MS, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    print("PATCHED", MS, len(t), "chars")
    print("ARCHIVED", ARCHIVE)
    print("figures", t.count("!["), "tables", t.count("**Table "),
          "refs", t.count("\n34. Shannon"))


if __name__ == "__main__":
    main()
