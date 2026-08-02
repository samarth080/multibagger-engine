#!/usr/bin/env python3
"""Deterministic release checks for the generated static site.

This verifier performs no network access and does not mutate the build. It is
intended for local CI, preview promotion checks, and rollback validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lxml import html


# Phase 11 M1 adds one root site-build manifest to the 508 Phase 10C JSON files.
EXPECTED = {"html": 279, "json": 509, "company": 250, "legacy": 25, "sitemap": 253}
REQUIRED_HEADERS = {
    "Content-Security-Policy",
    "Cross-Origin-Opener-Policy",
    "Permissions-Policy",
    "Referrer-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "X-Permitted-Cross-Domain-Policies",
}


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def public_value_hashes(site: Path) -> dict[str, str]:
    screener = json.loads((site / "api/v1/screener.json").read_text())
    score_rows = sorted(
        ({"instrument_id": row["instrument_id"], "values": row["values"], "report_url": row["report_url"]}
         for row in screener["data"]["rows"]),
        key=lambda row: row["instrument_id"],
    )
    financial_rows = []
    for path in sorted((site / "api/v1/research").glob("*.json")):
        data = json.loads(path.read_text())["data"]
        ranking = {key: value for key, value in data["ranking"].items()
                   if key not in {"build_timestamp", "data_cutoff", "model_build_id"}}
        financials = {key: value for key, value in data["financials"].items() if key != "data_cutoff"}
        financial_rows.append({
            "instrument_id": data["identity"]["instrument_id"],
            "ranking": ranking,
            "financials": financials,
        })
    return {"scores_sha256": _hash(score_rows), "financials_sha256": _hash(financial_rows)}


def verify(site: Path, root: Path, fixture: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    html_paths = sorted(site.rglob("*.html"))
    json_paths = sorted(site.rglob("*.json"))
    counts = {
        "html": len(html_paths),
        "json": len(json_paths),
        "company": len(list((site / "company").glob("*.html"))),
        "legacy": len(list((site / "reports").glob("*.html"))),
    }
    for key, expected in EXPECTED.items():
        if key != "sitemap" and counts[key] != expected:
            errors.append(f"expected {expected} {key} files, found {counts[key]}")

    for path in json_paths:
        try:
            json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(site)}: {exc}")

    build_manifest_path = site / "build-manifest.json"
    if not build_manifest_path.exists():
        errors.append("missing deterministic site/build-manifest.json")
    else:
        from mbe.builds.domain import FrozenInputManifest, SiteBuildManifest, sha256_file, sha256_tree
        try:
            site_manifest = SiteBuildManifest.model_validate_json(
                build_manifest_path.read_text()
            )
        except Exception as exc:
            errors.append(f"invalid site build manifest: {exc}")
        else:
            if site_manifest.network_used:
                errors.append("offline site build manifest reports network_used=true")
            if site_manifest.build_mode != "offline" or site_manifest.status != "complete":
                errors.append("site build manifest must describe a complete offline build")
            output_paths = {
                "data": site / "data.json",
                "rankings": site / "api/v1/rankings.json",
                "screener": site / "api/v1/screener.json",
                "search": site / "api/v1/search-index.json",
                "financials": site / "api/v1/financials",
                "research": site / "api/v1/research",
                "company_pages": site / "company",
                "legacy_pages": site / "reports",
                "frontend_assets": site / "assets",
                "index_html": site / "index.html",
                "screener_html": site / "screener.html",
                "methodology_html": site / "methodology.html",
            }
            actual = {
                key: sha256_tree(path) if path.is_dir() else sha256_file(path)
                for key, path in output_paths.items()
            }
            if actual != site_manifest.output_artifact_hashes:
                errors.append("site output hashes do not match the site build manifest")
        frozen_path = root / "builds/manifests/phase11-m1-frozen-inputs.json"
        try:
            frozen = FrozenInputManifest.model_validate_json(frozen_path.read_text())
            frozen.validate_artifacts(root)
        except Exception as exc:
            errors.append(f"invalid frozen input manifest: {exc}")

    indexable_canonicals: set[str] = set()
    titles: dict[str, str] = {}
    for path in html_paths:
        relative = path.relative_to(site).as_posix()
        try:
            document = html.fromstring(path.read_bytes())
        except Exception as exc:  # lxml reports a useful parser message
            errors.append(f"invalid HTML {relative}: {exc}")
            continue
        checks = {
            "main": document.xpath("//main"),
            "h1": document.xpath("//h1"),
            "title": document.xpath("/html/head/title"),
            "canonical": document.xpath("/html/head/link[@rel='canonical']/@href"),
            "description": document.xpath("/html/head/meta[@name='description']/@content"),
        }
        for label, values in checks.items():
            if len(values) != 1:
                errors.append(f"{relative}: expected one {label}, found {len(values)}")
        ids = document.xpath("//*[@id]/@id")
        if len(ids) != len(set(ids)):
            errors.append(f"{relative}: duplicate HTML id")
        if document.xpath("//script[not(@src) and normalize-space(text())]"):
            errors.append(f"{relative}: inline executable script violates CSP")
        robots = " ".join(document.xpath("/html/head/meta[@name='robots']/@content")).lower()
        is_legacy = relative.startswith("reports/")
        is_404 = relative == "404.html"
        if (is_legacy or is_404) and "noindex" not in robots:
            errors.append(f"{relative}: compatibility/error page must be noindex")
        if not is_legacy and not is_404 and checks["canonical"]:
            canonical = checks["canonical"][0]
            if canonical in indexable_canonicals:
                errors.append(f"{relative}: duplicate indexable canonical {canonical}")
            indexable_canonicals.add(canonical)
            if checks["title"]:
                title = checks["title"][0].text_content().strip()
                if title in titles:
                    errors.append(f"{relative}: duplicate indexable title shared with {titles[title]}")
                titles[title] = relative
        for target in document.xpath("//@href | //@src"):
            lowered = target.strip().lower()
            if lowered.startswith(("javascript:", "data:text/html", "vbscript:")):
                errors.append(f"{relative}: unsafe URL protocol {target[:32]}")
        for link in document.xpath("//a[@target='_blank']"):
            rel = set((link.get("rel") or "").split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                errors.append(f"{relative}: target=_blank link lacks noopener noreferrer")

    sitemap = html.fromstring((site / "sitemap.xml").read_bytes())
    locations = sitemap.xpath("//*[local-name()='loc']/text()")
    if len(locations) != EXPECTED["sitemap"]:
        errors.append(f"expected {EXPECTED['sitemap']} sitemap URLs, found {len(locations)}")
    sitemap_set = set(locations)
    if sitemap_set != indexable_canonicals:
        errors.append("sitemap URLs do not exactly match indexable canonical URLs")
    robots_text = (site / "robots.txt").read_text()
    for directive in ("Disallow: /api/", "Disallow: /reports/", "Sitemap: https://"):
        if directive not in robots_text:
            errors.append(f"robots.txt missing {directive}")

    config = json.loads((root / "vercel.json").read_text())
    global_rules = [rule for rule in config.get("headers", []) if rule.get("source") == "/(.*)"]
    configured = {entry["key"]: entry["value"] for rule in global_rules for entry in rule["headers"]}
    missing_headers = sorted(REQUIRED_HEADERS - configured.keys())
    if missing_headers:
        errors.append(f"vercel global security headers missing: {', '.join(missing_headers)}")
    csp = configured.get("Content-Security-Policy", "")
    if "script-src 'self'" not in csp or "unsafe-eval" in csp or "script-src 'self' 'unsafe-inline'" in csp:
        errors.append("CSP script policy is not release-safe")
    if config.get("outputDirectory") != "site":
        errors.append("Vercel outputDirectory must remain site")

    maps = sorted(path.relative_to(site).as_posix() for path in site.rglob("*.map"))
    if maps:
        errors.append(f"source maps present in public output: {maps[:3]}")
    budgets = {
        "app_css_bytes": (site / "assets/app.css").stat().st_size,
        "app_js_bytes": (site / "assets/app.js").stat().st_size,
        "screener_js_bytes": (site / "assets/screener.js").stat().st_size,
        "largest_company_html_bytes": max(path.stat().st_size for path in (site / "company").glob("*.html")),
    }
    limits = {"app_css_bytes": 100_000, "app_js_bytes": 100_000, "screener_js_bytes": 100_000,
              "largest_company_html_bytes": 300_000}
    for key, value in budgets.items():
        if value > limits[key]:
            errors.append(f"budget exceeded: {key}={value} > {limits[key]}")

    hashes = public_value_hashes(site)
    if fixture:
        expected_hashes = json.loads(fixture.read_text())
        if hashes != expected_hashes:
            errors.append("public score or financial value hash differs from the Phase 8 fixture")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "counts": {**counts, "sitemap": len(locations), "indexable": len(indexable_canonicals)},
        "budgets": budgets,
        "public_value_hashes": hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = verify(args.site, root, args.fixture)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
