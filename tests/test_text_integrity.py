"""Automated text and encoding integrity tests."""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files and directories to ignore during scan
EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".pytest_temp",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    "node_modules",
}


def get_tracked_text_files():
    """Yield all tracked text files (.py, .md, .json, .toml, .txt)."""
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in EXCLUDED_PARTS or part.startswith(".") for part in p.parts):
            continue
        if p.suffix in {".py", ".md", ".json", ".toml", ".txt", ".yml", ".yaml"}:
            yield p


def test_no_unicode_replacement_characters():
    """Ensure no file contains the Unicode replacement character \ufffd."""
    corrupted = []
    for path in get_tracked_text_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            corrupted.append(f"{path.relative_to(REPO_ROOT)}: Failed to decode as UTF-8")
            continue

        if "\ufffd" in content:
            corrupted.append(f"{path.relative_to(REPO_ROOT)}: Contains \\ufffd")

    assert not corrupted, f"Found Unicode replacement characters in: {corrupted}"


def test_no_double_question_mark_corruption():
    """Ensure no file contains corrupted '??' indicative of encoding degradation."""
    corrupted = []
    for path in get_tracked_text_files():
        # Exclude this test file itself from the literal '??' check
        if path.name == "test_text_integrity.py":
            continue

        content = path.read_text(encoding="utf-8")
        if "??" in content:
            corrupted.append(str(path.relative_to(REPO_ROOT)))

    assert not corrupted, f"Found '??' corruption markers in: {corrupted}"


def test_authentic_unicode_and_korean_strings():
    """Ensure key documentation and source files contain expected authentic Korean text."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "—" in readme, "README.md missing Unicode em dash"
    assert "국가종합전자조달시스템" in readme, "README.md missing KONEPS Korean translation"
    assert "조달청" in readme, "README.md missing Public Procurement Service Korean name"

    endpoints = (REPO_ROOT / "src" / "koneps_intel" / "endpoints.py").read_text(encoding="utf-8")
    for expected in ["물품", "외자", "공사", "용역", "업무구분"]:
        assert expected in endpoints, f"endpoints.py missing expected Korean term: {expected}"

    data_sources = (REPO_ROOT / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    assert "공공누리" in data_sources, "DATA_SOURCES.md missing KOGL Korean term"
    assert "조달청" in data_sources, "DATA_SOURCES.md missing agency name"
