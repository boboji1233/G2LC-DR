# ADR-0001: Core compiler architecture and scientific boundaries

- Status: Accepted
- Date: 2026-08-20
- Plan references: §3, §9–§12, C-01–C-04, D-01–D-05, P0

## Context

The first executable stage must reverse-compile a finite, declared evidence
language into a minimum-cost annotation scheme. It must distinguish incomplete
operator availability from evidence that a CFP-only system cannot observe, and
must never interpret absent evidence as negative.

## Decision

1. Pydantic v2 models are the validation boundary for YAML/JSON inputs. Loaders
   preserve the source path and wrap parsing/model errors with actionable context.
2. Evidence domains are finite for Stage 1. Complete states are enumerated for the
   small exact formulation. Missing values are used by case evaluation but are not
   silently introduced into the compiler's clinically feasible complete states.
3. Guideline expressions use strong Kleene three-valued logic. Priority resolves
   rules only after expression evaluation; unknown conditions cannot fire as false.
4. An annotation operator observes either an identity predicate value or an
   explicitly declared finite partition. This represents presence versus count-bin
   labels without pretending one has the other's information.
5. Derivations form a validated DAG. Compiler observation signatures use its
   transitive closure, while total count never implies a spatial distribution unless
   an explicit rule declares it.
6. Small exact compilation constructs the action-separating state-pair universe and
   solves weighted test cover with CP-SAT. A brute-force implementation is retained
   solely as an independent small-fixture oracle.
7. The scalable exact path uses a restricted CP-SAT master and a Z3 separation
   oracle. The greedy path is deterministic and reports no optimality claim.
8. Certificates contain canonical input hashes and no wall-clock timestamp, so the
   same inputs and seed serialize identically. Verification re-loads source files,
   checks hashes, checks selected-operator executability, and brute-forces optimality
   when the declared finite problem is small enough.
9. `INCOMPLETE` means the modality/evidence language is in scope but currently
   available operators are insufficient. Unavailable catalogue operators may be
   considered only for a repair recommendation. `OUT_OF_SPEC` means an unknown or
   modality-incompatible predicate, never a forced prediction.
10. All first-run thresholds and costs live only under `examples/synthetic` and carry
    synthetic provenance. No production clinical guideline is inferred from them.

## Consequences

- The first slice is executable and auditable without medical images.
- Finite enumeration is intentionally limited; Z3 separation is the scaling route.
- Certificate verification is computationally independent for small fixtures, but
  does not claim a proof object for arbitrary infinite/numeric evidence languages.
- Real-data adapters and visual models remain gated by Stage 1 and Oracle acceptance.

