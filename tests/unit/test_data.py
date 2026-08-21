from __future__ import annotations

import pytest

from g2lc.data.labels import normalize_label
from g2lc.data.license_registry import validate_license_registry
from g2lc.data.splits import compute_split_lock, write_split_lock
from g2lc.errors import SourceValidationError
from g2lc.types import EvidenceLabel, EvidenceState


def test_absent_dataset_label_is_unknown() -> None:
    assert normalize_label(None) is EvidenceLabel.UNKNOWN


def test_negative_is_not_unknown() -> None:
    assert normalize_label("negative") is EvidenceLabel.NEGATIVE


def test_invalid_label_rejected() -> None:
    with pytest.raises(ValueError, match="POSITIVE"):
        normalize_label("absent")


def test_missing_evidence_value_is_none() -> None:
    assert EvidenceState(values={}).value("ma_presence") is None


def test_license_registry_is_structurally_valid() -> None:
    assert validate_license_registry("data/licenses.csv") == 10


def test_split_lock_is_deterministic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "split.yaml"
    config.write_text(
        """schema_version: '1.0'
dataset_id: idrid
source_family: IDRID
assignments: {patient_b: test, patient_a: train}
output: split.lock.json
""",
        encoding="utf-8",
    )
    _, first_hash, output = write_split_lock(config)
    _, second_hash, _ = write_split_lock(config)
    assert first_hash == second_hash
    assert output.is_file()


def test_changed_split_requires_dangerous_override(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "split.yaml"
    config.write_text(
        """schema_version: '1.0'
dataset_id: idrid
source_family: IDRID
assignments: {patient_a: train}
output: split.lock.json
""",
        encoding="utf-8",
    )
    write_split_lock(config)
    config.write_text(
        """schema_version: '1.0'
dataset_id: idrid
source_family: IDRID
assignments: {patient_a: test}
output: split.lock.json
""",
        encoding="utf-8",
    )
    with pytest.raises(SourceValidationError, match="dangerous_override"):
        write_split_lock(config)


def test_maples_split_must_be_locked_test_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "maples.yaml"
    config.write_text(
        """schema_version: '1.0'
dataset_id: maples_messidor
source_family: MESSIDOR1
assignments: {case_001: train}
maples_test_lock: false
output: maples.lock.json
""",
        encoding="utf-8",
    )
    with pytest.raises(SourceValidationError, match="maples_test_lock"):
        compute_split_lock(config)
