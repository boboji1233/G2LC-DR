"""Ontology YAML loading."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from g2lc.ontology.models import EvidenceOntology
from g2lc.ontology.validator import validate_ontology
from g2lc.utils.io import load_yaml, validation_error


def load_ontology(path: str | Path) -> EvidenceOntology:
    """Load and semantically validate an ontology source."""

    try:
        ontology = EvidenceOntology.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc
    validate_ontology(ontology)
    return ontology
