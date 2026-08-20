# Stage 1.5 Semantic Soundness Audit

Date: 2026-08-20 (Asia/Shanghai)

## Scope and claim boundary

This audit treats the repository as a functional prototype, not a proven Stage-1
compiler. It covers only finite synthetic decision-sufficiency semantics, solver
equivalence, repairs, certificates, and independent verification. Real-data parsing,
Oracle experiments, and visual-model work are frozen.

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

## Baseline integrity

- Branch reported by Git: `master`.
- `git rev-parse HEAD`: exit 128; no commit exists in this checkout.
- `git log -5 --oneline`: exit 128; branch has no commits.
- `git status --short`: repository files are untracked.
- The prompt's expected baseline `8f96f8f6b496021d37606e5ddaa936bbaf7f58e7`
  cannot be verified locally. No replacement commit or command output is fabricated.
- Untouched test attempt: `uv run pytest -q`, exit 1 because `uv` was not found on PATH.

## Confirmed semantic defects before implementation

| ID | Severity | Confirmed defect | Required disposition |
|---|---:|---|---|
| S15-001 | P0 | `action_signature` serializes the entire evaluation trace/status | Introduce normalized action-only `decision_signature`; retain trace separately |
| S15-002 | P0 | A lower-priority true rule wins even when a higher-priority rule is unknown | Compute possible actions over feasible completions and respect priority |
| S15-003 | P0 | Python, finite, and Z3 guideline paths implement different semantics | Share one formal action program and prove differential equivalence |
| S15-004 | P0 | Finite states are an unconstrained Cartesian product | Add a versioned feasibility DSL and use it in finite and Z3 paths |
| S15-005 | P0 | Derivations are structural reachability and may read arbitrary output-state values | Require deterministic unary total tables and compute outputs |
| S15-006 | P0 | Operator prerequisites and modalities are not enforced by all solvers | Split and enforce operator/evidence/modality prerequisites |
| S15-007 | P0 | Certificate verifier imports compiler solver/problem helpers | Move verification into `g2lc_verifier` with an enforced import boundary |
| S15-008 | P1 | Certificate 1.0 omits semantic contract, proof scope, assumptions, hashes, objective tuple, and optimality detail | Define schema 1.1 and independently recompute substantive claims |
| S15-009 | P1 | CP-SAT cost coefficients round to 0.001 and do not implement cost/count/lex exactly | Use exact scaled decimals and staged deterministic objectives |
| S15-010 | P1 | Separation promotes a converged feasible master result to OPTIMAL | Preserve solver status and prove optimality before claiming it |
| S15-011 | P1 | Repair cost is the unavailable portion of a total augmented optimum, not a minimum incremental addition | Optimize additions relative to the available base scheme |
| S15-012 | P1 | Large guideline conflict validation silently skips finite validation | Use SMT-backed validation or block production as incomplete |
| S15-013 | P1 | Evidence states accept unknown keys, wrong types, and Python bool/int equality | Validate states against ontology with typed equality |
| S15-014 | P1 | Guideline action objects may omit declared schema keys; dates are unchecked | Enforce exact action keys and ISO dates with explicit synthetic mechanism |

## Evidence protocol

Every repaired issue must first have a minimal focused regression that fails against the
prototype. Machine-readable pre-fix results are stored in
`artifacts/audit/stage1_5/regressions_before.json`; post-fix and differential evidence is
stored beside it. A missing prerequisite or unrun mandatory check makes the final gate
FAIL, never an assumed PASS.

## Residual-risk policy

The final `gate.json` is authoritative. Any unresolved P0/P1 defect, unmet coverage
threshold, unavailable mandatory command, solver mismatch, verifier coupling, failed
tamper case, build failure, or missing artifact results in FAIL. External conditions are
reported distinctly and are never disguised as semantic success.

## Final disposition

All fourteen confirmed in-scope semantic defects have focused regression coverage and
are fixed under ADR-0003. The original ten-test regression slice failed 10/10 before
implementation (exit 1, 0.81 s); the expanded post-fix slice passed 11/11 (exit 0,
0.58 s). The machine records are `regressions_before.json` and
`regressions_after.json` in the Stage-1.5 audit directory.

The portable gate ran these authoritative commands, each with exit code 0:

1. `uv sync --locked --all-groups`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run mypy src tests`
5. `uv run pytest -q --cov=g2lc --cov=g2lc_verifier --cov-branch --cov-report=term-missing --cov-report=json:artifacts/audit/stage1_5/coverage.json --cov-fail-under=90`
6. `uv build`
7. `uv run g2lc synthetic matrix`
8. `uv run g2lc audit stage1-5 --output artifacts/audit/stage1_5/gate.json`

The final run passed 188 tests with zero failures. Whole-project line and branch coverage
were 92.4229% and 85.6073%; core line and branch coverage were 96.2706% and 90.1015%.
All 20 seeded finite exact/brute-force/Z3-separation objective cases agreed, all 66 valid
small schemes had identical finite and Z3 executability, the verifier import boundary
passed, and all 45 rehashed substantive-field mutations across finite and SMT-universal
EXECUTABLE/INCOMPLETE plus OUT_OF_SPEC certificates were rejected. The wheel and source
distribution built successfully. `artifacts/audit/stage1_5/gate.json` therefore records
`PASS`.

## Remaining limitations and external blockers

There are no known unresolved in-scope P0/P1 semantic defects in the tested finite
contract. Known limitations are fail-closed: multi-input derivations are rejected;
independent finite or SMT-universal optimum verification refuses catalogues above 24
candidates; and a large validation query that cannot complete returns non-success rather
than skipping the check. These are boundaries, not claims of broader support.

The requested baseline commit remains unverifiable because this checkout has no Git
`HEAD`. No real clinical data, official production guideline transcription, expert
review, Oracle experiment, metric, checkpoint, or visual model was created or evaluated.
Stage 2 and later work remain frozen.
