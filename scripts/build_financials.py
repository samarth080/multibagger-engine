#!/usr/bin/env python3
"""Build a financial dataset from a frozen model artifact, without network."""

import argparse
import json
from pathlib import Path

from mbe.builds.pipeline import build_financials_from_model
from mbe.models.instrument import stable_instrument_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--instrument-master", type=Path,
        default=Path("universes/nifty-smallcap250-instruments.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    master = json.loads(args.instrument_master.read_text())
    ids = {
        row["provider_symbols"]["yahoo"]: stable_instrument_id(
            exchange_code=row["exchange"], symbol=row["symbol"], isin=row.get("isin"),
        )
        for row in master["records"]
    }
    manifest = build_financials_from_model(
        model_dir=args.model, out=args.out, instrument_ids=ids,
    )
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
