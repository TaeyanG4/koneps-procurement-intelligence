#!/usr/bin/env python3
"""Build project-authored DOCX documentation from Markdown files.

Uses python-docx to parse project Markdown documents and generate styled .docx files
into docs/generated/.

The --check mode only verifies Markdown source hashes against the committed manifest.
It does NOT require python-docx to be installed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
OUTPUT_DIR = DOCS_DIR / "generated"

DOCUMENT_MAPPING: List[Tuple[str, str]] = [
    ("ARCHITECTURE.md", "ARCHITECTURE.ko.docx"),
    ("ARCHITECTURE.en.md", "ARCHITECTURE.en.docx"),
    ("DATA_SOURCES.md", "DATA_SOURCES.ko.docx"),
    ("DATA_SOURCES.en.md", "DATA_SOURCES.en.docx"),
    ("DATA_DICTIONARY.md", "DATA_DICTIONARY.ko.docx"),
    ("DATA_DICTIONARY.en.md", "DATA_DICTIONARY.en.docx"),
    ("LIVE_VALIDATION.md", "LIVE_VALIDATION.ko.docx"),
    ("LIVE_VALIDATION.en.md", "LIVE_VALIDATION.en.docx"),
    ("PILOT_2026_08.md", "PILOT_2026_08.ko.docx"),
    ("PILOT_2026_08.en.md", "PILOT_2026_08.en.docx"),
    ("RELATIONAL_MODEL.md", "RELATIONAL_MODEL.ko.docx"),
    ("RELATIONAL_MODEL.en.md", "RELATIONAL_MODEL.en.docx"),
]


def clean_inline_markdown(text: str) -> str:
    """Remove inline markdown formatting for plain document text."""
    # Bold / Italic
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    # Inline code
    text = re.sub(r"`(.*?)`", r"\1", text)
    # Links [label](url)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # LaTeX math \text{...} or $...$
    text = text.replace(r"\text{", "").replace("}", "")
    text = text.replace("$", "").replace(r"\rightarrow", "→")
    return text.strip()


def parse_table_row(line: str) -> List[str]:
    """Parse pipe-separated table row into trimmed cell values."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return [clean_inline_markdown(c) for c in cells]


def markdown_to_docx(md_path: Path, docx_path: Path) -> None:
    """Convert a Markdown file to a styled DOCX document.

    NOTE: python-docx is imported lazily here so that --check mode does not
    require the library to be installed.
    """
    # Lazy import — only needed when actually generating DOCX files
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()

    # Configure base margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    lines = md_path.read_text(encoding="utf-8").splitlines()
    in_code_block = False
    code_block_lines: List[str] = []
    in_table = False
    table_rows: List[List[str]] = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        num_cols = max(len(r) for r in table_rows)
        # Filter out markdown alignment separator rows (e.g. |---|---|)
        data_rows = [r for r in table_rows if not all(re.match(r"^:?-+:?$", c) for c in r if c)]
        if not data_rows:
            in_table = False
            table_rows = []
            return

        table = doc.add_table(rows=len(data_rows), cols=num_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Light Grid Accent 1" if "Light Grid Accent 1" in doc.styles else "Table Grid"

        for i, row_data in enumerate(data_rows):
            row = table.rows[i]
            for j, cell_text in enumerate(row_data):
                if j < num_cols:
                    cell = row.cells[j]
                    cell.text = cell_text
                    # Header formatting
                    if i == 0:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.font.bold = True

        doc.add_paragraph()  # spacing
        in_table = False
        table_rows = []

    def flush_code_block():
        nonlocal in_code_block, code_block_lines
        if code_block_lines:
            code_text = "\n".join(code_block_lines)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            run = p.add_run(code_text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(70, 70, 70)
        in_code_block = False
        code_block_lines = []

    for line in lines:
        stripped = line.strip()

        # Handle Code blocks
        if stripped.startswith("```"):
            if in_code_block:
                flush_code_block()
            else:
                if in_table:
                    flush_table()
                in_code_block = True
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # Handle Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_rows.append(parse_table_row(line))
            continue
        elif in_table:
            flush_table()

        # Empty line
        if not stripped:
            continue

        # Horizontal rules
        if stripped in {"---", "***", "___"}:
            continue

        # Headings
        if stripped.startswith("# "):
            p = doc.add_heading(level=0)
            run = p.add_run(clean_inline_markdown(stripped[2:]))
            run.font.bold = True
        elif stripped.startswith("## "):
            p = doc.add_heading(level=1)
            p.add_run(clean_inline_markdown(stripped[3:]))
        elif stripped.startswith("### "):
            p = doc.add_heading(level=2)
            p.add_run(clean_inline_markdown(stripped[4:]))
        elif stripped.startswith("#### "):
            p = doc.add_heading(level=3)
            p.add_run(clean_inline_markdown(stripped[5:]))
        # Blockquotes / Alerts
        elif stripped.startswith(">"):
            text = clean_inline_markdown(stripped.lstrip("> "))
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.3)
            run = p.add_run(text)
            run.font.italic = True
            run.font.color.rgb = RGBColor(100, 100, 100)
        # List items
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = clean_inline_markdown(stripped[2:])
            doc.add_paragraph(text, style="List Bullet")
        elif re.match(r"^\d+\.\s+", stripped):
            match = re.match(r"^\d+\.\s+", stripped)
            text = clean_inline_markdown(stripped[match.end():])
            doc.add_paragraph(text, style="List Number")
        # Regular paragraph
        else:
            text = clean_inline_markdown(stripped)
            doc.add_paragraph(text)

    if in_table:
        flush_table()
    if in_code_block:
        flush_code_block()

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))


def compute_source_hash(md_path: Path) -> str:
    """Compute a cross-platform SHA-256 hash of a Markdown source file.

    Normalizes CRLF and CR line endings to LF before hashing so that
    the hash is identical on Windows (CRLF) and Linux/macOS (LF).
    This ensures that the manifest recorded on Windows is valid in
    GitHub Actions (Ubuntu).
    """
    raw_bytes = md_path.read_bytes()
    # Strict UTF-8 decode, normalize line endings, re-encode to canonical UTF-8
    text = raw_bytes.decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    canonical = text.encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()



def build_all_docs() -> List[Path]:
    """Generate all target DOCX files from maintained Markdown files and write manifest."""
    generated: List[Path] = []
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {}

    print(f"Building project-authored DOCX files from {DOCS_DIR} into {OUTPUT_DIR}...")
    for md_name, docx_name in DOCUMENT_MAPPING:
        md_file = DOCS_DIR / md_name
        docx_file = OUTPUT_DIR / docx_name

        if not md_file.exists():
            print(f"  [WARN] Source file not found: {md_file}")
            continue

        src_hash = compute_source_hash(md_file)
        markdown_to_docx(md_file, docx_file)
        size_bytes = docx_file.stat().st_size
        size_kb = round(size_bytes / 1024, 1)
        print(f"  [OK] Generated {docx_name} ({size_kb} KB)")
        generated.append(docx_file)

        manifest[docx_name] = {
            "source": f"docs/{md_name}",
            "source_sha256": src_hash,
            "docx_size_bytes": size_bytes,
        }

    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  [OK] Saved DOCX source manifest to {manifest_path}")

    print(f"\nSuccessfully generated {len(generated)} DOCX documents.")
    return generated


def check_docs_freshness() -> bool:
    """Verify that all generated DOCX documents match the current SHA-256 of their Markdown sources."""
    manifest_path = OUTPUT_DIR / "manifest.json"
    if not manifest_path.exists():
        print(f"[FAIL] Manifest missing: {manifest_path}. Run 'python scripts/build_docs.py' to generate.")
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_fresh = True
    for md_name, docx_name in DOCUMENT_MAPPING:
        md_file = DOCS_DIR / md_name
        docx_file = OUTPUT_DIR / docx_name

        if not md_file.exists():
            print(f"[FAIL] Source Markdown file not found: {md_file}")
            all_fresh = False
            continue

        if not docx_file.exists():
            print(f"[FAIL] Generated DOCX missing: {docx_file}")
            all_fresh = False
            continue

        entry = manifest.get(docx_name)
        if not entry:
            print(f"[FAIL] Manifest entry missing for: {docx_name}")
            all_fresh = False
            continue

        current_hash = compute_source_hash(md_file)
        recorded_hash = entry.get("source_sha256")
        if current_hash != recorded_hash:
            print(f"[FAIL] STALE DOCX: {docx_name} (source {md_name} was modified without regenerating DOCX).")
            all_fresh = False
        else:
            print(f"[OK] FRESH: {docx_name}")

    if all_fresh:
        print(f"\n[PASS] All {len(DOCUMENT_MAPPING)} DOCX documents are up-to-date with their Markdown sources.")
    return all_fresh


if __name__ == "__main__":
    if "--check" in sys.argv:
        is_fresh = check_docs_freshness()
        sys.exit(0 if is_fresh else 1)
    else:
        build_all_docs()

