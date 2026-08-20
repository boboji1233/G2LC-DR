"""Semantic ontology validation beyond field-level schema checks."""

from __future__ import annotations

from g2lc.errors import OntologyValidationError
from g2lc.ontology.models import EvidenceOntology


def validate_ontology(ontology: EvidenceOntology) -> None:
    """Check references and reject parent/requirement cycles."""

    predicates = ontology.predicate_map()
    for predicate in ontology.predicates:
        references = list(predicate.requires)
        if predicate.parent_predicate is not None:
            references.append(predicate.parent_predicate)
        unknown = sorted(set(references) - predicates.keys())
        if unknown:
            raise OntologyValidationError(
                f"predicate {predicate.id!r} references unknown predicates {unknown}"
            )
        if predicate.id in references:
            raise OntologyValidationError(f"predicate {predicate.id!r} references itself")

    edges: dict[str, list[str]] = {
        item.id: sorted(
            set(item.requires)
            | ({item.parent_predicate} if item.parent_predicate is not None else set())
        )
        for item in ontology.predicates
    }
    _reject_cycles(edges, "ontology dependency")


def _reject_cycles(edges: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            start = trail.index(node)
            cycle = [*trail[start:], node]
            raise OntologyValidationError(f"{label} cycle: {' -> '.join(cycle)}")
        if node in visited:
            return
        visiting.add(node)
        for target in edges[node]:
            visit(target, [*trail, target])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node, [node])
