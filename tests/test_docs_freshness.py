"""Tests for cross-platform documentation freshness verification."""
from pathlib import Path
from scripts.build_docs import compute_source_hash, check_docs_freshness


def test_cross_platform_canonical_markdown_hashing(tmp_path: Path):
    """Verify that files with CRLF and LF produce identical SHA-256 hashes."""
    md_crlf = tmp_path / "doc_crlf.md"
    md_lf = tmp_path / "doc_lf.md"

    text_body = "# Sample Documentation\n\nSection with list:\n- Item 1\n- Item 2\n"
    md_crlf.write_bytes(text_body.replace("\n", "\r\n").encode("utf-8"))
    md_lf.write_bytes(text_body.encode("utf-8"))

    hash_crlf = compute_source_hash(md_crlf)
    hash_lf = compute_source_hash(md_lf)

    assert hash_crlf == hash_lf, "CRLF and LF versions must have identical canonical hashes"


def test_build_docs_check_clean_environment():
    """Verify that check_docs_freshness passes on the repository documentation."""
    assert check_docs_freshness() is True

