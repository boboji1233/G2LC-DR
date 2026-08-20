# G2LC-DR Runbook

All commands run from the repository root. Synthetic paths below are not clinical
guidelines. Production guideline files require official provenance and expert review.

## 1. Validate an ontology and guideline

```bash
uv run g2lc ontology validate examples/synthetic/minimal_dr/ontology.yaml
uv run g2lc guideline validate examples/synthetic/minimal_dr/guidelines.yaml \
  --ontology examples/synthetic/minimal_dr/ontology.yaml
uv run g2lc operator validate examples/synthetic/minimal_dr/operators.yaml \
  --ontology examples/synthetic/minimal_dr/ontology.yaml \
  --derivations examples/synthetic/minimal_dr/derivations.yaml
```

Validation failures return a nonzero exit and include the source path plus a field or
YAML context where available.

## 2. Compile an annotation scheme

```bash
uv run g2lc compile examples/synthetic/minimal_dr/project.yaml --solver exact
uv run g2lc compile examples/synthetic/minimal_dr/project.yaml --solver greedy
```

`exact` is CP-SAT on the finite state-pair formulation. `separation` uses a restricted
CP-SAT master and Z3 counterexamples. `greedy` is deterministic but does not claim
optimality.

## 3. Verify a certificate

```bash
uv run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json
```

The verifier resolves the recorded project from the certificate/repository hierarchy,
checks canonical and source hashes, reloads every input, and recomputes soundness. Never
edit a certificate by hand and retain its old hash.

## 4. Add a guideline safely

1. Create a versioned YAML file; include official URL, section, effective date, modality,
   review status and clause-level provenance.
2. Use only predicates already declared in the ontology or follow section 5 below.
3. Add positive, negative, boundary, unknown and conflicting-rule tests per clause.
4. Validate and run the Z3 conflict checker.
5. Generate an old/new decision-difference report before merging. Clinical review is
   required before changing `review_status` from draft.

## 5. Add an evidence predicate

1. Declare finite domain/value type, image observability, modalities, parent/requires,
   ambiguities, provenance and recommended annotation operators.
2. Do not invent a threshold: any bin edge must come from a cited target guideline.
3. Add ontology validation tests and at least one unknown-value evaluator test.
4. If no current modality can observe it, mark it external/OOS rather than adding a
   fake operator.

## 6. Add a dataset adapter

Dataset adapters begin only after Stage 1 acceptance. Require a local path, check the
expected structure, preserve original labels and provenance, convert absent labels to
`UNKNOWN`, hash files, record license/source family, and support a dry run. Never fetch
gated data. DDR/MMRDR-CFP must be `OIA_DDR`; Retinal-Lesions is an EyePACS overlap risk.

```bash
uv run g2lc data adapt idrid D:/legal/local/IDRiD data/manifests/idrid.parquet --dry-run
uv run g2lc data adapt idrid D:/legal/local/IDRiD data/manifests/idrid.parquet \
  --license-confirmed
```

The initial adapters intentionally emit `UNKNOWN` clinical labels until each official
source table parser is verified against legally supplied files. They never infer labels
from filenames. That source-specific parsing remains blocked when the dataset is absent.

## 7. Run the Oracle protocol

Oracle work begins only after legal access, deduplication and immutable split hashes.
Lock all MAPLES/MESSIDOR cases before reading target labels for evaluation. Derive
evidence operators from expert annotations, replay rules, and separately report
theoretical executability versus agreement. Any failure of Gate E stops visual training.

## 8. Reproduce a future paper table

The run registry must contain configuration, manifest, split, guideline, operator,
metric-code and checkpoint hashes plus seeds. A table builder must fail when required
runs are absent. No paper number is copied manually and no placeholder metric is valid.
