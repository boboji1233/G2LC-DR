from __future__ import annotations

import pandas as pd
import pytest

from g2lc.data.adapters import adapter_for
from g2lc.data.adapters.registry import SPECS
from g2lc.errors import SourceValidationError


def test_required_adapter_registry_is_complete() -> None:
    assert set(SPECS) == {
        "ddr",
        "messidor1",
        "maples_dr",
        "mmrdr_cfp",
        "mmrdr_uwf",
        "idrid",
        "deepdrid",
        "fgadr",
        "retinal_lesions",
        "tjdr",
    }


def test_ddr_and_mmrdr_cfp_share_source_family() -> None:
    assert SPECS["ddr"].source_family == "OIA_DDR"
    assert SPECS["mmrdr_cfp"].source_family == "OIA_DDR"


def test_unknown_adapter_is_actionable() -> None:
    with pytest.raises(SourceValidationError, match="choose one of"):
        adapter_for("unknown")


def test_dry_run_does_not_write_manifest(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "ddr"
    root.mkdir()
    (root / "sample.jpg").write_bytes(b"metadata-only-test")
    output = tmp_path / "manifest.parquet"
    audit = adapter_for("ddr").run(
        root,
        output,
        dry_run=True,
        license_confirmed=False,
    )
    assert audit.image_count == 1
    assert audit.unknown_label_count == 1
    assert not output.exists()


def test_manifest_write_hashes_files_and_keeps_unknown(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "fgadr"
    root.mkdir()
    (root / "image.png").write_bytes(b"not-a-clinical-image")
    output = tmp_path / "manifest.parquet"
    audit = adapter_for("fgadr").run(
        root,
        output,
        dry_run=False,
        license_confirmed=True,
    )
    frame = pd.read_parquet(output)
    assert audit.manifest_hash is not None
    assert frame.loc[0, "label_status"] == "UNKNOWN"
    assert len(str(frame.loc[0, "sha256"])) == 64


def test_write_requires_explicit_license_confirmation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "fgadr"
    root.mkdir()
    (root / "image.png").write_bytes(b"test")
    with pytest.raises(SourceValidationError, match="license-confirmed"):
        adapter_for("fgadr").run(
            root,
            tmp_path / "manifest.parquet",
            dry_run=False,
            license_confirmed=False,
        )


def test_idrid_checks_authoritative_plan_layout(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SourceValidationError, match="A_Segmentation"):
        adapter_for("idrid").run(
            tmp_path,
            tmp_path / "manifest.parquet",
            dry_run=True,
            license_confirmed=False,
        )


def test_maples_records_are_locked(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "case.jpg").write_bytes(b"locked-test-placeholder")
    records = adapter_for("maples_messidor").records(tmp_path, compute_hashes=False)
    assert records[0].maples_test_locked is True
