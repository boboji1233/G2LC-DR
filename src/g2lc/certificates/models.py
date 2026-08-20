"""Versioned, deterministic certificate schemas."""

from __future__ import annotations

from decimal import Decimal
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


class OptimalityPayload(StrictModel):
    """Explicitly separate feasibility from each proved objective tier."""

    claimed: bool = False
    cost_proven: bool = False
    count_proven: bool = False
    lexical_proven: bool = False


class EvidenceLanguagePayload(StrictModel):
    """A non-vacuity witness independently recomputable from source semantics."""

    nonempty: Literal[True] = True
    method: Literal["z3-sat"] = "z3-sat"
    witness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CertificateBase(StrictModel):
    """Fields shared by all certificate outcomes."""

    schema_version: Literal["1.1"] = "1.1"
    certificate_type: str
    semantic_contract: Literal["action-only-decision-sufficiency-v1.1"]
    proof_scope: Literal["FINITE_EXHAUSTIVE", "SMT_UNIVERSAL", "BOUNDED"]
    assumptions: list[str]
    project_id: str
    project_config: str
    source_hashes: list[SourceHash]
    ontology_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    guideline_hashes: dict[str, str]
    operator_catalogue_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    derivation_graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feasibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_language: EvidenceLanguagePayload
    relevant_predicates: list[str]
    relevant_predicate_closure_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_generated_gate_passed: bool | None = None
    selected_operators: list[str] = Field(default_factory=list)
    derived_predicates: list[str] = Field(default_factory=list)
    operator_closure: dict[str, list[str]]
    action_distinction_count: int | None = Field(default=None, ge=0)
    total_cost: Decimal = Field(default=Decimal(0), ge=0)
    objective_tuple: tuple[Decimal, int, list[str]]
    optimality: OptimalityPayload
    solver: SolverKind
    solver_status: SolverStatus
    verification: VerificationPayload
    content_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutabilityCertificate(CertificateBase):
    """A scheme asserted to preserve every target decision distinction."""

    certificate_type: Literal["EXECUTABLE"] = "EXECUTABLE"
    guidelines_covered: list[str]
    decision_programs_covered: list[str]
    action_distinctions_covered: int = Field(ge=0)
    clauses_provenance: list[str]
    action_programs: dict[str, list[str]]


class MissingEvidenceCertificate(CertificateBase):
    """An in-scope project lacking currently available annotation evidence."""

    certificate_type: Literal["INCOMPLETE"] = "INCOMPLETE"
    uncovered_counterexamples: list[Counterexample] = Field(min_length=1)
    missing_predicates: list[str] = Field(min_length=1)
    minimal_additions: list[str] = Field(default_factory=list)
    minimum_repair_cost: Decimal | None = Field(default=None, ge=0)


class OutOfSpecificationCertificate(CertificateBase):
    """A guideline whose evidence lies outside the declared modality/language."""

    certificate_type: Literal["OUT_OF_SPEC"] = "OUT_OF_SPEC"
    findings: list[OutOfSpecFinding] = Field(min_length=1)


Certificate: TypeAlias = Annotated[
    ExecutabilityCertificate | MissingEvidenceCertificate | OutOfSpecificationCertificate,
    Field(discriminator="certificate_type"),
]
