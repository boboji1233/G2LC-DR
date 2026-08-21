"""Typer command-line interface for validation, compilation and verification."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib.resources import as_file, files
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich.console import Console

from g2lc import __version__
from g2lc.audit.stage1_5 import generate_gate as generate_stage1_5_gate
from g2lc.audit.stage1_5 import run_synthetic_matrix
from g2lc.audit.stage1_6 import generate_gate as generate_stage1_6_gate
from g2lc.audit.stage2a import generate_gate as generate_stage2a_gate
from g2lc.certificates.verifier import verify_certificate
from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.problem import load_compiler_problem
from g2lc.compiler.result import SolverKind
from g2lc.data.adapters import adapter_for
from g2lc.data.builder import build_manifest_from_local_root
from g2lc.data.dedup import audit_duplicate_bundle, exact_duplicate_groups
from g2lc.data.manifest import audit_manifest
from g2lc.data.registry import (
    access_plan,
    inspect_registry_status,
    load_dataset_registry,
)
from g2lc.data.schemas import load_manifest_bundle, validate_manifest_bundle
from g2lc.data.splits import (
    create_relational_split_plan,
    verify_relational_split_lock,
    write_relational_split_lock,
    write_split_lock,
)
from g2lc.errors import G2LCError, SourceValidationError
from g2lc.guidelines.evaluator import DecisionContext, evaluate_guideline
from g2lc.guidelines.parser import load_guidelines
from g2lc.guidelines.validator import validate_guidelines
from g2lc.ontology.loader import load_ontology
from g2lc.operators.lattice import (
    load_derivation_graph,
    load_operator_catalogue,
    validate_operators,
)
from g2lc.types import EvidenceState, Modality
from g2lc.utils.io import load_json, load_yaml, resolve_from

app = typer.Typer(help="Certified guideline-to-label compilation.", no_args_is_help=True)
ontology_app = typer.Typer(help="Evidence ontology commands.")
guideline_app = typer.Typer(help="Guideline DSL commands.")
operator_app = typer.Typer(help="Annotation operator commands.")
certificate_app = typer.Typer(help="Certificate commands.")
synthetic_app = typer.Typer(help="Explicitly synthetic development fixtures.")
data_app = typer.Typer(help="Metadata-only data governance commands.")
audit_app = typer.Typer(help="Machine-readable stage-gate audits.")
app.add_typer(ontology_app, name="ontology")
app.add_typer(guideline_app, name="guideline")
app.add_typer(operator_app, name="operator")
app.add_typer(certificate_app, name="certificate")
app.add_typer(synthetic_app, name="synthetic")
app.add_typer(data_app, name="data")
app.add_typer(audit_app, name="audit")
console = Console()
error_console = Console(stderr=True)


def _emit(value: Any, json_output: bool) -> None:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    if json_output:
        typer.echo(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=lambda item: str(item) if isinstance(item, Decimal) else repr(item),
            )
        )
    else:
        console.print(payload)


def _fail(exc: Exception) -> None:
    error_console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=2)


def _root_mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    raw = load_yaml(path)
    if not isinstance(raw, dict):
        raise SourceValidationError("root map must be a YAML mapping", path=path)
    roots = raw.get("roots", raw)
    if not isinstance(roots, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in roots.items()
    ):
        raise SourceValidationError("root map values must be dataset_id: local_path", path=path)
    return dict(roots)


def _confirmed_ids(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


@app.command("version")
def version_command() -> None:
    """Print the installed G2LC-DR package version."""

    typer.echo(__version__)


@ontology_app.command("validate")
def ontology_validate(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Validate a versioned evidence ontology."""

    try:
        ontology = load_ontology(path)
        _emit(
            {
                "valid": True,
                "ontology_id": ontology.ontology_id,
                "predicates": len(ontology.predicates),
            },
            json_output,
        )
    except (G2LCError, ValidationError) as exc:
        _fail(exc)


@guideline_app.command("validate")
def guideline_validate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    ontology: Annotated[Path | None, typer.Option("--ontology")] = None,
    derivations: Annotated[Path | None, typer.Option("--derivations")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate one guideline file or every YAML file in a directory."""

    try:
        paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
        if not paths:
            raise SourceValidationError("directory contains no YAML guidelines", path=path)
        if (ontology is None) != (derivations is None):
            raise SourceValidationError(
                "--ontology and --derivations must be provided together", path=path
            )
        evidence = load_ontology(ontology) if ontology is not None else None
        graph = load_derivation_graph(derivations) if derivations is not None else None
        count = 0
        for item in paths:
            bundle = load_guidelines(item)
            validate_guidelines(bundle, evidence, graph)
            count += len(bundle.guidelines)
        _emit({"valid": True, "files": len(paths), "guidelines": count}, json_output)
    except (G2LCError, ValidationError) as exc:
        _fail(exc)


@operator_app.command("validate")
def operator_validate(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    ontology: Annotated[Path | None, typer.Option("--ontology")] = None,
    derivations: Annotated[Path | None, typer.Option("--derivations")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate an operator catalogue, optionally including lattice semantics."""

    try:
        catalogue = load_operator_catalogue(path)
        if (ontology is None) != (derivations is None):
            raise SourceValidationError(
                "--ontology and --derivations must be provided together", path=path
            )
        if ontology is not None and derivations is not None:
            validate_operators(
                catalogue, load_derivation_graph(derivations), load_ontology(ontology)
            )
        _emit(
            {
                "valid": True,
                "catalogue_id": catalogue.catalogue_id,
                "operators": len(catalogue.operators),
            },
            json_output,
        )
    except (G2LCError, ValidationError) as exc:
        _fail(exc)


@guideline_app.command("evaluate")
def guideline_evaluate(
    guideline: Annotated[Path, typer.Option("--guideline", exists=True, dir_okay=False)],
    state: Annotated[Path, typer.Option("--state", exists=True, dir_okay=False)],
    ontology: Annotated[Path, typer.Option("--ontology", exists=True, dir_okay=False)] = Path(
        "knowledge/evidence_ontology.yaml"
    ),
    derivations: Annotated[Path, typer.Option("--derivations", exists=True, dir_okay=False)] = Path(
        "knowledge/derivation_graph.yaml"
    ),
    guideline_id: Annotated[str | None, typer.Option("--guideline-id")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Evaluate one guideline on a partial YAML/JSON evidence state."""

    try:
        bundle = load_guidelines(guideline)
        candidates = [
            item for item in bundle.guidelines if guideline_id is None or item.id == guideline_id
        ]
        if len(candidates) != 1:
            raise SourceValidationError(
                f"expected one guideline, found {len(candidates)}; specify --guideline-id",
                path=guideline,
            )
        raw = load_json(state) if state.suffix.lower() == ".json" else load_yaml(state)
        state_model = EvidenceState.model_validate(
            raw if isinstance(raw, dict) and "values" in raw else {"values": raw}
        )
        result = evaluate_guideline(
            candidates[0],
            state_model,
            DecisionContext(
                ontology=load_ontology(ontology),
                derivations=load_derivation_graph(derivations),
            ),
        )
        _emit(result, json_output)
    except (G2LCError, ValidationError) as exc:
        _fail(exc)


@app.command("compile")
def compile_command(
    project_config: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    solver: Annotated[SolverKind, typer.Option("--solver")] = SolverKind.EXACT,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compile a project and write a deterministic certificate."""

    try:
        loaded = load_compiler_problem(project_config)
        solution = compile_problem(loaded, solver)
        certificate = build_certificate(loaded, solution)
        destination = output or resolve_from(project_config, loaded.config.output)
        write_certificate(certificate, destination)
        _emit(
            {
                "status": solution.status,
                "solver_status": solution.solver_status,
                "selected_operators": solution.selected_operators,
                "total_cost": solution.total_cost,
                "certificate": str(Path(destination).resolve()),
            },
            json_output,
        )
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@certificate_app.command("verify")
def certificate_verify(
    certificate_json: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Independently verify a compiler certificate."""

    try:
        _emit(verify_certificate(certificate_json), json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@synthetic_app.command("run")
def synthetic_run(
    fixture: Annotated[str, typer.Option("--fixture")] = "minimal_dr",
    solver: Annotated[SolverKind, typer.Option("--solver")] = SolverKind.EXACT,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run a named, explicitly non-clinical fixture."""

    allowed = {"minimal_dr", "missing_evidence", "out_of_spec"}
    if fixture not in allowed:
        _fail(ValueError(f"unknown fixture {fixture!r}; choose one of {sorted(allowed)}"))
    checkout_project = Path("examples") / "synthetic" / fixture / "project.yaml"
    if checkout_project.is_file():
        compile_command(checkout_project, solver, None, json_output)
        return
    packaged_project = files("g2lc").joinpath("fixtures", "synthetic", fixture, "project.yaml")
    with as_file(packaged_project) as project:
        compile_command(project, solver, None, json_output)


@synthetic_app.command("matrix")
def synthetic_matrix(
    random_seeds: Annotated[int, typer.Option("--random-seeds", min=1)] = 20,
    semantic_generated_cases: Annotated[int, typer.Option("--semantic-generated-cases", min=0)] = 0,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run deterministic finite/brute-force/Z3/separation/tamper equivalence checks."""

    try:
        result = run_synthetic_matrix(
            random_seeds=random_seeds,
            semantic_generated_cases=semantic_generated_cases,
        )
        _emit(result, json_output)
        if not all(
            bool(result[item]["passed"])
            for item in (
                "finite_vs_bruteforce_results",
                "finite_vs_z3_results",
                "exact_vs_separation_results",
                "verifier_independence_check",
                "tamper_matrix_results",
            )
        ):
            raise typer.Exit(code=1)
        if semantic_generated_cases and not result["semantic_generated_results"]["passed"]:
            raise typer.Exit(code=1)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@audit_app.command("stage1-5")
def audit_stage1_5(
    output: Annotated[Path, typer.Option("--output")] = Path("artifacts/audit/stage1_5/gate.json"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Generate the Stage-1.5 gate from current command, coverage, and matrix evidence."""

    try:
        _emit(generate_stage1_5_gate(output), json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@audit_app.command("stage1-6")
def audit_stage1_6(
    output: Annotated[Path, typer.Option("--output")] = Path("artifacts/audit/stage1_6/gate.json"),
    required_pythons: Annotated[str | None, typer.Option("--required-pythons")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Aggregate recorded Stage-1.6 evidence without self-asserted command success."""

    try:
        required = (
            [item.strip() for item in required_pythons.split(",")] if required_pythons else None
        )
        _emit(generate_stage1_6_gate(output, required), json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@audit_app.command("stage2a")
def audit_stage2a(
    output: Annotated[Path, typer.Option("--output")] = Path("artifacts/audit/stage2a/gate.json"),
    required_pythons: Annotated[str | None, typer.Option("--required-pythons")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Aggregate recorded Stage-2A governance evidence and finalized review hashes."""

    try:
        required = (
            [item.strip() for item in required_pythons.split(",")] if required_pythons else None
        )
        gate = generate_stage2a_gate(output, required, require_review=True)
        _emit(gate, json_output)
        if gate["final_status"] != "PASS":
            raise typer.Exit(code=1)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("status")
def data_status(
    registry_path: Annotated[
        Path, typer.Option("--registry", exists=True, dir_okay=False, readable=True)
    ] = Path("data/dataset_registry.yaml"),
    roots: Annotated[
        Path | None, typer.Option("--roots", exists=True, dir_okay=False, readable=True)
    ] = None,
    license_confirmed: Annotated[
        str, typer.Option("--license-confirmed", help="Comma-separated dataset IDs.")
    ] = "",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Join the public access ledger to truthful local adapter states."""

    try:
        registry = load_dataset_registry(registry_path)
        statuses = inspect_registry_status(
            registry,
            _root_mapping(roots),
            license_confirmed=_confirmed_ids(license_confirmed),
        )
        _emit({"datasets": [item.model_dump(mode="json") for item in statuses]}, json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("inspect-root")
def data_inspect_root(
    dataset_id: Annotated[str, typer.Argument()],
    local_path: Annotated[Path, typer.Argument()],
    license_confirmed: Annotated[bool, typer.Option("--license-confirmed")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect one local dataset root without downloading or modifying it."""

    try:
        inspection = adapter_for(dataset_id).inspect_root(
            local_path, license_confirmed=license_confirmed
        )
        _emit(inspection, json_output)
        if inspection.state.value != "READY":
            raise typer.Exit(code=1)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("build-manifest")
def data_build_manifest(
    dataset_id: Annotated[str, typer.Argument()],
    local_path: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Argument()],
    registry_path: Annotated[
        Path, typer.Option("--registry", exists=True, dir_okay=False, readable=True)
    ] = Path("data/dataset_registry.yaml"),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    license_confirmed: Annotated[bool, typer.Option("--license-confirmed")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inventory a local root into six provenance-safe relations."""

    try:
        entry = load_dataset_registry(registry_path).entry(dataset_id)
        _emit(
            build_manifest_from_local_root(
                entry,
                local_path,
                output,
                dry_run=dry_run,
                license_confirmed=license_confirmed,
            ),
            json_output,
        )
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("validate-manifest")
def data_validate_manifest(
    manifest: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate schema, hashes, references, and split leakage policy."""

    try:
        report = validate_manifest_bundle(manifest)
        _emit(report, json_output)
        if not report.valid:
            raise typer.Exit(code=1)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("audit-duplicates")
def data_audit_duplicates(
    manifest: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output: Annotated[Path, typer.Argument()],
    phash_threshold: Annotated[int, typer.Option("--phash-threshold", min=0, max=64)] = 8,
    dhash_threshold: Annotated[int, typer.Option("--dhash-threshold", min=0, max=64)] = 8,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Audit exact, decoded-pixel, pHash, and dHash duplicate evidence."""

    try:
        _emit(
            audit_duplicate_bundle(
                manifest,
                output,
                phash_threshold=phash_threshold,
                dhash_threshold=dhash_threshold,
            ),
            json_output,
        )
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("create-split")
def data_create_split(
    manifest: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output: Annotated[Path, typer.Argument()],
    train_percent: Annotated[int, typer.Option("--train-percent", min=1, max=98)] = 70,
    validation_percent: Annotated[int, typer.Option("--validation-percent", min=1, max=98)] = 15,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create a target-blind, group-aware split proposal or immutable lock."""

    try:
        plan = create_relational_split_plan(
            load_manifest_bundle(manifest),
            train_percent=train_percent,
            validation_percent=validation_percent,
        )
        lock_path = None if dry_run else write_relational_split_lock(plan, output)
        _emit(
            {
                "dry_run": dry_run,
                "assignments": len(plan.assignments),
                "split_hash": plan.split_hash,
                "lock_file": str(lock_path) if lock_path is not None else None,
                "target_labels_opened": False,
            },
            json_output,
        )
    except (G2LCError, ValidationError, OSError, ValueError) as exc:
        _fail(exc)


@data_app.command("verify-split-lock")
def data_verify_split_lock(
    lock_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Verify a relational split lock and every leakage prohibition."""

    try:
        plan = verify_relational_split_lock(lock_file)
        _emit(
            {
                "valid": True,
                "assignments": len(plan.assignments),
                "split_hash": plan.split_hash,
            },
            json_output,
        )
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("access-plan")
def data_access_plan(
    registry_path: Annotated[
        Path, typer.Option("--registry", exists=True, dir_okay=False, readable=True)
    ] = Path("data/dataset_registry.yaml"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Print public owner actions without performing access steps."""

    try:
        _emit({"actions": access_plan(load_dataset_registry(registry_path))}, json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("audit")
def data_audit(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Dry-run audit a user-supplied metadata manifest."""

    try:
        _emit(audit_manifest(manifest), json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("adapt")
def data_adapt(
    dataset_id: Annotated[str, typer.Argument()],
    local_path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Argument()],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    license_confirmed: Annotated[bool, typer.Option("--license-confirmed")] = False,
    modality: Annotated[Modality | None, typer.Option("--modality")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Audit or write a metadata-only Parquet manifest from a local dataset path."""

    try:
        result = adapter_for(dataset_id).run(
            local_path,
            output,
            dry_run=dry_run,
            license_confirmed=license_confirmed,
            modality=modality,
        )
        _emit(result, json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("dedup")
def data_dedup(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run exact SHA-256 duplicate grouping; no files are modified."""

    try:
        _emit({"duplicate_groups": exact_duplicate_groups(manifest)}, json_output)
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@data_app.command("lock-split")
def data_lock_split(
    config: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate and hash an immutable split assignment description."""

    try:
        split, digest, output = write_split_lock(config)
        _emit(
            {
                "dataset_id": split.dataset_id,
                "split_hash": digest,
                "maples_test_lock": split.maples_test_lock,
                "lock_file": str(output),
            },
            json_output,
        )
    except (G2LCError, ValidationError, OSError) as exc:
        _fail(exc)


@app.command("status")
def status_command() -> None:
    """Print the tracked project status without changing it."""

    path = Path("STATUS.md")
    if not path.is_file():
        _fail(FileNotFoundError("STATUS.md is missing"))
    typer.echo(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()
