"""Canonical certificate construction and writing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from g2lc.certificates.models import (
    Certificate,
    EvidenceLanguagePayload,
    ExecutabilityCertificate,
    MissingEvidenceCertificate,
    OptimalityPayload,
    OutOfSpecificationCertificate,
    SourceHash,
    VerificationPayload,
)
from g2lc.compiler.counterexample import find_feasible_state
from g2lc.compiler.problem import (
    LoadedCompilerProblem,
    enumerate_states,
    relevant_predicate_closure,
)
from g2lc.compiler.result import CompilerSolution, CompilerStatus
from g2lc.errors import CompilationError
from g2lc.operators.lattice import operator_prerequisite_closure
from g2lc.utils.io import canonical_json, load_yaml, sha256_file, sha256_json


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
    symbolic = (
        solution.solver.value == "separation" and solution.status is not CompilerStatus.OUT_OF_SPEC
    )
    state_count: int | None = None
    if solution.status is not CompilerStatus.OUT_OF_SPEC and not symbolic:
        state_count = len(enumerate_states(loaded))
    selected_map = loaded.catalogue.operator_map()
    closure = set(operator_prerequisite_closure(solution.selected_operators, selected_map))
    witness = find_feasible_state(loaded)
    if witness is None:
        raise CompilationError("UNSAT_EVIDENCE_LANGUAGE cannot produce a certificate")
    relevant = list(relevant_predicate_closure(loaded))
    guideline_source_hashes = {
        str(path.resolve()): sha256_file(path) for path in loaded.guideline_paths
    }
    decision_program = [
        {
            "id": guideline.id,
            "version": guideline.version,
            "action_schema": guideline.action_schema,
            "rules": [
                {
                    "id": rule.id,
                    "priority": rule.priority,
                    "when": rule.when.model_dump(mode="json"),
                    "action": rule.action.model_dump(mode="json"),
                }
                for rule in guideline.rules
            ],
            "default_action": (
                guideline.default_action.model_dump(mode="json")
                if guideline.default_action is not None
                else None
            ),
        }
        for guideline in sorted(loaded.guidelines, key=lambda item: (item.id, item.version))
    ]
    return {
        "schema_version": "1.1",
        "semantic_contract": "action-only-decision-sufficiency-v1.1",
        "proof_scope": (
            "BOUNDED"
            if solution.status is CompilerStatus.OUT_OF_SPEC
            else "SMT_UNIVERSAL"
            if symbolic
            else "FINITE_EXHAUSTIVE"
        ),
        "assumptions": [
            "finite declared predicate domains",
            "None alone denotes unknown evidence",
            "typed scalar identity distinguishes booleans, integers, numbers, and strings",
            "only declared feasibility and deterministic unary derivations constrain states",
            "the evidence language contains at least one legal complete state",
            "synthetic fixtures are not clinical rules or measured costs",
        ],
        "project_id": loaded.config.project_id,
        "project_config": _portable(loaded.config_path, root),
        "source_hashes": sorted(sources, key=lambda item: (item.role, item.path)),
        "ontology_hash": sha256_file(loaded.ontology_path),
        "guideline_hashes": {
            f"{guideline.id}@{guideline.version}": guideline_source_hashes[str(path.resolve())]
            for path, bundle in zip(loaded.guideline_paths, loaded.guideline_bundles, strict=True)
            for guideline in bundle.guidelines
        },
        "operator_catalogue_hash": sha256_file(loaded.operator_path),
        "derivation_graph_hash": sha256_file(loaded.derivation_path),
        "feasibility_hash": sha256_json(
            load_yaml(loaded.ontology_path).get(
                "feasibility", {"schema_version": "1.0", "constraints": []}
            )
        ),
        "decision_program_hash": sha256_json(decision_program),
        "evidence_language": EvidenceLanguagePayload(witness_hash=sha256_json(witness.values)),
        "relevant_predicates": relevant,
        "relevant_predicate_closure_hash": sha256_json(relevant),
        "semantic_generated_gate_passed": None,
        "selected_operators": solution.selected_operators,
        "derived_predicates": solution.derived_predicates,
        "operator_closure": {
            "selected": sorted(solution.selected_operators),
            "required": sorted(closure - set(solution.selected_operators)),
            "derived_predicates": sorted(solution.derived_predicates),
        },
        "action_distinction_count": solution.required_pair_count,
        "total_cost": solution.total_cost,
        "objective_tuple": (
            solution.total_cost,
            len(solution.selected_operators),
            sorted(solution.selected_operators),
        ),
        "optimality": OptimalityPayload(
            claimed=solution.optimal,
            cost_proven=solution.optimal,
            count_proven=solution.optimal,
            lexical_proven=solution.optimal,
        ),
        "solver": solution.solver,
        "solver_status": solution.solver_status,
        "verification": VerificationPayload(
            method=("z3-counterexample-separation" if symbolic else "z3-and-finite-bruteforce"),
            no_counterexample_expected=solution.status is CompilerStatus.EXECUTABLE,
            finite_state_count=state_count,
            required_pair_count=solution.required_pair_count,
            optimality_claimed=solution.optimal,
            seed=loaded.config.seed,
        ),
    }


def _with_hash(model_type: type[Any], payload: dict[str, Any]) -> Certificate:
    unhashed = {
        **payload,
        "content_checksum": "0" * 64,
        "certificate_hash": "0" * 64,
    }
    model = model_type.model_validate(unhashed)
    body = model.model_dump(mode="json")
    body.pop("certificate_hash")
    body.pop("content_checksum")
    digest = sha256_json(body)
    payload["content_checksum"] = digest
    payload["certificate_hash"] = digest
    return cast(Certificate, model_type.model_validate(payload))


def build_certificate(
    loaded: LoadedCompilerProblem,
    solution: CompilerSolution,
) -> Certificate:
    """Construct the certificate subtype implied by a compiler solution."""

    if solution.status is CompilerStatus.UNSAT_EVIDENCE_LANGUAGE:
        raise CompilationError(
            "UNSAT_EVIDENCE_LANGUAGE cannot be certified as executable, incomplete, or OOS"
        )
    payload = _base_payload(loaded, solution)
    if solution.status is CompilerStatus.EXECUTABLE:
        payload.update(
            {
                "certificate_type": "EXECUTABLE",
                "guidelines_covered": sorted(
                    f"{item.id}@{item.version}" for item in loaded.guidelines
                ),
                "decision_programs_covered": sorted(
                    f"{item.id}@{item.version}" for item in loaded.guidelines
                ),
                "action_distinctions_covered": solution.required_pair_count or 0,
                "clauses_provenance": sorted(
                    f"{guideline.id}:{rule.id}"
                    for guideline in loaded.guidelines
                    for rule in guideline.rules
                ),
                "action_programs": {
                    guideline.id: sorted(rule.id for rule in guideline.rules)
                    for guideline in loaded.guidelines
                },
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
