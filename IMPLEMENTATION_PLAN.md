# G2LC-DR Implementation Plan

This plan is subordinate to `G2LC_DR_KBS_Research_Plan_CN.md` (v1.0). Task IDs and
section numbers below refer to that document. A task is complete only after its
listed acceptance checks pass.

## Scientific guardrails

- The core contribution is guideline-to-label reverse compilation (§0–§4).
- Evidence is explicitly three-valued; `UNKNOWN` is never a negative (§8.2, §9.6).
- Only declared image-observable evidence is executable; unsupported evidence is
  `OUT_OF_SPEC` (§9.2, §11.7, P6).
- Every guideline clause requires source, version, provenance, and review status
  (§3.2, §9.5). Synthetic rules are permanently labelled synthetic.
- MAPLES/MESSIDOR is locked test data and DDR/MMRDR-CFP share source family
  `OIA_DDR` (§8.6–§8.7, §18.1).
- Oracle gates precede visual-model and real-data experiment work (§13, Gate E).

## Module-to-plan mapping

| Module or artifact | Research-plan task/section | Deliverable and acceptance |
|---|---|---|
| `pyproject.toml`, `uv.lock`, `Makefile`, CI, pre-commit | A-01, §7, WP0 | `uv sync`, ruff, mypy, pytest pass |
| `src/g2lc/types.py`, `errors.py` | C-01, §3, §8.2 | Strict enums, evidence state, actionable errors |
| `src/g2lc/ontology/models.py` | C-01, §9.1–§9.2 | Versioned predicate and provenance schemas |
| `src/g2lc/ontology/loader.py` | C-01, §9.1 | YAML loader with path/context errors |
| `src/g2lc/ontology/validator.py` | C-01, §9.2, §9.6 | Domains, references, parent cycles, modality checks |
| `src/g2lc/ontology/observability.py` | C-01, §9.2, §11.7 | Image-language and modality preflight |
| `src/g2lc/guidelines/ast.py` | C-02, §9.3 | Typed AND/OR/NOT/comparison/Known AST |
| `src/g2lc/guidelines/parser.py` | C-02, §9.3 | Source-friendly YAML DSL parser |
| `src/g2lc/guidelines/trivalued.py` | C-02, §9.6, A09 | Kleene logic with explicit unknown |
| `src/g2lc/guidelines/evaluator.py` | C-02, §3.2, §9.6 | Unique/action-set/insufficient/OOS outcomes |
| `src/g2lc/guidelines/provenance.py` | C-02/C-03, §9.5 | Deterministic clause/source hashing |
| `src/g2lc/guidelines/validator.py` | C-04, §9.6 | Predicate/type/priority/conflict checks |
| `src/g2lc/operators/models.py` | D-01, §10.1–§10.2 | Cost, instability, prerequisites, availability |
| `src/g2lc/operators/lattice.py` | D-02, §10.1, §11.5 | DAG validation and derivation closure |
| `src/g2lc/operators/derivation.py` | D-02, §10.1 | Deterministic operator observation signatures |
| `src/g2lc/operators/cost.py` | D-01, §10.3–§10.4 | Weighted cost without fabricated empirical values |
| `src/g2lc/compiler/problem.py` | D-03, §3, §11 | Project loading, finite feasible states and pairs |
| `src/g2lc/compiler/exact.py` | D-03, §11.1, §11.3, P0 | CP-SAT weighted test-cover; brute-force agreement |
| `src/g2lc/compiler/counterexample.py` | D-03, §11.2, §11.8 | Z3 state-pair separation and iterative master loop |
| `src/g2lc/compiler/greedy.py` | D-04, §11.4 | Deterministic marginal-benefit/cost solver |
| `src/g2lc/compiler/dominance.py` | D-04, §11.5, A08 | Safe dominance detection with cost/stability checks |
| `src/g2lc/compiler/repair.py` | D-05, §3.6, §11.6, A11 | Minimum unavailable-operator repair explanation |
| `src/g2lc/compiler/result.py` | D-03–D-05, §11.3 | Typed deterministic solver results |
| `src/g2lc/certificates/models.py` | D-05, §11.6–§11.8 | EXECUTABLE/INCOMPLETE/OUT_OF_SPEC schemas |
| `src/g2lc/certificates/writer.py` | D-05, §11.8, WP0 | Canonical deterministic JSON and hashes |
| `src/g2lc/certificates/verifier.py` | D-05, §11.8, P0 | Re-load inputs; independently check soundness/optimum |
| `src/g2lc/cli.py` | §7.4, launch objective §11 | Required validation/compile/certificate/synthetic CLI |
| `examples/synthetic/*` | EX00, P0, launch objective §10 | Minimal, missing-evidence, and OOS fixtures |
| `tests/unit`, `tests/guidelines` | C-04, D Gate, §12 | At least 30 focused unit and 10 semantics tests |
| `tests/property` | C-04, D Gate, §12 | At least 10 Hypothesis properties |
| `src/g2lc/data/manifest.py`, `labels.py` | A-03/F-01, §8.1–§8.2 | Typed metadata and POSITIVE/NEGATIVE/UNKNOWN |
| `src/g2lc/data/splits.py` | F-01, §8.7, §18.1 | Patient/source-family locks and MAPLES test lock |
| `src/g2lc/data/dedup.py` | F-01, §8.5–§8.6 | SHA-256 audit first; optional later stages explicit |
| `src/g2lc/data/license_registry.py` | A-02/A-03, §6.3 | Access/license metadata without gated download |
| `src/g2lc/data/adapters/*` | F-01, user objective §14 | Metadata-only adapters after Stage 1 acceptance |
| `src/g2lc/experiments/*`, `metrics/*` | §16, §20–§22 | Non-fabricated schemas after Oracle/data gates |
| `docs/claim_contract.md` | B-02, §1, §4 | Frozen allowed/non-allowed claims |
| `docs/data_access.md`, `data_access_log.md` | A-02, §6 | Official acquisition actions; no auto gated download |
| `docs/runbook.md` | WP0, §27.5 | Exact safe operational procedures |

## Execution order and gates

1. **Stage 1A — governance/tooling (A-01):** repository, dependency lock, CI,
   plans, ADRs. Gate: environment and empty smoke test are runnable.
2. **Stage 1B — knowledge representation (C-01, C-02, D-01, D-02):** strict
   ontology/guideline/operator schemas, three-valued evaluator, derivation DAG.
   Gate C: validation and guideline tests pass.
3. **Stage 1C — compiler/certificates (D-03–D-05, P0):** CP-SAT exact,
   brute force, Z3 separation, greedy, repair, three certificate types, verifier.
   Gate D: fixtures, tamper tests, properties, deterministic output pass.
4. **Stage 1D — interface/docs:** CLI, synthetic demo, README/runbook, CI and
   coverage. Gate: every command in the first-run acceptance block passes.
5. **Stage 2 — data metadata only (A-02/A-03/F-01):** begins only after the
   Stage 1 gate. Missing gated datasets remain `BLOCKED`; no synthetic substitute.
6. **Stage 3 — Oracle (E-01–E-04):** begins only after legal data access and split
   locks. Gate E determines whether any visual model work is scientifically valid.
7. **Later stages F–I:** visual evidence, baselines, experiments and paper outputs
   remain out of scope until preceding gates pass.

## First vertical-slice acceptance

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run g2lc synthetic run --fixture minimal_dr
uv run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json
```

