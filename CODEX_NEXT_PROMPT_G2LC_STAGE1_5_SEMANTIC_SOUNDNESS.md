# Codex Task — G2LC-DR Stage 1.5 Semantic Soundness, Solver Equivalence, and Independent Certification

You are continuing work in the existing repository:

- repository: `boboji1233/G2LC-DR`
- expected baseline branch: `main`
- reviewed baseline commit: `8f96f8f6b496021d37606e5ddaa936bbaf7f58e7`

The authoritative research specification remains:

- `G2LC_DR_KBS_Research_Plan_CN.md`

Also read completely before changing code:

1. `README.md`
2. `IMPLEMENTATION_PLAN.md`
3. `STATUS.md`
4. `CHANGELOG.md`
5. every ADR under `docs/decisions/`
6. all files under:
   - `src/g2lc/guidelines/`
   - `src/g2lc/ontology/`
   - `src/g2lc/operators/`
   - `src/g2lc/compiler/`
   - `src/g2lc/certificates/`
   - `tests/`
   - `examples/synthetic/`

Read `G2LC_DR_REPO_AUDIT_2026-08-20.md` if it is present in the repository root. Treat its identified semantic risks as hypotheses to reproduce with tests, not as conclusions to copy blindly.

---

## 1. Mission

Repair and harden the Stage-1 compiler so that all of the following implement the **same formally documented decision-sufficiency problem**:

1. Python guideline reference semantics;
2. finite exhaustive problem construction;
3. CP-SAT exact optimization;
4. brute-force oracle;
5. Z3 counterexample oracle;
6. counterexample-separation solver;
7. minimum incremental repair solver;
8. certificate writer;
9. algorithmically independent certificate verifier.

This is a correctness task, not a feature-expansion task.

Do **not**:

- start visual-model code;
- train any model;
- add real experiment numbers;
- fabricate clinical rules, thresholds, labels, costs, or datasets;
- transcribe production guidelines without authoritative sources and review metadata;
- download gated data;
- begin Oracle claims;
- change the core research claim into a network or LLM contribution;
- use destructive Git commands;
- reset, clean, force-checkout, rewrite history, or force-push;
- push or open a PR unless the user separately authorizes it.

Preserve all existing user changes.

---

## 2. Status correction before implementation

The current repository claims the Stage-1 compiler gate is complete. Do not trust that claim.

Before editing implementation code:

1. record:
   ```bash
   git status --short
   git branch --show-current
   git rev-parse HEAD
   git log -5 --oneline
   ```
2. create:
   - `AUDIT_REPORT_STAGE1_5.md`
   - `THEORY_TO_TEST_MATRIX.md`
   - `docs/decisions/0003-formal-decision-semantics.md`
3. update `STATUS.md` to state:
   ```text
   Stage 1 functional prototype exists.
   Stage 1.5 semantic soundness gate is pending.
   Stage 2, Oracle, and visual training are frozen.
   ```
4. do not mark Stage 1.5 complete until every mandatory gate below passes.

For every issue in this prompt:

- first add a minimal failing regression test;
- preserve the failure output in `artifacts/audit/stage1_5/regressions_before.json`;
- then implement the fix;
- rerun the focused test;
- finally rerun the full gate.

Do not weaken tests merely to make them pass.

---

## 3. Freeze one formal decision semantics

Write the formal contract in ADR-0003 before modifying solvers.

### 3.1 Separate clinical decision from execution trace

Introduce two distinct canonical representations:

```python
decision_signature(...)
trace_signature(...)
```

Requirements:

- `decision_signature` contains only the normalized possible clinical action set.
- It must not include:
  - matched clause IDs;
  - unknown clause IDs;
  - provenance;
  - evaluator status labels that do not change the possible action set;
  - diagnostic trace metadata.
- `trace_signature` may include those fields, but it is audit-only.
- All compiler state-pair generation and executability checks must use `decision_signature`.
- Trace sufficiency must not be silently substituted for action sufficiency.

Add a fixture where:

- two different clauses produce the same clinical action;
- one state reaches the action through a clause;
- another reaches the same action through `default_action`.

The minimum decision-sufficient scheme must not be forced to distinguish those states.

### 3.2 Define partial-evidence priority semantics by feasible completions

For a partial evidence state \(s\), define:

```text
PossibleActions(s, g)
  = all actions produced by guideline g
    over all clinically feasible complete states extending s
```

Required behavior:

- one possible action -> `UNIQUE_ACTION`;
- multiple possible actions -> `ACTION_SET`;
- no legal completion or unsupported evidence -> explicit error/status;
- unknown higher-priority rules may not be ignored;
- a lower-priority true rule cannot produce a unique action if a higher-priority unknown rule can produce a different action.

Mandatory regression:

```text
priority 90: nv_presence == present -> urgent
priority 60: hem_presence == present -> refer
state: hem_presence=present, nv_presence=UNKNOWN
expected possible actions: {urgent, refer}
not expected: unique refer
```

The evaluator must report the decision-critical unknown predicates.

### 3.3 Complete-state semantics

For a complete, feasible state:

- evaluate every rule with two-valued truth induced by the complete state;
- select the maximum triggered priority;
- if multiple maximum-priority rules produce different actions, the guideline is semantically conflicting and must be rejected before compilation;
- if they produce the same action, deduplicate the action;
- if no rule fires, use `default_action` only when present;
- otherwise return an explicit no-action/underspecified status.

### 3.4 Action schema

Every action must contain exactly the declared `action_schema` keys, unless ADR-0003 explicitly defines optional keys with a separate schema mechanism.

Do not accept a silent subset of required action dimensions.

---

## 4. Strict evidence typing and state validation

Implement an ontology-owned state validator.

It must check:

- every state key exists in the ontology;
- every known value belongs to the predicate domain;
- type identity is preserved;
- `True` is not equal to integer `1`;
- `False` is not equal to integer `0`;
- numeric predicates reject booleans;
- missing/`None` remains unknown;
- duplicate or malformed values are rejected at the input boundary.

Use typed scalar identity, for example:

```python
(type(value).__name__, value)
```

or a domain-index representation, not Python's loose equality alone.

Apply the same typed domain encoding in:

- Python evaluation;
- finite enumeration;
- observation mappings;
- Z3 encoding;
- certificate verification.

Add tests for bool/int collision, out-of-domain state values, unknown keys, and numeric booleans.

Validate:

- production `effective_date` as ISO-8601 date;
- synthetic fixtures may use an explicit `synthetic_effective_date` mechanism rather than an invalid date string;
- provenance versions and source fields;
- URL shape when a URL is provided.

---

## 5. Add clinically feasible-state constraints

The compiler must not use the unconstrained Cartesian product as its scientific state space.

### 5.1 Constraint language

Add a versioned, typed feasibility-constraint schema. At minimum support:

- implication;
- mutual exclusion;
- conditional allowed values;
- exactly-one;
- at-most-one;
- equality to a deterministic derived value;
- parent-child consistency.

Example conceptual forms:

```yaml
- id: absent_nv_has_zero_nvd_nve
  kind: implication
  if: {eq: [nv_presence, absent]}
  then:
    all:
      - {eq: [nvd_presence, absent]}
      - {eq: [nve_presence, absent]}
```

Do not fabricate real DR constraints in production directories. Use explicitly synthetic fixtures.

### 5.2 One implementation contract

A constraint must have:

- Python reference evaluation;
- finite-state filtering;
- Z3 translation;
- source/version/provenance;
- unit tests;
- differential tests.

### 5.3 Relevant predicate closure

Finite enumeration should use only:

- predicates referenced by target guideline decisions;
- transitive prerequisites;
- deterministic derivation inputs/outputs;
- predicates referenced by feasibility constraints that can affect them.

Do not multiply the state space by unrelated ontology predicates.

### 5.4 Mandatory fixtures

Add synthetic fixtures proving:

1. an impossible state would create a false counterexample without constraints;
2. the constrained finite solver excludes it;
3. Z3 excludes the same state;
4. Python and Z3 enumerate/recognize the same feasible states.

---

## 6. Make derivation semantics executable and sound

The current input/output-only derivation edge is insufficient because it does not define output values.

Implement one sound design and document it in an ADR.

### Preferred Stage-1.5 design

Use finite deterministic mapping rules:

```yaml
- id: count_bin_to_presence
  inputs: [hem_count_bin]
  outputs: [hem_presence]
  table:
    - when: {hem_count_bin: "0"}
      then: {hem_presence: absent}
    - when: {hem_count_bin: "1_3"}
      then: {hem_presence: present}
    - when: {hem_count_bin: "4_plus"}
      then: {hem_presence: present}
```

Requirements:

- the table is total over the input domain;
- the table is deterministic;
- outputs are in-domain;
- overlapping rows with different outputs are rejected;
- derivation cycles are rejected;
- complete feasible states are consistent with deterministic mappings;
- observation closure computes mapped output values;
- it may not reveal an arbitrary output value stored independently in the state.

If general multi-input mappings are implemented, they must have a total finite truth table and full Python/Z3 parity.

If general multi-input mappings cannot be implemented soundly in this session:

- explicitly restrict schema version 1.1 to unary deterministic mappings;
- reject multi-input rules;
- state the limitation in ADR, README, and certificate assumptions.

Do not retain an unsound generic structural closure.

---

## 7. Formalize annotation-operator prerequisites

The current `prerequisites` field is ambiguous.

Choose and enforce one typed design, preferably separating:

```text
required_operator_ids
required_evidence_conditions
required_modalities
```

Rules:

- operator prerequisites must be enforced by exact, greedy, separation, repair, and verifier;
- selecting an operator automatically requires its operator dependencies;
- evidence-condition prerequisites affect case-level applicability and must not be misused as global operator dependencies;
- modality scope must be validated against each output;
- unavailable or license-blocked prerequisites make the scheme infeasible or repairable, not silently selectable;
- `derivable_outputs` must not bypass the derivation semantics.

Add tests for:

- required operator not selected;
- transitive prerequisites;
- prerequisite cycle;
- unavailable prerequisite;
- modality mismatch;
- case-level condition unknown;
- removal of the `derivable_outputs` shortcut.

---

## 8. Repair the exact optimization formulation

### 8.1 Action-only pair universe

Construct required state pairs using `decision_signature` over complete feasible states.

### 8.2 Joint observation semantics

The exact solver must evaluate the information available from the **selected operator set**, not only the union of state pairs separated by individual operators when derivation synergy is possible.

Choose one of:

#### Option A — restricted unary derivations

If all derivations are unary deterministic mappings, prove/test that per-operator closure preserves the weighted test-cover formulation.

The validator must reject any rule that violates the restriction.

#### Option B — explicit observability CP-SAT

Model:

- operator-selection variables;
- direct observation-channel variables;
- derivation activation variables;
- observed/derived predicate variables;
- prerequisite implications;
- pair-separation constraints based on active observation channels.

Do not claim general exactness without one of these sound formulations.

### 8.3 Exact objective

Replace implicit float-to-0.001 rounding with a declared exact objective representation:

- Decimal string plus declared scale; or
- integer cost units in source schemas.

Use hierarchical optimization:

1. minimum weighted cost;
2. minimum operator count;
3. deterministic lexicographic operator-ID tie-break.

CP-SAT and brute force must optimize exactly the same tuple.

Add tests for:

- costs differing below 0.001;
- equal cost, different counts;
- equal cost and count, lexicographic tie;
- zero-cost operators;
- instability weight;
- deterministic repeated solutions.

### 8.4 Solver status

Never convert `FEASIBLE` to `OPTIMAL`.

A certificate may claim optimality only if the relevant solver and verification method establish it.

---

## 9. Make all solver paths mathematically equivalent

Create a reusable formal semantics layer that all solvers target.

Mandatory small-problem differential suite:

- generate random finite ontologies;
- generate random valid, conflict-free guidelines;
- generate random valid operators and deterministic derivations;
- generate random feasibility constraints;
- keep sizes small enough for exhaustive checking.

For each generated problem, compare:

```text
Python exhaustive optimum
CP-SAT exact optimum
Z3 counterexample executability
counterexample-separation optimum
independent verifier result
```

Required equality:

- same feasible state set;
- same decision signatures;
- same executable/non-executable classification;
- same exact objective tuple for exact methods;
- same selected operator set under deterministic tie-break.

Store minimized failing examples under:

```text
tests/fixtures/regressions/
```

Do not use Hypothesis only to rerun one static fixture with irrelevant random integers.

---

## 10. Correct minimum incremental repair

Define repair as:

```text
Given the current available evidence capability,
find the minimum incremental unavailable/blocked operator additions
that make the guideline family executable.
```

Requirements:

- current available operators are fixed as already available or have zero incremental acquisition cost;
- optimize only incremental additions;
- use the same exact cost/instability objective;
- honor prerequisites;
- additions plus current available set must independently verify as executable;
- report exact minimum incremental cost;
- report all tied minimal repairs when tractable, or a deterministic one plus tie metadata;
- `missing_predicates` must be a verified explanatory set, not merely the union of all predicates that differ in uncovered pairs.

Add a fixture where re-optimizing total cost would choose a different repair than minimizing incremental cost.

---

## 11. Build an algorithmically independent verifier

Create an independent verification package boundary, for example:

```text
src/g2lc_verifier/
```

or another clearly isolated package.

### 11.1 Dependency rule

The independent verifier must not import:

```text
g2lc.compiler.*
g2lc.certificates.writer
solver result constructors
compiler coverage helpers
```

It may import immutable schemas only if the ADR explains why this does not share the algorithm under verification.

Add an automated import-boundary test that fails if the verifier imports forbidden modules.

### 11.2 Independent checks

For an `EXECUTABLE` certificate, recompute:

- source hashes;
- semantic hashes;
- project ID;
- exact selected operator list and uniqueness;
- prerequisite closure;
- derived evidence closure;
- cost objective tuple;
- decision executability;
- claimed proof method;
- claimed optimality only when independently established;
- guideline/action coverage fields.

For `INCOMPLETE`, recompute:

- that all currently available operators are insufficient;
- every provided counterexample;
- observational equality;
- decision inequality;
- missing evidence explanation;
- minimum incremental repair;
- repair cost.

For `OUT_OF_SPEC`, recompute and compare full findings:

- predicate ID;
- reason code;
- required modality;
- source clauses;
- ontology/modality scope.

### 11.3 Certificate terminology

Document clearly:

- `certificate_hash` is a deterministic content checksum;
- it does not authenticate an author or trusted clinical authority;
- provenance authenticity requires an external signing/trust mechanism and is outside this version unless implemented separately.

---

## 12. Certificate schema 1.1

Introduce a backward-compatible reader if practical, but write new certificates as schema `1.1`.

Recommended fields:

```text
certificate_type
semantic_contract_version
proof_method
proof_scope
assumptions
feasibility_constraint_hash
decision_semantics_hash
selected_operator_ids
operator_prerequisite_closure
action_programs_covered
action_distinction_count
objective_tuple
optimality_claimed
optimality_verified
source_hashes
content_checksum
```

Remove or rename `clauses_covered` unless clause-trace sufficiency is separately proven.

Do not enumerate the complete finite state space merely to write an SMT/separation certificate.

### Mandatory rehashed tamper matrix

For every substantive field:

1. modify the field;
2. recompute the outer content checksum;
3. verify that semantic verification still rejects it.

Include at least:

- selected operators;
- cost;
- guideline hash;
- ontology hash;
- derivation hash;
- feasibility-constraint hash;
- action coverage;
- OOS reason/modalities/source clauses;
- missing predicates;
- repair additions;
- repair cost;
- proof method;
- optimality flag;
- counterexample state;
- counterexample action.

---

## 13. Guideline validation hardening

Implement SMT-backed validation for all production-size guideline bundles.

Detect:

- same-priority different-action conflicts;
- unreachable/dead rules;
- duplicate semantic rules;
- missing default/no-action regions;
- invalid action schemas;
- invalid predicates/types;
- unsupported evidence;
- priority-shadowed clauses;
- inconsistent feasibility constraints.

Do not silently skip conflict checking when a finite state threshold is exceeded.

If validation cannot be completed within a configured limit, return a non-successful `VALIDATION_INCOMPLETE` result and prohibit compilation of source-verified/clinician-reviewed guidelines.

Synthetic fixtures may remain small and exhaustive.

---

## 14. Required regression fixtures

Add at least these fixtures, all explicitly synthetic:

1. `priority_unknown_blocks_lower_action`
2. `same_action_different_clause`
3. `default_same_action_as_rule`
4. `typed_bool_int_collision`
5. `infeasible_state_false_counterexample`
6. `deterministic_derivation_mapping`
7. `derivation_inconsistent_state_rejected`
8. `two_operator_synergy` if multi-input derivation remains supported
9. `operator_prerequisite_chain`
10. `unavailable_prerequisite_repair`
11. `modality_mismatch`
12. `submill_cost_ordering`
13. `equal_cost_lexicographic_tie`
14. `incremental_repair_differs_from_total_reopt`
15. `same_priority_conflict_large_space`
16. `rehashed_certificate_tamper_matrix`
17. `symbolic_certificate_does_not_enumerate`
18. `verifier_import_boundary`

Every fixture needs:

- expected semantic outcome;
- expected exact objective;
- expected certificate type;
- source provenance marked `SYNTHETIC`;
- a focused test.

---

## 15. Quality gates

### 15.1 Make targets

Add:

```text
make stage1-gate
make stage1-5-gate
make review-bundle
```

`stage1-5-gate` must run at least:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q \
  --cov=g2lc \
  --cov=g2lc_verifier \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:artifacts/audit/stage1_5/coverage.json \
  --cov-fail-under=90
uv build
uv run g2lc synthetic matrix
uv run g2lc audit stage1-5 --output artifacts/audit/stage1_5/gate.json
```

If `make` is unavailable on Windows, also provide a portable Python entry point:

```bash
uv run python scripts/stage1_5_gate.py
```

The Make target and Python entry point must execute the same command plan.

### 15.2 Coverage

- enable branch coverage;
- do not exclude the entire data package merely to increase the percentage;
- report:
  - whole-package line coverage;
  - whole-package branch coverage;
  - core semantic module line/branch coverage;
- require at least:
  - 90% whole-package line coverage;
  - 85% whole-package branch coverage;
  - 95% line and 90% branch coverage for guidelines/compiler/certificate semantics.

If these thresholds are temporarily unattainable, the gate must remain FAIL rather than lowering them without an ADR.

### 15.3 Machine-readable gate artifact

Create:

```text
artifacts/audit/stage1_5/gate.json
```

It must include:

```text
git_commit
dirty_worktree
python_version
uv_version
dependency_lock_hash
commands
exit_codes
test_count
failed_test_count
line_coverage
branch_coverage
core_line_coverage
core_branch_coverage
fixture_hashes
finite_vs_bruteforce_results
finite_vs_z3_results
exact_vs_separation_results
verifier_independence_check
tamper_matrix_results
package_build_result
final_status
```

The final status must be one of:

```text
PASS
FAIL
BLOCKED_EXTERNAL
```

Internal code defects are `FAIL`, not `BLOCKED_EXTERNAL`.

### 15.4 CI

Update GitHub Actions to:

- run the portable Stage-1.5 gate;
- build the wheel/sdist;
- upload `artifacts/audit/stage1_5/` even on failure;
- show branch coverage;
- run on Python 3.11 and 3.12 if dependencies support both;
- use locked dependencies.

Do not claim CI passed unless the actual workflow run is green.

---

## 16. Documentation updates

Update:

- `README.md`
- `STATUS.md`
- `CHANGELOG.md`
- `IMPLEMENTATION_PLAN.md`
- `docs/claim_contract.md`
- `docs/runbook.md`
- ADR-0003
- any schema reference docs

Required wording:

```text
Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.
```

Do not claim:

- arbitrary future guideline support;
- clinical validity;
- clinical deployment readiness;
- expert-validated production rules;
- cryptographic authorship;
- general optimality beyond the verified proof scope.

---

## 17. Review bundle

Before stopping, generate a privacy-safe bundle:

```text
artifacts/review/G2LC_DR_STAGE1_5_REVIEW_<short_commit>.zip
artifacts/review/G2LC_DR_STAGE1_5_REVIEW_<short_commit>.sha256
artifacts/review/G2LC_DR_STAGE1_5_REVIEW_<short_commit>_manifest.tsv
```

Include:

- source code;
- tests;
- synthetic fixtures;
- schemas;
- CI and Makefile;
- ADRs;
- audit report;
- theory-to-test matrix;
- gate JSON;
- coverage JSON;
- command logs;
- package build metadata.

Exclude:

- `.git/`;
- virtual environments;
- caches;
- secrets;
- raw/interim/processed medical data;
- restricted labels;
- checkpoints;
- large generated binaries unrelated to review.

---

## 18. Stopping rule

Do not stop after writing plans.

Continue until one of these is true:

### PASS

All mandatory Stage-1.5 gates pass.

### FAIL with useful progress

A reproducible internal defect remains. In that case:

- leave final gate status `FAIL`;
- fix the highest-severity defect possible;
- preserve its failing test;
- report the smallest remaining blocker;
- do not begin Stage 2.

### BLOCKED_EXTERNAL

Use only when an external service/toolchain prevents execution and no repository code change can resolve it. Real medical data is not needed for this Stage-1.5 task, so lack of datasets is not a valid blocker.

---

## 19. Final response requirements

Before ending the Codex session, report exactly:

1. baseline commit and final local commit/worktree state;
2. files changed;
3. formal semantic decisions made;
4. defects reproduced;
5. defects fixed;
6. exact commands and exit codes;
7. test count and failures;
8. line and branch coverage;
9. randomized differential-test count;
10. exact-vs-brute-force-vs-separation equivalence result;
11. certificate tamper matrix result;
12. verifier import-boundary result;
13. package build result;
14. gate JSON path and final status;
15. review bundle path and SHA-256;
16. unresolved issues;
17. whether Stage 2 remained frozen;
18. the single next dependency-satisfied task.

Never report a command as passed unless it was actually executed and returned success.
