"""Deterministic exact, decoded-pixel, and perceptual duplicate audit."""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageOps
from pydantic import Field

from g2lc.data.manifest import load_manifest
from g2lc.data.schemas import ImageRecord, load_manifest_bundle, stable_global_id
from g2lc.errors import SourceValidationError
from g2lc.types import StrictModel
from g2lc.utils.io import canonical_json, sha256_file


def exact_duplicate_groups(manifest_path: str | Path) -> list[list[str]]:
    """Return global-image ID groups with identical file bytes."""

    source = Path(manifest_path).resolve()
    groups: dict[str, list[str]] = defaultdict(list)
    for row in load_manifest(source):
        image = (source.parent / row.image_path).resolve()
        if not image.is_file():
            raise SourceValidationError(
                f"cannot hash missing image for {row.global_image_id!r}", path=image
            )
        digest = row.sha256 or sha256_file(image)
        groups[digest].append(row.global_image_id)
    return sorted((sorted(ids) for ids in groups.values() if len(ids) > 1), key=lambda ids: ids[0])


class DuplicatePair(StrictModel):
    """One deterministic confirmed or ambiguous image pair."""

    pair_id: str
    left_image_id: str
    right_image_id: str
    left_dataset: str
    right_dataset: str
    left_source_family: str
    right_source_family: str
    relation: Literal["EXACT", "DECODED_PIXEL", "PERCEPTUAL_CANDIDATE"]
    file_sha256_equal: bool
    decoded_pixel_hash_equal: bool
    phash_distance: int | None = None
    dhash_distance: int | None = None
    cross_source_family: bool


class DuplicateGroup(StrictModel):
    """Confirmed duplicate component; perceptual candidates never auto-join it."""

    duplicate_group_id: str
    image_ids: list[str] = Field(min_length=2)
    datasets: list[str]
    source_families: list[str]
    cross_source_family: bool


class DuplicateAuditReport(StrictModel):
    """Source-family-aware audit with an explicit no-deletion/embedding disposition."""

    schema_version: Literal["1.0"] = "1.0"
    images_scanned: int
    exact_pairs: list[DuplicatePair]
    decoded_pixel_pairs: list[DuplicatePair]
    ambiguous_pairs: list[DuplicatePair]
    duplicate_groups: list[DuplicateGroup]
    decode_errors: list[dict[str, str]]
    review_csv: str
    review_html: str
    embedding_based_deduplication: Literal["NOT_RUN"] = "NOT_RUN"
    automatic_deletion: Literal[False] = False


class _ImageFingerprint(StrictModel):
    image: ImageRecord
    file_sha256: str
    decoded_pixel_hash: str
    phash: str
    dhash: str


def _dct_matrix(size: int) -> np.ndarray:
    positions = np.arange(size, dtype=np.float64)
    frequencies = positions[:, None]
    matrix = np.cos((np.pi / size) * (positions + 0.5) * frequencies)
    matrix[0, :] *= np.sqrt(1.0 / size)
    matrix[1:, :] *= np.sqrt(2.0 / size)
    return matrix


def _bits_to_hex(bits: np.ndarray) -> str:
    value = 0
    for bit in bits.astype(bool).flat:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def image_fingerprints(path: str | Path) -> tuple[str, str, str]:
    """Return decoded-pixel SHA-256, 64-bit pHash, and 64-bit dHash."""

    source = Path(path)
    with Image.open(source) as opened:
        rgb = ImageOps.exif_transpose(opened).convert("RGB")
        digest = hashlib.sha256()
        digest.update(f"RGB:{rgb.width}x{rgb.height}:".encode())
        digest.update(rgb.tobytes())
        pixel_hash = digest.hexdigest()
        grayscale = rgb.convert("L")
        difference = np.asarray(grayscale.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
        dhash = _bits_to_hex(difference[:, 1:] > difference[:, :-1])
        sample = np.asarray(grayscale.resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float64)
        dct = _dct_matrix(32) @ sample @ _dct_matrix(32).T
        low = dct[:8, :8]
        median = float(np.median(low.flat[1:]))
        phash = _bits_to_hex(low > median)
    return pixel_hash, phash, dhash


def _hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _pair(
    left: _ImageFingerprint,
    right: _ImageFingerprint,
    relation: Literal["EXACT", "DECODED_PIXEL", "PERCEPTUAL_CANDIDATE"],
) -> DuplicatePair:
    ordered = sorted((left, right), key=lambda item: item.image.global_image_id)
    first, second = ordered
    return DuplicatePair(
        pair_id=stable_global_id(
            "duppair", first.image.global_image_id, second.image.global_image_id, relation
        ),
        left_image_id=first.image.global_image_id,
        right_image_id=second.image.global_image_id,
        left_dataset=first.image.source_dataset,
        right_dataset=second.image.source_dataset,
        left_source_family=first.image.source_family,
        right_source_family=second.image.source_family,
        relation=relation,
        file_sha256_equal=first.file_sha256 == second.file_sha256,
        decoded_pixel_hash_equal=first.decoded_pixel_hash == second.decoded_pixel_hash,
        phash_distance=_hamming(first.phash, second.phash),
        dhash_distance=_hamming(first.dhash, second.dhash),
        cross_source_family=first.image.source_family != second.image.source_family,
    )


def _confirmed_groups(
    fingerprints: list[_ImageFingerprint], pairs: list[DuplicatePair]
) -> list[DuplicateGroup]:
    parent = {item.image.global_image_id: item.image.global_image_id for item in fingerprints}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for pair in pairs:
        union(pair.left_image_id, pair.right_image_id)
    members: dict[str, list[str]] = defaultdict(list)
    for image_id in parent:
        members[find(image_id)].append(image_id)
    by_id = {item.image.global_image_id: item.image for item in fingerprints}
    results: list[DuplicateGroup] = []
    for image_ids in sorted(sorted(value) for value in members.values() if len(value) > 1):
        datasets = sorted({by_id[image_id].source_dataset for image_id in image_ids})
        families = sorted({by_id[image_id].source_family for image_id in image_ids})
        results.append(
            DuplicateGroup(
                duplicate_group_id=stable_global_id("dupgroup", *image_ids),
                image_ids=image_ids,
                datasets=datasets,
                source_families=families,
                cross_source_family=len(families) > 1,
            )
        )
    return results


def _write_review(pairs: list[DuplicatePair], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "ambiguous_pairs.csv"
    fields = list(DuplicatePair.model_fields)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(pair.model_dump(mode="json") for pair in pairs)
    html_path = output / "ambiguous_pairs.html"
    header = "".join(f"<th>{escape(field)}</th>" for field in fields)
    rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(str(pair.model_dump(mode='json')[field]))}</td>" for field in fields
        )
        + "</tr>"
        for pair in pairs
    )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Duplicate review</title>"
        "</head><body><h1>Ambiguous perceptual duplicate candidates</h1>"
        "<p>No file is deleted or automatically confirmed by this report.</p>"
        f"<table border='1'><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table>"
        "</body></html>\n",
        encoding="utf-8",
    )
    return csv_path, html_path


def audit_duplicate_bundle(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    phash_threshold: int = 8,
    dhash_threshold: int = 8,
) -> DuplicateAuditReport:
    """Audit a v2 manifest; perceptual matches remain review-only candidates."""

    tables = load_manifest_bundle(manifest_path)
    fingerprints: list[_ImageFingerprint] = []
    decode_errors: list[dict[str, str]] = []
    for image in sorted(tables.images, key=lambda item: item.global_image_id):
        path = Path(image.image_path)
        if not path.is_file():
            raise SourceValidationError(
                f"cannot audit missing image {image.global_image_id}", path=path
            )
        try:
            pixel_hash, phash, dhash = image_fingerprints(path)
        except (OSError, ValueError) as exc:
            decode_errors.append(
                {"global_image_id": image.global_image_id, "error": type(exc).__name__}
            )
            continue
        fingerprints.append(
            _ImageFingerprint(
                image=image,
                file_sha256=image.file_sha256 or sha256_file(path),
                decoded_pixel_hash=pixel_hash,
                phash=phash,
                dhash=dhash,
            )
        )
    exact_pairs: list[DuplicatePair] = []
    decoded_pairs: list[DuplicatePair] = []
    ambiguous: list[DuplicatePair] = []
    for left_index, left in enumerate(fingerprints):
        for right in fingerprints[left_index + 1 :]:
            if left.file_sha256 == right.file_sha256:
                exact_pairs.append(_pair(left, right, "EXACT"))
            elif left.decoded_pixel_hash == right.decoded_pixel_hash:
                decoded_pairs.append(_pair(left, right, "DECODED_PIXEL"))
            else:
                phash_distance = _hamming(left.phash, right.phash)
                dhash_distance = _hamming(left.dhash, right.dhash)
                if phash_distance <= phash_threshold or dhash_distance <= dhash_threshold:
                    ambiguous.append(_pair(left, right, "PERCEPTUAL_CANDIDATE"))
    exact_pairs.sort(key=lambda item: item.pair_id)
    decoded_pairs.sort(key=lambda item: item.pair_id)
    ambiguous.sort(key=lambda item: item.pair_id)
    output = Path(output_path).resolve()
    csv_path, html_path = _write_review(ambiguous, output)
    confirmed = [*exact_pairs, *decoded_pairs]
    report = DuplicateAuditReport(
        images_scanned=len(fingerprints),
        exact_pairs=exact_pairs,
        decoded_pixel_pairs=decoded_pairs,
        ambiguous_pairs=ambiguous,
        duplicate_groups=_confirmed_groups(fingerprints, confirmed),
        decode_errors=decode_errors,
        review_csv=str(csv_path),
        review_html=str(html_path),
    )
    (output / "duplicate_audit.json").write_text(
        canonical_json(report.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    return report
