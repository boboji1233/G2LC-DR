"""Independent certificate verification from authoritative source files."""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

from pydantic import Field, TypeAdapter, ValidationError

from g2lc.certificates.models import (
    Certificate,
    ExecutabilityCertificate,
    MissingEvidenceCertificate,
    OutOfSpecificationCertificate,
)
from g2lc.compiler.counterexample import find_counterexample
from g2lc.compiler.exact import brute_force_optimum
from g2lc.compiler.problem import build_finite_problem, load_compiler_problem, preflight_oos
from g2lc.errors import CertificateVerificationError
from g2lc.guidelines.provenance import guideline_hash
from g2lc.operators.cost import scheme_cost
from g2lc.operators.derivation import exact_observed_predicates
from g2lc.operators.models import OperatorAvailability
from g2lc.types import StrictModel
from g2lc.utils.io import load_json, sha256_file, sha256_json, validation_error

CERTIFICATE_ADAPTER: TypeAdapter[Certificate] = TypeAdapter(Certificate)


class VerificationReport(StrictModel):
    """Human- and machine-readable verifier outcome."""

    valid: bool
    certificate_type: str
    checks: list[str] = Field(default_factory=list)


def _certificate_root(certificate_path: Path, project_config: str) -> Path:
    project = Path(project_config)
    if project.is_absolute() and project.is_file():
        return project.parent
    for candidate in (certificate_path.parent, *certificate_path.parents, Path.cwd().resolve()):
        if (candidate / project).is_file():
            return candidate
    raise CertificateVerificationError(
        f"cannot resolve recorded project_config {project_config!r} from certificate location"
    )


def _check_hash(certificate: Certificate) -> None:
    body = certificate.model_dump(mode="json")
    claimed = cast(str, body.pop("certificate_hash"))
    actual = sha256_json(body)
    if actual != claimed:
        raise CertificateVerificationError(
            f"certificate hash mismatch: claimed {claimed}, computed {actual}"
        )


def verify_certificate(path: str | Path) -> VerificationReport:
    """Re-load, re-hash and independently verify a compiler certificate."""

    certificate_path = Path(path).resolve()
    try:
        certificate = CERTIFICATE_ADAPTER.validate_python(load_json(certificate_path))
    except ValidationError as exc:
        raise validation_error(certificate_path, exc) from exc
    _check_hash(certificate)
    checks = ["certificate_hash"]
    root = _certificate_root(certificate_path, certificate.project_config)
    for source in certificate.source_hashes:
        source_path = Path(source.path)
        resolved = source_path if source_path.is_absolute() else (root / source_path)
        if not resolved.is_file():
            raise CertificateVerificationError(f"recorded source is missing: {source.path}")
        actual_hash = sha256_file(resolved)
        if actual_hash != source.sha256:
            raise CertificateVerificationError(
                f"source hash mismatch for {source.path}: claimed {source.sha256}, "
                f"computed {actual_hash}"
            )
    checks.append("source_hashes")
    project_path = Path(certificate.project_config)
    if not project_path.is_absolute():
        project_path = root / project_path
    loaded = load_compiler_problem(project_path)
    if loaded.config.project_id != certificate.project_id:
        raise CertificateVerificationError("project ID does not match reloaded source")
    expected_guideline_hashes = {
        f"{guideline.id}@{guideline.version}": guideline_hash(guideline)
        for guideline in sorted(loaded.guidelines, key=lambda item: (item.id, item.version))
    }
    semantic_hashes_match = (
        certificate.ontology_hash == sha256_file(loaded.ontology_path)
        and certificate.operator_catalogue_hash == sha256_file(loaded.operator_path)
        and certificate.derivation_graph_hash == sha256_file(loaded.derivation_path)
        and certificate.guideline_hashes == expected_guideline_hashes
    )
    if not semantic_hashes_match:
        raise CertificateVerificationError(
            "semantic hash payload for ontology/guidelines/operators/derivations does not "
            "match reloaded sources"
        )
    checks.append("semantic_hashes")

    if isinstance(certificate, ExecutabilityCertificate):
        available = {operator.id: operator for operator in loaded.available_operators()}
        unknown = sorted(set(certificate.selected_operators) - available.keys())
        if unknown:
            raise CertificateVerificationError(
                f"certificate selects unavailable/unknown operators: {unknown}"
            )
        selected = [available[item] for item in certificate.selected_operators]
        actual_cost = scheme_cost(selected, loaded.config.instability_weight)
        if not math.isclose(actual_cost, certificate.total_cost, abs_tol=1e-9):
            raise CertificateVerificationError(
                f"selected operator cost mismatch: claimed {certificate.total_cost}, "
                f"got {actual_cost}"
            )
        actual_derived = sorted(exact_observed_predicates(selected, loaded.graph))
        if actual_derived != certificate.derived_predicates:
            raise CertificateVerificationError("derived predicate payload is incorrect")
        counterexample = find_counterexample(loaded, certificate.selected_operators)
        if counterexample is not None:
            witness = counterexample.model_dump(mode="json")
            raise CertificateVerificationError(
                f"Z3 found an action-separating counterexample: {witness}"
            )
        checks.extend(["selected_cost", "derived_predicates", "z3_no_counterexample"])
        if certificate.verification.optimality_claimed:
            finite = build_finite_problem(loaded)
            optimum = brute_force_optimum(finite)
            if optimum is None or not math.isclose(
                optimum[1], certificate.total_cost, abs_tol=1e-9
            ):
                raise CertificateVerificationError(
                    f"brute-force optimum does not match certificate: {optimum}"
                )
            checks.append("bruteforce_optimum")
    elif isinstance(certificate, MissingEvidenceCertificate):
        all_available = [operator.id for operator in loaded.available_operators()]
        counterexample = find_counterexample(loaded, all_available)
        if counterexample is None:
            raise CertificateVerificationError(
                "all available operators execute the guidelines; INCOMPLETE is unsound"
            )
        finite = build_finite_problem(loaded, include_repair=True)
        optimum = brute_force_optimum(finite)
        if certificate.minimal_additions:
            if optimum is None:
                raise CertificateVerificationError(
                    "claimed repair exists but augmented catalogue is insufficient"
                )
            operator_map = {operator.id: operator for operator in finite.operators}
            optimum_unavailable = sorted(
                item
                for item in optimum[0]
                if operator_map[item].availability is not OperatorAvailability.AVAILABLE
            )
            if optimum_unavailable != certificate.minimal_additions:
                raise CertificateVerificationError(
                    f"minimal repair mismatch: claimed {certificate.minimal_additions}, "
                    f"independent optimum {optimum_unavailable}"
                )
        checks.extend(["incomplete_counterexample", "bruteforce_repair"])
    elif isinstance(certificate, OutOfSpecificationCertificate):
        actual_issues = preflight_oos(loaded)
        actual_predicates = sorted(item[0] for item in actual_issues)
        claimed_predicates = sorted(item.predicate_id for item in certificate.findings)
        if actual_predicates != claimed_predicates:
            raise CertificateVerificationError(
                f"OOS findings mismatch: claimed {claimed_predicates}, actual {actual_predicates}"
            )
        checks.append("oos_recomputed")
    else:
        raise AssertionError(f"unhandled certificate type {type(certificate).__name__}")
    return VerificationReport(
        valid=True,
        certificate_type=certificate.certificate_type,
        checks=checks,
    )
