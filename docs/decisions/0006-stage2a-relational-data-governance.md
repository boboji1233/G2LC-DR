# ADR-0006: Relational data governance and locked source-family policy

- Status: Accepted for Stage 2A
- Date: 2026-08-21
- Plan references: A-02/A-03, F-01, §6, §8, §13, §18.1

## Context

Oracle readiness requires stable cross-dataset identity, explicit missingness, provenance,
duplicate evidence, and leakage-safe splits before any target rule is executed. A single
image table cannot faithfully represent case/view grouping, annotation granularity,
spatial regions, correspondences, and multiple intended uses. No real official dataset is
present, so source columns and layouts cannot be guessed.

## Decision

1. Schema v2 is six versioned Parquet relations: `cases`, `images`, `labels`, `regions`,
   `correspondences`, and `splits`. Every row has deterministic global identity, canonical
   content hash, source dataset/family/row/hash, and JSON provenance.
2. Labels retain raw and normalized JSON separately. Status is one of `POSITIVE`,
   `NEGATIVE`, `UNKNOWN`, `AMBIGUOUS`, `NOT_APPLICABLE`, `WEAK`, or `DERIVED`; absence is
   never converted to `NEGATIVE`.
3. Ten adapters inspect only user-supplied local roots and return exactly `READY`,
   `MISSING_FILES`, `LICENSE_REQUIRED`, `UNSUPPORTED_VERSION`, or `SCHEMA_MISMATCH`.
   They never download, accept terms, infer diagnoses from filenames, or guess source
   schemas.
4. `DDR` and `MMRDR-CFP` are one `OIA_DDR` family. `MESSIDOR-1` and `MAPLES-DR` are one
   `MESSIDOR1` family. MAPLES-corresponding images are locked final same-case tests and
   cannot be used for training, validation, calibration, threshold, hyperparameter, or
   model selection.
5. Split construction is target-blind and groups patient, eye, visit, and confirmed
   duplicate identities. Missing verified patient identity remains null; it is not parsed
   from filenames.
6. Duplicate auditing records file SHA-256, decoded-pixel SHA-256, pHash, and dHash.
   Exact/decoded matches form deterministic groups; perceptual matches remain review-only.
   No source file is deleted. Embedding-based deduplication is explicitly `NOT_RUN`.
7. Public access facts are versioned in `data/dataset_registry.yaml`. Private requests,
   signatures, tokens, download links, medical data, and local restricted metadata remain
   outside Git.

## Consequences

The repository can validate legally supplied local inputs without claiming that any
dataset is present or schema-compatible. Any non-ready adapter state, changed split lock,
source-family relabeling, MAPLES selection use, checksum mismatch, or group leakage fails
closed. Oracle execution and all visual-model work remain blocked by later gates.
