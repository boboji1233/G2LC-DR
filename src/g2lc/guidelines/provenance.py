"""Deterministic guideline and clause provenance hashes."""

from __future__ import annotations

from g2lc.guidelines.ast import Guideline, GuidelineClause
from g2lc.utils.io import sha256_json


def guideline_hash(guideline: Guideline) -> str:
    """Hash semantic guideline content including provenance metadata."""

    return sha256_json(guideline.model_dump(mode="json"))


def clause_hash(clause: GuidelineClause) -> str:
    """Hash one executable clause including its source/version metadata."""

    return sha256_json(clause.model_dump(mode="json"))
