"""Actionable domain errors exposed by loaders and the CLI."""

from __future__ import annotations

from pathlib import Path


class G2LCError(Exception):
    """Base class for expected, user-actionable failures."""


class SourceValidationError(G2LCError):
    """An external YAML/JSON source could not be parsed or validated."""

    def __init__(
        self,
        message: str,
        *,
        path: str | Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        location = str(path) if path is not None else "<input>"
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"{location}: {message}")
        self.path = Path(path) if path is not None else None
        self.line = line
        self.column = column


class OntologyValidationError(G2LCError):
    """The evidence ontology violates a semantic invariant."""


class GuidelineValidationError(G2LCError):
    """A guideline is malformed, contradictory, or references invalid evidence."""


class OperatorValidationError(G2LCError):
    """An annotation operator or derivation graph is invalid."""


class OutOfSpecificationError(G2LCError):
    """A request refers to evidence outside the declared language or modality."""


class CompilationError(G2LCError):
    """A compiler input or solver execution is invalid."""


class CertificateVerificationError(G2LCError):
    """A certificate failed independent verification."""
