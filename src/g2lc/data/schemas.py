"""Versioned relational, Parquet-compatible medical-data manifest schemas.

The schemas preserve source values and missingness.  They describe metadata only and
contain no rule that turns an absent field, missing file, or unparsed source value into a
negative clinical label.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import Field, model_validator

from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, Modality, StrictModel
from g2lc.utils.io import canonical_json, sha256_file, sha256_json

SCHEMA_VERSION = "2.0"
TABLE_NAMES = ("cases", "images", "labels", "regions", "correspondences", "splits")
_ID_PATTERN = r"^[a-z][a-z0-9_]*:[0-9a-f]{32}$"
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class LabelKind(StrEnum):
    """Supported label representations without conflating their granularity."""

    IMAGE = "IMAGE"
    POINT = "POINT"
    BOX = "BOX"
    MASK = "MASK"
    COUNT = "COUNT"
    ORDINAL_BIN = "ORDINAL_BIN"
    QUADRANT = "QUADRANT"
    QUALITY = "QUALITY"
    ANATOMY = "ANATOMY"
    GUIDELINE_SPECIFIC = "GUIDELINE_SPECIFIC"


class RegionKind(StrEnum):
    """Spatial annotation encodings stored in the regions relation."""

    POINT = "POINT"
    BOX = "BOX"
    MASK = "MASK"
    QUADRANT = "QUADRANT"
    ANATOMY = "ANATOMY"
    POLYGON = "POLYGON"


class CorrespondenceKind(StrEnum):
    """Auditable relations between source records or images."""

    SAME_CASE = "SAME_CASE"
    SAME_IMAGE = "SAME_IMAGE"
    SAME_EYE_VISIT = "SAME_EYE_VISIT"
    DERIVED_COPY = "DERIVED_COPY"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"


class SplitPurpose(StrEnum):
    """Every use that can leak target information is named explicitly."""

    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    CALIBRATION = "CALIBRATION"
    THRESHOLD_SELECTION = "THRESHOLD_SELECTION"
    HYPERPARAMETER_SELECTION = "HYPERPARAMETER_SELECTION"
    MODEL_SELECTION = "MODEL_SELECTION"
    TEST = "TEST"


def stable_global_id(kind: str, *parts: str | None) -> str:
    """Create a deterministic opaque ID from an immutable source identity tuple."""

    if not kind or not kind.replace("_", "").isalnum() or not kind[0].isalpha():
        raise ValueError(f"invalid global ID kind {kind!r}")
    if not parts or any(part is None or not str(part) for part in parts):
        raise ValueError("stable global IDs require nonempty identity parts")
    digest = sha256_json({"kind": kind, "parts": list(parts)})[:32]
    return f"{kind}:{digest}"


def json_value(value: Any) -> str:
    """Serialize an unmodified source or normalized value into a typed JSON scalar/object."""

    return canonical_json(value)


class HashedRecord(StrictModel):
    """Base relation row whose deterministic content hash detects any mutation."""

    schema_version: Literal["2.0"] = "2.0"
    content_hash: str | None = Field(default=None, pattern=_HASH_PATTERN, frozen=True)

    def model_post_init(self, __context: Any) -> None:
        expected = sha256_json(self.model_dump(mode="json", exclude={"content_hash"}))
        if self.content_hash is not None and self.content_hash != expected:
            raise ValueError("content_hash does not match canonical record content")
        object.__setattr__(self, "content_hash", expected)


class ProvenanceRecord(HashedRecord):
    """Source-level provenance shared by every manifest relation."""

    source_dataset: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    source_row: str | None = None
    source_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    provenance_json: str = Field(min_length=2)

    @model_validator(mode="after")
    def provenance_is_json(self) -> ProvenanceRecord:
        try:
            value = json.loads(self.provenance_json)
        except json.JSONDecodeError as exc:
            raise ValueError("provenance_json must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("provenance_json must encode an object")
        return self


class CaseRecord(ProvenanceRecord):
    """One patient/eye/visit case; unavailable identifiers remain null."""

    global_case_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    patient_id: str | None = None
    eye_id: str | None = None
    laterality: str | None = None
    visit_id: str | None = None
    duplicate_group_id: str | None = None


class ImageRecord(ProvenanceRecord):
    """One image/view linked to its case and immutable source identity."""

    global_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_case_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    source_image_id: str = Field(min_length=1)
    patient_id: str | None = None
    eye_id: str | None = None
    visit_id: str | None = None
    view_id: str | None = None
    modality: Modality
    image_path: str = Field(min_length=1)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    file_sha256: str | None = Field(default=None, pattern=_HASH_PATTERN)
    decoded_pixel_hash: str | None = Field(default=None, pattern=_HASH_PATTERN)
    phash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    dhash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    official_split: str | None = None
    duplicate_group_id: str | None = None


class LabelRecord(ProvenanceRecord):
    """One clinical or technical label at an explicit annotation granularity."""

    global_label_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_case_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_region_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    concept_id: str = Field(min_length=1)
    label_kind: LabelKind
    status: EvidenceLabel
    raw_value_json: str
    normalized_value_json: str
    annotator_id: str | None = None
    annotator_role: str | None = None
    annotation_round: str | None = None
    consensus_method: str | None = None
    adjudication_record_id: str | None = None
    guideline_system: str | None = None
    guideline_version: str | None = None
    granularity_detail: str | None = None
    uncertainty_json: str | None = None

    @model_validator(mode="after")
    def label_json_values_are_valid(self) -> LabelRecord:
        for name in ("raw_value_json", "normalized_value_json", "uncertainty_json"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{name} must be valid JSON") from exc
        return self


class RegionRecord(ProvenanceRecord):
    """Point, box, mask, quadrant, polygon, or anatomy geometry."""

    global_region_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_label_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    region_kind: RegionKind
    geometry_json: str
    coordinate_system: str = Field(min_length=1)
    mask_path: str | None = None
    annotator_id: str | None = None

    @model_validator(mode="after")
    def geometry_is_json(self) -> RegionRecord:
        try:
            json.loads(self.geometry_json)
        except json.JSONDecodeError as exc:
            raise ValueError("geometry_json must be valid JSON") from exc
        return self


class CorrespondenceRecord(ProvenanceRecord):
    """Explicit same-case/image/copy or possible-duplicate correspondence."""

    global_correspondence_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    left_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    right_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    relation: CorrespondenceKind
    status: EvidenceLabel
    evidence_json: str
    reviewer_id: str | None = None

    @model_validator(mode="after")
    def evidence_is_json(self) -> CorrespondenceRecord:
        if self.left_image_id == self.right_image_id:
            raise ValueError("a correspondence must connect two different images")
        try:
            json.loads(self.evidence_json)
        except json.JSONDecodeError as exc:
            raise ValueError("evidence_json must be valid JSON") from exc
        return self


class SplitRecord(ProvenanceRecord):
    """One image-use assignment with all leakage-relevant group identities."""

    global_split_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_image_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    global_case_id: str = Field(pattern=_ID_PATTERN, frozen=True)
    dataset_id: str = Field(min_length=1)
    patient_group_id: str | None = None
    eye_group_id: str | None = None
    visit_group_id: str | None = None
    duplicate_group_id: str | None = None
    project_split: str = Field(min_length=1)
    purpose: SplitPurpose
    domain_id: str = Field(min_length=1)
    lock_group_id: str | None = None
    locked: bool = False
    lock_reason: str | None = None


class ManifestTables(StrictModel):
    """In-memory representation of all six versioned relations."""

    cases: list[CaseRecord] = Field(default_factory=list)
    images: list[ImageRecord] = Field(default_factory=list)
    labels: list[LabelRecord] = Field(default_factory=list)
    regions: list[RegionRecord] = Field(default_factory=list)
    correspondences: list[CorrespondenceRecord] = Field(default_factory=list)
    splits: list[SplitRecord] = Field(default_factory=list)


class ManifestValidationReport(StrictModel):
    """Deterministic structural and referential-integrity report."""

    schema_version: Literal["2.0"] = "2.0"
    valid: bool
    table_rows: dict[str, int]
    errors: list[str]
    bundle_hash: str | None = None


MODEL_BY_TABLE: dict[str, type[HashedRecord]] = {
    "cases": CaseRecord,
    "images": ImageRecord,
    "labels": LabelRecord,
    "regions": RegionRecord,
    "correspondences": CorrespondenceRecord,
    "splits": SplitRecord,
}


def _field(name: str, data_type: pa.DataType, *, nullable: bool = True) -> pa.Field:
    return pa.field(name, data_type, nullable=nullable)


_COMMON_FIELDS = [
    _field("schema_version", pa.string(), nullable=False),
    _field("content_hash", pa.string(), nullable=False),
    _field("source_dataset", pa.string(), nullable=False),
    _field("source_family", pa.string(), nullable=False),
    _field("source_row", pa.string()),
    _field("source_hash", pa.string()),
    _field("provenance_json", pa.string(), nullable=False),
]


TABLE_SCHEMAS: dict[str, pa.Schema] = {
    "cases": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_case_id", pa.string(), nullable=False),
            _field("patient_id", pa.string()),
            _field("eye_id", pa.string()),
            _field("laterality", pa.string()),
            _field("visit_id", pa.string()),
            _field("duplicate_group_id", pa.string()),
        ]
    ),
    "images": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_image_id", pa.string(), nullable=False),
            _field("global_case_id", pa.string(), nullable=False),
            _field("source_image_id", pa.string(), nullable=False),
            _field("patient_id", pa.string()),
            _field("eye_id", pa.string()),
            _field("visit_id", pa.string()),
            _field("view_id", pa.string()),
            _field("modality", pa.string(), nullable=False),
            _field("image_path", pa.string(), nullable=False),
            _field("width", pa.int64()),
            _field("height", pa.int64()),
            _field("file_sha256", pa.string()),
            _field("decoded_pixel_hash", pa.string()),
            _field("phash", pa.string()),
            _field("dhash", pa.string()),
            _field("official_split", pa.string()),
            _field("duplicate_group_id", pa.string()),
        ]
    ),
    "labels": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_label_id", pa.string(), nullable=False),
            _field("global_image_id", pa.string(), nullable=False),
            _field("global_case_id", pa.string(), nullable=False),
            _field("global_region_id", pa.string()),
            _field("concept_id", pa.string(), nullable=False),
            _field("label_kind", pa.string(), nullable=False),
            _field("status", pa.string(), nullable=False),
            _field("raw_value_json", pa.string(), nullable=False),
            _field("normalized_value_json", pa.string(), nullable=False),
            _field("annotator_id", pa.string()),
            _field("annotator_role", pa.string()),
            _field("annotation_round", pa.string()),
            _field("consensus_method", pa.string()),
            _field("adjudication_record_id", pa.string()),
            _field("guideline_system", pa.string()),
            _field("guideline_version", pa.string()),
            _field("granularity_detail", pa.string()),
            _field("uncertainty_json", pa.string()),
        ]
    ),
    "regions": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_region_id", pa.string(), nullable=False),
            _field("global_image_id", pa.string(), nullable=False),
            _field("global_label_id", pa.string()),
            _field("region_kind", pa.string(), nullable=False),
            _field("geometry_json", pa.string(), nullable=False),
            _field("coordinate_system", pa.string(), nullable=False),
            _field("mask_path", pa.string()),
            _field("annotator_id", pa.string()),
        ]
    ),
    "correspondences": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_correspondence_id", pa.string(), nullable=False),
            _field("left_image_id", pa.string(), nullable=False),
            _field("right_image_id", pa.string(), nullable=False),
            _field("relation", pa.string(), nullable=False),
            _field("status", pa.string(), nullable=False),
            _field("evidence_json", pa.string(), nullable=False),
            _field("reviewer_id", pa.string()),
        ]
    ),
    "splits": pa.schema(
        [
            *_COMMON_FIELDS,
            _field("global_split_id", pa.string(), nullable=False),
            _field("global_image_id", pa.string(), nullable=False),
            _field("global_case_id", pa.string(), nullable=False),
            _field("dataset_id", pa.string(), nullable=False),
            _field("patient_group_id", pa.string()),
            _field("eye_group_id", pa.string()),
            _field("visit_group_id", pa.string()),
            _field("duplicate_group_id", pa.string()),
            _field("project_split", pa.string(), nullable=False),
            _field("purpose", pa.string(), nullable=False),
            _field("domain_id", pa.string(), nullable=False),
            _field("lock_group_id", pa.string()),
            _field("locked", pa.bool_(), nullable=False),
            _field("lock_reason", pa.string()),
        ]
    ),
}


def _id_field(table_name: str) -> str:
    return {
        "cases": "global_case_id",
        "images": "global_image_id",
        "labels": "global_label_id",
        "regions": "global_region_id",
        "correspondences": "global_correspondence_id",
        "splits": "global_split_id",
    }[table_name]


def _validate_tables(tables: ManifestTables) -> list[str]:
    errors: list[str] = []
    ids: dict[str, set[str]] = {}
    for table_name in TABLE_NAMES:
        rows = getattr(tables, table_name)
        field = _id_field(table_name)
        values = [str(getattr(row, field)) for row in rows]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            errors.append(f"{table_name} contains duplicate IDs: {duplicates}")
        ids[table_name] = set(values)
    case_ids = ids["cases"]
    image_ids = ids["images"]
    label_ids = ids["labels"]
    region_ids = ids["regions"]
    for image_row in tables.images:
        if image_row.global_case_id not in case_ids:
            errors.append(f"image {image_row.global_image_id} references missing case")
    for label_row in tables.labels:
        if label_row.global_image_id not in image_ids or label_row.global_case_id not in case_ids:
            errors.append(f"label {label_row.global_label_id} has a missing image or case")
        if label_row.global_region_id is not None and label_row.global_region_id not in region_ids:
            errors.append(f"label {label_row.global_label_id} references missing region")
    for region_row in tables.regions:
        if region_row.global_image_id not in image_ids:
            errors.append(f"region {region_row.global_region_id} references missing image")
        if region_row.global_label_id is not None and region_row.global_label_id not in label_ids:
            errors.append(f"region {region_row.global_region_id} references missing label")
    for correspondence_row in tables.correspondences:
        if (
            correspondence_row.left_image_id not in image_ids
            or correspondence_row.right_image_id not in image_ids
        ):
            errors.append(
                f"correspondence {correspondence_row.global_correspondence_id} has a missing image"
            )
    for split_row in tables.splits:
        if split_row.global_image_id not in image_ids or split_row.global_case_id not in case_ids:
            errors.append(f"split {split_row.global_split_id} has a missing image or case")
    return sorted(errors)


def write_manifest_bundle(tables: ManifestTables, output_dir: str | Path) -> dict[str, Any]:
    """Validate and deterministically write all six Parquet relations."""

    errors = _validate_tables(tables)
    if errors:
        raise SourceValidationError("; ".join(errors), path=output_dir)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    file_hashes: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    for table_name in TABLE_NAMES:
        rows = sorted(
            getattr(tables, table_name), key=lambda row: str(getattr(row, _id_field(table_name)))
        )
        payload = [row.model_dump(mode="json") for row in rows]
        table = pa.Table.from_pylist(payload, schema=TABLE_SCHEMAS[table_name])
        path = destination / f"{table_name}.parquet"
        pq.write_table(table, path, compression="zstd", version="2.6")
        file_hashes[path.name] = sha256_file(path)
        row_counts[table_name] = len(rows)
    bundle_hash = sha256_json({"schema_version": SCHEMA_VERSION, "files": file_hashes})
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "tables": row_counts,
        "files": file_hashes,
        "bundle_hash": bundle_hash,
    }
    (destination / "manifest_metadata.json").write_text(
        canonical_json(metadata) + "\n", encoding="utf-8"
    )
    return metadata


def load_manifest_bundle(path: str | Path) -> ManifestTables:
    """Load and type-check every relation in a v2 manifest directory."""

    root = Path(path).resolve()
    metadata_path = root / "manifest_metadata.json"
    if not metadata_path.is_file():
        raise SourceValidationError("manifest_metadata.json is missing", path=root)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceValidationError(
            "manifest metadata is invalid JSON", path=metadata_path
        ) from exc
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise SourceValidationError(
            f"unsupported manifest schema {metadata.get('schema_version')!r}", path=metadata_path
        )
    loaded: dict[str, list[HashedRecord]] = {}
    for table_name in TABLE_NAMES:
        table_path = root / f"{table_name}.parquet"
        if not table_path.is_file():
            raise SourceValidationError(f"{table_name}.parquet is missing", path=root)
        expected_hash = metadata.get("files", {}).get(table_path.name)
        if expected_hash != sha256_file(table_path):
            raise SourceValidationError("table checksum mismatch", path=table_path)
        table = pq.read_table(table_path, schema=TABLE_SCHEMAS[table_name])
        loaded[table_name] = [
            MODEL_BY_TABLE[table_name].model_validate(row) for row in table.to_pylist()
        ]
    return ManifestTables.model_validate(loaded)


def validate_manifest_bundle(path: str | Path) -> ManifestValidationReport:
    """Return a report or raise an actionable error for corrupt/unsupported input."""

    root = Path(path).resolve()
    tables = load_manifest_bundle(root)
    errors = _validate_tables(tables)
    if tables.splits:
        from g2lc.data.splits import split_policy_errors

        errors.extend(split_policy_errors(tables.splits))
    metadata = json.loads((root / "manifest_metadata.json").read_text(encoding="utf-8"))
    return ManifestValidationReport(
        valid=not errors,
        table_rows={name: len(getattr(tables, name)) for name in TABLE_NAMES},
        errors=sorted(set(errors)),
        bundle_hash=metadata["bundle_hash"],
    )


def migrate_legacy_image_parquet(source: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Migrate the Stage-1 image table while preserving every label state exactly."""

    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise SourceValidationError("legacy Parquet file is missing", path=source_path)
    rows = pq.read_table(source_path).to_pylist()
    cases: dict[str, CaseRecord] = {}
    images: list[ImageRecord] = []
    labels: list[LabelRecord] = []
    for index, row in enumerate(rows):
        dataset_id = str(row.get("dataset_id") or "")
        source_family = str(row.get("source_family") or "")
        source_image_id = str(row.get("source_image_id") or row.get("global_image_id") or "")
        if not dataset_id or not source_family or not source_image_id:
            raise SourceValidationError(
                f"legacy row {index} lacks dataset/source identity", path=source_path
            )
        patient_id = row.get("patient_id")
        eye_id = row.get("eye_id")
        visit_id = row.get("visit_id")
        case_token = str(patient_id or source_image_id)
        case_id = stable_global_id(
            "case",
            source_family,
            dataset_id,
            case_token,
            str(eye_id or "NO_EYE_ID"),
            str(visit_id or "NO_VISIT_ID"),
        )
        provenance = json_value({"migration": "stage1-image-parquet-to-v2", "legacy_row": index})
        if case_id not in cases:
            cases[case_id] = CaseRecord(
                global_case_id=case_id,
                patient_id=patient_id,
                eye_id=eye_id,
                visit_id=visit_id,
                source_dataset=dataset_id,
                source_family=source_family,
                source_row=str(index),
                source_hash=None,
                provenance_json=provenance,
            )
        image_id = stable_global_id("image", source_family, dataset_id, source_image_id)
        image = ImageRecord(
            global_image_id=image_id,
            global_case_id=case_id,
            source_image_id=source_image_id,
            patient_id=patient_id,
            eye_id=eye_id,
            visit_id=visit_id,
            view_id=row.get("view_id"),
            modality=Modality(str(row.get("modality") or "CFP")),
            image_path=str(row.get("image_path") or "UNAVAILABLE"),
            file_sha256=row.get("sha256"),
            official_split=row.get("official_split"),
            source_dataset=dataset_id,
            source_family=source_family,
            source_row=str(index),
            source_hash=row.get("sha256"),
            provenance_json=provenance,
        )
        images.append(image)
        status = EvidenceLabel(str(row.get("label_status") or EvidenceLabel.UNKNOWN.value))
        raw_grade = row.get("dr_grade")
        labels.append(
            LabelRecord(
                global_label_id=stable_global_id("label", image_id, "dr_grade", "legacy"),
                global_image_id=image_id,
                global_case_id=case_id,
                concept_id="dr_grade",
                label_kind=LabelKind.GUIDELINE_SPECIFIC,
                status=status,
                raw_value_json=json_value(raw_grade),
                normalized_value_json=json_value(raw_grade),
                guideline_system=row.get("grade_system"),
                guideline_version=row.get("grade_version"),
                source_dataset=dataset_id,
                source_family=source_family,
                source_row=str(index),
                source_hash=row.get("sha256"),
                provenance_json=provenance,
            )
        )
    return write_manifest_bundle(
        ManifestTables(cases=list(cases.values()), images=images, labels=labels), output_dir
    )
