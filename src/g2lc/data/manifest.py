"""Small metadata manifest reader/auditor used before dataset-specific adapters."""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import Field

from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, StrictModel


class ManifestRow(StrictModel):
    """Minimum safe manifest row; no image or label inference is performed."""

    global_image_id: str
    dataset_id: str
    source_family: str
    image_path: str
    label_status: EvidenceLabel = EvidenceLabel.UNKNOWN
    patient_id: str | None = None
    official_split: str | None = None
    project_split: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ManifestAudit(StrictModel):
    """Deterministic dry-run audit summary."""

    rows: int
    datasets: list[str]
    source_families: list[str]
    unknown_labels: int
    missing_files: list[str]
    duplicate_ids: list[str]
    warnings: list[str]


def load_manifest(path: str | Path) -> list[ManifestRow]:
    """Load CSV metadata; Parquet is deferred until the adapter stage."""

    source = Path(path)
    if source.suffix.lower() != ".csv":
        raise SourceValidationError(
            "Stage 1 manifest audit supports CSV; Parquet support begins with data adapters",
            path=source,
        )
    if not source.is_file():
        raise SourceValidationError("manifest does not exist", path=source)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [ManifestRow.model_validate(row) for row in csv.DictReader(handle)]


def audit_manifest(path: str | Path) -> ManifestAudit:
    """Audit IDs, local paths, labels and known source-family overlap risk."""

    source = Path(path).resolve()
    rows = load_manifest(source)
    ids = [row.global_image_id for row in rows]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    missing = sorted(
        row.image_path for row in rows if not (source.parent / row.image_path).resolve().is_file()
    )
    families = sorted({row.source_family for row in rows})
    warnings: list[str] = []
    dataset_ids = {row.dataset_id.lower() for row in rows}
    if {"ddr", "mmrdr_cfp"}.issubset(dataset_ids):
        warnings.append("DDR and MMRDR-CFP are one OIA_DDR source family, not independent domains")
    return ManifestAudit(
        rows=len(rows),
        datasets=sorted({row.dataset_id for row in rows}),
        source_families=families,
        unknown_labels=sum(row.label_status is EvidenceLabel.UNKNOWN for row in rows),
        missing_files=missing,
        duplicate_ids=duplicates,
        warnings=warnings,
    )
