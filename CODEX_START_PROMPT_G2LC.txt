You are the lead research software engineer for the project **G2LC-DR: Guideline-to-Label Compiler for Diabetic Retinopathy**.

The project directory contains the authoritative research specification:

- `G2LC_DR_KBS_Research_Plan_CN.md`

Read that file completely before making changes. Treat it as the source of truth. Do not silently change the scientific claims, data split rules, guideline semantics, acceptance gates, or reproducibility requirements.

# 1. Mission

Build a production-quality, research-reproducible Python repository that implements the first executable stages of G2LC-DR:

1. a versioned clinical-evidence ontology;
2. a typed guideline DSL with three-valued logic;
3. a typed annotation-operator catalogue and derivation lattice;
4. a guideline-to-label compiler that finds a minimum-cost sufficient annotation scheme;
5. an exact CP-SAT solver;
6. a Z3 counterexample/executability checker;
7. a scalable greedy/counterexample-separation solver;
8. executable, missing-evidence, and out-of-specification certificates;
9. an independent certificate verifier;
10. synthetic fixtures, unit tests, property tests, CLI commands, documentation, and CI;
11. dataset adapters and manifests only after the compiler core passes its acceptance tests.

This is not a request for a README-only scaffold or pseudocode. Implement working code and tests.

# 2. Non-negotiable scientific constraints

- The single core innovation is **reverse-compiling a family of clinical guidelines into a minimum-cost executable annotation design**.
- Do not invent a new backbone, attention module, graph network, loss, or LLM component and present it as the main innovation.
- Do not claim support for arbitrary future guidelines. The system supports only a declared, image-observable evidence language and must return `OUT_OF_SPEC` for unsupported predicates/modalities.
- Do not fabricate datasets, labels, clinical rules, costs, metrics, results, or completed experiments.
- Do not treat missing labels as negatives. Use `POSITIVE`, `NEGATIVE`, and `UNKNOWN` explicitly.
- Do not download or redistribute gated datasets automatically. Implement documented adapters and explicit user-invoked download/request helpers only.
- Never use target test labels for model selection, thresholding, calibration, rule tuning, or hyperparameter selection.
- MAPLES/MESSIDOR is a locked same-case multi-guideline test set. Build the lock mechanism before any real experiment code.
- DDR and MMRDR-CFP belong to the same source family and must never be treated as independent domains.
- Every executable guideline clause must carry source, version, and provenance metadata.
- LLM output is never clinical ground truth.

# 3. Work protocol

Before writing implementation code:

1. Read `G2LC_DR_KBS_Research_Plan_CN.md` fully.
2. Inspect the current repository.
3. Create or update:
   - `IMPLEMENTATION_PLAN.md`
   - `STATUS.md`
   - `CHANGELOG.md`
   - `docs/decisions/0001-architecture.md`
4. In `IMPLEMENTATION_PLAN.md`, map every planned module to the relevant section/task ID in the research plan.
5. Then immediately implement the first incomplete task whose dependencies are satisfied. Do not stop after planning.

At the end of every working session:

- update `STATUS.md` with completed, in-progress, blocked, and next tasks;
- list exact commands run and their outcomes;
- record any assumptions in an ADR under `docs/decisions/`;
- keep the repository runnable;
- never mark a task complete unless its tests and acceptance checks pass.

# 4. Required technology choices

Use these defaults unless the existing repository already has a better compatible choice:

- Python 3.11
- `uv` for dependency and environment management
- PyTorch for later visual models
- Pydantic v2 for typed schemas
- PyYAML or ruamel.yaml for YAML parsing with source-friendly errors
- OR-Tools CP-SAT for the exact minimum-cost compiler
- `z3-solver` for logical satisfiability, counterexamples, and certificate verification
- Typer for CLI
- Hydra/OmegaConf for experiment configuration
- pandas or polars + Parquet for manifests and run registry
- pytest + hypothesis for tests
- ruff + mypy for quality
- pre-commit
- GitHub Actions CI

Avoid adding heavy dependencies without a clear need. Pin or constrain versions in `pyproject.toml` and create a lock file.

# 5. Required repository structure

Create this structure, adjusting only when justified in an ADR:

```text
.
├── G2LC_DR_KBS_Research_Plan_CN.md
├── CODEX_START_PROMPT_G2LC.txt
├── README.md
├── IMPLEMENTATION_PLAN.md
├── STATUS.md
├── CHANGELOG.md
├── LICENSE
├── CITATION.cff
├── pyproject.toml
├── uv.lock
├── Makefile
├── .gitignore
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── src/g2lc/
│   ├── __init__.py
│   ├── cli.py
│   ├── types.py
│   ├── errors.py
│   ├── ontology/
│   │   ├── models.py
│   │   ├── loader.py
│   │   ├── validator.py
│   │   └── observability.py
│   ├── guidelines/
│   │   ├── ast.py
│   │   ├── parser.py
│   │   ├── evaluator.py
│   │   ├── trivalued.py
│   │   ├── provenance.py
│   │   └── validator.py
│   ├── operators/
│   │   ├── models.py
│   │   ├── lattice.py
│   │   ├── derivation.py
│   │   └── cost.py
│   ├── compiler/
│   │   ├── problem.py
│   │   ├── exact.py
│   │   ├── greedy.py
│   │   ├── counterexample.py
│   │   ├── dominance.py
│   │   ├── repair.py
│   │   └── result.py
│   ├── certificates/
│   │   ├── models.py
│   │   ├── writer.py
│   │   └── verifier.py
│   ├── data/
│   │   ├── manifest.py
│   │   ├── labels.py
│   │   ├── splits.py
│   │   ├── dedup.py
│   │   ├── license_registry.py
│   │   └── adapters/
│   ├── metrics/
│   ├── experiments/
│   └── utils/
├── knowledge/
│   ├── evidence_ontology.yaml
│   ├── annotation_operators.yaml
│   ├── derivation_graph.yaml
│   └── guidelines/
├── examples/
│   ├── synthetic/
│   └── certificates/
├── configs/
├── scripts/
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   ├── guidelines/
│   └── fixtures/
├── docs/
│   ├── data_access.md
│   ├── data_access_log.md
│   ├── claim_contract.md
│   ├── runbook.md
│   └── decisions/
├── data/
│   ├── raw/.gitkeep
│   ├── interim/.gitkeep
│   ├── processed/.gitkeep
│   ├── manifests/.gitkeep
│   └── licenses.csv
├── runs/.gitkeep
└── artifacts/.gitkeep
```

All raw/interim/processed image data and model checkpoints must be excluded from Git.

# 6. Core domain models to implement first

Implement strict, serializable models with type hints and validation for at least:

- `EvidencePredicate`
  - id
  - name
  - description
  - value_type
  - allowed_values/domain
  - modality
  - observability
  - parent predicate
  - source/provenance
- `EvidenceState`
- `TriValue = TRUE | FALSE | UNKNOWN`
- `Guideline`
- `GuidelineClause`
- typed guideline expressions:
  - `And`
  - `Or`
  - `Not`
  - `Equals`
  - `GreaterEqual`
  - `LessEqual`
  - `InSet`
  - `Known`
- `ClinicalAction`
- `AnnotationOperator`
  - output predicates
  - granularity
  - modality
  - cost
  - instability/reliability
  - prerequisites
  - derivable outputs
- `DerivationRule`
- `CompilerProblem`
- `CompilerSolution`
- `ExecutabilityCertificate`
- `MissingEvidenceCertificate`
- `OutOfSpecificationCertificate`

Validation errors must be explicit and actionable, including YAML file path and field/line context where possible.

# 7. Three-valued guideline semantics

Implement Kleene-style three-valued logic or an explicitly documented equivalent:

- `TRUE AND UNKNOWN = UNKNOWN`
- `FALSE AND UNKNOWN = FALSE`
- `TRUE OR UNKNOWN = TRUE`
- `FALSE OR UNKNOWN = UNKNOWN`
- comparisons with unknown evidence return `UNKNOWN`

A guideline evaluation may return:

- a unique action;
- an action set;
- `INSUFFICIENT_EVIDENCE`;
- `OUT_OF_SPEC`.

Never coerce `UNKNOWN` to false.

# 8. Compiler behavior

Given:

- a family of guidelines;
- an evidence ontology;
- candidate annotation operators;
- derivation rules;
- costs and instability weights;

find a minimum-cost set of annotation operators that separates every clinically feasible evidence-state pair that any target guideline maps to different actions.

Implement two complementary formulations:

## 8.1 Small exact formulation

For finite synthetic state spaces:

- enumerate distinguishable state pairs;
- formulate weighted test-cover/set-cover constraints;
- solve with CP-SAT;
- verify the result by brute force for small fixtures.

## 8.2 Scalable counterexample-separation formulation

Do not enumerate a huge Cartesian state space. Implement an iterative loop:

1. solve the current restricted master problem;
2. ask Z3 whether two feasible states remain indistinguishable under selected operators but receive different guideline actions;
3. if a counterexample exists, add the corresponding separation constraint;
4. repeat until no counterexample exists or a configured limit is reached;
5. return a verifiable certificate and optimality information.

Implement a greedy scalable alternative using marginal separated-pair/estimated-counterexample benefit divided by cost.

# 9. Certificate requirements

Every compiler run must emit deterministic JSON with schema version, hashes, selected operators, guideline hashes, ontology hash, cost, solver status, and a verification payload.

Required certificate types:

1. `EXECUTABLE`
   - selected operators
   - derived predicates
   - total cost
   - guidelines/clauses covered
   - no-counterexample proof/check result
2. `INCOMPLETE`
   - uncovered clauses or action-separating counterexamples
   - minimal missing predicates/operators
   - minimum repair cost
3. `OUT_OF_SPEC`
   - unsupported predicates
   - unsupported modality
   - source guideline clauses
   - reason no image-only solution exists

Create an independent verifier that does not trust the original solver result. It must re-load the source files, check hashes, and use Z3/brute force as appropriate.

# 10. Synthetic fixtures required before real data work

Create at least three fixtures:

## Fixture A: minimal DR-like example

Evidence:

- `ma_presence`
- `hem_count_bin ∈ {0, 1_3, 4_plus}`
- `nv_presence`
- `gradable`

Guidelines:

- Guideline 1 depends on MA and hemorrhage threshold.
- Guideline 2 uses a different hemorrhage threshold and NV.

Operators:

- image-level grade only
- MA presence
- hemorrhage presence
- hemorrhage count bin
- NV presence
- full mask that derives count/presence
- quality label

The known optimum must be asserted in tests.

## Fixture B: missing-evidence example

Remove the only operator capable of observing `nv_presence`. The compiler must return `INCOMPLETE` and the exact missing evidence/operator set.

## Fixture C: out-of-spec example

Add a guideline clause requiring `oct_central_thickness` or visual acuity. In a CFP-only project the compiler must return `OUT_OF_SPEC`.

# 11. CLI commands required

Implement at least:

```bash
g2lc ontology validate PATH
g2lc guideline validate PATH
g2lc operator validate PATH
g2lc guideline evaluate --guideline PATH --state PATH
g2lc compile PROJECT_CONFIG
g2lc compile PROJECT_CONFIG --solver exact
g2lc compile PROJECT_CONFIG --solver greedy
g2lc certificate verify CERTIFICATE_JSON
g2lc synthetic run --fixture minimal_dr
g2lc data audit MANIFEST
g2lc data lock-split CONFIG
g2lc data dedup MANIFEST
g2lc status
```

Commands must return nonzero exit codes on validation or certificate failure and print concise human-readable summaries plus optional JSON output.

# 12. Test requirements

Do not consider Stage 1 complete until all of the following exist and pass:

- at least 30 focused unit tests;
- at least 10 guideline semantic tests;
- at least 10 property-based tests;
- exact solver equals brute-force optimum on all small fixtures;
- executable certificate verifier accepts valid certificates;
- verifier rejects tampered certificates;
- missing evidence fixture recovers the exact missing set;
- OOS fixture identifies the unsupported predicate and modality;
- unknown evidence is never silently treated as false;
- deterministic output under the same input and seed;
- invalid cyclic derivation graph is rejected;
- dominated operators are handled correctly;
- malformed or contradictory guideline clauses produce actionable errors.

Target initial code coverage: at least 85% for ontology, guideline, compiler, and certificate modules.

# 13. Quality commands and acceptance gate

Create Make targets so these commands work:

```bash
make install
make format
make lint
make typecheck
make test
make test-fast
make quality
make synthetic-demo
```

Stage 1 acceptance requires:

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run g2lc synthetic run --fixture minimal_dr
uv run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json
```

All must pass. Do not move to real dataset adapters if they fail.

# 14. Data adapter stage after core acceptance

After Stage 1 passes, implement metadata-only adapters for:

- DDR
- MMRDR-CFP/UWF
- IDRiD
- DeepDRiD
- FGADR
- MAPLES-DR/MESSIDOR
- Retinal-Lesions

Each adapter must:

- require a user-supplied local path;
- never auto-download gated data;
- produce a unified Parquet manifest;
- preserve original labels and provenance;
- convert absent labels to `UNKNOWN`, not negative;
- record source family and overlap risk;
- compute file hashes;
- support a dry-run audit;
- validate expected directory structure;
- emit clear instructions when files are missing.

Create `docs/data_access.md` with official URLs and license notes from the research plan.

Implement dataset split locking:

- patient-level where possible;
- source-family-aware split constraints;
- MAPLES test lock;
- deterministic split hashes;
- explicit override requiring a dangerous-action flag and audit log.

# 15. Duplicate audit

Implement an extensible duplicate pipeline:

1. exact SHA-256;
2. perceptual hash candidate generation;
3. optional embedding nearest-neighbor candidate generation;
4. optional SSIM confirmation;
5. human-review CSV for ambiguous pairs.

Hard-code no dataset-specific conclusion, but add a validation rule warning that DDR and MMRDR-CFP are the same source family.

# 16. Experiment infrastructure skeleton

After the compiler and adapters pass, create non-fabricated experiment scaffolding for:

- Oracle evidence-to-guideline evaluation;
- direct grade baselines;
- concept bottleneck baselines;
- DAPHNE-style rule baseline;
- annotation selection baselines;
- certificate/abstention baselines;
- later RETFound, FLAIR, GDRNet, DECO, DG-ADR adapters.

Do not claim these experiments have run until real datasets and checkpoints are present. Missing resources must result in a clear `BLOCKED` status, not dummy metrics.

Create:

- `runs/run_registry.parquet` schema;
- config hashing;
- dataset manifest hashing;
- guideline and operator hashing;
- seed tracking;
- metrics JSON schema;
- automatic table/figure script placeholders that fail clearly when required runs are absent.

# 17. Documentation requirements

The README must include:

- the scientific problem in plain language;
- what G2LC is and is not;
- a 5-minute synthetic demo;
- installation;
- CLI examples;
- certificate example;
- data access constraints;
- contribution/reproducibility notes.

Create `docs/runbook.md` with exact steps for:

1. validating ontology/guidelines;
2. compiling an annotation scheme;
3. verifying a certificate;
4. adding a new guideline safely;
5. adding a new evidence predicate;
6. adding a dataset adapter;
7. running the Oracle protocol;
8. reproducing a paper table later.

# 18. Coding standards

- Fully typed public APIs.
- Clear docstrings explaining domain semantics, not redundant syntax.
- No broad `except Exception` without re-raising contextual errors.
- No hidden global state.
- Deterministic ordering and serialization.
- Pure functions where possible.
- Separate domain logic from CLI and I/O.
- Use explicit enums, not magic strings.
- Validate all external YAML/JSON/Parquet inputs.
- Do not suppress type errors to make CI pass.
- Avoid premature framework abstraction, but keep exact/greedy solvers behind a common protocol.
- Add comments for mathematical constraints and certificate invariants.

# 19. Do not do these things

- Do not create fake DR images or fake expert labels and present them as data.
- Do not insert invented NHS/ICDR thresholds into production guideline files.
- Synthetic guideline files must be clearly labeled `synthetic` and must never be confused with validated clinical rules.
- Do not scrape gated datasets or bypass licenses.
- Do not commit raw medical images or checkpoints.
- Do not treat the current plan as proof that a guideline rule is clinically validated; preserve provenance and `review_status`.
- Do not add LLM-based rule extraction as a core dependency.
- Do not skip tests because a dependency is difficult.
- Do not report “state of the art” or paper-ready results without actual unified runs.
- Do not change the locked test-set policy.

# 20. First execution objective

In this first Codex run, complete as much as possible of the following in order:

1. inspect and document the architecture;
2. initialize the repository and tooling;
3. implement domain schemas;
4. implement three-valued guideline parser/evaluator;
5. implement operator lattice and validation;
6. implement exact CP-SAT compiler for finite fixtures;
7. implement Z3 counterexample checker;
8. implement certificates and independent verifier;
9. implement the three synthetic fixtures;
10. implement CLI;
11. write tests and CI;
12. run all quality commands;
13. update `STATUS.md` with exact pass/fail results;
14. only then begin real dataset adapter scaffolding if time and tests permit.

When a real-data task is blocked by a missing dataset, record the exact official acquisition action in `STATUS.md` and continue with other unblocked engineering tasks. Never replace missing real data with fabricated results.

Start now by reading `G2LC_DR_KBS_Research_Plan_CN.md`, inspecting the directory, writing `IMPLEMENTATION_PLAN.md`, and then implementing the first working vertical slice from YAML input to a verified synthetic certificate.
