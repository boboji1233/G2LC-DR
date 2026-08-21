from __future__ import annotations

from pathlib import Path

import pytest

from g2lc.data.adapters import AdapterState, adapter_for
from g2lc.data.adapters.registry import SPECS
from g2lc.data.registry import inspect_registry_status, load_dataset_registry
from g2lc.errors import SourceValidationError

EXPECTED_IDS = {
    "messidor1",
    "maples_dr",
    "ddr",
    "mmrdr_cfp",
    "mmrdr_uwf",
    "idrid",
    "deepdrid",
    "fgadr",
    "retinal_lesions",
    "tjdr",
}


def test_registry_and_adapters_cover_the_same_ten_datasets() -> None:
    registry = load_dataset_registry()
    assert set(SPECS) == EXPECTED_IDS
    assert {item.dataset_id for item in registry.datasets} == EXPECTED_IDS


def test_adapter_states_are_explicit_and_local_only(tmp_path: Path) -> None:
    assert (
        adapter_for("messidor1").inspect_root(tmp_path / "missing").state
        is AdapterState.LICENSE_REQUIRED
    )
    assert adapter_for("ddr").inspect_root(tmp_path / "missing").state is AdapterState.MISSING_FILES

    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / ".g2lc-adapter.json").write_text(
        '{"dataset_id":"tjdr","adapter_schema_version":"1.0"}', encoding="utf-8"
    )
    assert adapter_for("ddr").inspect_root(wrong).state is AdapterState.SCHEMA_MISMATCH

    old = tmp_path / "old"
    old.mkdir()
    (old / ".g2lc-adapter.json").write_text(
        '{"dataset_id":"ddr","adapter_schema_version":"0.1"}', encoding="utf-8"
    )
    assert adapter_for("ddr").inspect_root(old).state is AdapterState.UNSUPPORTED_VERSION

    ready = tmp_path / "ready"
    ready.mkdir()
    (ready / "synthetic.jpg").write_bytes(b"not-decoded-by-inspection")
    inspection = adapter_for("ddr").inspect_root(ready)
    assert inspection.state is AdapterState.READY
    assert inspection.image_count == 1


def test_source_family_identity_is_not_counted_as_independent_domains() -> None:
    assert adapter_for("ddr").spec.source_family == "OIA_DDR"
    assert adapter_for("mmrdr_cfp").spec.source_family == "OIA_DDR"
    assert adapter_for("messidor1").spec.source_family == "MESSIDOR1"
    assert adapter_for("maples_dr").spec.source_family == "MESSIDOR1"


def test_registry_status_uses_explicit_roots_and_access_states(tmp_path: Path) -> None:
    ready = tmp_path / "ddr"
    ready.mkdir()
    (ready / "synthetic.jpg").write_bytes(b"inventory")
    registry = load_dataset_registry()
    statuses = inspect_registry_status(registry, {"ddr": str(ready)})
    by_id = {item.dataset_id: item for item in statuses}
    assert by_id["ddr"].adapter_state is AdapterState.READY
    assert by_id["messidor1"].adapter_state is AdapterState.LICENSE_REQUIRED
    assert by_id["retinal_lesions"].adapter_state is AdapterState.LICENSE_REQUIRED


def test_registry_lookup_and_source_family_validation_fail_closed(tmp_path: Path) -> None:
    registry = load_dataset_registry()
    with pytest.raises(SourceValidationError, match="not registered"):
        registry.entry("missing")

    content = Path("data/dataset_registry.yaml").read_text(encoding="utf-8")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(content.replace("source_family: OIA_DDR", "source_family: WRONG", 1))
    with pytest.raises(SourceValidationError, match="source_family"):
        load_dataset_registry(invalid)


def test_invalid_and_unsupported_adapter_markers_are_distinct(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / ".g2lc-adapter.json").write_text("not-json", encoding="utf-8")
    assert adapter_for("ddr").inspect_root(invalid).state is AdapterState.SCHEMA_MISMATCH

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SourceValidationError, match="no supported image"):
        adapter_for("ddr").discover_images(empty)
