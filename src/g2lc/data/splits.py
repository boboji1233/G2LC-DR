"""Deterministic split-lock hashing without opening locked target labels."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from g2lc.errors import SourceValidationError
from g2lc.types import StrictModel
from g2lc.utils.io import (
    canonical_json,
    load_json,
    load_yaml,
    sha256_file,
    sha256_json,
    validation_error,
)


class SplitLockConfig(StrictModel):
    """Patient/source-family split assignment with an audited override policy."""

    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    dataset_id: str
    source_family: str
    assignments: dict[str, str] = Field(min_length=1)
    maples_test_lock: bool = False
    output: str
    dangerous_override: bool = False
    override_reason: str | None = None
    audit_log: str = "docs/split_override_audit.jsonl"

    @model_validator(mode="after")
    def validate_lock_policy(self) -> SplitLockConfig:
        if any(not patient or not split for patient, split in self.assignments.items()):
            raise ValueError("patient IDs and split names must be nonempty")
        if self.dataset_id.startswith("maples") and not self.maples_test_lock:
            raise ValueError("MAPLES/MESSIDOR assignments must enable maples_test_lock")
        if self.maples_test_lock and set(self.assignments.values()) != {"test"}:
            raise ValueError("a MAPLES test lock may assign cases only to the test split")
        if self.dangerous_override and not self.override_reason:
            raise ValueError("dangerous_override requires a nonempty override_reason")
        return self


def compute_split_lock(path: str | Path) -> tuple[SplitLockConfig, str]:
    """Validate and hash a deterministic patient/source-family assignment."""

    try:
        config = SplitLockConfig.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise validation_error(path, exc) from exc
    normalized = config.model_dump(mode="json")
    for runtime_key in ("output", "dangerous_override", "override_reason", "audit_log"):
        normalized.pop(runtime_key)
    normalized["assignments"] = dict(sorted(config.assignments.items()))
    return config, sha256_json(normalized)


def write_split_lock(path: str | Path) -> tuple[SplitLockConfig, str, Path]:
    """Create an immutable lock or require an explicit audited dangerous override."""

    config_path = Path(path).resolve()
    config, digest = compute_split_lock(config_path)
    output = (config_path.parent / config.output).resolve()
    payload = {
        "schema_version": config.schema_version,
        "dataset_id": config.dataset_id,
        "source_family": config.source_family,
        "assignments": dict(sorted(config.assignments.items())),
        "maples_test_lock": config.maples_test_lock,
        "split_hash": digest,
        "config_sha256": sha256_file(config_path),
    }
    if output.exists():
        existing = load_json(output)
        if isinstance(existing, dict) and existing.get("split_hash") == digest:
            return config, digest, output
        if not config.dangerous_override:
            raise SourceValidationError(
                "split lock differs from the existing lock; set dangerous_override with a reason "
                "only after deliberate review",
                path=output,
            )
        audit_path = (config_path.parent / config.audit_log).resolve()
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dataset_id": config.dataset_id,
            "old_split_hash": existing.get("split_hash") if isinstance(existing, dict) else None,
            "new_split_hash": digest,
            "reason": config.override_reason,
            "config_sha256": sha256_file(config_path),
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return config, digest, output
