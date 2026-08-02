#!/usr/bin/env python3
"""Generate frozen company research payloads from model and financial builds."""

import argparse
import json
from pathlib import Path

from mbe.builds.pipeline import build_research_payloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--financials", type=Path, required=True)
    parser.add_argument(
        "--instrument-master", type=Path,
        default=Path("universes/nifty-smallcap250-instruments.json"),
    )
    parser.add_argument("--context", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_research_payloads(
        model_dir=args.model, financial_dir=args.financials,
        instrument_master=args.instrument_master, context_path=args.context,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
