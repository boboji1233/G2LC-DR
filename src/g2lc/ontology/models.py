"""Typed evidence-ontology models."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from g2lc.types import (
    JsonScalar,
    Modality,
    Observability,
    Provenance,
    StrictModel,
    ValueType,
)


class EvidencePredicate(StrictModel):
    """One finite clinical-evidence variable in the declared language."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    value_type: ValueType
    allowed_values: list[JsonScalar] = Field(min_length=1)
    modalities: list[Modality] = Field(min_length=1)
    observability: Observability
    parent_predicate: str | None = None
    requires: list[str] = Field(default_factory=list)
    known_ambiguities: list[str] = Field(default_factory=list)
    recommended_operators: list[str] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("allowed_values")
    @classmethod
    def unique_domain(cls, values: list[JsonScalar]) -> list[JsonScalar]:
        keys = [(type(value).__name__, value) for value in values]
        if len(set(keys)) != len(keys):
            raise ValueError("allowed_values must be unique")
        if any(value is None for value in values):
            raise ValueError("None/UNKNOWN is not a domain value; it is evidence absence")
        return values

    @model_validator(mode="after")
    def domain_matches_type(self) -> EvidencePredicate:
        values = self.allowed_values
        if self.value_type == ValueType.BOOLEAN and not all(
            isinstance(value, bool) for value in values
        ):
            raise ValueError("BOOLEAN predicate domain must contain only booleans")
        if self.value_type == ValueType.INTEGER and not all(
            isinstance(value, int) and not isinstance(value, bool) for value in values
        ):
            raise ValueError("INTEGER predicate domain must contain only integers")
        if self.value_type == ValueType.NUMBER and not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
        ):
            raise ValueError("NUMBER predicate domain must contain only numbers")
        return self


class EvidenceOntology(StrictModel):
    """A versioned finite evidence language."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    ontology_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    predicates: list[EvidencePredicate] = Field(min_length=1)
    provenance: Provenance

    @model_validator(mode="after")
    def unique_predicates(self) -> EvidenceOntology:
        ids = [predicate.id for predicate in self.predicates]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate predicate ids: {duplicates}")
        return self

    def predicate_map(self) -> dict[str, EvidencePredicate]:
        """Return a fresh deterministic ID lookup."""

        return {predicate.id: predicate for predicate in self.predicates}

    def predicate(self, predicate_id: str) -> EvidencePredicate:
        """Resolve a predicate or raise ``KeyError``."""

        return self.predicate_map()[predicate_id]
