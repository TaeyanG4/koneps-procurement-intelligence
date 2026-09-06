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


def test_markdown_language_pairs_exist():
    """Ensure all public documentation exists as paired Korean (.md) and English (.en.md) files."""
    pairs = [
        ("README.md", "README.en.md"),
        ("docs/ARCHITECTURE.md", "docs/ARCHITECTURE.en.md"),
        ("docs/DATA_SOURCES.md", "docs/DATA_SOURCES.en.md"),
        ("docs/DATA_DICTIONARY.md", "docs/DATA_DICTIONARY.en.md"),
        ("docs/LIVE_VALIDATION.md", "docs/LIVE_VALIDATION.en.md"),
        ("docs/PILOT_2026_08.md", "docs/PILOT_2026_08.en.md"),
        ("docs/RELATIONAL_MODEL.md", "docs/RELATIONAL_MODEL.en.md"),
    ]
    missing = []
    for ko_rel, en_rel in pairs:
        ko_path = REPO_ROOT / ko_rel
        en_path = REPO_ROOT / en_rel
        if not ko_path.is_file() or ko_path.stat().st_size == 0:
            missing.append(str(ko_rel))
        if not en_path.is_file() or en_path.stat().st_size == 0:
            missing.append(str(en_rel))

    assert not missing, f"Missing or empty documentation pair files: {missing}"


def test_readme_and_doc_links_resolve():
    """Ensure relative links in README and docs files resolve to existing files."""
    import re

    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    broken_links = []

    docs_to_check = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "README.en.md",
    ] + list((REPO_ROOT / "docs").glob("*.md"))

    for doc_file in docs_to_check:
        if not doc_file.is_file():
            continue
        content = doc_file.read_text(encoding="utf-8")
        for match in link_pattern.finditer(content):
            target = match.group(2).strip()
            # Ignore web links, mailto, and pure in-page anchors
            if target.startswith(("http://", "https://", "mailto:")) or target.startswith("#"):
                continue
            # Strip in-page anchor e.g. target#section
            target_clean = target.split("#")[0].strip()
            if not target_clean:
                continue
            # Resolve relative to doc_file
            target_path = (doc_file.parent / target_clean).resolve()
            if not target_path.exists():
                broken_links.append(
                    f"{doc_file.relative_to(REPO_ROOT)}: '{target}' -> {target_clean} (not found)"
                )

    assert not broken_links, f"Found broken relative links:\n" + "\n".join(broken_links)


def test_no_broken_arrows_or_separators():
    """Ensure no text files contain corrupted question-mark arrows (' ? ') or broken separators."""
    corrupted = []
    for path in get_tracked_text_files():
        if path.name == "test_text_integrity.py":
            continue
        content = path.read_text(encoding="utf-8")
        if " ? " in content:
            corrupted.append(f"{path.relative_to(REPO_ROOT)}: Contains ' ? '")

    assert not corrupted, f"Found corrupted question-mark separators in: {corrupted}"


def test_legitimate_url_question_marks_remain_valid():
    """Verify that legitimate query parameter question marks in URLs or regexes remain intact."""
    data_sources = (REPO_ROOT / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
    assert "data.go.kr" in data_sources
    assert "?" in data_sources or "?" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_generated_docx_files_exist():
    """Ensure all 12 project-authored DOCX files in docs/generated/ exist and are valid non-empty files."""
    import zipfile

    expected_docx = [
        "ARCHITECTURE.ko.docx",
        "ARCHITECTURE.en.docx",
        "DATA_SOURCES.ko.docx",
        "DATA_SOURCES.en.docx",
        "DATA_DICTIONARY.ko.docx",
        "DATA_DICTIONARY.en.docx",
        "LIVE_VALIDATION.ko.docx",
        "LIVE_VALIDATION.en.docx",
        "PILOT_2026_08.ko.docx",
        "PILOT_2026_08.en.docx",
        "RELATIONAL_MODEL.ko.docx",
        "RELATIONAL_MODEL.en.docx",
    ]

    gen_dir = REPO_ROOT / "docs" / "generated"
    assert gen_dir.exists(), "docs/generated directory does not exist"

    missing_or_invalid = []
    for docx_name in expected_docx:
        file_path = gen_dir / docx_name
        if not file_path.is_file() or file_path.stat().st_size == 0:
            missing_or_invalid.append(f"{docx_name} (missing or 0 bytes)")
            continue
        # DOCX is a zip file containing [Content_Types].xml
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                if "[Content_Types].xml" not in zf.namelist():
                    missing_or_invalid.append(f"{docx_name} (corrupt zip structure)")
        except Exception as e:
            missing_or_invalid.append(f"{docx_name} (zip error: {e})")

    assert not missing_or_invalid, f"Issues with generated DOCX files: {missing_or_invalid}"



