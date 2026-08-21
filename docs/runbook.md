# G2LC-DR Runbook

All commands run from the repository root. Synthetic paths below are not clinical
guidelines. Production guideline files require official provenance and expert review.

Stage 1.5 proves decision sufficiency only under the declared finite evidence,
feasibility, derivation, modality, and guideline semantics.

## 1. Validate an ontology and guideline

```bash
uv run g2lc ontology validate examples/synthetic/minimal_dr/ontology.yaml
uv run g2lc guideline validate examples/synthetic/minimal_dr/guidelines.yaml \
  --ontology examples/synthetic/minimal_dr/ontology.yaml \
  --derivations examples/synthetic/minimal_dr/derivations.yaml
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
checks canonical and source hashes, reloads every raw input, and recomputes all three
outcomes without compiler or certificate-writer imports. Never edit a certificate by
hand and retain its old hash; even a correctly rehashed substantive mutation must fail
source-semantic recomputation.

## 4. Run the Stage-1.5 semantic gate

```bash
uv run python scripts/stage1_5_gate.py
uv run python scripts/review_bundle.py
```

The first command executes the exact locked sync, ruff, formatting, mypy, branch-aware
pytest, package build, synthetic differential matrix, and audit sequence. It stores logs,
coverage JSON, solver equivalence, tamper results, and the final result under
`artifacts/audit/stage1_5/`. The second command packages only source, tests, synthetic
fixtures, documentation, CI configuration, and Stage-1.5 audit evidence; it excludes
data, checkpoints, caches, and Git internals and emits a SHA-256 checksum.

## 4a. Run the Stage-1.6 cross-path gate

The immutable baseline is the full commit
`ec3250d7e3dba0379c3b5205949c23e4f4ee5d59`. Capture its pre-change evidence before
running the gate on a clean descendant:

```bash
uv run python scripts/stage1_6_capture_baseline.py /path/to/detached/ec3250d-checkout
uv run --python 3.11 python scripts/stage1_6_gate.py
uv run --python 3.12 python scripts/stage1_6_gate.py
uv run --python 3.12 g2lc audit stage1-6 --required-pythons 3.11,3.12 \
  --output artifacts/audit/stage1_6/gate.json
```

The runner records each real exit code, branch-aware coverage, JUnit outcomes, package
build, 20 cost perturbations, 200 varied semantic problems, tamper rejection, and bundle
verification. It never inserts a synthetic successful exit code for its own audit step.
The enforced coverage floors are 92%/86% whole-project line/branch and 96%/91% core
line/branch. The weekly/manual CI stress job expands the semantic generator to 2,000 cases.

## 4b. Stage-1.6.1 packaging and review finalization

`stage1_6_gate.py` builds into a unique ignored directory rather than repository `dist/`,
then runs `scripts/package_audit.py`. The audit requires exactly one wheel and one sdist,
wheel <2 MiB, sdist <5 MiB, no virtual environments/caches/generated outputs/medical data/
logs/checkpoints/secrets/local absolute paths, and clean isolated installed-CLI smoke tests
for both archives. `g2lc version` must report `0.1.0`; `g2lc synthetic run --fixture
minimal_dr --json` must pass using the fixture packaged in the wheel/sdist.

Run the two Python environments, aggregate them, then finalize the review archive:

```bash
uv run --python 3.11 python scripts/stage1_6_gate.py
uv run --python 3.12 python scripts/stage1_6_gate.py
uv run --python 3.12 g2lc audit stage1-6 --required-pythons 3.11,3.12 \
  --output artifacts/audit/stage1_6/gate.json
uv run --python 3.12 python scripts/review_bundle.py --stage 1.6.1 --finalize
uv run --python 3.12 g2lc audit stage1-6 --required-pythons 3.11,3.12 \
  --output artifacts/audit/stage1_6/gate.json
```

The ZIP's embedded gate deliberately stores `EXTERNALIZED` instead of a recursive archive
hash. Verify the final ZIP against both sibling files:

```text
G2LC_DR_STAGE1_6_1_REVIEW_<commit>.sha256
G2LC_DR_STAGE1_6_1_REVIEW_<commit>_final_metadata.json
```

The review export replaces local roots with `<WORKSPACE>` or `<LOCAL_PATH>`. Raw audit
logs remain unchanged on disk; the ZIP manifest hashes the normalized exported copies.

## 5. Add a guideline safely

1. Create a versioned YAML file; include official URL, section, effective date, modality,
   review status and clause-level provenance.
2. Use only predicates already declared in the ontology or follow section 5 below.
3. Add positive, negative, boundary, unknown and conflicting-rule tests per clause.
4. Validate and run the Z3 conflict checker.
5. Generate an old/new decision-difference report before merging. Clinical review is
   required before changing `review_status` from draft.

## 6. Add an evidence predicate

1. Declare finite domain/value type, image observability, modalities, parent/requires,
   ambiguities, provenance and recommended annotation operators.
2. Do not invent a threshold: any bin edge must come from a cited target guideline.
3. Add ontology validation tests and at least one unknown-value evaluator test.
4. If no current modality can observe it, mark it external/OOS rather than adding a
   fake operator.

## 7. Add a dataset adapter

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

## 8. Run the Oracle protocol

Oracle work begins only after legal access, deduplication and immutable split hashes.
Lock all MAPLES/MESSIDOR cases before reading target labels for evaluation. Derive
evidence operators from expert annotations, replay rules, and separately report
theoretical executability versus agreement. Any failure of Gate E stops visual training.

## 9. Reproduce a future paper table

The run registry must contain configuration, manifest, split, guideline, operator,
metric-code and checkpoint hashes plus seeds. A table builder must fail when required
runs are absent. No paper number is copied manually and no placeholder metric is valid.
