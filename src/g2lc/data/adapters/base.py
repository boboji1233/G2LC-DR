"""Safe metadata-only dataset adapter primitives.

Adapters scan local files and preserve their provenance. They do not download data,
infer diagnoses, or turn absent source labels into negatives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd
from pydantic import Field

from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, Modality, StrictModel
from g2lc.utils.io import sha256_file, sha256_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


class AdapterState(StrEnum):
    """Truthful outcome of a local-only adapter preflight."""

    READY = "READY"
    MISSING_FILES = "MISSING_FILES"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"


class UnifiedImageRecord(StrictModel):
    """Unified image-level metadata without fabricated clinical values."""

    global_image_id: str
    dataset_id: str
    source_family: str
    source_image_id: str
    patient_id: str | None = None
    eye_id: str | None = None
    laterality: str | None = None
    view_id: str | None = None
    modality: Modality
    camera: str | None = None
    field_of_view: str | None = None
    image_path: str
    official_split: str | None = None
    project_split: str | None = None
    grade_system: str | None = None
    grade_version: str | None = None
    dr_grade: str | None = None
    label_status: EvidenceLabel = EvidenceLabel.UNKNOWN
    label_source: str | None = None
    annotation_granularity: str | None = None
    license_id: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dataset_version: str | None = None
    maples_test_locked: bool = False


class AdapterAudit(StrictModel):
    """Dry-run or materialized adapter outcome."""

    dataset_id: str
    source_family: str
    local_path: str
    image_count: int
    unknown_label_count: int
    output_path: str | None = None
    manifest_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AdapterInspection(StrictModel):
    """Non-mutating local root inspection with no inferred clinical metadata."""

    dataset_id: str
    source_family: str
    state: AdapterState
    local_path: str
    image_count: int = 0
    missing_paths: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    source_version: str | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AdapterSpec:
    """Dataset-specific facts frozen from the authoritative research plan."""

    dataset_id: str
    source_family: str
    default_modality: Modality
    license_id: str
    required_path_groups: tuple[tuple[str, ...], ...] = ()
    warnings: tuple[str, ...] = ()
    maples_test_locked: bool = False
    license_confirmation_required: bool = False


class MetadataAdapter:
    """Base local scanner; subclasses/configuration add only verified layout facts."""

    def __init__(self, spec: AdapterSpec) -> None:
        self.spec = spec

    def validate_root(self, local_path: str | Path) -> Path:
        """Require a local directory and all declared alternative path groups."""

        root = Path(local_path).resolve()
        if not root.is_dir():
            raise SourceValidationError(
                "dataset root does not exist; acquire it from the documented official source",
                path=root,
            )
        for alternatives in self.spec.required_path_groups:
            if not any((root / relative).exists() for relative in alternatives):
                raise SourceValidationError(
                    f"expected at least one of {list(alternatives)} under the dataset root",
                    path=root,
                )
        return root

    def inspect_root(
        self, local_path: str | Path, *, license_confirmed: bool = False
    ) -> AdapterInspection:
        """Inspect an explicitly supplied local root and return one defined state."""

        root = Path(local_path).resolve()
        warnings = list(self.spec.warnings)
        if self.spec.license_confirmation_required and not license_confirmed:
            return AdapterInspection(
                dataset_id=self.spec.dataset_id,
                source_family=self.spec.source_family,
                state=AdapterState.LICENSE_REQUIRED,
                local_path=str(root),
                errors=["current access/licence confirmation is required"],
                warnings=warnings,
            )
        if not root.is_dir():
            return AdapterInspection(
                dataset_id=self.spec.dataset_id,
                source_family=self.spec.source_family,
                state=AdapterState.MISSING_FILES,
                local_path=str(root),
                errors=["dataset root does not exist"],
                warnings=warnings,
            )
        marker = root / ".g2lc-adapter.json"
        source_version: str | None = None
        if marker.is_file():
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return AdapterInspection(
                    dataset_id=self.spec.dataset_id,
                    source_family=self.spec.source_family,
                    state=AdapterState.SCHEMA_MISMATCH,
                    local_path=str(root),
                    errors=[f"invalid .g2lc-adapter.json: {exc}"],
                    warnings=warnings,
                )
            if not isinstance(payload, dict) or payload.get("dataset_id") != self.spec.dataset_id:
                return AdapterInspection(
                    dataset_id=self.spec.dataset_id,
                    source_family=self.spec.source_family,
                    state=AdapterState.SCHEMA_MISMATCH,
                    local_path=str(root),
                    errors=["adapter marker dataset_id does not match the requested adapter"],
                    warnings=warnings,
                )
            if payload.get("adapter_schema_version") != "1.0":
                return AdapterInspection(
                    dataset_id=self.spec.dataset_id,
                    source_family=self.spec.source_family,
                    state=AdapterState.UNSUPPORTED_VERSION,
                    local_path=str(root),
                    errors=["adapter marker schema version is not supported"],
                    source_version=str(payload.get("source_version") or "") or None,
                    warnings=warnings,
                )
            source_version = str(payload.get("source_version") or "") or None
        missing = [
            " | ".join(alternatives)
            for alternatives in self.spec.required_path_groups
            if not any((root / relative).exists() for relative in alternatives)
        ]
        images = self.discover_images(root, allow_empty=True)
        if missing or not images:
            errors = ["required local layout entries are missing"] if missing else []
            if not images:
                errors.append("no supported image files were found")
            return AdapterInspection(
                dataset_id=self.spec.dataset_id,
                source_family=self.spec.source_family,
                state=AdapterState.MISSING_FILES,
                local_path=str(root),
                image_count=len(images),
                missing_paths=missing,
                errors=errors,
                source_version=source_version,
                warnings=warnings,
            )
        return AdapterInspection(
            dataset_id=self.spec.dataset_id,
            source_family=self.spec.source_family,
            state=AdapterState.READY,
            local_path=str(root),
            image_count=len(images),
            source_version=source_version,
            warnings=warnings,
        )

    def discover_images(self, root: Path, *, allow_empty: bool = False) -> list[Path]:
        """Discover local image files without decoding or modifying them."""

        images = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not images and not allow_empty:
            raise SourceValidationError(
                "no supported image files found; verify the official archive was fully extracted",
                path=root,
            )
        return images

    def records(
        self,
        local_path: str | Path,
        *,
        modality: Modality | None = None,
        compute_hashes: bool = True,
    ) -> list[UnifiedImageRecord]:
        """Build records with UNKNOWN labels until a verified source parser supplies one."""

        root = self.validate_root(local_path)
        selected_modality = modality or self.spec.default_modality
        records: list[UnifiedImageRecord] = []
        for image in self.discover_images(root):
            relative = image.relative_to(root).as_posix()
            source_id = relative
            stable_id = sha256_json(
                {
                    "dataset_id": self.spec.dataset_id,
                    "source_family": self.spec.source_family,
                    "source_image_id": source_id,
                }
            )[:24]
            records.append(
                UnifiedImageRecord(
                    global_image_id=f"{self.spec.dataset_id}:{stable_id}",
                    dataset_id=self.spec.dataset_id,
                    source_family=self.spec.source_family,
                    source_image_id=source_id,
                    modality=selected_modality,
                    image_path=str(image),
                    license_id=self.spec.license_id,
                    sha256=sha256_file(image) if compute_hashes else None,
                    maples_test_locked=self.spec.maples_test_locked,
                )
            )
        return records

    def run(
        self,
        local_path: str | Path,
        output_path: str | Path,
        *,
        dry_run: bool,
        license_confirmed: bool,
        modality: Modality | None = None,
    ) -> AdapterAudit:
        """Audit or write a unified Parquet manifest; never download source files."""

        if not dry_run and not license_confirmed:
            raise SourceValidationError(
                "refusing to write a manifest until --license-confirmed is explicitly supplied",
                path=local_path,
            )
        records = self.records(local_path, modality=modality, compute_hashes=not dry_run)
        output: Path | None = None
        manifest_hash: str | None = None
        if not dry_run:
            output = Path(output_path).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            rows = [record.model_dump(mode="json") for record in records]
            pd.DataFrame(rows).sort_values("global_image_id").to_parquet(
                output, index=False, engine="pyarrow"
            )
            manifest_hash = sha256_file(output)
        return AdapterAudit(
            dataset_id=self.spec.dataset_id,
            source_family=self.spec.source_family,
            local_path=str(Path(local_path).resolve()),
            image_count=len(records),
            unknown_label_count=sum(
                record.label_status is EvidenceLabel.UNKNOWN for record in records
            ),
            output_path=str(output) if output is not None else None,
            manifest_hash=manifest_hash,
            warnings=list(self.spec.warnings),
        )
