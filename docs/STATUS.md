# DevSecOops — build status

## Prompt 1 — Foundation & first executable vertical slice ✅ COMPLETE

Acceptance gates (blueprint p.3), each verified against real execution:

| Gate | Status | Evidence |
|---|---|---|
| A real executable was ingested and run with traceable input/output | ✅ | `run_workflow.py` output; `executions` table |
| Job records survive service restart (durable execution claimed) | ✅ | state in Postgres; `test_report_derives_from_saved_records` re-reads via fresh connection |
| Artifact hash and execution evidence can be inspected | ✅ | SHA-256 content-addressing; `/api/artifacts`, `/api/executions/{id}` |
| Frontend shows actual backend state, not simulated timers | ✅ | `apps/api/static/index.html` reads only `/api/*` |
| Automated tests run with recorded pass/fail results | ✅ | **14 passed** (`pytest`) |
| Dev environment & reproduction commands documented | ✅ | `README.md`, `docs/DEVELOPMENT.md` |

Extra (blueprint "implement now" items):
- ✅ C excess-of-loss CLI with defined input schema (CSV).
- ✅ Source + ground-truth spec in separately-permissioned `evaluation-private/`.
- ✅ Ingestion: validation, size quotas, SHA-256, immutable metadata.
- ✅ Restricted execution captures exit/stdout/stderr/duration/limits/IDs.
- ✅ Isolation test confirms config is *enforced*; provenance test confirms
     reports derive from saved records.

## Prompt 2 — Black-box business-rule archaeology ✅ COMPLETE

The system infers the hidden treaty rule **source-blind** and an independent
harness verifies it. Run: `./.venv/bin/python run_investigation.py`.

| Gate | Status | Evidence |
|---|---|---|
| A previously hidden meaningful financial rule is inferred and evaluated | ✅ | recovers attachment=$100,000.00, limit=$500,000.00, half-up rounding (confidence 1.0) |
| Every displayed inference links to real experiments | ✅ | hypothesis → `supporting_observation_ids` → observations → `ExecutionRecord`; `test_inference_links_to_real_experiments` |
| At least one hypothesis refinement / disambiguating experiment | ✅ | truncation hypothesis refuted by a real sub-cent probe ($100000.006→0.01); recorded as REFUTED |
| Ground-truth isolation is tested, not assumed | ✅ | `test_ground_truth_isolation.py`: evidence allowlist blocks `evaluation-private/`, investigator imports no oracle, runner mounts nothing private |
| Failed guesses and uncertainty remain visible | ✅ | refuted hypothesis persisted; blinded verifier reports the unsampled >$2M region (OOPS-001) as unresolved |

How it works:
- **LIEF** static recon (symbols `dollars_to_cents`/`xol_recovery`, strings
  `claim_id,recovery`) — hints only, never conclusions.
- Batched experiments through the restricted runner (one execution probes many
  inputs): coarse scan → algebraic derivation of attachment/limit/slope →
  cent-level refinement → sub-cent rounding disambiguation. Bounded by a budget
  (4 of 12 executions used).
- **Blinded verifier** (`services/verifier/`) is the *only* component that reads
  the oracle, and only for a SUBMITTED (frozen) hypothesis: precision 1.0 (28/28).
- Model-adapter seam (`agent.py`): with no API key, AI narration is labelled
  **unavailable** and the deterministic baseline runs in full (never faked).

Tests: **25 passing** total (Prompt 1 + Prompt 2).

## Prompt 3 — Offensive financial assurance / the Oops ✅ COMPLETE

Authorized red-team (synthetic artifact only) rediscovers the seeded defect.
Run: `./.venv/bin/python run_redteam.py`.

| Gate | Status | Evidence |
|---|---|---|
| A deliberately seeded issue is discovered through actual testing | ✅ | large-value probes diverge from the inferred rule; OOPS-001 found black-box |
| Evidence reproduces the defect on the legacy executable | ✅ | $30,000,000 claim → legacy `0.00`, re-run deterministically; real isolated `execution_ids` on the finding |
| Independent oracle supports the expected result | ✅ | oracle expects `500000.00`; `test_independent_oracle_supports_expected` |
| UI exposes the Oops and reproduction evidence | ✅ | console Red-team panel: trigger/observed/expected/root-cause/reproduction/regression test |
| No production-target access or unsafe automation | ✅ | every probe runs through the same `--network none` restricted container |

Discipline enforced:
- An Oops is created ONLY when the discrepancy **reproduced** AND the
  **independent oracle supports** the expected value. Benign classes
  (negative/zero, malformed) produced no finding and are recorded as
  unsuccessful attempts.
- Root cause localized black-box: wrong-band lower edge pinned to the cent
  (**$21,574,836.48**), attributed to signed **32-bit cents overflow** (2^31),
  including the double-wrap signature where some huge values are coincidentally
  correct. No over-extrapolation: "$500,000 synthetic under-recovery per
  affected claim," real exposure explicitly out of scope.
- A **permanent regression test** is auto-generated
  (`tests/generated/test_oops_integer_overflow.py`) encoding the correct
  behaviour for Prompt 4 to satisfy.

Tests: **31 passing** total (Prompts 1–3).

## Prompt 4 — Verified financial modernization ✅ COMPLETE

Modern replacement built from the human-approved requirements file, verified on
two independent tracks. Run: `./.venv/bin/python run_modernize.py`.

| Gate | Status | Evidence |
|---|---|---|
| Replacement performs a verified, nontrivial subset | ✅ | 13 boundary/layer/cap cases compatible_and_correct; property-based (200 cases) modern == oracle |
| Differential + independent oracle tests run & store artifacts | ✅ | `comparison_reports` row + `var/reports/<id>.json`; Track A (vs legacy, real execution) + Track B (vs oracle) |
| Seeded defect corrected under approved rules, compat differences not hidden | ✅ | $25M/$30M: modern `500000.00` vs legacy `0.00` → intentionally_corrected / approved_divergence; legacy value recorded |
| Release workflow distinguishes verified / approved / pending / rejected / unresolved | ✅ | `ReleaseStatus`; `test_unapproved_divergence_is_pending` proves the pending path |
| No universal equivalence / decompilation claimed without evidence | ✅ | report `disclaimer`: "not a mathematical proof of equivalence"; verification limited to tested cases |

Design notes:
- The modern service (`services/modern/`, standalone `apps/modern/` + `infra/Dockerfile.modern`)
  is built from `demo/approved-requirements.json` — **policy input**, not the
  oracle and not the legacy binary. Decimal arithmetic, robust validation,
  deterministic output, and a transparent per-claim calculation trace.
- The agent never self-approves: an intentional correction is released as
  `approved_divergence` only when a matching approved entry exists in the policy
  file; otherwise `pending_approval`.

Tests: **41 passing** total (Prompts 1–4), including a Hypothesis property-based
check of modern vs oracle across the supported subset.

## Prompt 5 — The five-minute product reveal ✅ COMPLETE

Next.js (14, TypeScript, Tailwind) + React Flow app in `apps/web/`, telling the
five-act story over the real records the engine produces. One click
(`/api/demo/run`) runs the entire pipeline; every figure is read from stored
records. `next build` compiles clean; verified rendering live against the API.

| Gate | Status | Evidence |
|---|---|---|
| A new developer can reproduce the demo from documented commands | ✅ | README quick start; `npm run build` + `npm start`; `/api/demo/run` |
| Five-minute narrative using real fixtures and actual execution | ✅ | Acts I–V render from `/api/demo/run` (ingest→investigate→verify→red-team→compare) |
| Visible agent activity is backed by records | ✅ | React Flow provenance graph: hypotheses→observations→real executions; footer states "no simulated progress" |
| Reports and UI agree on observations and verification statuses | ✅ | UI, `/report` aggregate, and `var/reports/*.json` all read the same stored records |
| Mobile/tablet responsiveness and accessibility | ✅ (basic) | Tailwind responsive grids, 16px gutters; semantic landmarks, aria-labelled graph, reduced-motion support, dark-contrast palette |

Acts: I Black Box (artifact + LIEF recon) · II Investigation (hypotheses incl.
the refuted one, blinded precision, provenance graph) · III The Oops
(legacy $0.00 vs oracle $500,000.00, reproduction + attempts) · IV–V Rebuild &
Proof (Track A/B table, approved divergence, equivalence disclaimer). Export:
print-to-PDF (print stylesheet) + download evidence JSON.

## Final success definition — MET
Source-blind rule inference on a real executable ✓; an undisclosed seeded defect
discovered and reproduced ✓; an independently verified modern implementation of
the chosen subset ✓; a polished interface showing the whole evidence trail with
no fictional results ✓. Total: **41 automated tests passing**, 5 headless
workflow scripts, Docker/compose/k8s infra.

## Prompt 5 — Product reveal ⏳ NOT STARTED
Next.js + React Flow UI, five-act narrative over real records, exportable report.
