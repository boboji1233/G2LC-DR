"""License-registry validation with no acquisition side effects."""

from __future__ import annotations

import csv
from pathlib import Path

from g2lc.errors import SourceValidationError

REQUIRED_COLUMNS = {
    "dataset_id",
    "source_url",
    "license",
    "access_type",
    "redistribution_allowed",
    "approval_status",
    "source_family",
}


def validate_license_registry(path: str | Path) -> int:
    """Return row count after checking mandatory governance fields."""

    source = Path(path)
    if not source.is_file():
        raise SourceValidationError("license registry does not exist", path=source)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise SourceValidationError(f"license registry missing columns {missing}", path=source)
        rows = list(reader)
    return len(rows)
