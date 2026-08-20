"""Typer command-line interface for validation, compilation and verification."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich.console import Console

from g2lc.audit.stage1_5 import generate_gate as generate_stage1_5_gate
from g2lc.audit.stage1_5 import run_synthetic_matrix
from g2lc.audit.stage1_6 import generate_gate as generate_stage1_6_gate
from g2lc.certificates.verifier import verify_certificate
from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.problem import load_compiler_problem
from g2lc.compiler.result import SolverKind
from g2lc.data.adapters import adapter_for
from g2lc.data.dedup import exact_duplicate_groups
from g2lc.data.manifest import audit_manifest
from g2lc.data.splits import write_split_lock
from g2lc.errors import G2LCError, SourceValidationError
from g2lc.guidelines.evaluator import evaluate_guideline
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
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate one guideline file or every YAML file in a directory."""

    try:
        paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
        if not paths:
            raise SourceValidationError("directory contains no YAML guidelines", path=path)
        evidence = load_ontology(ontology) if ontology is not None else None
        count = 0
        for item in paths:
            bundle = load_guidelines(item)
            validate_guidelines(bundle, evidence)
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
        result = evaluate_guideline(candidates[0], state_model, load_ontology(ontology))
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
    project = Path("examples") / "synthetic" / fixture / "project.yaml"
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
