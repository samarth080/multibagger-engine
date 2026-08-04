"""Offline site/search/frontend builders backed only by hashed artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from mbe.builds.domain import (
    FrozenInputManifest, SiteBuildManifest, sha256_file, sha256_tree,
)
from mbe.builds.network import deny_network
from mbe.publish import (
    ASSET_DIR, _copy_assets, _render_company_page, _render_index,
    _render_methodology, _render_not_found, _render_screener,
    build_search_asset_payload,
)
from mbe.research.builder import canonical_company_url
from mbe.search.classification import CLASSIFICATION_POLICY_VERSION
from mbe.search.ranking import SEARCH_RANKING_POLICY_VERSION


def load_manifest(path: Path) -> tuple[FrozenInputManifest, Path]:
    manifest = FrozenInputManifest.model_validate_json(path.read_text())
    root = path.resolve().parents[2]
    manifest.validate_artifacts(root)
    return manifest, root


def _artifact(manifest: FrozenInputManifest, role: str):
    matches = [item for item in manifest.artifacts if item.role == role]
    if len(matches) != 1:
        raise ValueError(f"expected one frozen artifact with role {role!r}, found {len(matches)}")
    return matches[0]


def _json(root: Path, manifest: FrozenInputManifest, role: str):
    return json.loads((root / _artifact(manifest, role).path).read_text())


def _controlled_time(manifest: FrozenInputManifest) -> datetime:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if raw_epoch:
        return datetime.fromtimestamp(int(raw_epoch), tz=timezone.utc)
    return manifest.created_at.astimezone(timezone.utc)


def _copy_frozen_artifacts(
    manifest: FrozenInputManifest, root: Path, out: Path,
) -> None:
    for artifact in manifest.artifacts:
        if not artifact.role.startswith("site-"):
            continue
        source = root / artifact.path
        try:
            relative = source.relative_to(root / "site")
        except ValueError:
            continue
        target = out / relative
        if artifact.kind == "tree":
            if target.exists() and target.resolve() != source.resolve():
                shutil.rmtree(target)
            if target.resolve() != source.resolve():
                shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.resolve() != source.resolve():
                shutil.copyfile(source, target)


def _load_research(root: Path, manifest: FrozenInputManifest) -> dict[str, dict]:
    directory = root / _artifact(manifest, "site-research").path
    return {
        path.stem: json.loads(path.read_text())["data"]
        for path in sorted(directory.glob("*.json"))
    }


def render_frontend_only(
    manifest_path: Path, out: Path, *, write_manifest: bool = True,
) -> SiteBuildManifest:
    manifest, root = load_manifest(manifest_path)
    controlled_time = _controlled_time(manifest)
    data = _json(root, manifest, "site-data")
    screener = _json(root, manifest, "site-screener")
    data["_screener_rows"] = screener["data"]["rows"]
    research = _load_research(root, manifest)
    out.mkdir(parents=True, exist_ok=True)
    with deny_network() as audit, patch.dict(
        os.environ, {"MBE_FRONTEND_DATA_MODE": "static"}, clear=False,
    ):
        _copy_assets(out)
        company_dir = out / "company"
        reports_dir = out / "reports"
        company_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        expected_company = {f"{instrument_id}.html" for instrument_id in research}
        for old in company_dir.glob("*.html"):
            if old.name not in expected_company:
                old.unlink()
        for instrument_id, payload in sorted(research.items()):
            (company_dir / f"{instrument_id}.html").write_text(
                _render_company_page(payload)
            )
        top = data.get("top", [])
        expected_legacy = {row["ticker_path"] for row in top}
        for old in reports_dir.glob("*.html"):
            if old.name not in expected_legacy:
                old.unlink()
        for row in top:
            payload = research[row["instrument_id"]]
            (reports_dir / row["ticker_path"]).write_text(
                _render_company_page(payload, canonical=False)
            )
        (out / "index.html").write_text(
            _render_index(data, rendered_at=controlled_time)
        )
        (out / "methodology.html").write_text(_render_methodology(data))
        (out / "screener.html").write_text(_render_screener(data))
        (out / "404.html").write_text(_render_not_found())
        sitemap_urls = ["/", "/screener.html", "/methodology.html", *(
            canonical_company_url(instrument_id) for instrument_id in sorted(research)
        )]
        from mbe.publish import PUBLIC_SITE_URL
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(
                f"  <url><loc>{PUBLIC_SITE_URL}{path}</loc></url>\n"
                for path in sitemap_urls
            )
            + "</urlset>\n"
        )
        (out / "sitemap.xml").write_text(sitemap)
        (out / "robots.txt").write_text(
            "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /reports/\n"
            f"Sitemap: {PUBLIC_SITE_URL}/sitemap.xml\n"
        )
    if audit.attempted:
        raise AssertionError("offline frontend build attempted network access")
    result = _site_manifest(manifest, out, controlled_time, "frontend-only")
    if write_manifest:
        _write_site_manifest(out, result)
    return result


def build_search_only(
    manifest_path: Path, out: Path, *, write_manifest: bool = True,
) -> SiteBuildManifest:
    manifest, root = load_manifest(manifest_path)
    controlled_time = _controlled_time(manifest)
    data = _json(root, manifest, "site-data")
    screener = _json(root, manifest, "site-screener")
    data["_screener_rows"] = screener["data"]["rows"]
    nse_rows = json.loads((root / "universes/nse-search-universe.json").read_text())["records"]
    bse_rows = json.loads((root / "universes/bse-search-universe.json").read_text())["records"]
    with deny_network() as audit:
        payload = build_search_asset_payload(
            data=data, search_universe_rows=nse_rows, bse_rows=bse_rows,
        )
        target = out / "api/v1/search-index.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=1))
        assets = out / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        for name in ("app.js", "app.css"):
            shutil.copyfile(ASSET_DIR / name, assets / name)
    if audit.attempted:
        raise AssertionError("offline search build attempted network access")
    result = _site_manifest(manifest, out, controlled_time, "search-only")
    if write_manifest:
        _write_site_manifest(out, result)
    return result


def build_coverage_only(manifest_path: Path, out: Path) -> dict:
    """Aggregates the per-record coverage fields already written into
    api/v1/search-index.json (by build_search_only) into a small reporting
    artifact. Must run after build_search_only against the same `out` — it
    does not recompute assess_coverage itself, only tallies what's already
    there, so it can never disagree with the per-instrument data."""
    manifest, root = load_manifest(manifest_path)
    controlled_time = _controlled_time(manifest)
    search_path = out / "api/v1/search-index.json"
    with deny_network() as audit:
        rows = json.loads(search_path.read_text())["data"]
        level_counts = {"0": 0, "1": 0, "2": 0, "3": 0}
        reason_counts: dict[str, int] = {}
        for row in rows:
            level_counts[str(row["research_coverage_level"])] += 1
            for reason in row.get("research_eligibility_reasons", []):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        payload = {
            "schema_version": "1.0",
            "coverage_policy_version": rows[0]["coverage_policy_version"] if rows else "",
            "search_build_id": sha256_file(search_path),
            "financial_build_id": manifest.financial_build_id,
            "model_build_ids": [v for v in manifest.model_build_ids.values() if v],
            "instrument_count": len(rows),
            "level_counts": level_counts,
            "coverage_reasons": reason_counts,
            "generated_at": controlled_time.isoformat(),
            "source_hashes": {
                "search_index": sha256_file(search_path),
                "financial_build": manifest.financial_build_id,
                "model_build": next(iter(manifest.model_build_ids.values()), None),
            },
        }
        target = out / "data/research-coverage.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=1, sort_keys=True))
    if audit.attempted:
        raise AssertionError("offline coverage-artifact build attempted network access")
    return payload


def render_site_from_manifest(manifest_path: Path, out: Path) -> SiteBuildManifest:
    manifest, root = load_manifest(manifest_path)
    controlled_time = _controlled_time(manifest)
    with deny_network() as audit:
        _copy_frozen_artifacts(manifest, root, out)
    if audit.attempted:
        raise AssertionError("offline site build attempted network access")
    # Frontend rendering has its own nested fail-closed guard.
    render_frontend_only(manifest_path, out, write_manifest=False)
    result = _site_manifest(manifest, out, controlled_time, "offline")
    # Search is copied from the frozen search build. It is never recomputed by
    # the normal render command.
    _write_site_manifest(out, result)
    return result


def _output_hashes(out: Path) -> dict[str, str]:
    candidates = {
        "data": out / "data.json",
        "rankings": out / "api/v1/rankings.json",
        "screener": out / "api/v1/screener.json",
        "search": out / "api/v1/search-index.json",
        "financials": out / "api/v1/financials",
        "research": out / "api/v1/research",
        "universal_scores": out / "api/v1/universal-scores",
        "company_pages": out / "company",
        "legacy_pages": out / "reports",
        "frontend_assets": out / "assets",
        "index_html": out / "index.html",
        "screener_html": out / "screener.html",
        "methodology_html": out / "methodology.html",
    }
    hashes = {}
    for key, path in candidates.items():
        if path.is_dir():
            hashes[key] = sha256_tree(path)
        elif path.is_file():
            hashes[key] = sha256_file(path)
    return hashes


def _site_manifest(
    frozen: FrozenInputManifest, out: Path, generated_at: datetime,
    mode: str,
) -> SiteBuildManifest:
    data = json.loads((out / "data.json").read_text()) if (out / "data.json").exists() else {}
    search_path = out / "api/v1/search-index.json"
    search_hash = sha256_file(search_path) if search_path.exists() else frozen.search_build_id
    build = data.get("build") or {}
    news_dates = [
        item.get("published") for row in data.get("top", []) for item in row.get("news", [])
        if item.get("published")
    ]
    news_cutoff = max(news_dates) if news_dates else None
    return SiteBuildManifest.create(
        generated_at=generated_at, search_build_id=search_hash,
        search_ranking_policy_version=SEARCH_RANKING_POLICY_VERSION,
        classification_policy_version=CLASSIFICATION_POLICY_VERSION,
        small_cap_model_build_id=(
            frozen.model_build_ids.get("india-small-cap-v1")
            or build.get("build_id") or "unknown"
        ),
        financial_build_id=frozen.financial_build_id,
        universe_versions=frozen.universe_versions,
        input_artifact_hashes={item.role: item.sha256 for item in frozen.artifacts},
        output_artifact_hashes=_output_hashes(out),
        build_configuration_hash=frozen.configuration_hash(),
        build_mode=mode, news_cutoff=(
            datetime.fromisoformat(news_cutoff.replace("Z", "+00:00"))
            if news_cutoff else None
        ),
        warnings=list(frozen.warnings),
    )


def _write_site_manifest(out: Path, manifest: SiteBuildManifest) -> None:
    (out / "build-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )


def tree_digest(path: Path) -> str:
    """One deterministic digest for every output except its self-describing manifest."""
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        if item.name == "build-manifest.json" and item.parent == path:
            continue
        relative = item.relative_to(path).as_posix().encode()
        digest.update(relative + b"\0" + bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()
