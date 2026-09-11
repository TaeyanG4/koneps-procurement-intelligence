#!/usr/bin/env python3
"""Generate complete Kaggle Data Explorer metadata for the KONEPS public release."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.kaggle_metadata import (
    DEFAULT_SLUG,
    build_dataset_metadata,
    configured_kaggle_owner,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Kaggle dataset-metadata.json")
    parser.add_argument("--owner", help="Kaggle username or organization slug; defaults to KAGGLE_USERNAME")
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument(
        "--release-dir",
        default="data/processed/kaggle_release_202509_202608",
    )
    parser.add_argument(
        "--cover",
        default="assets/koneps_dataset_cover.png",
        help="Kaggle cover image copied beside dataset-metadata.json",
    )
    parser.add_argument(
        "--no-cover",
        action="store_true",
        help="Do not copy a dataset cover image into the release directory",
    )
    args = parser.parse_args()

    owner = args.owner or configured_kaggle_owner()
    if not owner:
        parser.error("Kaggle owner is required via --owner or KAGGLE_USERNAME")

    release_dir = Path(args.release_dir)
    metadata = build_dataset_metadata(release_dir, owner=owner, slug=args.slug)
    cover_output = None
    if not args.no_cover:
        cover_source = Path(args.cover)
        if not cover_source.exists():
            parser.error(f"Kaggle cover image not found: {cover_source}")
        cover_output = release_dir / "dataset-cover-image.png"
        shutil.copy2(cover_source, cover_output)

    print("=== KONEPS KAGGLE METADATA ===")
    print(f"id        : {metadata['id']}")
    print(f"resources : {len(metadata['resources'])}")
    print(f"license   : {metadata['licenses'][0]['name']}")
    print(f"output    : {release_dir / 'dataset-metadata.json'}")
    if cover_output is not None:
        print(f"cover     : {cover_output}")


if __name__ == "__main__":
    main()
