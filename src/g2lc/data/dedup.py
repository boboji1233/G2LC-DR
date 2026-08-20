"""Exact-hash duplicate audit; scalable perceptual stages remain explicitly later work."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from g2lc.data.manifest import load_manifest
from g2lc.errors import SourceValidationError
from g2lc.utils.io import sha256_file


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
