# ADR-0003: Formal action-only decision-sufficiency semantics

- Status: Accepted; verification status is machine-recorded by the Stage-1.5 gate
- Date: 2026-08-20

## Context

The functional prototype compared serialized evaluator results. Those results include
matched-clause and unknown-clause traces, so two evidence states that imply exactly the
same clinical action could still create a compiler separation obligation. The finite and
symbolic evaluators also disagreed on unknown higher-priority rules, feasibility,
derivations, prerequisites, and objective precision.

## Decision

### Decision and trace signatures

`decision_signature` is the canonical JSON encoding of only the normalized set of
possible action objects. Action objects have exactly the guideline's declared action
schema. Duplicates are removed and the remaining actions are sorted canonically.
Evaluation status, matched rules, unknown rules, and diagnostic reasons are excluded.

`trace_signature` is a separate audit-only encoding. It must never be used to construct
state pairs, coverage constraints, solver objectives, repair obligations, executability
claims, or certificate action-distinction counts.

### Complete and partial guideline evaluation

For a feasible complete state, rules are evaluated by descending priority. The first
priority containing true rules determines the result. Equal-priority true rules with the
same normalized action are deduplicated. Equal-priority true rules with different actions
are an invalid guideline. If no rule is true, the declared default action is used; absent
default means the explicit empty action set.

For a partial state, `PossibleActions` is the union of complete-state decision results
over every feasible completion consistent with the known evidence. Therefore a true
lower-priority rule does not erase a possible higher-priority action whose condition is
unknown. No feasible completion yields an out-of-specification/invalid-state result;
zero feasible completions is not silently interpreted as a default action.

### Typed states and feasibility

Every state boundary validates known predicate IDs and exact domain membership with
booleans distinct from integers. `None` alone denotes unknown. The finite universe and
Z3 universe are restricted by the same versioned feasibility contract. The supported
Stage 1.5 primitives are implication, mutual exclusion, conditional allowed values,
exactly-one, at-most-one, derived equality, and parent-child constraints. Relevant-state
construction includes transitive predicates referenced by those constraints.

### Derivations and operators

Stage 1.5 admits only deterministic unary derivations represented by total input/output
value tables. A derived output is computed from its source value; an arbitrary stored
output value cannot influence observation equality. Multi-input derivations are rejected
until an equivalently sound finite and SMT encoding exists.

Operator prerequisites are split into required operator IDs, required evidence
conditions, and required modalities. Cycles, unavailable required operators, unsatisfied
evidence conditions, and missing modalities make a scheme invalid. The former
`derivable_outputs` shortcut is not evidence of a derivation.

### Optimization and repairs

Costs are parsed as exact decimal quantities and converted to a lossless common integer
scale for CP-SAT. Exact schemes are ordered lexicographically by total cost, selected
operator count, and sorted operator-ID tuple. A solver may claim OPTIMAL only when that
ordering is proven. Repair minimizes incremental unavailable additions relative to the
available base scheme and reports incremental cost, not total scheme cost.

### Certificates and verification

Certificate schema 1.1 records the semantic contract, proof scope, assumptions,
feasibility and decision-program hashes, operator closure, action-distinction count,
objective tuple, explicit optimality flags, authoritative source hashes, and a canonical
content checksum. The independent `g2lc_verifier` package may parse source formats but
must not import compiler solvers, compiler problem/result helpers, or certificate writer
helpers. It independently recomputes EXECUTABLE, INCOMPLETE, and OUT_OF_SPEC claims.

Symbolic proof scope does not require finite-state enumeration. A certificate must state
whether proof is finite exhaustive, SMT universal, or bounded/incomplete.

## Consequences

- Existing 1.0 certificates are historical prototype artifacts and do not pass the
  Stage 1.5 gate.
- Any semantic mismatch among Python, finite CP-SAT, brute force, Z3 separation, repair,
  and independent verification fails the gate.
- Large-bundle validation that cannot finish is explicitly incomplete and blocks a
  production claim.
- Stage 2, Oracle experiments, real-data parsing, and visual training remain frozen until
  the Stage 1.5 gate passes.

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

The current checkout's gate records `PASS`; because this Git repository has no `HEAD`,
the evidence is bound to the recorded dirty worktree, source/fixture hashes, dependency
lock hash, and review-bundle checksum rather than to a commit identifier.
