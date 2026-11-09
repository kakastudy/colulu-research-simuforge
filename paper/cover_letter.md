# Cover letter (draft)

[Corresponding author name, affiliation, address, email, ORCID]
[Date]

To the Editor,
[Journal Name]

Dear Editor,

We submit our original research article entitled **"Falsifiable bioprocess digital twins: an evidence-gated framework tested on 86 industrial-scale penicillin fed-batches"** for consideration in [Journal Name].

**What we report.** Digital twins in bioprocessing are normally certified by accuracy metrics, but the metrics themselves are rarely tested for falsifiability. Using the publicly released IndPenSim benchmark (100 fed-batch penicillin fermentations, 100,000 L vessel), we ported a 33-state mechanistic model, froze a byte-identical 86-batch regression anchor (end-of-batch product-mass RMSE 2.3448%, 86/86 within ±5%), and then adversarially audited every instrument used to certify the twin. Three acceptance instruments proved unfalsifiable: a residual-quantile interval coverage that returns 0.899548532731377 for both a fitted model and a zero-information constant predictor; a crash classifier that returns `normal` for all 86 batches; and an innovation criterion that flags 84.38% of unperturbed batches as degraded. We replaced them with discriminating instruments, established structural non-identifiability of the mycelial compartment states (rank 0 / nullity 4 of the observation operator), demonstrated that two continuous control knobs produce 99.8–101.5 percentage-point discontinuous responses, and recorded a pre-registered NO_GO for eight-path disturbance-variance injection after a seed-transfer collapse (96.06 pp and 3/6 catastrophic collapses at full amplitude; a tuned scale of 0.35 failing at 99.85 pp on an unseen seed).

**Why this fits [Journal Name].** The manuscript offers (i) an operational, machine-checkable definition of falsifiability for scientific digital twins, (ii) a four-layer governance architecture separating evaluation from authorisation, (iii) a transferable nine-item checklist, and (iv) an executable evidence trail — 25/25 integration gate, 20/20 final consistency check, six browser views, 14 runtime-verified capabilities and 12 operators — that a reviewer can re-run. Beyond process systems engineering, the work speaks to the broader reproducibility and model-credibility debate: it shows, with a concrete industrial-scale benchmark, how a metric-level leakage can manufacture a green dashboard. We believe this methodological generality, combined with a complete negative result rather than a curated success story, will interest the readership of [Journal Name].

**Scope and honesty.** All evidence is in silico; we make no claim of prospective plant validation or GMP qualification. Each validation batch uses its own calibrated parameter vector, so the reported accuracy quantifies reconstruction consistency, not prospective prediction; this qualification appears in the Abstract, Methods, Results and Limitations. Bit-exact reproduction of the original MATLAB simulator is not claimed because its stochastic seed was not recorded. No candidate was promoted into the default production path.

**Declarations.** This work has not been published previously and is not under consideration for publication elsewhere. All named authors have approved the manuscript [to be confirmed before submission]. The authors declare no competing interests [to be confirmed]. All machine-readable evidence, the versioned contract, the debt ledger, the sign-off records, figure-generation scripts and the numerical appendix accompanying the manuscript are reproducible from pinned dependencies; a DOI-issuing repository deposit with an explicit licence will be completed before acceptance and the permanent identifiers inserted into the Data and Code Availability statement. No human participants, animals or regulated process data were involved, so ethical approval was not required.

**Suggested reviewers.** [to be completed by the submitting author; we suggest specialists in (i) bioprocess modelling and IndPenSim, (ii) identifiability / verification-and-validation methodology, and (iii) reproducibility and evaluation-metric design.]

We appreciate your consideration and look forward to your decision.

Yours sincerely,

[Corresponding author]
[on behalf of all authors]
