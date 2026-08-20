"""Build the privacy-safe Stage-1.5 source and evidence review bundle."""

from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "artifacts" / "review"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "nohead"


def _files() -> list[Path]:
    roots = [
        ROOT / "src",
        ROOT / "tests",
        ROOT / "examples" / "synthetic",
        ROOT / "schemas",
        ROOT / "docs",
        ROOT / ".github",
        ROOT / "artifacts" / "audit" / "stage1_5",
    ]
    files = [
        ROOT / "README.md",
        ROOT / "STATUS.md",
        ROOT / "CHANGELOG.md",
        ROOT / "IMPLEMENTATION_PLAN.md",
        ROOT / "AUDIT_REPORT_STAGE1_5.md",
        ROOT / "THEORY_TO_TEST_MATRIX.md",
        ROOT / "CODEX_NEXT_PROMPT_G2LC_STAGE1_5_SEMANTIC_SOUNDNESS.md",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        ROOT / "Makefile",
    ]
    for source in roots:
        if source.is_dir():
            files.extend(path for path in source.rglob("*") if path.is_file())
    excluded_parts = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    return sorted(
        {
            path.resolve()
            for path in files
            if path.is_file()
            and not excluded_parts.intersection(path.parts)
            and path.suffix not in {".pyc", ".pyo", ".ckpt", ".pth"}
        },
        key=lambda item: item.relative_to(ROOT).as_posix(),
    )


def main() -> int:
    REVIEW.mkdir(parents=True, exist_ok=True)
    short = _short_commit()
    stem = f"G2LC_DR_STAGE1_5_REVIEW_{short}"
    archive = REVIEW / f"{stem}.zip"
    checksum = REVIEW / f"{stem}.sha256"
    manifest = REVIEW / f"{stem}_manifest.tsv"
    rows = ["path\tsha256\tsize"]
    selected = _files()
    for path in selected:
        rows.append(f"{path.relative_to(ROOT).as_posix()}\t{_hash(path)}\t{path.stat().st_size}")
    manifest_text = "\n".join(rows) + "\n"
    manifest.write_text(manifest_text, encoding="utf-8")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in selected:
            bundle.write(path, path.relative_to(ROOT).as_posix())
        bundle.writestr(f"{stem}_manifest.tsv", manifest_text)
    digest = _hash(archive)
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(archive.relative_to(ROOT).as_posix())
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
