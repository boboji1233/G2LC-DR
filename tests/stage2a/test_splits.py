from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from g2lc.data.schemas import (
    CaseRecord,
    ImageRecord,
    ManifestTables,
    SplitPurpose,
    SplitRecord,
    json_value,
    stable_global_id,
)
from g2lc.data.splits import (
    MAPLES_LOCK_GROUP,
    RelationalSplitPlan,
    create_relational_split_plan,
    split_policy_errors,
    verify_relational_split_lock,
    write_relational_split_lock,
)
from g2lc.errors import SourceValidationError
from g2lc.types import Modality


def _split(
    image_token: str,
    *,
    dataset: str = "idrid",
    family: str = "IDRID",
    project_split: str = "train",
    purpose: SplitPurpose = SplitPurpose.TRAIN,
    patient: str | None = None,
    duplicate: str | None = None,
    locked: bool = False,
    lock_group: str | None = None,
) -> SplitRecord:
    image_id = stable_global_id("image", family, image_token)
    return SplitRecord(
        global_split_id=stable_global_id("split", image_id, project_split),
        global_image_id=image_id,
        global_case_id=stable_global_id("case", family, image_token),
        dataset_id=dataset,
        patient_group_id=patient,
        duplicate_group_id=duplicate,
        project_split=project_split,
        purpose=purpose,
        domain_id=family,
        lock_group_id=lock_group,
        locked=locked,
        lock_reason="synthetic lock" if locked else None,
        source_dataset=dataset,
        source_family=family,
        provenance_json=json_value({"fixture": "synthetic"}),
    )


def test_patient_and_duplicate_groups_cannot_cross_splits() -> None:
    rows = [
        _split("a", patient="p1", duplicate="dup"),
        _split(
            "b",
            project_split="test",
            purpose=SplitPurpose.TEST,
            patient="p1",
            duplicate="dup",
        ),
    ]
    errors = split_policy_errors(rows)
    assert any("patient group" in error for error in errors)
    assert any("duplicate group" in error for error in errors)


@pytest.mark.parametrize(
    ("project_split", "purpose"),
    [
        ("train", SplitPurpose.TRAIN),
        ("validation", SplitPurpose.VALIDATION),
        ("calibration", SplitPurpose.CALIBRATION),
        ("threshold", SplitPurpose.THRESHOLD_SELECTION),
        ("model", SplitPurpose.MODEL_SELECTION),
    ],
)
def test_maples_adversarial_selection_uses_are_rejected(
    project_split: str, purpose: SplitPurpose
) -> None:
    row = _split(
        "maples-a",
        dataset="maples_dr",
        family="MESSIDOR1",
        project_split=project_split,
        purpose=purpose,
        locked=True,
        lock_group=MAPLES_LOCK_GROUP,
    )
    with pytest.raises(ValidationError, match="same-case test"):
        RelationalSplitPlan(assignments=[row])


def test_maples_is_locked_test_and_split_lock_verifies(tmp_path: Path) -> None:
    family = "MESSIDOR1"
    case_id = stable_global_id("case", family, "maples-a")
    image_id = stable_global_id("image", family, "maples-a")
    common = {
        "source_dataset": "maples_dr",
        "source_family": family,
        "provenance_json": json_value({"fixture": "synthetic"}),
    }
    tables = ManifestTables(
        cases=[CaseRecord(global_case_id=case_id, **common)],
        images=[
            ImageRecord(
                global_image_id=image_id,
                global_case_id=case_id,
                source_image_id="synthetic.png",
                modality=Modality.CFP,
                image_path="synthetic.png",
                **common,
            )
        ],
    )
    plan = create_relational_split_plan(tables)
    row = plan.assignments[0]
    assert (row.project_split, row.purpose) == ("test", SplitPurpose.TEST)
    assert row.locked and row.lock_group_id == MAPLES_LOCK_GROUP

    path = write_relational_split_lock(plan, tmp_path / "split.lock.json")
    assert verify_relational_split_lock(path).split_hash == plan.split_hash


def test_source_family_relabeling_is_rejected() -> None:
    row = _split("ddr-a", dataset="ddr", family="FAKE_INDEPENDENT_DOMAIN")
    assert any("OIA_DDR" in error for error in split_policy_errors([row]))


def test_eye_visit_and_duplicate_assignment_errors_are_all_reported() -> None:
    first = _split("a")
    first = SplitRecord.model_validate(
        {
            **first.model_dump(mode="json", exclude={"content_hash"}),
            "eye_group_id": "eye",
            "visit_group_id": "visit",
        }
    )
    second = _split("b", project_split="test", purpose=SplitPurpose.TEST)
    second = SplitRecord.model_validate(
        {
            **second.model_dump(mode="json", exclude={"content_hash"}),
            "eye_group_id": "eye",
            "visit_group_id": "visit",
        }
    )
    duplicate_assignment = SplitRecord.model_validate(
        {
            **first.model_dump(mode="json", exclude={"content_hash"}),
            "global_split_id": stable_global_id("split", first.global_image_id, "duplicate"),
        }
    )
    errors = split_policy_errors([first, second, duplicate_assignment])
    assert any("eye group" in error for error in errors)
    assert any("visit group" in error for error in errors)
    assert any("multiple split assignments" in error for error in errors)


def test_relational_lock_rejects_changed_existing_file_and_invalid_hash(tmp_path: Path) -> None:
    plan = RelationalSplitPlan(assignments=[_split("a")])
    path = write_relational_split_lock(plan, tmp_path / "split.json")
    path.write_text('{"split_hash":"different"}', encoding="utf-8")
    with pytest.raises(SourceValidationError, match="differs"):
        write_relational_split_lock(plan, path)
    with pytest.raises(SourceValidationError):
        verify_relational_split_lock(path)


def test_empty_manifest_and_invalid_percentages_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        create_relational_split_plan(ManifestTables(), train_percent=90, validation_percent=10)
    with pytest.raises(SourceValidationError, match="empty"):
        create_relational_split_plan(ManifestTables())
