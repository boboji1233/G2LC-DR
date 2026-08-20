# G2LC-DR

G2LC-DR asks a knowledge-engineering question before training a vision model:
given versioned clinical guideline programs and candidate annotation operations,
which minimum-cost annotations preserve every action distinction the guidelines
need? If the current operators are insufficient, the compiler explains the missing
evidence. If a guideline asks for evidence that the declared imaging modality cannot
observe, it returns `OUT_OF_SPEC`.

This repository does **not** introduce a new DR backbone, claim support for arbitrary
future guidelines, or treat an LLM as clinical ground truth. The first release is a
synthetic, executable verification slice; its rules and relative costs are development
fixtures, not validated clinical thresholds or experimental results.

## Five-minute synthetic demo

Prerequisites are Python 3.11 and `uv`.

```bash
uv sync
uv run g2lc synthetic run --fixture minimal_dr
uv run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json
```

The demo loads a finite evidence ontology, two explicitly synthetic DR-like guideline
programs, an operator catalogue and a derivation graph. CP-SAT selects the minimum-cost
scheme; the certificate verifier reloads and hashes the inputs and independently checks
the finite problem.

## Common commands

```bash
uv run g2lc ontology validate examples/synthetic/minimal_dr/ontology.yaml
uv run g2lc guideline validate examples/synthetic/minimal_dr/guidelines.yaml
uv run g2lc operator validate examples/synthetic/minimal_dr/operators.yaml
uv run g2lc compile examples/synthetic/minimal_dr/project.yaml --solver exact
uv run g2lc synthetic run --fixture missing_evidence
uv run g2lc synthetic run --fixture out_of_spec
uv run pytest -q
```

Guideline evaluation accepts a YAML or JSON evidence state and never converts missing
values into false. See `docs/runbook.md` for the complete workflow and extension rules.

After the compiler gate, a metadata-only local adapter can be audited without writing:

```bash
uv run g2lc data adapt idrid D:/legal/local/IDRiD data/manifests/idrid.parquet --dry-run
```

Materialization requires `--license-confirmed`, hashes every image and writes Parquet.
Until an official dataset table parser is verified against supplied files, clinical
labels remain `UNKNOWN`; filenames are never used to invent them.

## Certificates

Certificates are canonical JSON with schema version, source hashes, selected operators,
cost, solver status and a verification payload. Types are:

- `EXECUTABLE`: selected observations separate every guideline action pair;
- `INCOMPLETE`: in-scope evidence lacks currently available annotation support;
- `OUT_OF_SPEC`: a predicate or modality lies outside the declared image language.

A certificate is not accepted on solver authority alone: verification checks its own
hash, reloads the source project, checks every source hash, and rechecks executability.

## Data access and reproducibility

No gated dataset is downloaded automatically or redistributed. Users must supply legal
local paths. Missing labels must be `UNKNOWN`, never negative. MAPLES/MESSIDOR remains a
locked same-case test set, and DDR/MMRDR-CFP is one source family. See
`docs/data_access.md`, `docs/claim_contract.md`, and `docs/runbook.md`.

Generated medical images, raw/interim/processed data and model checkpoints are excluded
from Git. Contributions that add guideline clauses must include provenance, version,
review status, boundary tests and an impact diff.
