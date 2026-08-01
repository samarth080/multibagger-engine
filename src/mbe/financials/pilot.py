"""Bounded Phase 6 official-corpus pilot contracts and offline workflows.

Pilot artifacts are intentionally local/versioned files.  They do not alter the
public financial projection or imply that an NSE filing has passed review.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PILOT_MANIFEST_SCHEMA_VERSION = "1.0"
CORPUS_MANIFEST_SCHEMA_VERSION = "1.0"
OPERATOR_REVIEW_SCHEMA_VERSION = "1.0"
REVIEW_WORKFLOW_VERSION = "2026-08-01.1"
TIER_A_POLICY_VERSION = "2026-08-01.1"
GROUND_TRUTH_SCHEMA_VERSION = "1.0"
OPERATOR_ACKNOWLEDGEMENT = (
    "I confirm that I reviewed current NSE access and data-use terms, request cadence, "
    "cache retention, public redistribution, and attribution for this bounded pilot."
)


class ReviewState(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_CAVEAT = "accepted_with_caveat"
    REJECTED = "rejected"
    NEEDS_SOURCE_CLARIFICATION = "needs_source_clarification"
    NEEDS_TAXONOMY_MAPPING = "needs_taxonomy_mapping"
    NEEDS_PERIOD_REVIEW = "needs_period_review"
    NEEDS_UNIT_REVIEW = "needs_unit_review"
    NEEDS_CONSOLIDATION_REVIEW = "needs_consolidation_review"
    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"


class AcquisitionLimits(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_companies: int = Field(ge=1, le=25)
    max_discovery_pages: int = Field(ge=1, le=50)
    max_filings_per_company: int = Field(ge=1, le=10)
    max_attachments_per_filing: int = Field(ge=1, le=5)
    max_documents: int = Field(ge=1, le=100)
    max_document_bytes: int = Field(ge=1024, le=50_000_000)
    max_total_bytes: int = Field(ge=1024, le=500_000_000)
    max_requests: int = Field(ge=1, le=150)
    per_host_concurrency: int = Field(default=1, ge=1, le=1)
    minimum_request_interval_seconds: Decimal = Field(ge=Decimal("0.5"), le=Decimal("30"))
    max_retries: int = Field(ge=0, le=2)
    max_runtime_seconds: int = Field(ge=60, le=3600)
    quarantine_stop_rate: Decimal = Field(ge=0, le=Decimal("0.5"))
    identity_anomaly_stop_count: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def coherent_caps(self):
        possible = self.max_companies * self.max_filings_per_company * self.max_attachments_per_filing
        if self.max_documents > possible:
            raise ValueError("document cap exceeds the manifest's possible attachment scope")
        if self.max_total_bytes < self.max_document_bytes:
            raise ValueError("total byte cap must be at least the per-document cap")
        return self


class PilotMember(BaseModel):
    model_config = ConfigDict(frozen=True)
    instrument_id: str = Field(min_length=36, max_length=36)
    company_name: str = Field(min_length=1, max_length=300)
    nse_symbol: str = Field(pattern=r"^[A-Z0-9&_-]{1,40}$")
    isin: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    sector: str | None = Field(default=None, max_length=120)
    industry: str = Field(min_length=1, max_length=120)
    selection_reason: str = Field(min_length=10, max_length=500)
    expected_filing_categories: tuple[str, ...]
    expected_document_formats: tuple[str, ...]
    segregated_accounting_case: bool = False


class PilotManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = PILOT_MANIFEST_SCHEMA_VERSION
    pilot_id: str = Field(pattern=r"^nse-official-pilot-[a-z0-9-]+-v[0-9]+$")
    manifest_version: str
    selection_date: date
    date_from: date
    date_to: date
    filing_categories: tuple[str, ...]
    selection_method: str
    manual_review_budget: int = Field(ge=1, le=500)
    operator_review_status: str = "not_reviewed"
    limits: AcquisitionLimits
    members: tuple[PilotMember, ...]

    @model_validator(mode="after")
    def bounded_and_unique(self):
        if self.schema_version != PILOT_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported pilot manifest schema version")
        if self.date_from > self.date_to:
            raise ValueError("pilot date range is reversed")
        if not self.members or len(self.members) > self.limits.max_companies:
            raise ValueError("pilot membership is empty or exceeds the company cap")
        if self.filing_categories != ("annual_results",):
            raise ValueError("Phase 6 pilot is restricted to annual results")
        ids = [member.instrument_id for member in self.members]
        symbols = [member.nse_symbol for member in self.members]
        if len(ids) != len(set(ids)) or len(symbols) != len(set(symbols)):
            raise ValueError("pilot membership contains duplicate instruments or symbols")
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def scope_hash(self) -> str:
        raw = json.dumps(self.deterministic_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


class OperatorReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = OPERATOR_REVIEW_SCHEMA_VERSION
    review_id: str = Field(min_length=12, max_length=80)
    operator_id: str = Field(min_length=2, max_length=120)
    reviewed_at: datetime
    expires_at: datetime
    pilot_id: str
    pilot_scope_hash: str = Field(min_length=64, max_length=64)
    terms_reviewed: bool
    cadence_reviewed: bool
    caching_and_retention_reviewed: bool
    redistribution_reviewed: bool
    attribution_reviewed: bool
    responsibility_accepted: bool
    acknowledgement_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def valid_record(self):
        if self.schema_version != OPERATOR_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported operator review schema version")
        if self.reviewed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("operator review timestamps must be timezone-aware")
        if self.expires_at <= self.reviewed_at:
            raise ValueError("operator review expiry must follow review time")
        if self.expires_at - self.reviewed_at > timedelta(days=90):
            raise ValueError("operator review may not remain valid for more than 90 days")
        checks = (
            self.terms_reviewed,
            self.cadence_reviewed,
            self.caching_and_retention_reviewed,
            self.redistribution_reviewed,
            self.attribution_reviewed,
            self.responsibility_accepted,
        )
        if not all(checks):
            raise ValueError("every operator review topic requires explicit confirmation")
        expected = hashlib.sha256(OPERATOR_ACKNOWLEDGEMENT.encode()).hexdigest()
        if self.acknowledgement_sha256 != expected:
            raise ValueError("operator acknowledgement text does not match the reviewed contract")
        return self


class CorpusRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    corpus_record_id: str
    canonical_filing_id: str | None = None
    nse_source_identifier: str
    instrument_id: str
    company_name: str
    nse_symbol: str
    filing_timestamp: datetime
    filing_category: str
    filing_subject: str
    source_metadata_url: str
    attachment_url: str
    original_filename: str
    validated_mime_type: str
    file_signature: str
    byte_size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    full_source_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    retrieval_timestamp: datetime
    cache_status: str
    parser_eligibility: str
    parser_id: str | None = None
    parser_version: str | None = None
    taxonomy_namespace: str | None = None
    taxonomy_version: str | None = None
    filing_basis: str
    filing_period: str
    revision_status: str
    quality_status: str
    review_status: ReviewState = ReviewState.UNREVIEWED
    public_redistribution_status: str = "not_reviewed"
    artifact_path: str | None = None
    artifact_kind: str = "reduced_excerpt"

    @field_validator("source_metadata_url", "attachment_url")
    @classmethod
    def official_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("corpus URLs must use HTTPS")
        return value

    @field_validator("artifact_path")
    @classmethod
    def relative_artifact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("corpus artifact paths must be safe repository-relative paths")
        return path.as_posix()


class CorpusManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str = CORPUS_MANIFEST_SCHEMA_VERSION
    corpus_id: str
    pilot_id: str
    manifest_version: str
    generated_at: datetime
    acquisition_mode: str
    live_acquisition_authorized: bool = False
    records: tuple[CorpusRecord, ...]

    @model_validator(mode="after")
    def unique_records(self):
        if self.schema_version != CORPUS_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported corpus manifest schema version")
        ids = [record.corpus_record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus record IDs must be unique")
        if self.acquisition_mode != "live" and self.live_acquisition_authorized:
            raise ValueError("offline/captured corpus cannot claim live authorization")
        return self


class ReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    review_id: str
    state: ReviewState
    operator_id: str = Field(min_length=2, max_length=120)
    decided_at: datetime
    note: str = Field(default="", max_length=2000)
    rule_version: str = REVIEW_WORKFLOW_VERSION
    reverses_decision_id: str | None = None


def load_pilot_manifest(path: Path) -> PilotManifest:
    return PilotManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_corpus_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))


def validate_operator_review(
    path: Path | None,
    manifest: PilotManifest,
    *,
    expected_review_id: str | None,
    now: datetime | None = None,
) -> OperatorReviewRecord:
    if path is None or expected_review_id is None:
        raise PermissionError("live NSE pilot access requires an explicit review record and review ID")
    record = OperatorReviewRecord.model_validate_json(path.read_text(encoding="utf-8"))
    current = now or datetime.now(timezone.utc)
    if record.review_id != expected_review_id:
        raise PermissionError("operator review ID does not match the requested live run")
    if record.pilot_id != manifest.pilot_id or record.pilot_scope_hash != manifest.scope_hash():
        raise PermissionError("operator review does not cover this exact pilot manifest")
    if current > record.expires_at:
        raise PermissionError("operator review has expired; current terms must be reviewed again")
    return record


def build_operator_review_record(
    manifest: PilotManifest,
    *,
    operator_id: str,
    review_id: str,
    reviewed_at: datetime,
    expires_at: datetime,
    acknowledgement: str,
) -> OperatorReviewRecord:
    if acknowledgement != OPERATOR_ACKNOWLEDGEMENT:
        raise ValueError("the complete operator acknowledgement must be supplied exactly")
    return OperatorReviewRecord(
        review_id=review_id,
        operator_id=operator_id,
        reviewed_at=reviewed_at,
        expires_at=expires_at,
        pilot_id=manifest.pilot_id,
        pilot_scope_hash=manifest.scope_hash(),
        terms_reviewed=True,
        cadence_reviewed=True,
        caching_and_retention_reviewed=True,
        redistribution_reviewed=True,
        attribution_reviewed=True,
        responsibility_accepted=True,
        acknowledgement_sha256=hashlib.sha256(acknowledgement.encode()).hexdigest(),
    )


def atomic_write_private_json(path: Path, payload: Any) -> None:
    resolved = path.resolve()
    repository = Path.cwd().resolve()
    if resolved == repository or repository in resolved.parents:
        private_root = (repository / "data").resolve()
        if resolved != private_root and private_root not in resolved.parents:
            raise ValueError("private pilot artifacts inside the repository must remain under data/")
    path.parent.mkdir(parents=True, exist_ok=True)
    public = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    data = json.dumps(public, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_corpus_integrity(manifest: CorpusManifest, repository_root: Path) -> dict[str, Any]:
    verified = missing = mismatched = 0
    errors: list[str] = []
    root = repository_root.resolve()
    for record in manifest.records:
        if not record.artifact_path:
            missing += 1
            errors.append(f"{record.corpus_record_id}: no local artifact")
            continue
        target = (root / record.artifact_path).resolve()
        if root not in target.parents:
            mismatched += 1
            errors.append(f"{record.corpus_record_id}: artifact escapes repository root")
            continue
        if not target.is_file():
            missing += 1
            errors.append(f"{record.corpus_record_id}: artifact is missing")
            continue
        content = target.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != record.byte_size or digest != record.sha256:
            mismatched += 1
            errors.append(f"{record.corpus_record_id}: size or checksum mismatch")
            continue
        verified += 1
    return {
        "corpus_id": manifest.corpus_id,
        "records": len(manifest.records),
        "verified": verified,
        "missing": missing,
        "mismatched": mismatched,
        "ok": not errors,
        "errors": errors,
    }


def stable_review_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"review-{digest}"


def effective_review_decisions(decisions: list[ReviewDecision]) -> dict[str, ReviewDecision]:
    """Return the latest append-only decision per review item.

    Reversal is another attributed event; history is never edited in place.
    """
    effective: dict[str, ReviewDecision] = {}
    for decision in sorted(decisions, key=lambda item: (item.decided_at, item.decision_id)):
        effective[decision.review_id] = decision
    return effective


def tier_a_fact_eligibility(evidence: dict[str, Any], review_state: ReviewState) -> dict[str, Any]:
    requirements = {
        "official_identity_verified": bool(evidence.get("official_identity_verified")),
        "checksum_preserved": bool(evidence.get("source_filing_checksum")),
        "supported_parser": bool(evidence.get("parser_version")),
        "supported_taxonomy": evidence.get("taxonomy_status") == "supported",
        "accepted_mapping": evidence.get("mapping_status") == "accepted",
        "period_resolved": evidence.get("period_status") == "resolved",
        "unit_resolved": evidence.get("unit_status") == "resolved",
        "basis_resolved": evidence.get("basis") in {"consolidated", "standalone"},
        "normalization_valid": evidence.get("normalization_status") == "valid",
        "no_duplicate_conflict": not evidence.get("duplicate_conflict", False),
        "not_superseded": not evidence.get("superseded", False),
        "quality_accepted": evidence.get("quality_status") in {"valid", "valid_with_warning"},
        "review_accepted": review_state in {ReviewState.ACCEPTED, ReviewState.ACCEPTED_WITH_CAVEAT},
    }
    eligible = all(requirements.values())
    return {
        "eligible": eligible,
        "tier": "A" if eligible else "C",
        "policy_version": TIER_A_POLICY_VERSION,
        "requirements": requirements,
        "blocking_requirements": sorted(key for key, value in requirements.items() if not value),
        "publication_state": "eligible_not_published" if eligible else "not_eligible",
    }


def evaluate_ground_truth(expected_rows: list[dict[str, Any]], actual_rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = {(row["case_id"], row["metric_id"]): row for row in actual_rows}
    exact = rounding = incorrect = missing = 0
    dimensions = {"period": 0, "unit": 0, "basis": 0, "mapping": 0}
    for expected in expected_rows:
        row = actual.get((expected["case_id"], expected["metric_id"]))
        if row is None:
            missing += 1
            continue
        expected_value = Decimal(str(expected["expected_value"]))
        actual_value = Decimal(str(row["value"]))
        tolerance = Decimal(str(expected.get("rounding_tolerance", "0")))
        if actual_value == expected_value:
            exact += 1
        elif abs(actual_value - expected_value) <= tolerance:
            rounding += 1
        else:
            incorrect += 1
        for dimension in dimensions:
            if row.get(dimension) == expected.get(f"expected_{dimension}"):
                dimensions[dimension] += 1
    sample = len(expected_rows)
    return {
        "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
        "sample_size": sample,
        "exact": exact,
        "within_rounding": rounding,
        "incorrect": incorrect,
        "missing": missing,
        "exact_or_rounding_accuracy": str(Decimal(exact + rounding) / Decimal(sample)) if sample else None,
        "dimension_accuracy": {
            key: {"correct": value, "sample_size": sample, "rate": str(Decimal(value) / Decimal(sample)) if sample else None}
            for key, value in dimensions.items()
        },
    }
