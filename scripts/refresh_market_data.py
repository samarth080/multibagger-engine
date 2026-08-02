#!/usr/bin/env python3
"""Explicit networked acquisition into a frozen source-data artifact."""

import argparse
from pathlib import Path

from mbe.builds.pipeline import refresh_market_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="nifty-smallcap250")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = refresh_market_data(universe_id=args.universe, out=args.out)
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
