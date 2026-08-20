"""Safe metadata-only dataset adapter primitives.

Adapters scan local files and preserve their provenance. They do not download data,
infer diagnoses, or turn absent source labels into negatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pydantic import Field

from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, Modality, StrictModel
from g2lc.utils.io import sha256_file, sha256_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


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

    def discover_images(self, root: Path) -> list[Path]:
        """Discover local image files without decoding or modifying them."""

        images = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not images:
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
