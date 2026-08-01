from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mbe.cli import app as cli_app
from mbe.data.provider import ProviderError
from mbe.financials.nse_official import parse_discovery_entry
from mbe.financials.official_domain import AttachmentFormat, FetchedDocument
from mbe.financials.parsers import parse_nse_results_xbrl
from mbe.financials.reconciliation import reconcile_values
from mbe.financials.domain import ConsolidationBasis
from mbe.financials.document_fetch import FetchPolicy, HttpResult, SafeDocumentFetcher
from mbe.financials.pilot import (
    AcquisitionLimits,
    CorpusManifest,
    OPERATOR_ACKNOWLEDGEMENT,
    OperatorReviewRecord,
    PilotManifest,
    ReviewDecision,
    ReviewState,
    build_operator_review_record,
    atomic_write_private_json,
    effective_review_decisions,
    evaluate_ground_truth,
    load_corpus_manifest,
    load_pilot_manifest,
    tier_a_fact_eligibility,
    validate_operator_review,
    verify_corpus_integrity,
)


ROOT = Path(__file__).parents[1]
PILOT = ROOT / "universes" / "phase6-official-pilot-v1.json"
CORPUS = ROOT / "tests" / "fixtures" / "phase6-pilot" / "corpus-manifest.json"
OFFICIAL = ROOT / "tests" / "fixtures" / "nse-official"
runner = CliRunner()


def _manifest() -> PilotManifest:
    return load_pilot_manifest(PILOT)


def _discovery():
    metadata = json.loads((OFFICIAL / "kfintech-2024-metadata.json").read_text())
    return parse_discovery_entry(
        metadata,
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_url=metadata["_fixture_provenance"]["source"],
    )


def _document(content: bytes) -> FetchedDocument:
    return FetchedDocument(
        source_url=_discovery().attachments[0].source_url,
        filename="fixture.xml",
        detected_content_type="application/xml",
        attachment_format=AttachmentFormat.XBRL_XML,
        content_length=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cache_hit=True,
        content=content,
    )


def _review_record(manifest: PilotManifest, *, reviewed_at: datetime, expires_at: datetime):
    return build_operator_review_record(
        manifest,
        operator_id="local-test-operator",
        review_id="phase6-review-test",
        reviewed_at=reviewed_at,
        expires_at=expires_at,
        acknowledgement=OPERATOR_ACKNOWLEDGEMENT,
    )


def test_pilot_manifest_is_bounded_unique_reproducible_and_diverse():
    manifest = _manifest()
    assert manifest.pilot_id == "nse-official-pilot-2026-08-v1"
    assert len(manifest.members) == manifest.limits.max_companies == 12
    assert manifest.filing_categories == ("annual_results",)
    assert len({member.industry for member in manifest.members}) >= 9
    assert sum(member.segregated_accounting_case for member in manifest.members) == 3
    assert manifest.scope_hash() == _manifest().scope_hash()
    assert manifest.operator_review_status == "not_reviewed"


def test_pilot_manifest_rejects_duplicate_membership_and_version_mismatch():
    payload = _manifest().model_dump(mode="json")
    payload["members"][1] = payload["members"][0]
    with pytest.raises(ValueError, match="duplicate"):
        PilotManifest(**payload)
    payload = _manifest().model_dump(mode="json")
    payload["schema_version"] = "999"
    with pytest.raises(ValueError, match="unsupported"):
        PilotManifest(**payload)


def test_acquisition_limits_reject_unbounded_or_incoherent_scope():
    payload = _manifest().limits.model_dump()
    payload["max_companies"] = 26
    with pytest.raises(ValueError):
        AcquisitionLimits(**payload)
    payload = _manifest().limits.model_dump()
    payload["max_documents"] = 100
    with pytest.raises(ValueError, match="possible attachment"):
        AcquisitionLimits(**payload)


def test_operator_gate_rejects_missing_record_and_requires_exact_acknowledgement(tmp_path):
    manifest = _manifest()
    with pytest.raises(PermissionError, match="explicit review"):
        validate_operator_review(None, manifest, expected_review_id=None)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="complete operator acknowledgement"):
        build_operator_review_record(
            manifest, operator_id="operator", review_id="review-invalid",
            reviewed_at=now, expires_at=now + timedelta(days=1), acknowledgement="yes",
        )


def test_operator_gate_accepts_exact_scope_and_rejects_expiry_or_wrong_id(tmp_path):
    manifest = _manifest()
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    record = _review_record(manifest, reviewed_at=now, expires_at=now + timedelta(days=30))
    path = tmp_path / "review.json"
    path.write_text(record.model_dump_json())
    accepted = validate_operator_review(path, manifest, expected_review_id=record.review_id, now=now)
    assert accepted.review_id == record.review_id
    with pytest.raises(PermissionError, match="does not match"):
        validate_operator_review(path, manifest, expected_review_id="wrong-review", now=now)
    with pytest.raises(PermissionError, match="expired"):
        validate_operator_review(path, manifest, expected_review_id=record.review_id, now=now + timedelta(days=31))


def test_operator_record_requires_all_review_topics():
    manifest = _manifest()
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    payload = _review_record(manifest, reviewed_at=now, expires_at=now + timedelta(days=1)).model_dump()
    payload["redistribution_reviewed"] = False
    with pytest.raises(ValueError, match="every operator review topic"):
        OperatorReviewRecord(**payload)


def test_alternate_live_discovery_path_cannot_bypass_operator_gate(monkeypatch):
    monkeypatch.setenv("MBE_NSE_INGESTION_ENABLED", "true")
    result = runner.invoke(cli_app, [
        "nse-filings-discover", "--symbols", "KFINTECH",
        "--date-from", "2024-01-01", "--date-to", "2025-01-01",
    ])
    assert result.exit_code == 2
    assert "Live pilot gate rejected" in result.output
    assert "explicit review" in result.output and "review ID" in result.output


def test_live_subset_cannot_exceed_per_company_filing_cap(monkeypatch, tmp_path):
    manifest = _manifest()
    now = datetime.now(timezone.utc)
    record = _review_record(manifest, reviewed_at=now, expires_at=now + timedelta(days=1))
    record_path = tmp_path / "review.json"
    record_path.write_text(record.model_dump_json())
    monkeypatch.setenv("MBE_NSE_INGESTION_ENABLED", "true")
    result = runner.invoke(cli_app, [
        "nse-filings-discover", "--symbols", "KFINTECH", "--max-filings", "5",
        "--date-from", "2024-01-01", "--date-to", "2025-01-01",
        "--operator-review-record", str(record_path),
        "--operator-review-id", record.review_id,
    ])
    assert result.exit_code == 2
    assert "filing cap exceeds" in result.output


def test_fixture_discovery_remains_available_without_operator_record():
    result = runner.invoke(cli_app, [
        "nse-filings-discover", "--fixture-dir", str(OFFICIAL),
    ])
    assert result.exit_code == 0
    assert '"fixture_mode": true' in result.output


def test_corpus_manifest_and_checksum_verify_offline():
    manifest = load_corpus_manifest(CORPUS)
    result = verify_corpus_integrity(manifest, ROOT)
    assert result == {
        "corpus_id": "phase6-captured-corpus-v1", "records": 1,
        "verified": 1, "missing": 0, "mismatched": 0, "ok": True, "errors": [],
    }


def test_corpus_integrity_detects_checksum_mismatch(tmp_path):
    artifact = tmp_path / "fixture.xml"
    artifact.write_bytes(b"changed")
    payload = load_corpus_manifest(CORPUS).model_dump(mode="json")
    payload["records"][0]["artifact_path"] = "fixture.xml"
    manifest = CorpusManifest(**payload)
    result = verify_corpus_integrity(manifest, tmp_path)
    assert not result["ok"] and result["mismatched"] == 1


def test_private_artifact_writer_refuses_public_repository_paths():
    with pytest.raises(ValueError, match="remain under data"):
        atomic_write_private_json(ROOT / "site" / "review.json", {"private": True})


def test_fetcher_enforces_total_byte_cap_and_repeated_denial_stop(tmp_path):
    body = b"<x/>xx"
    fetcher = SafeDocumentFetcher(
        FetchPolicy(
            cache_dir=tmp_path / "bytes", request_interval_seconds=0,
            max_document_bytes=10, max_total_bytes=10, max_requests=5,
        ),
        transport=lambda url, headers, timeout, policy: HttpResult(
            200, url, {"content-type": "application/xml"}, body
        ),
        sleeper=lambda _: None,
    )
    fetcher.fetch_document("https://nsearchives.nseindia.com/one.xml", filename="one.xml")
    with pytest.raises(ProviderError, match="total byte limit"):
        fetcher.fetch_document("https://nsearchives.nseindia.com/two.xml", filename="two.xml")

    denied = SafeDocumentFetcher(
        FetchPolicy(cache_dir=tmp_path / "denied", request_interval_seconds=0, max_retries=2),
        transport=lambda url, headers, timeout, policy: HttpResult(
            429, url, {"content-type": "application/json"}, b"{}"
        ),
        sleeper=lambda _: None,
    )
    with pytest.raises(ProviderError, match="failed safely"):
        denied.fetch_document("https://www.nseindia.com/api/denied", filename="denied.json")
    assert denied.stats.requests == 2
    with pytest.raises(ProviderError, match="repeated 403/429"):
        denied.fetch_document("https://www.nseindia.com/api/still-denied", filename="denied.json")


def test_parser_evidence_preserves_decimals_context_unit_mapping_and_checksum_inputs():
    content = (OFFICIAL / "kfintech-2024-results.xml").read_bytes()
    parsed = parse_nse_results_xbrl(_document(content), _discovery())
    revenue = next(item for item in parsed.fact_evidence if item.canonical_metric_id == "revenue")
    assert revenue.concept == "RevenueFromOperations"
    assert revenue.context_id == "FourD" and revenue.unit_ref == "INR"
    assert revenue.decimals == "-6" and revenue.scale == 0
    assert revenue.mapping_status == "accepted"
    assert parsed.taxonomy_status == "supported_excerpt"


def test_parser_applies_scale_once_and_preserves_original_value():
    content = (OFFICIAL / "kfintech-2024-results.xml").read_text()
    content = content.replace(
        'contextRef="FourD" unitRef="INR" decimals="-6">8375330000.00',
        'contextRef="FourD" unitRef="INR" decimals="2" scale="6">8375.33',
        1,
    ).encode()
    parsed = parse_nse_results_xbrl(_document(content), _discovery())
    revenue = next(item for item in parsed.fact_evidence if item.canonical_metric_id == "revenue")
    assert revenue.original_value == "8375.33"
    assert revenue.normalized_value == Decimal("8375330000.00")
    assert revenue.scale == 6


def test_parser_collapses_duplicate_equivalent_and_excludes_conflicting_duplicates():
    original = (OFFICIAL / "kfintech-2024-results.xml").read_text()
    fact = '<RevenueFromOperations contextRef="FourD" unitRef="INR" decimals="-6">8375330000.00</RevenueFromOperations>'
    equivalent = original.replace(fact, fact + fact)
    parsed = parse_nse_results_xbrl(_document(equivalent.encode()), _discovery())
    evidence = next(item for item in parsed.fact_evidence if item.canonical_metric_id == "revenue")
    assert evidence.duplicate_equivalent and evidence.candidate_count == 2
    conflicting = original.replace(fact, fact + fact.replace("8375330000.00", "999"))
    parsed = parse_nse_results_xbrl(_document(conflicting.encode()), _discovery())
    assert "revenue" not in {item.metric_id for item in parsed.facts}
    assert any("Conflicting duplicate" in warning for warning in parsed.warnings)


def test_parser_ignores_nil_facts_and_rejects_unknown_taxonomy_for_publication():
    original = (OFFICIAL / "kfintech-2024-results.xml").read_text()
    nil = original.replace(
        '<RevenueFromOperations contextRef="FourD" unitRef="INR" decimals="-6">8375330000.00</RevenueFromOperations>',
        '<RevenueFromOperations contextRef="FourD" unitRef="INR" nil="true"></RevenueFromOperations>',
    )
    parsed = parse_nse_results_xbrl(_document(nil.encode()), _discovery())
    revenue = next(item for item in parsed.facts if item.metric_id == "revenue")
    assert revenue.source_field == "Income"
    namespaced = original.replace("<xbrl>", '<xbrl xmlns="urn:unknown-company-taxonomy">').encode()
    parsed = parse_nse_results_xbrl(_document(namespaced), _discovery())
    assert parsed.taxonomy_namespace == "urn:unknown-company-taxonomy"
    assert parsed.taxonomy_status == "unsupported"


def test_parser_rejects_excessive_depth():
    wrapped = "<xbrl>" + ("<a>" * 65) + "1" + ("</a>" * 65) + "</xbrl>"
    with pytest.raises(ProviderError, match="depth"):
        parse_nse_results_xbrl(_document(wrapped.encode()), _discovery())


def test_review_decisions_are_append_only_effective_and_reversible():
    first = ReviewDecision(
        decision_id="decision-1", review_id="review-1", state="accepted",
        operator_id="operator", decided_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    second = ReviewDecision(
        decision_id="decision-2", review_id="review-1", state="rejected",
        operator_id="operator", decided_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        reverses_decision_id="decision-1",
    )
    assert effective_review_decisions([first, second])["review-1"] == second


def test_tier_a_fact_requires_supported_taxonomy_and_review():
    evidence = {
        "official_identity_verified": True, "source_filing_checksum": "a" * 64,
        "parser_version": "1", "taxonomy_status": "supported", "mapping_status": "accepted",
        "period_status": "resolved", "unit_status": "resolved", "basis": "consolidated",
        "normalization_status": "valid", "duplicate_conflict": False,
        "superseded": False, "quality_status": "valid",
    }
    assert tier_a_fact_eligibility(evidence, ReviewState.ACCEPTED)["eligible"]
    evidence["taxonomy_status"] = "unsupported"
    result = tier_a_fact_eligibility(evidence, ReviewState.ACCEPTED)
    assert not result["eligible"] and "supported_taxonomy" in result["blocking_requirements"]
    evidence["taxonomy_status"] = "supported"
    assert not tier_a_fact_eligibility(evidence, ReviewState.UNREVIEWED)["eligible"]


def test_unreviewed_official_value_cannot_replace_approved_public_fallback():
    period = _discovery().period
    result = reconcile_values(
        instrument_id="instrument", metric_id="revenue_cagr_3y",
        official_period=period, compatibility_period=period,
        official_basis=ConsolidationBasis.CONSOLIDATED,
        compatibility_basis=ConsolidationBasis.CONSOLIDATED,
        official_value=Decimal("0.20"), compatibility_value=Decimal("0.19"),
        official_unit="ratio", compatibility_unit="ratio",
        official_publication_state="unreviewed",
    )
    assert result.selected_source == "yahoo_compatibility"
    assert "review/publication gate failed" in result.rejected_alternatives[0]["reason"]


def test_ground_truth_reports_sample_sizes_and_dimension_accuracy():
    expected = [{
        "case_id": "case", "metric_id": "revenue", "expected_value": "100",
        "rounding_tolerance": "1", "expected_period": "2024-03-31",
        "expected_unit": "INR", "expected_basis": "consolidated", "expected_mapping": "Revenue",
    }]
    actual = [{
        "case_id": "case", "metric_id": "revenue", "value": "100.5",
        "period": "2024-03-31", "unit": "INR", "basis": "consolidated", "mapping": "Revenue",
    }]
    result = evaluate_ground_truth(expected, actual)
    assert result["sample_size"] == 1 and result["within_rounding"] == 1
    assert result["dimension_accuracy"]["basis"]["rate"] == "1"


@pytest.mark.parametrize("command", [
    ["official-pilot-validate"],
    ["official-pilot-corpus-verify"],
    ["official-pilot-parse", "--dry-run"],
    ["official-pilot-review-list", "--dry-run"],
    ["official-pilot-evaluate", "--dry-run"],
])
def test_offline_pilot_commands_are_deterministic_and_need_no_network(command):
    result = runner.invoke(cli_app, command)
    assert result.exit_code == 0, result.output


def test_public_assets_contain_no_operator_identity_review_notes_or_private_paths():
    forbidden = ("operator-review.json", "review-decisions.json", "local-test-operator", "data/official-pilot")
    for path in (ROOT / "site").rglob("*"):
        if path.is_file():
            text = path.read_text(errors="ignore")
            assert not any(item in text for item in forbidden), path
