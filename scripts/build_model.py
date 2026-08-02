#!/usr/bin/env python3
"""Build and persist scores from a frozen source-data manifest."""

import argparse
from pathlib import Path

from mbe.builds.pipeline import build_model_from_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_model_from_source(source_dir=args.source, out=args.out)
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
