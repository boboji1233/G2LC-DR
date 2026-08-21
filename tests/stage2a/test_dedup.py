from __future__ import annotations

from pathlib import Path

from PIL import Image

from g2lc.data.dedup import audit_duplicate_bundle
from g2lc.data.schemas import (
    CaseRecord,
    ImageRecord,
    ManifestTables,
    json_value,
    stable_global_id,
    write_manifest_bundle,
)
from g2lc.types import Modality
from g2lc.utils.io import sha256_file


def test_duplicate_audit_is_deterministic_review_only_and_never_deletes(tmp_path: Path) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    exact_a = image_dir / "exact-a.png"
    exact_b = image_dir / "exact-b.png"
    pixel_copy = image_dir / "pixel-copy.bmp"
    candidate = image_dir / "candidate.png"
    Image.new("RGB", (16, 16), (255, 0, 0)).save(exact_a)
    exact_b.write_bytes(exact_a.read_bytes())
    Image.open(exact_a).save(pixel_copy)
    Image.new("RGB", (16, 16), (254, 0, 0)).save(candidate)

    paths = [exact_a, exact_b, pixel_copy, candidate]
    cases = []
    images = []
    for index, path in enumerate(paths):
        dataset = "ddr" if index < 2 else "mmrdr_cfp"
        family = "OIA_DDR"
        case_id = stable_global_id("case", family, str(index))
        image_id = stable_global_id("image", family, str(index))
        common = {
            "source_dataset": dataset,
            "source_family": family,
            "source_row": str(index),
            "source_hash": sha256_file(path),
            "provenance_json": json_value({"fixture": "synthetic"}),
        }
        cases.append(CaseRecord(global_case_id=case_id, **common))
        images.append(
            ImageRecord(
                global_image_id=image_id,
                global_case_id=case_id,
                source_image_id=path.name,
                modality=Modality.CFP,
                image_path=str(path),
                file_sha256=sha256_file(path),
                **common,
            )
        )
    write_manifest_bundle(ManifestTables(cases=cases, images=images), tmp_path / "manifest")

    report = audit_duplicate_bundle(
        tmp_path / "manifest", tmp_path / "review", phash_threshold=64, dhash_threshold=64
    )
    second = audit_duplicate_bundle(
        tmp_path / "manifest", tmp_path / "review-second", phash_threshold=64, dhash_threshold=64
    )

    assert len(report.exact_pairs) == 1
    assert len(report.decoded_pixel_pairs) >= 1
    assert report.ambiguous_pairs
    assert report.automatic_deletion is False
    assert report.embedding_based_deduplication == "NOT_RUN"
    assert report.duplicate_groups == second.duplicate_groups
    assert all(path.is_file() for path in paths)
    assert (tmp_path / "review" / "ambiguous_pairs.csv").is_file()
    assert (tmp_path / "review" / "ambiguous_pairs.html").is_file()


def test_duplicate_audit_records_decode_errors_without_deleting_source(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-an-image")
    family = "TJDR"
    case_id = stable_global_id("case", family, "bad")
    image_id = stable_global_id("image", family, "bad")
    common = {
        "source_dataset": "tjdr",
        "source_family": family,
        "provenance_json": json_value({"fixture": "synthetic"}),
    }
    tables = ManifestTables(
        cases=[CaseRecord(global_case_id=case_id, **common)],
        images=[
            ImageRecord(
                global_image_id=image_id,
                global_case_id=case_id,
                source_image_id=bad.name,
                modality=Modality.CFP,
                image_path=str(bad),
                **common,
            )
        ],
    )
    write_manifest_bundle(tables, tmp_path / "manifest")
    report = audit_duplicate_bundle(tmp_path / "manifest", tmp_path / "review")
    assert report.images_scanned == 0
    assert report.decode_errors == [
        {"global_image_id": image_id, "error": "UnidentifiedImageError"}
    ]
    assert bad.is_file()
