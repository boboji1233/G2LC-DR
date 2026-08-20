"""Shared strongly typed domain primitives.

Missing evidence is represented by ``None`` in an :class:`EvidenceState`. It is never
coerced to a false value or to an absent clinical finding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

JsonScalar: TypeAlias = str | int | float | bool | None


class StrictModel(BaseModel):
    """Base model that rejects unrecognised external fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Modality(StrEnum):
    """Evidence acquisition modality."""

    CFP = "CFP"
    UWF = "UWF"
    OCT = "OCT"
    CLINICAL = "CLINICAL"


class Observability(StrEnum):
    """Whether a predicate belongs to the declared image evidence language."""

    IMAGE_OBSERVABLE = "IMAGE_OBSERVABLE"
    EXTERNAL_CLINICAL = "EXTERNAL_CLINICAL"
    DERIVED = "DERIVED"


class ValueType(StrEnum):
    """Finite evidence domain representation."""

    BOOLEAN = "BOOLEAN"
    CATEGORICAL = "CATEGORICAL"
    ORDINAL = "ORDINAL"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"


class EvidenceLabel(StrEnum):
    """Dataset label state; UNKNOWN is distinct from NEGATIVE."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


class ReviewStatus(StrEnum):
    """Provenance review state for knowledge artifacts."""

    SYNTHETIC = "SYNTHETIC"
    DRAFT = "DRAFT"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    CLINICIAN_REVIEWED = "CLINICIAN_REVIEWED"


class Provenance(StrictModel):
    """Versioned origin metadata for evidence, rules, and operators."""

    source: str = Field(min_length=1)
    source_url: str | None = None
    source_section: str | None = None
    version: str = Field(min_length=1)
    review_status: ReviewStatus
    note: str | None = None


class EvidenceState(StrictModel):
    """A possibly incomplete evidence assignment.

    ``None`` means unknown. Values absent from the mapping are also unknown.
    """

    values: dict[str, JsonScalar] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def validate_keys(cls, values: dict[str, JsonScalar]) -> dict[str, JsonScalar]:
        for key in values:
            if not key or key.strip() != key:
                raise ValueError(f"invalid evidence predicate key {key!r}")
        return values

    def value(self, predicate_id: str) -> JsonScalar:
        """Return a value or explicit unknown for a missing key."""

        return self.values.get(predicate_id)

    def known(self, predicate_id: str) -> bool:
        """Return whether a predicate has a non-unknown value."""

        return self.value(predicate_id) is not None


def scalar_key(value: JsonScalar) -> str:
    """Return a stable mapping key without conflating booleans and integers."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def json_scalar(value: Any) -> JsonScalar:
    """Validate a dynamically loaded scalar."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"expected a JSON scalar, got {type(value).__name__}")
