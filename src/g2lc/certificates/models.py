"""Versioned, deterministic certificate schemas."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from g2lc.compiler.result import Counterexample, OutOfSpecFinding, SolverKind, SolverStatus
from g2lc.types import StrictModel


class SourceHash(StrictModel):
    """Authoritative source path and byte hash."""

    role: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VerificationPayload(StrictModel):
    """Solver-independent checks expected from a verifier."""

    method: str
    no_counterexample_expected: bool
    finite_state_count: int | None = Field(default=None, ge=0)
    required_pair_count: int | None = Field(default=None, ge=0)
    optimality_claimed: bool = False
    seed: int = Field(ge=0)


class CertificateBase(StrictModel):
    """Fields shared by all certificate outcomes."""

    schema_version: Literal["1.0"] = "1.0"
    certificate_type: str
    project_id: str
    project_config: str
    source_hashes: list[SourceHash]
    ontology_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    guideline_hashes: dict[str, str]
    operator_catalogue_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    derivation_graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_operators: list[str] = Field(default_factory=list)
    derived_predicates: list[str] = Field(default_factory=list)
    total_cost: float = Field(default=0, ge=0)
    solver: SolverKind
    solver_status: SolverStatus
    verification: VerificationPayload
    certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutabilityCertificate(CertificateBase):
    """A scheme asserted to execute every target guideline clause."""

    certificate_type: Literal["EXECUTABLE"] = "EXECUTABLE"
    guidelines_covered: list[str]
    clauses_covered: list[str]


class MissingEvidenceCertificate(CertificateBase):
    """An in-scope project lacking currently available annotation evidence."""

    certificate_type: Literal["INCOMPLETE"] = "INCOMPLETE"
    uncovered_counterexamples: list[Counterexample] = Field(min_length=1)
    missing_predicates: list[str] = Field(min_length=1)
    minimal_additions: list[str] = Field(default_factory=list)
    minimum_repair_cost: float | None = Field(default=None, ge=0)


class OutOfSpecificationCertificate(CertificateBase):
    """A guideline whose evidence lies outside the declared modality/language."""

    certificate_type: Literal["OUT_OF_SPEC"] = "OUT_OF_SPEC"
    findings: list[OutOfSpecFinding] = Field(min_length=1)


Certificate: TypeAlias = Annotated[
    ExecutabilityCertificate | MissingEvidenceCertificate | OutOfSpecificationCertificate,
    Field(discriminator="certificate_type"),
]
