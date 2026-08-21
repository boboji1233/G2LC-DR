from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from g2lc.data.schemas import (
    CaseRecord,
    CorrespondenceKind,
    CorrespondenceRecord,
    ImageRecord,
    LabelKind,
    LabelRecord,
    ManifestTables,
    RegionKind,
    RegionRecord,
    SplitPurpose,
    SplitRecord,
    json_value,
    load_manifest_bundle,
    migrate_legacy_image_parquet,
    stable_global_id,
    validate_manifest_bundle,
    write_manifest_bundle,
)
from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, Modality
from g2lc.utils.io import sha256_file


def _provenance() -> str:
    return json_value({"fixture": "synthetic-non-clinical"})


def _base_tables() -> ManifestTables:
    case_ids = [stable_global_id("case", "IDRID", token) for token in ("a", "b")]
    image_ids = [stable_global_id("image", "IDRID", token) for token in ("a", "b")]
    label_id = stable_global_id("label", image_ids[0], "synthetic")
    region_id = stable_global_id("region", image_ids[0], "synthetic")
    common = {
        "source_dataset": "idrid",
        "source_family": "IDRID",
        "provenance_json": _provenance(),
    }
    cases = [
        CaseRecord(global_case_id=case_id, source_row=str(index), **common)
        for index, case_id in enumerate(case_ids)
    ]
    images = [
        ImageRecord(
            global_image_id=image_id,
            global_case_id=case_id,
            source_image_id=f"synthetic-{index}.png",
            modality=Modality.CFP,
            image_path=f"synthetic-{index}.png",
            source_row=str(index),
            **common,
        )
        for index, (image_id, case_id) in enumerate(zip(image_ids, case_ids, strict=True))
    ]
    label = LabelRecord(
        global_label_id=label_id,
        global_image_id=image_ids[0],
        global_case_id=case_ids[0],
        global_region_id=region_id,
        concept_id="synthetic_presence",
        label_kind=LabelKind.POINT,
        status=EvidenceLabel.AMBIGUOUS,
        raw_value_json=json_value("uncertain"),
        normalized_value_json=json_value(None),
        **common,
    )
    region = RegionRecord(
        global_region_id=region_id,
        global_image_id=image_ids[0],
        global_label_id=label_id,
        region_kind=RegionKind.POINT,
        geometry_json=json_value({"x": 1, "y": 2}),
        coordinate_system="synthetic-pixels",
        **common,
    )
    correspondence = CorrespondenceRecord(
        global_correspondence_id=stable_global_id("correspondence", *image_ids),
        left_image_id=image_ids[0],
        right_image_id=image_ids[1],
        relation=CorrespondenceKind.POSSIBLE_DUPLICATE,
        status=EvidenceLabel.UNKNOWN,
        evidence_json=json_value({"review": "NOT_PERFORMED"}),
        **common,
    )
    split = SplitRecord(
        global_split_id=stable_global_id("split", image_ids[0], "train"),
        global_image_id=image_ids[0],
        global_case_id=case_ids[0],
        dataset_id="idrid",
        project_split="train",
        purpose=SplitPurpose.TRAIN,
        domain_id="IDRID",
        **common,
    )
    return ManifestTables(
        cases=cases,
        images=images,
        labels=[label],
        regions=[region],
        correspondences=[correspondence],
        splits=[split],
    )


def test_relational_parquet_round_trip_preserves_status_and_hashes(tmp_path: Path) -> None:
    tables = _base_tables()
    metadata = write_manifest_bundle(tables, tmp_path / "manifest")
    loaded = load_manifest_bundle(tmp_path / "manifest")

    assert metadata["tables"] == {
        "cases": 2,
        "images": 2,
        "labels": 1,
        "regions": 1,
        "correspondences": 1,
        "splits": 1,
    }
    assert loaded.labels[0].status is EvidenceLabel.AMBIGUOUS
    assert loaded.correspondences[0].status is EvidenceLabel.UNKNOWN
    assert loaded.labels[0].content_hash == tables.labels[0].content_hash
    assert validate_manifest_bundle(tmp_path / "manifest").valid


def test_all_nonbinary_label_states_survive_round_trip(tmp_path: Path) -> None:
    base = _base_tables()
    template = base.labels[0]
    states = [
        EvidenceLabel.UNKNOWN,
        EvidenceLabel.AMBIGUOUS,
        EvidenceLabel.NOT_APPLICABLE,
        EvidenceLabel.WEAK,
        EvidenceLabel.DERIVED,
    ]
    base.labels = [
        LabelRecord.model_validate(
            {
                **template.model_dump(mode="json", exclude={"content_hash"}),
                "global_label_id": stable_global_id("label", template.global_image_id, state),
                "global_region_id": None,
                "status": state,
            }
        )
        for state in states
    ]
    base.regions = []
    write_manifest_bundle(base, tmp_path)

    assert [row.status for row in load_manifest_bundle(tmp_path).labels] == sorted(
        states, key=lambda state: stable_global_id("label", template.global_image_id, state)
    )


def test_legacy_migration_preserves_unknown_instead_of_inventing_negative(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "dataset_id": "idrid",
                    "source_family": "IDRID",
                    "source_image_id": "synthetic.png",
                    "modality": "CFP",
                    "image_path": "synthetic.png",
                    "label_status": "UNKNOWN",
                    "dr_grade": None,
                }
            ]
        ),
        legacy,
    )

    migrate_legacy_image_parquet(legacy, tmp_path / "migrated")
    migrated = load_manifest_bundle(tmp_path / "migrated")
    assert migrated.labels[0].status is EvidenceLabel.UNKNOWN
    assert migrated.labels[0].normalized_value_json == "null"


def test_schema_validators_reject_tampered_hashes_and_invalid_json() -> None:
    tables = _base_tables()
    label = tables.labels[0]
    with pytest.raises(ValidationError, match="content_hash"):
        LabelRecord.model_validate({**label.model_dump(mode="json"), "content_hash": "0" * 64})
    with pytest.raises(ValidationError, match="provenance_json"):
        CaseRecord(
            global_case_id=stable_global_id("case", "IDRID", "bad-json"),
            source_dataset="idrid",
            source_family="IDRID",
            provenance_json="[]",
        )
    with pytest.raises(ValidationError, match="raw_value_json"):
        LabelRecord.model_validate(
            {
                **label.model_dump(mode="json", exclude={"content_hash"}),
                "raw_value_json": "not-json",
            }
        )
    with pytest.raises(ValidationError, match="different images"):
        CorrespondenceRecord(
            global_correspondence_id=stable_global_id("correspondence", "same", "same"),
            left_image_id=tables.images[0].global_image_id,
            right_image_id=tables.images[0].global_image_id,
            relation=CorrespondenceKind.SAME_IMAGE,
            status=EvidenceLabel.POSITIVE,
            evidence_json=json_value({}),
            source_dataset="idrid",
            source_family="IDRID",
            provenance_json=json_value({}),
        )
    with pytest.raises(ValueError, match="nonempty"):
        stable_global_id("case", "")


def test_manifest_loading_rejects_missing_metadata_and_checksum_tamper(tmp_path: Path) -> None:
    with pytest.raises(SourceValidationError, match=r"manifest_metadata\.json"):
        load_manifest_bundle(tmp_path)

    root = tmp_path / "manifest"
    write_manifest_bundle(_base_tables(), root)
    images = root / "images.parquet"
    images.write_bytes(images.read_bytes() + b"tamper")
    with pytest.raises(SourceValidationError, match="checksum mismatch"):
        load_manifest_bundle(root)


def test_manifest_validation_reports_referential_and_split_policy_errors(tmp_path: Path) -> None:
    tables = _base_tables()
    wrong_family = tables.splits[0].model_dump(mode="json", exclude={"content_hash"})
    wrong_family["source_family"] = "WRONG"
    wrong_family["domain_id"] = "WRONG"
    tables.splits = [SplitRecord.model_validate(wrong_family)]
    root = tmp_path / "manifest"
    write_manifest_bundle(tables, root)
    report = validate_manifest_bundle(root)
    assert report.valid is False
    assert any("IDRID" in error for error in report.errors)


def test_metadata_with_unsupported_schema_or_invalid_json_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "manifest"
    write_manifest_bundle(_base_tables(), root)
    metadata = root / "manifest_metadata.json"
    metadata.write_text("not-json", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="invalid JSON"):
        load_manifest_bundle(root)
    metadata.write_text('{"schema_version":"9.9"}', encoding="utf-8")
    with pytest.raises(SourceValidationError, match="unsupported manifest schema"):
        load_manifest_bundle(root)


def test_source_file_hash_helper_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "value"
    path.write_bytes(b"same")
    assert sha256_file(path) == sha256_file(path)
