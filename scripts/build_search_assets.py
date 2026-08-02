#!/usr/bin/env python3
"""Regenerate only search JSON and its directly coupled frontend assets."""

import argparse
from pathlib import Path

from mbe.builds.offline import build_search_only


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("builds/manifests/phase11-m1-frozen-inputs.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("site"))
    args = parser.parse_args()
    print(build_search_only(args.manifest, args.out).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
