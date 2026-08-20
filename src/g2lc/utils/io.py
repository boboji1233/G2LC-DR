"""Deterministic source loading, path handling, and hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from yaml.error import MarkedYAMLError

from g2lc.errors import SourceValidationError


def load_yaml(path: str | Path) -> Any:
    """Load YAML safely and preserve useful parser line/column context."""

    source = Path(path)
    if not source.is_file():
        raise SourceValidationError("file does not exist", path=source)
    try:
        with source.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except MarkedYAMLError as exc:
        mark = exc.problem_mark
        raise SourceValidationError(
            exc.problem or "invalid YAML",
            path=source,
            line=(mark.line + 1) if mark is not None else None,
            column=(mark.column + 1) if mark is not None else None,
        ) from exc
    except UnicodeDecodeError as exc:
        raise SourceValidationError("file is not valid UTF-8", path=source) from exc
    if value is None:
        raise SourceValidationError("document is empty", path=source)
    return value


def load_json(path: str | Path) -> Any:
    """Load JSON with path and line context."""

    source = Path(path)
    if not source.is_file():
        raise SourceValidationError("file does not exist", path=source)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceValidationError(
            exc.msg, path=source, line=exc.lineno, column=exc.colno
        ) from exc


def validation_error(path: str | Path, exc: ValidationError) -> SourceValidationError:
    """Convert a Pydantic error into a compact path-aware user error."""

    errors = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"])
        errors.append(f"{location or '<root>'}: {item['msg']}")
    return SourceValidationError("; ".join(errors), path=path)


def model_from_yaml(model_type: type[BaseModel], path: str | Path) -> BaseModel:
    """Validate a YAML document against a Pydantic model class."""

    try:
        return model_type.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value deterministically."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Return a lower-case SHA-256 hex digest."""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash a file without normalizing its authoritative bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    """Hash canonical JSON."""

    return sha256_bytes(canonical_json(value).encode("utf-8"))


def resolve_from(base_file: str | Path, referenced: str | Path) -> Path:
    """Resolve a project-relative source path against its containing directory."""

    target = Path(referenced)
    if target.is_absolute():
        return target.resolve()
    return (Path(base_file).resolve().parent / target).resolve()
