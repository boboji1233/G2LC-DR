"""Typed annotation-operator and derivation-rule models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from g2lc.types import JsonScalar, Modality, Provenance, StrictModel


class Granularity(StrEnum):
    """Annotation information granularity."""

    IMAGE_GRADE = "IMAGE_GRADE"
    PRESENCE = "PRESENCE"
    ORDINAL_BURDEN = "ORDINAL_BURDEN"
    COUNT_BIN = "COUNT_BIN"
    EXACT_COUNT = "EXACT_COUNT"
    QUADRANT = "QUADRANT"
    POINT = "POINT"
    PIXEL_MASK = "PIXEL_MASK"
    QUALITY = "QUALITY"
    SPATIAL = "SPATIAL"
    ANATOMY = "ANATOMY"


class OperatorAvailability(StrEnum):
    """Whether an operator is selectable in the current project."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"


class AnnotationOperator(StrictModel):
    """One candidate annotation protocol.

    A ``value_mapping`` explicitly coarsens a predicate domain (for example count bin
    to presence). Mapped outputs do not imply access to the uncoarsened predicate.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    output_predicates: list[str] = Field(default_factory=list)
    granularity: Granularity
    modalities: list[Modality] = Field(min_length=1)
    cost: float = Field(ge=0, allow_inf_nan=False)
    instability: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    prerequisites: list[str] = Field(default_factory=list)
    derivable_outputs: list[str] = Field(default_factory=list)
    value_mappings: dict[str, dict[str, JsonScalar]] = Field(default_factory=dict)
    availability: OperatorAvailability = OperatorAvailability.AVAILABLE
    provenance: Provenance

    @field_validator("output_predicates", "prerequisites", "derivable_outputs")
    @classmethod
    def unique_predicate_lists(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("predicate lists must not contain duplicates")
        return values

    @model_validator(mode="after")
    def mappings_target_outputs(self) -> AnnotationOperator:
        unknown = sorted(set(self.value_mappings) - set(self.output_predicates))
        if unknown:
            raise ValueError(f"value_mappings target non-output predicates: {unknown}")
        return self


class OperatorCatalogue(StrictModel):
    """A versioned collection of candidate annotation operators."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    catalogue_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    synthetic: bool = False
    operators: list[AnnotationOperator] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def unique_operator_ids(self) -> OperatorCatalogue:
        ids = [operator.id for operator in self.operators]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate operator ids: {duplicates}")
        return self

    def operator_map(self) -> dict[str, AnnotationOperator]:
        """Return a fresh deterministic ID lookup."""

        return {operator.id: operator for operator in self.operators}


class DerivationRule(StrictModel):
    """A typed implication between exactly observed evidence predicates."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    input_predicates: list[str] = Field(min_length=1)
    output_predicates: list[str] = Field(min_length=1)
    provenance: Provenance

    @field_validator("input_predicates", "output_predicates")
    @classmethod
    def unique_derivation_lists(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("derivation predicate lists must not contain duplicates")
        return values


class DerivationGraph(StrictModel):
    """A versioned, acyclic set of evidence derivations."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    graph_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    rules: list[DerivationRule] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def unique_rule_ids(self) -> DerivationGraph:
        ids = [rule.id for rule in self.rules]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate derivation rule ids: {duplicates}")
        return self
