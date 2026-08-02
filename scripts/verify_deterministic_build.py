#!/usr/bin/env python3
"""Build twice from one frozen manifest and compare every output byte."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from mbe.builds.offline import render_site_from_manifest, tree_digest
try:
    from scripts.verify_release import public_value_hashes
except ModuleNotFoundError:  # direct ``python scripts/...`` execution
    from verify_release import public_value_hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=Path("builds/manifests/phase11-m1-frozen-inputs.json"),
    )
    args = parser.parse_args()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="mbe-determinism-") as temp:
        root = Path(temp)
        first, second = root / "first", root / "second"
        render_site_from_manifest(args.manifest, first)
        render_site_from_manifest(args.manifest, second)
        first_hash, second_hash = tree_digest(first), tree_digest(second)
        first_values, second_values = public_value_hashes(first), public_value_hashes(second)
        result = {
            "status": "pass" if first_hash == second_hash and first_values == second_values else "fail",
            "first_output_sha256": first_hash,
            "second_output_sha256": second_hash,
            "output_hashes_identical": first_hash == second_hash,
            "public_value_hashes_identical": first_values == second_values,
            "public_value_hashes": first_values,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
