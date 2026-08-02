#!/usr/bin/env python3
"""Regenerate the static coverage-level reporting artifact. Must run after
build_search_assets.py against the same --out directory."""

import argparse
import json
from pathlib import Path

from mbe.builds.offline import build_coverage_only


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("builds/manifests/phase11-m1-frozen-inputs.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("site"))
    args = parser.parse_args()
    print(json.dumps(build_coverage_only(args.manifest, args.out), indent=2))


if __name__ == "__main__":
    main()
