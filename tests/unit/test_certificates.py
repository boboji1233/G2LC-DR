from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import g2lc.certificates.writer as writer_module
from g2lc.certificates.models import Certificate
from g2lc.certificates.verifier import verify_certificate
from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.problem import LoadedCompilerProblem
from g2lc.compiler.result import SolverKind
from g2lc.errors import CertificateVerificationError
from g2lc.utils.io import sha256_json


def _write(
    problem: LoadedCompilerProblem,
    tmp_path: Path,
    solver: SolverKind = SolverKind.EXACT,
) -> tuple[Certificate, Path]:
    solution = compile_problem(problem, solver)
    certificate = build_certificate(problem, solution)
    path = tmp_path / "certificate.json"
    write_certificate(certificate, path)
    return certificate, path


def _rehash(data: dict[str, object]) -> None:
    body = dict(data)
    body.pop("certificate_hash")
    body.pop("content_checksum")
    digest = sha256_json(body)
    data["certificate_hash"] = digest
    data["content_checksum"] = digest


def test_valid_executable_certificate(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    assert verify_certificate(path).valid


def test_valid_missing_certificate(missing_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(missing_problem, tmp_path)
    report = verify_certificate(path)
    assert report.certificate_type == "INCOMPLETE"


def test_valid_symbolic_missing_certificate(missing_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    certificate, path = _write(missing_problem, tmp_path, SolverKind.SEPARATION)
    report = verify_certificate(path)
    assert certificate.proof_scope == "SMT_UNIVERSAL"
    assert certificate.verification.finite_state_count is None
    assert report.certificate_type == "INCOMPLETE"


def test_valid_oos_certificate(oos_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(oos_problem, tmp_path)
    report = verify_certificate(path)
    assert report.certificate_type == "OUT_OF_SPEC"


def test_tampered_selected_operators_rejected(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["selected_operators"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="content checksum mismatch"):
        verify_certificate(path)


def test_tampered_hash_rejected(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["certificate_hash"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="checksum mismatch"):
        verify_certificate(path)


def test_rehashed_semantic_hash_tamper_is_rejected(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ontology_hash"] = "0" * 64
    _rehash(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="semantic hash"):
        verify_certificate(path)


@pytest.mark.parametrize(
    "field",
    [
        "proof_scope",
        "assumptions",
        "feasibility_hash",
        "decision_program_hash",
        "evidence_language",
        "relevant_predicates",
        "relevant_predicate_closure_hash",
        "semantic_generated_gate_passed",
        "selected_operators",
        "derived_predicates",
        "operator_closure",
        "action_distinction_count",
        "total_cost",
        "objective_tuple",
        "optimality",
        "solver_status",
        "verification",
        "action_programs",
        "guidelines_covered",
        "decision_programs_covered",
        "action_distinctions_covered",
        "clauses_provenance",
        "source_hashes",
    ],
)
def test_rehashed_substantive_tamper_matrix_rejected(
    minimal_problem: Any, tmp_path: Path, field: str
) -> None:
    _, path = _write(minimal_problem, tmp_path / field)
    data = json.loads(path.read_text(encoding="utf-8"))
    if field == "proof_scope":
        data[field] = "BOUNDED"
    elif field == "assumptions":
        data[field] = []
    elif field in {
        "feasibility_hash",
        "decision_program_hash",
        "relevant_predicate_closure_hash",
    }:
        data[field] = "0" * 64
    elif field in {
        "selected_operators",
        "derived_predicates",
        "guidelines_covered",
        "decision_programs_covered",
        "clauses_provenance",
        "relevant_predicates",
    }:
        data[field] = []
    elif field in {"operator_closure", "action_programs"}:
        data[field] = {}
    elif field in {"action_distinction_count", "action_distinctions_covered"}:
        data[field] += 1
    elif field == "evidence_language":
        data[field]["witness_hash"] = "0" * 64
    elif field == "semantic_generated_gate_passed":
        data[field] = True
    elif field == "total_cost":
        data[field] = "999"
    elif field == "objective_tuple":
        data[field][0] = "999"
    elif field == "optimality":
        data[field]["lexical_proven"] = False
    elif field == "solver_status":
        data[field] = "FEASIBLE"
    elif field == "verification":
        data[field]["finite_state_count"] += 1
    elif field == "source_hashes":
        data[field][0]["sha256"] = "0" * 64
    else:  # pragma: no cover - parameter list is exhaustive
        raise AssertionError(field)
    _rehash(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError):
        verify_certificate(path)


def test_certificate_serialization_is_deterministic(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    first, first_path = _write(minimal_problem, tmp_path / "a")
    second, second_path = _write(minimal_problem, tmp_path / "b")
    assert first.certificate_hash == second.certificate_hash
    assert first_path.read_bytes() == second_path.read_bytes()


def test_symbolic_certificate_does_not_enumerate_without_a_symbolic_proof(
    minimal_problem: Any,
    oos_problem: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finite, _ = _write(minimal_problem, tmp_path / "finite")
    bounded, _ = _write(oos_problem, tmp_path / "bounded")
    monkeypatch.setattr(
        writer_module,
        "enumerate_states",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("enumerated")),
    )
    symbolic, symbolic_path = _write(minimal_problem, tmp_path / "symbolic", SolverKind.SEPARATION)

    assert finite.proof_scope == "FINITE_EXHAUSTIVE"
    assert finite.verification.finite_state_count is not None
    assert bounded.proof_scope == "BOUNDED"
    assert bounded.verification.finite_state_count is None
    assert symbolic.proof_scope == "SMT_UNIVERSAL"
    assert symbolic.verification.finite_state_count is None
    assert symbolic.action_distinction_count is None
    assert verify_certificate(symbolic_path).valid
