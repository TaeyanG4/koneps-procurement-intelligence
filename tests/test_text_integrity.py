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
    """Ensure key documentation and source files contain expected authentic Korean text and proper language links."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# 대한민국 공공조달 인텔리전스 — KONEPS"), "README.md must start with Korean title"
    assert "**한국어** | [English](README.en.md)" in readme, "README.md missing language selector"
    assert "—" in readme, "README.md missing Unicode em dash"
    assert "국가종합전자조달시스템" in readme, "README.md missing KONEPS Korean translation"
    assert "나라장터" in readme, "README.md missing Narajangteo Korean term"
    assert "조달청" in readme, "README.md missing Public Procurement Service Korean name"
    assert "공공누리" in readme, "README.md missing KOGL Korean term"

    readme_en = (REPO_ROOT / "README.en.md").read_text(encoding="utf-8")
    assert readme_en.startswith("# South Korea Public Procurement Intelligence — KONEPS"), "README.en.md must start with English title"
    assert "[한국어](README.md) | **English**" in readme_en, "README.en.md missing language selector"

    endpoints = (REPO_ROOT / "src" / "koneps_intel" / "endpoints.py").read_text(encoding="utf-8")
    for expected in ["물품", "외자", "공사", "용역", "업무구분"]:
        assert expected in endpoints, f"endpoints.py missing expected Korean term: {expected}"

    data_sources = (REPO_ROOT / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    assert "공공누리" in data_sources, "DATA_SOURCES.md missing KOGL Korean term"
    assert "조달청" in data_sources, "DATA_SOURCES.md missing agency name"


def test_cautious_licensing_language():
    """Ensure README files and docs use cautious per-source license language."""
    readme_ko = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    expected_ko = "각 원천 데이터의 이용조건은 공공데이터포털 및 나라장터의 해당 서비스 페이지에 표시된 이용허락범위를 따릅니다. Kaggle 재배포 전 데이터 소스별 이용조건을 다시 확인합니다."
    assert expected_ko in readme_ko, "README.md missing cautious Korean license wording"

    readme_en = (REPO_ROOT / "README.en.md").read_text(encoding="utf-8")
    expected_en = "Specific terms of use for each raw dataset follow the scope of permission indicated on the respective service page on data.go.kr and KONEPS. Terms of use per data source will be re-verified prior to Kaggle redistribution."
    assert expected_en in readme_en, "README.en.md missing cautious English license wording"

    data_sources = (REPO_ROOT / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    assert "Source-by-Source License Re-Verification" in data_sources, "DATA_SOURCES.md missing publication checkpoint"


def test_python_version_and_metadata_consistency():
    """Ensure pyproject.toml, CI workflow, and READMEs agree on supported Python version >=3.11."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.11"' in pyproject, "pyproject.toml must require >=3.11"
    assert "Production-grade" not in pyproject, "pyproject.toml must not use premature 'Production-grade' overclaim"

    ci_yml = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '"3.11"' in ci_yml and '"3.12"' in ci_yml, "ci.yml must test 3.11 and 3.12"

    readme_ko = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "3.11" in readme_ko and "3.12" in readme_ko

    readme_en = (REPO_ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "3.11" in readme_en and "3.12" in readme_en


