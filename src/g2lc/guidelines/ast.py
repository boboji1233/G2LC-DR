"""Pydantic models for the guideline expression language."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from g2lc.types import JsonScalar, Modality, Provenance, StrictModel


class And(StrictModel):
    """Three-valued conjunction."""

    op: Literal["and"] = "and"
    terms: list[Expression] = Field(min_length=1)


class Or(StrictModel):
    """Three-valued disjunction."""

    op: Literal["or"] = "or"
    terms: list[Expression] = Field(min_length=1)


class Not(StrictModel):
    """Three-valued negation."""

    op: Literal["not"] = "not"
    term: Expression


class Equals(StrictModel):
    """Predicate equality."""

    op: Literal["equals"] = "equals"
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: JsonScalar

    @field_validator("value")
    @classmethod
    def value_cannot_be_unknown(cls, value: JsonScalar) -> JsonScalar:
        if value is None:
            raise ValueError("compare with Known instead of comparing to null/UNKNOWN")
        return value


class GreaterEqual(StrictModel):
    """Numeric greater-than-or-equal comparison."""

    op: Literal["greater_equal"] = "greater_equal"
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: int | float


class LessEqual(StrictModel):
    """Numeric less-than-or-equal comparison."""

    op: Literal["less_equal"] = "less_equal"
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: int | float


class InSet(StrictModel):
    """Finite set-membership comparison."""

    op: Literal["in_set"] = "in_set"
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    values: list[JsonScalar] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def set_values_are_known(cls, values: list[JsonScalar]) -> list[JsonScalar]:
        if any(value is None for value in values):
            raise ValueError("InSet cannot contain null/UNKNOWN")
        if len({(type(value).__name__, value) for value in values}) != len(values):
            raise ValueError("InSet values must be unique")
        return values


class Known(StrictModel):
    """Test whether evidence is present rather than unknown."""

    op: Literal["known"] = "known"
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


Expression: TypeAlias = Annotated[
    And | Or | Not | Equals | GreaterEqual | LessEqual | InSet | Known,
    Field(discriminator="op"),
]

And.model_rebuild(_types_namespace={"Expression": Expression})
Or.model_rebuild(_types_namespace={"Expression": Expression})
Not.model_rebuild(_types_namespace={"Expression": Expression})


class ClinicalAction(StrictModel):
    """A structured guideline output such as grade/referral/acquisition action."""

    values: dict[str, str] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def nonempty_action_values(cls, values: dict[str, str]) -> dict[str, str]:
        if any(not key or not value for key, value in values.items()):
            raise ValueError("clinical action keys and values must be nonempty")
        return values


class GuidelineClause(StrictModel):
    """One prioritized executable clause with clause-level provenance."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    priority: int = Field(ge=0)
    when: Expression
    action: ClinicalAction
    provenance: Provenance


class Guideline(StrictModel):
    """A versioned guideline program over the evidence language."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    effective_date: str
    modality_scope: list[Modality] = Field(min_length=1)
    action_schema: list[str] = Field(min_length=1)
    rules: list[GuidelineClause] = Field(min_length=1)
    default_action: ClinicalAction | None = None
    provenance: Provenance

    @field_validator("action_schema")
    @classmethod
    def unique_action_schema(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("action_schema entries must be unique")
        return values

    @model_validator(mode="after")
    def unique_clause_ids(self) -> Guideline:
        ids = [rule.id for rule in self.rules]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate clause ids: {duplicates}")
        return self


class GuidelineBundle(StrictModel):
    """A source file containing one or more target guideline programs."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    synthetic: bool = False
    guidelines: list[Guideline] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_guidelines(self) -> GuidelineBundle:
        keys = [(guideline.id, guideline.version) for guideline in self.guidelines]
        duplicates = sorted({item for item in keys if keys.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate guideline id/version pairs: {duplicates}")
        return self


def expression_predicates(expression: Expression) -> set[str]:
    """Return all predicate IDs referenced by an expression."""

    if isinstance(expression, (And, Or)):
        return set().union(*(expression_predicates(term) for term in expression.terms))
    if isinstance(expression, Not):
        return expression_predicates(expression.term)
    return {expression.predicate}


def guideline_predicates(guideline: Guideline) -> set[str]:
    """Return every evidence predicate referenced by a guideline."""

    return set().union(*(expression_predicates(rule.when) for rule in guideline.rules))
