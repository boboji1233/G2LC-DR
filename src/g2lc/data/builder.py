"""Local-only construction of a provenance-safe relational manifest."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from g2lc.data.adapters import AdapterState, adapter_for
from g2lc.data.registry import DatasetRegistryEntry
from g2lc.data.schemas import (
    CaseRecord,
    ImageRecord,
    ManifestTables,
    json_value,
    stable_global_id,
    write_manifest_bundle,
)
from g2lc.errors import SourceValidationError
from g2lc.types import StrictModel
from g2lc.utils.io import sha256_file


class ManifestBuildReport(StrictModel):
    """Dry-run/materialized result without clinical claims."""

    dataset_id: str
    source_family: str
    adapter_state: AdapterState
    dry_run: bool
    image_count: int
    case_count: int
    output_path: str | None = None
    bundle_hash: str | None = None
    unknown_preserved: bool = True
    clinical_labels_parsed: int = 0
    warnings: list[str] = Field(default_factory=list)


def build_manifest_from_local_root(
    entry: DatasetRegistryEntry,
    local_path: str | Path,
    output_path: str | Path,
    *,
    dry_run: bool,
    license_confirmed: bool,
) -> ManifestBuildReport:
    """Inventory source files; do not parse labels or infer patient/diagnosis tokens."""

    adapter = adapter_for(entry.dataset_id)
    inspection = adapter.inspect_root(local_path, license_confirmed=license_confirmed)
    if inspection.state is not AdapterState.READY:
        raise SourceValidationError(
            f"adapter state is {inspection.state.value}: {'; '.join(inspection.errors)}",
            path=local_path,
        )
    if not dry_run and not license_confirmed:
        raise SourceValidationError(
            "refusing to materialize a manifest without explicit current licence confirmation",
            path=local_path,
        )
    root = Path(local_path).resolve()
    images = adapter.discover_images(root)
    if dry_run:
        return ManifestBuildReport(
            dataset_id=entry.dataset_id,
            source_family=entry.source_family,
            adapter_state=inspection.state,
            dry_run=True,
            image_count=len(images),
            case_count=len(images),
            warnings=inspection.warnings,
        )
    case_rows: list[CaseRecord] = []
    image_rows: list[ImageRecord] = []
    for index, image_path in enumerate(images):
        source_image_id = image_path.relative_to(root).as_posix()
        source_hash = sha256_file(image_path)
        case_id = stable_global_id("case", entry.source_family, entry.dataset_id, source_image_id)
        image_id = stable_global_id("image", entry.source_family, entry.dataset_id, source_image_id)
        provenance = json_value(
            {
                "official_landing_page": entry.official_landing_page,
                "inventory_method": "local-file-only-v1",
                "relative_source_path": source_image_id,
                "clinical_inference": "NOT_PERFORMED",
            }
        )
        case_rows.append(
            CaseRecord(
                global_case_id=case_id,
                source_dataset=entry.dataset_id,
                source_family=entry.source_family,
                source_row=str(index),
                source_hash=source_hash,
                provenance_json=provenance,
            )
        )
        image_rows.append(
            ImageRecord(
                global_image_id=image_id,
                global_case_id=case_id,
                source_image_id=source_image_id,
                modality=adapter.spec.default_modality,
                image_path=str(image_path),
                file_sha256=source_hash,
                source_dataset=entry.dataset_id,
                source_family=entry.source_family,
                source_row=str(index),
                source_hash=source_hash,
                provenance_json=provenance,
            )
        )
    metadata = write_manifest_bundle(
        ManifestTables(cases=case_rows, images=image_rows), output_path
    )
    return ManifestBuildReport(
        dataset_id=entry.dataset_id,
        source_family=entry.source_family,
        adapter_state=inspection.state,
        dry_run=False,
        image_count=len(image_rows),
        case_count=len(case_rows),
        output_path=str(Path(output_path).resolve()),
        bundle_hash=str(metadata["bundle_hash"]),
        warnings=inspection.warnings,
    )
