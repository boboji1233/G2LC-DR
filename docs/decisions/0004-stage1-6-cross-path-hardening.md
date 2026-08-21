# ADR-0004: Stage 1.6 cross-path hardening

Status: Accepted for synthetic Stage 1.6

## Context

Stage 1.5 established action-only decision sufficiency but retained cross-path gaps:
greedy could consume prerequisite capability without selecting it, finite conflict
validation could reason over infeasible states, empty languages could prove claims
vacuously, partial evaluation omitted derivations, and randomized tests varied costs only.

## Decision

1. Every selected scheme is interpreted through one transitive prerequisite closure;
   marginal and final costs charge each newly selected operator once.
2. A decision context consists of ontology feasibility, deterministic unary total
   derivations, target modalities, and a semantic-contract version. Partial evaluation
   rejects an omitted derivation declaration and projects only the transitive
   decision-relevant dependency closure while existentially checking all other fields.
3. The evidence language must contain at least one legal complete state. Unsatisfiable
   languages return `UNSAT_EVIDENCE_LANGUAGE` and cannot emit the three claim certificates.
4. Finite optimization may enumerate the decision-relevant dependency closure. Full
   enumeration remains the oracle and certificate state-count source for bounded problems.
5. Incremental repair is CP-SAT lexicographic optimization. Brute force is an oracle only
   through 18 unavailable operators; the symbolic path fails closed above that bound.
6. Generated semantic tests vary 2–6 Boolean, integer, or categorical predicates, 1–3
   guidelines with priorities/defaults, all seven feasibility kinds, transitive unary
   derivations, prerequisite DAGs, and exact Decimal objectives across all solver paths.
7. Certificates bind a canonical non-vacuity witness and relevant-predicate closure and
   speak of decision programs/action distinctions; clause IDs are provenance only.

## Consequences

Stage 1.6 remains deliberately finite, unary-derivation, and synthetic. Multi-input
derivation, clinical correctness, data availability, visual learnability, and Stage 2
are not implied. A local gate PASS remains conditional on CI and human review for merge.
