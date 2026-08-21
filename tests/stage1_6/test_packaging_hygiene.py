from __future__ import annotations

import io
import json
import runpy
import tarfile
import tomllib
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from g2lc.audit.package import audit_artifact_set, inspect_archive

_REVIEW_BUNDLE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts" / "review_bundle.py"),
    run_name="g2lc_review_bundle_test",
)
_externalize_gate = cast(
    Callable[[dict[str, Any], str], dict[str, Any]],
    _REVIEW_BUNDLE["_externalize_gate"],
)
_normalize_text = cast(
    Callable[[str], str],
    _REVIEW_BUNDLE["_normalize_text"],
)
_normalize_json = cast(
    Callable[[Any], Any],
    _REVIEW_BUNDLE["_normalize_json"],
)


def _write_wheel(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def _write_sdist(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in members.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))


def test_package_audit_accepts_one_small_safe_wheel_and_sdist(tmp_path: Path) -> None:
    wheel = tmp_path / "g2lc_dr-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "g2lc_dr-0.1.0.tar.gz"
    _write_wheel(
        wheel,
        {
            "g2lc/__init__.py": b"__version__ = '0.1.0'\n",
            "g2lc_dr-0.1.0.dist-info/METADATA": b"Name: g2lc-dr\nVersion: 0.1.0\n",
        },
    )
    _write_sdist(
        sdist,
        {
            "g2lc_dr-0.1.0/pyproject.toml": b"[project]\nname='g2lc-dr'\n",
            "g2lc_dr-0.1.0/src/g2lc/__init__.py": b"__version__ = '0.1.0'\n",
        },
    )

    result = audit_artifact_set([wheel, sdist], workspace_roots=[tmp_path / "workspace"])

    assert result["passed"] is True
    assert {item["kind"] for item in result["archives"]} == {"wheel", "sdist"}


def test_package_audit_rejects_local_environment_and_absolute_path(tmp_path: Path) -> None:
    sdist = tmp_path / "g2lc_dr-0.1.0.tar.gz"
    _write_sdist(
        sdist,
        {
            "g2lc_dr-0.1.0/.venv311/pyvenv.cfg": b"home = C:\\Users\\person\\Python311\n",
        },
    )

    result = inspect_archive(sdist)

    assert result["passed"] is False
    assert result["forbidden_members"] == [
        {
            "path": "g2lc_dr-0.1.0/.venv311/pyvenv.cfg",
            "kind": "virtual_environment",
        }
    ]
    assert result["content_findings"][0]["kind"] == "windows_user_path"


def test_hatch_sdist_policy_is_explicit_and_excludes_generated_roots() -> None:
    configuration = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    sdist = configuration["tool"]["hatch"]["build"]["targets"]["sdist"]

    assert "/src" in sdist["include"]
    assert "/tests" in sdist["include"]
    assert {
        "/.venv*",
        "/.python",
        "/.uv-cache",
        "/artifacts",
        "/runs",
        "/data/raw",
        "/data/interim",
        "/data/processed",
        "/dist",
        "/build",
    }.issubset(set(sdist["exclude"]))


def test_review_bundle_externalizes_recursive_checksum_and_normalizes_paths() -> None:
    payload = {
        "bundle_summary": {"sha256": "old", "checksum_matches": True},
        "review_bundle_artifact": {"sha256": "old", "checksum_matches": True},
    }

    result = _externalize_gate(payload, "final_metadata.json")

    assert result["bundle_summary"]["sha256"] == "EXTERNALIZED"
    assert result["review_bundle_artifact"]["sha256"] == "EXTERNALIZED"
    assert result["embedded_review_bundle_checksum"]["authority"] == (
        "external_sha256_and_final_metadata"
    )
    local = f"command ran under {Path.cwd()}"
    assert str(Path.cwd()) not in _normalize_text(local)
    assert "<WORKSPACE>" in _normalize_text(local)


def test_externalized_gate_remains_json_serializable() -> None:
    result = _externalize_gate({"bundle_summary": {}}, "metadata.json")

    assert json.loads(json.dumps(result))["embedded_review_bundle_checksum"]["value"] == (
        "EXTERNALIZED"
    )


def test_json_path_normalization_preserves_nested_json_syntax() -> None:
    payload = {
        "stdout": '{"certificate": "C:\\\\Users\\\\person\\\\certificate.json"}',
    }

    normalized = _normalize_json(payload)
    serialized = json.dumps(normalized)

    assert json.loads(serialized) == normalized
    assert "C:\\\\Users" not in serialized
    assert "<LOCAL_PATH>" in serialized
