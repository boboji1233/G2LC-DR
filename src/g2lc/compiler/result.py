"""Typed compiler results shared by solver implementations."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from g2lc.types import EvidenceState, StrictModel


class CompilerStatus(StrEnum):
    """Scientific outcome independent of a solver's internal status."""

    EXECUTABLE = "EXECUTABLE"
    INCOMPLETE = "INCOMPLETE"
    OUT_OF_SPEC = "OUT_OF_SPEC"
    UNSAT_EVIDENCE_LANGUAGE = "UNSAT_EVIDENCE_LANGUAGE"


class SolverKind(StrEnum):
    """Available compilation algorithms."""

    EXACT = "exact"
    GREEDY = "greedy"
    SEPARATION = "separation"


class SolverStatus(StrEnum):
    """Portable solver status vocabulary."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    LIMIT_REACHED = "LIMIT_REACHED"


class Counterexample(StrictModel):
    """Two observationally equal states with different guideline actions."""

    left: EvidenceState
    right: EvidenceState
    differing_guidelines: list[str] = Field(min_length=1)
    left_actions: dict[str, str]
    right_actions: dict[str, str]


class OutOfSpecFinding(StrictModel):
    """An unsupported predicate and its source clauses."""

    predicate_id: str
    reason: str
    required_modalities: list[str] = Field(default_factory=list)
    source_clauses: list[str] = Field(default_factory=list)


class CompilerSolution(StrictModel):
    """A solver result before certificate serialization."""

    status: CompilerStatus
    solver: SolverKind
    solver_status: SolverStatus
    selected_operators: list[str] = Field(default_factory=list)
    derived_predicates: list[str] = Field(default_factory=list)
    total_cost: Decimal = Field(default=Decimal(0), ge=0)
    optimal: bool = False
    separated_pair_count: int = Field(default=0, ge=0)
    required_pair_count: int | None = Field(default=0, ge=0)
    iterations: int = Field(default=0, ge=0)
    counterexamples: list[Counterexample] = Field(default_factory=list)
    missing_predicates: list[str] = Field(default_factory=list)
    minimal_additions: list[str] = Field(default_factory=list)
    minimum_repair_cost: Decimal | None = Field(default=None, ge=0)
    out_of_spec: list[OutOfSpecFinding] = Field(default_factory=list)
