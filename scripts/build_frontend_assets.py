#!/usr/bin/env python3
"""Rebuild assets and HTML from frozen research payloads only."""

import argparse
from pathlib import Path

from mbe.builds.offline import render_frontend_only


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("builds/manifests/phase11-m1-frozen-inputs.json"),
    )
    parser.add_argument("--out", type=Path, default=Path("site"))
    args = parser.parse_args()
    print(render_frontend_only(args.manifest, args.out).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
