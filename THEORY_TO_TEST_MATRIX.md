# Stage 1.5 Theory-to-Test Matrix

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

| Contract | Python evaluator | Finite/CP-SAT | Brute force | Z3/separation | Repair | Independent verifier | Focused evidence |
|---|---|---|---|---|---|---|---|
| Action-only signature; trace ignored | required | required | required | required | n/a | recompute | same action/different matched trace |
| Priority under partial evidence | possible-action completions | pair universe | oracle | symbolic action | n/a | recompute | higher unknown vs lower true |
| Complete-state priority/tie/default | required | required | oracle | required | n/a | recompute | same-action dedup; conflicting tie; default |
| Exact action schema and typed equality | required | encoded | oracle | typed indices | n/a | reload/recompute | missing/extra keys; bool vs int |
| Feasibility DSL | filter/validate | feasible states only | same universe | asserted | same universe | independent parser | implication, mutex, cardinality, equality |
| Deterministic unary total derivation | compute table | closure observations | same | encode function | same | independent implementation | arbitrary stored output cannot alter result |
| Operator/evidence/modality prerequisites | validate selection | constraints | same | observations | candidate constraints | recompute | missing operator/evidence/modality; cycles |
| Exact objective `(cost,count,lex)` | n/a | staged CP-SAT | tuple oracle | restricted master | incremental tuple | recompute | sub-milliscale costs; deterministic tie |
| Solver equivalence | reference actions | candidate optimum | oracle optimum | same witness/result | equivalent additions | accepts iff sound | seeded small finite differential suite |
| Certificate 1.1 semantic payload | n/a | writer input | optimum evidence | proof scope | repair evidence | all substantive fields | rehashed tamper matrix |
| Validation completeness | SMT agreement | load blocks incomplete | n/a | validation query | n/a | source reload | large bundle cannot silently skip |

## Required fixture/regression inventory

The machine-readable inventory is
`examples/synthetic/stage1_5/fixture_matrix.yaml`. It records each expected semantic
outcome, exact objective (or explicit non-applicability), certificate outcome,
`SYNTHETIC` provenance, and focused pytest node. `two_operator_synergy` is omitted because
Stage 1.5 rejects multi-input derivations until a sound finite and SMT encoding exists.

The Stage 1.5 suite must cover: trace-only differences; higher-unknown priority; same
priority same action; same-priority action conflict; exact action schema; bool/int typed
states; feasibility implication; mutual exclusion; conditional allowed values; exactly
one; at most one; derived equality; deterministic unary derivation; rejected multi-input
derivation; missing operator prerequisite; evidence prerequisite; modality prerequisite;
sub-0.001 objective ordering; deterministic lexical tie; incremental repair; separation
limit/no false optimality; large-bundle validation; all three certificate outcomes; and a
rehashed substantive-field tamper matrix.

Status is reported by `artifacts/audit/stage1_5/gate.json`; this matrix does not mark a
row complete until the referenced command has run successfully in the current checkout.
The current checkout's gate is `PASS`: 188 tests passed, every coverage threshold was
met, 20 seeded objective comparisons and 66 finite/Z3 scheme comparisons agreed, and all
45 rehashed certificate mutations were rejected.

## Stage 1.6 hardening matrix

| Residual risk | Failing reproduction | Corrected paths | Acceptance evidence |
|---|---|---|---|
| Greedy omits prerequisite/cost | `test_greedy_selects_and_pays_direct_prerequisite` | greedy, dominance, certificate closure | selected closure and exact cost |
| Finite conflict sees impossible overlap | `test_finite_conflict_validation_ignores_infeasible_overlap` | finite and SMT guideline validation | same feasibility/derivation context |
| Empty state space passes vacuously | three `empty_evidence_language` tests | exact, greedy, separation, API, writer, verifier | explicit `UNSAT_EVIDENCE_LANGUAGE` |
| Partial evaluation ignores derivation/context | derivation, fail-loud API, and projection tests | explicit `DecisionContext` and all decision callers | impossible completion excluded; unrelated dimensions existential |
| Full Cartesian state blow-up | relevant projection regression | dependency closure and projected enumeration | exact optimum unchanged |
| Repair brute force cannot scale | repair unit/property tests | CP-SAT plus <=18-operator oracle | fail closed above symbolic bound |
| Cost-only random testing | generated semantic matrix | typed domains, all seven constraints, transitive derivation, finite, brute, CP-SAT, Z3, greedy, verifier | >=200 varied problems, zero mismatch |
| Certificate wording/non-vacuity | rehashed tamper matrix | writer and independent raw verifier | nonempty witness and action distinctions |

The current Stage-1.6 measurements are authoritative only in
`artifacts/audit/stage1_6/gate.json`; this document contains no substituted PASS claim.
