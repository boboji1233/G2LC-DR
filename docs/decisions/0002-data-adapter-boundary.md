# ADR-0002: Metadata-only adapter boundary before legal source files exist

- Status: Accepted
- Date: 2026-08-20
- Plan references: A-02/A-03, §6, §8, F-01

## Context

Stage 1 passed, so metadata-only adapter scaffolding is permitted. No real dataset or
official source label table is present. Guessing column names or deriving labels from
filenames would violate the provenance and no-fabrication constraints.

## Decision

1. Adapters require a user-supplied local directory and never perform network access.
2. The first adapter layer scans image metadata, computes byte hashes when materialized,
   and writes a unified Parquet manifest. Every clinical label remains `UNKNOWN` until
   a dataset-specific source-table parser is verified against legally supplied files.
3. Dataset identity facts are limited to the research plan: DDR and MMRDR-CFP use
   `OIA_DDR`; Retinal-Lesions uses `EYEPACS_RLDR`; MAPLES/MESSIDOR is test locked;
   MESSIDOR-2 is not an acceptable substitute. Only IDRiD/DeepDRiD layout paths stated
   in the plan are enforced; unverified archive layouts are not invented.
4. A dry run does not write a manifest or require a license-confirmation flag. Writing
   requires an explicit `--license-confirmed` acknowledgement.
5. Split locks hash sorted patient assignments and source-family metadata. MAPLES cases
   may only be assigned to `test`. Changing an existing lock fails unless a dangerous
   override and reason are supplied, in which case an append-only JSONL audit event is
   written.

## Consequences

- Local file inventory and leakage safeguards are executable now.
- Source clinical labels are preserved by omission rather than misinterpreted: their
  parsers remain blocked until real official files can be inspected and tested.
- Dataset adapter completion and experiment infrastructure cannot be claimed yet.

