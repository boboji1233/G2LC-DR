"""Deterministic split-lock hashing without opening locked target labels."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from g2lc.data.schemas import (
    ManifestTables,
    SplitPurpose,
    SplitRecord,
    json_value,
    stable_global_id,
)
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

CANONICAL_SOURCE_FAMILIES = {
    "ddr": "OIA_DDR",
    "mmrdr_cfp": "OIA_DDR",
    "mmrdr_uwf": "MMRDR_UWF",
    "messidor1": "MESSIDOR1",
    "maples_dr": "MESSIDOR1",
    "idrid": "IDRID",
    "deepdrid": "DEEPDRID",
    "fgadr": "FGADR",
    "retinal_lesions": "EYEPACS_RLDR",
    "tjdr": "TJDR",
}
MAPLES_DATASETS = {"maples_dr", "messidor1"}
MAPLES_LOCK_GROUP = "MAPLES_MESSIDOR_LOCKED_SAME_CASE_TEST"
FORBIDDEN_MAPLES_PURPOSES = {
    SplitPurpose.TRAIN,
    SplitPurpose.VALIDATION,
    SplitPurpose.CALIBRATION,
    SplitPurpose.THRESHOLD_SELECTION,
    SplitPurpose.HYPERPARAMETER_SELECTION,
    SplitPurpose.MODEL_SELECTION,
}


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


class RelationalSplitPlan(StrictModel):
    """Immutable Stage-2A split policy over image-level relational assignments."""

    schema_version: Literal["2.0"] = "2.0"
    assignments: list[SplitRecord] = Field(min_length=1)
    split_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", frozen=True)

    @model_validator(mode="after")
    def validate_governance(self) -> RelationalSplitPlan:
        errors = split_policy_errors(self.assignments)
        if errors:
            raise ValueError("; ".join(errors))
        expected = split_plan_hash(self.assignments)
        if self.split_hash is not None and self.split_hash != expected:
            raise ValueError("split_hash does not match canonical assignments")
        object.__setattr__(self, "split_hash", expected)
        return self


def split_plan_hash(assignments: list[SplitRecord]) -> str:
    """Hash sorted assignments without their record content hashes."""

    rows = [
        item.model_dump(mode="json", exclude={"content_hash"})
        for item in sorted(assignments, key=lambda row: row.global_split_id)
    ]
    return sha256_json({"schema_version": "2.0", "assignments": rows})


def _cross_split_errors(assignments: list[SplitRecord], field_name: str, label: str) -> list[str]:
    groups: dict[tuple[str, str], set[str]] = {}
    for row in assignments:
        value = getattr(row, field_name)
        if value is None:
            continue
        family = "GLOBAL" if field_name == "duplicate_group_id" else row.source_family
        groups.setdefault((family, value), set()).add(row.project_split)
    return [
        f"{label} {value!r} crosses splits {sorted(splits)}"
        for (_family, value), splits in sorted(groups.items())
        if len(splits) > 1
    ]


def split_policy_errors(assignments: list[SplitRecord]) -> list[str]:
    """Return every prohibited source-family, locked-test, and grouping configuration."""

    errors: list[str] = []
    image_ids = [row.global_image_id for row in assignments]
    duplicates = sorted({value for value in image_ids if image_ids.count(value) > 1})
    if duplicates:
        errors.append(f"images have multiple split assignments: {duplicates}")
    for row in assignments:
        expected_family = CANONICAL_SOURCE_FAMILIES.get(row.dataset_id)
        if expected_family is None:
            errors.append(f"unknown dataset split policy for {row.dataset_id!r}")
        elif row.source_family != expected_family:
            errors.append(
                f"{row.dataset_id} must use source_family {expected_family}, "
                f"not {row.source_family}"
            )
        if row.domain_id != row.source_family:
            errors.append(
                f"{row.dataset_id} cannot be presented as independent domain {row.domain_id!r}; "
                f"use {row.source_family!r}"
            )
        if row.dataset_id in MAPLES_DATASETS:
            if row.purpose in FORBIDDEN_MAPLES_PURPOSES or row.project_split.lower() != "test":
                errors.append(
                    f"{row.dataset_id} is locked same-case test data and cannot be used for "
                    f"{row.purpose.value}/{row.project_split}"
                )
            if not row.locked or row.lock_group_id != MAPLES_LOCK_GROUP:
                errors.append(f"{row.dataset_id} must carry the MAPLES/MESSIDOR lock group")
    for field, label in (
        ("patient_group_id", "patient group"),
        ("eye_group_id", "eye group"),
        ("visit_group_id", "visit group"),
        ("duplicate_group_id", "duplicate group"),
    ):
        errors.extend(_cross_split_errors(assignments, field, label))
    return sorted(set(errors))


def create_relational_split_plan(
    tables: ManifestTables, *, train_percent: int = 70, validation_percent: int = 15
) -> RelationalSplitPlan:
    """Create deterministic group-aware assignments without opening target labels."""

    if train_percent < 1 or validation_percent < 1 or train_percent + validation_percent >= 100:
        raise ValueError("train/validation percentages must be positive and leave a test partition")
    cases = {row.global_case_id: row for row in tables.cases}
    group_split: dict[tuple[str, str], tuple[str, SplitPurpose]] = {}
    assignments: list[SplitRecord] = []
    for image in sorted(tables.images, key=lambda row: row.global_image_id):
        case = cases[image.global_case_id]
        if image.source_dataset in MAPLES_DATASETS:
            project_split, purpose = "test", SplitPurpose.TEST
            lock_group_id = MAPLES_LOCK_GROUP
            locked = True
            lock_reason = "same-case multi-guideline final test; never selection data"
        else:
            group_id = case.patient_id or case.global_case_id
            group_key = (image.source_family, group_id)
            if group_key not in group_split:
                bucket = (
                    int(
                        sha256_json({"family": group_key[0], "group": group_key[1]})[:8],
                        16,
                    )
                    % 100
                )
                if bucket < train_percent:
                    group_split[group_key] = ("train", SplitPurpose.TRAIN)
                elif bucket < train_percent + validation_percent:
                    group_split[group_key] = ("validation", SplitPurpose.VALIDATION)
                else:
                    group_split[group_key] = ("test", SplitPurpose.TEST)
            project_split, purpose = group_split[group_key]
            lock_group_id = None
            locked = False
            lock_reason = None
        patient_group = case.patient_id
        eye_group = (
            f"{case.patient_id}:{case.eye_id}"
            if case.patient_id is not None and case.eye_id is not None
            else case.eye_id
        )
        visit_group = (
            f"{case.patient_id or case.global_case_id}:{case.eye_id or ''}:{case.visit_id}"
            if case.visit_id is not None
            else None
        )
        assignments.append(
            SplitRecord(
                global_split_id=stable_global_id("split", image.global_image_id, project_split),
                global_image_id=image.global_image_id,
                global_case_id=image.global_case_id,
                dataset_id=image.source_dataset,
                patient_group_id=patient_group,
                eye_group_id=eye_group,
                visit_group_id=visit_group,
                duplicate_group_id=image.duplicate_group_id or case.duplicate_group_id,
                project_split=project_split,
                purpose=purpose,
                domain_id=image.source_family,
                lock_group_id=lock_group_id,
                locked=locked,
                lock_reason=lock_reason,
                source_dataset=image.source_dataset,
                source_family=image.source_family,
                source_row=image.source_row,
                source_hash=image.source_hash,
                provenance_json=json_value(
                    {
                        "method": "deterministic_group_hash_v1",
                        "target_labels_opened": False,
                    }
                ),
            )
        )
    if not assignments:
        raise SourceValidationError("cannot create a split from an empty image relation")
    return RelationalSplitPlan(assignments=assignments)


def write_relational_split_lock(plan: RelationalSplitPlan, output: str | Path) -> Path:
    """Write one deterministic JSON lock; existing differing locks fail closed."""

    path = Path(output).resolve()
    payload = plan.model_dump(mode="json")
    if path.exists():
        existing = load_json(path)
        if not isinstance(existing, dict) or existing.get("split_hash") != plan.split_hash:
            raise SourceValidationError("existing split lock differs from proposed plan", path=path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return path


def verify_relational_split_lock(path: str | Path) -> RelationalSplitPlan:
    """Verify the hash and every prohibited configuration in an immutable lock."""

    source = Path(path).resolve()
    try:
        return RelationalSplitPlan.model_validate(load_json(source))
    except ValidationError as exc:
        raise validation_error(source, exc) from exc
