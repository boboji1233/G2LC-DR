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
    """Dataset label state; UNKNOWN and AMBIGUOUS are never negative."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WEAK = "WEAK"
    DERIVED = "DERIVED"


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
    """Return a stable typed mapping key.

    JSON and Python both make it easy to conflate ``true``, ``1``, ``1.0`` and
    ``"1"``.  Operator mappings and solver domain indices are semantic data, so the
    runtime type is part of their key.
    """

    if value is None:
        return "null:"
    if isinstance(value, bool):
        return f"bool:{str(value).lower()}"
    if isinstance(value, str):
        return f"str:{value}"
    if isinstance(value, int):
        return f"int:{value}"
    if isinstance(value, float):
        return f"float:{value!r}"
    raise TypeError(f"expected a JSON scalar, got {type(value).__name__}")


def scalar_equal(left: JsonScalar, right: JsonScalar) -> bool:
    """Compare finite-domain values without Python's bool/int coercion."""

    return type(left) is type(right) and left == right


def json_scalar(value: Any) -> JsonScalar:
    """Validate a dynamically loaded scalar."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"expected a JSON scalar, got {type(value).__name__}")
