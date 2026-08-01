"""Vercel ASGI entry point for the versioned read API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.api.app import app  # noqa: E402

__all__ = ["app"]
