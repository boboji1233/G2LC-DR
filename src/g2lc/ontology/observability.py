"""Preflight checks for the declared evidence language and target modality."""

from __future__ import annotations

from dataclasses import dataclass

from g2lc.ontology.models import EvidenceOntology
from g2lc.types import Modality, Observability


@dataclass(frozen=True)
class ObservabilityIssue:
    """A predicate that cannot be executed in the current project scope."""

    predicate_id: str
    reason: str
    required_modalities: tuple[str, ...]


def find_observability_issues(
    ontology: EvidenceOntology,
    predicate_ids: set[str],
    target_modalities: set[Modality],
) -> list[ObservabilityIssue]:
    """Return deterministic OOS findings for unknown/external predicates."""

    predicates = ontology.predicate_map()
    issues: list[ObservabilityIssue] = []
    for predicate_id in sorted(predicate_ids):
        predicate = predicates.get(predicate_id)
        if predicate is None:
            issues.append(
                ObservabilityIssue(
                    predicate_id,
                    "predicate is not declared in the evidence ontology",
                    (),
                )
            )
            continue
        modalities = set(predicate.modalities)
        if predicate.observability == Observability.EXTERNAL_CLINICAL:
            issues.append(
                ObservabilityIssue(
                    predicate_id,
                    "predicate is external clinical evidence, not image-observable",
                    tuple(sorted(modality.value for modality in modalities)),
                )
            )
        elif not modalities.intersection(target_modalities):
            issues.append(
                ObservabilityIssue(
                    predicate_id,
                    "predicate is not observable in the project target modality",
                    tuple(sorted(modality.value for modality in modalities)),
                )
            )
    return issues
