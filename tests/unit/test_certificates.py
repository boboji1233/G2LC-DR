from __future__ import annotations

import json

import pytest

from g2lc.certificates.verifier import verify_certificate
from g2lc.certificates.writer import build_certificate, write_certificate
from g2lc.compiler.api import compile_problem
from g2lc.compiler.result import SolverKind
from g2lc.errors import CertificateVerificationError
from g2lc.utils.io import sha256_json


def _write(problem, tmp_path, solver=SolverKind.EXACT):  # type: ignore[no-untyped-def]
    solution = compile_problem(problem, solver)
    certificate = build_certificate(problem, solution)
    path = tmp_path / "certificate.json"
    write_certificate(certificate, path)
    return certificate, path


def test_valid_executable_certificate(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    assert verify_certificate(path).valid


def test_valid_missing_certificate(missing_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(missing_problem, tmp_path)
    report = verify_certificate(path)
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
    with pytest.raises(CertificateVerificationError, match="certificate hash mismatch"):
        verify_certificate(path)


def test_tampered_hash_rejected(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["certificate_hash"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="hash mismatch"):
        verify_certificate(path)


def test_rehashed_semantic_hash_tamper_is_rejected(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, path = _write(minimal_problem, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ontology_hash"] = "0" * 64
    body = dict(data)
    body.pop("certificate_hash")
    data["certificate_hash"] = sha256_json(body)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CertificateVerificationError, match="semantic hash"):
        verify_certificate(path)


def test_certificate_serialization_is_deterministic(minimal_problem, tmp_path) -> None:  # type: ignore[no-untyped-def]
    first, first_path = _write(minimal_problem, tmp_path / "a")
    second, second_path = _write(minimal_problem, tmp_path / "b")
    assert first.certificate_hash == second.certificate_hash
    assert first_path.read_bytes() == second_path.read_bytes()
