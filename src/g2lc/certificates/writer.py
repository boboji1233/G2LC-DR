"""Canonical certificate construction and writing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from g2lc.certificates.models import (
    Certificate,
    ExecutabilityCertificate,
    MissingEvidenceCertificate,
    OutOfSpecificationCertificate,
    SourceHash,
    VerificationPayload,
)
from g2lc.compiler.problem import LoadedCompilerProblem, enumerate_states
from g2lc.compiler.result import CompilerSolution, CompilerStatus
from g2lc.guidelines.provenance import guideline_hash
from g2lc.utils.io import canonical_json, sha256_file, sha256_json


def _repository_root(path: Path) -> Path:
    for candidate in (path.parent, *path.parents):
        if (candidate / ".git").exists() or (
            candidate / "G2LC_DR_KBS_Research_Plan_CN.md"
        ).is_file():
            return candidate
    return Path.cwd().resolve()


def _portable(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _base_payload(
    loaded: LoadedCompilerProblem,
    solution: CompilerSolution,
) -> dict[str, Any]:
    root = _repository_root(loaded.config_path)
    sources = [
        SourceHash(
            role="project",
            path=_portable(loaded.config_path, root),
            sha256=sha256_file(loaded.config_path),
        ),
        SourceHash(
            role="ontology",
            path=_portable(loaded.ontology_path, root),
            sha256=sha256_file(loaded.ontology_path),
        ),
        SourceHash(
            role="operators",
            path=_portable(loaded.operator_path, root),
            sha256=sha256_file(loaded.operator_path),
        ),
        SourceHash(
            role="derivations",
            path=_portable(loaded.derivation_path, root),
            sha256=sha256_file(loaded.derivation_path),
        ),
    ]
    sources.extend(
        SourceHash(role="guideline", path=_portable(path, root), sha256=sha256_file(path))
        for path in loaded.guideline_paths
    )
    state_count: int | None = None
    if solution.status is not CompilerStatus.OUT_OF_SPEC:
        state_count = len(enumerate_states(loaded))
    return {
        "schema_version": "1.0",
        "project_id": loaded.config.project_id,
        "project_config": _portable(loaded.config_path, root),
        "source_hashes": sorted(sources, key=lambda item: (item.role, item.path)),
        "ontology_hash": sha256_file(loaded.ontology_path),
        "guideline_hashes": {
            f"{guideline.id}@{guideline.version}": guideline_hash(guideline)
            for guideline in sorted(loaded.guidelines, key=lambda item: (item.id, item.version))
        },
        "operator_catalogue_hash": sha256_file(loaded.operator_path),
        "derivation_graph_hash": sha256_file(loaded.derivation_path),
        "selected_operators": solution.selected_operators,
        "derived_predicates": solution.derived_predicates,
        "total_cost": solution.total_cost,
        "solver": solution.solver,
        "solver_status": solution.solver_status,
        "verification": VerificationPayload(
            method="z3-and-finite-bruteforce",
            no_counterexample_expected=solution.status is CompilerStatus.EXECUTABLE,
            finite_state_count=state_count,
            required_pair_count=solution.required_pair_count,
            optimality_claimed=solution.optimal,
            seed=loaded.config.seed,
        ),
    }


def _with_hash(model_type: type[Any], payload: dict[str, Any]) -> Certificate:
    unhashed = {**payload, "certificate_hash": "0" * 64}
    model = model_type.model_validate(unhashed)
    body = model.model_dump(mode="json")
    body.pop("certificate_hash")
    payload["certificate_hash"] = sha256_json(body)
    return cast(Certificate, model_type.model_validate(payload))


def build_certificate(
    loaded: LoadedCompilerProblem,
    solution: CompilerSolution,
) -> Certificate:
    """Construct the certificate subtype implied by a compiler solution."""

    payload = _base_payload(loaded, solution)
    if solution.status is CompilerStatus.EXECUTABLE:
        payload.update(
            {
                "certificate_type": "EXECUTABLE",
                "guidelines_covered": sorted(
                    f"{item.id}@{item.version}" for item in loaded.guidelines
                ),
                "clauses_covered": sorted(
                    f"{guideline.id}:{rule.id}"
                    for guideline in loaded.guidelines
                    for rule in guideline.rules
                ),
            }
        )
        return _with_hash(ExecutabilityCertificate, payload)
    if solution.status is CompilerStatus.INCOMPLETE:
        payload.update(
            {
                "certificate_type": "INCOMPLETE",
                "uncovered_counterexamples": solution.counterexamples,
                "missing_predicates": solution.missing_predicates,
                "minimal_additions": solution.minimal_additions,
                "minimum_repair_cost": solution.minimum_repair_cost,
            }
        )
        return _with_hash(MissingEvidenceCertificate, payload)
    payload.update({"certificate_type": "OUT_OF_SPEC", "findings": solution.out_of_spec})
    return _with_hash(OutOfSpecificationCertificate, payload)


def write_certificate(certificate: Certificate, path: str | Path) -> Path:
    """Write canonical deterministic JSON, creating only the target parent directory."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = certificate.model_dump(mode="json")
    output.write_text(canonical_json(data) + "\n", encoding="utf-8")
    return output
