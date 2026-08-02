"""Typed contracts for frozen inputs and deterministic site builds."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SCHEMA_VERSION = "2026-08-02.11.1"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    """Hash relative names and bytes so directory membership is also frozen."""
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content_hash = bytes.fromhex(sha256_file(item))
        digest.update(content_hash)
    return digest.hexdigest()


class FrozenArtifact(BaseModel):
    path: str
    sha256: str
    kind: Literal["file", "tree"] = "file"
    role: str


class FrozenInputManifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    manifest_id: str
    created_at: datetime
    data_cutoff: datetime
    universe_versions: dict[str, str]
    model_build_ids: dict[str, str | None] = Field(default_factory=dict)
    financial_build_id: str
    search_build_id: str
    artifacts: list[FrozenArtifact]
    status: Literal["complete", "legacy_baseline"] = "complete"
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_paths(self):
        paths = [artifact.path for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("frozen artifact paths must be unique")
        return self

    def validate_artifacts(self, root: Path) -> None:
        errors = []
        for artifact in self.artifacts:
            path = (root / artifact.path).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                errors.append(f"artifact escapes repository root: {artifact.path}")
                continue
            if not path.exists():
                errors.append(f"missing frozen artifact: {artifact.path}")
                continue
            actual = sha256_file(path) if artifact.kind == "file" else sha256_tree(path)
            if actual != artifact.sha256:
                errors.append(
                    f"frozen artifact hash mismatch: {artifact.path} "
                    f"expected={artifact.sha256} actual={actual}"
                )
        if errors:
            raise ValueError("\n".join(errors))

    def configuration_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"created_at"})
        return hashlib.sha256(canonical_json(payload)).hexdigest()


class SourceDataManifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source_data_build_id: str
    generated_at: datetime
    provider_cutoff: datetime
    universe_id: str
    universe_version: str
    membership_count: int
    provider_versions: dict[str, str]
    source_hashes: dict[str, str]
    network_used: bool
    status: Literal["complete", "failed"]
    warnings: list[str] = Field(default_factory=list)


class FrozenModelBuildManifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    model_build_id: str
    generated_at: datetime
    data_cutoff: datetime
    universe_id: str
    universe_version: str
    model_version: str
    source_data_build_id: str
    source_manifest_hash: str
    model_artifact_path: str
    model_artifact_hash: str
    attempted_count: int
    scored_count: int
    failed_count: int
    network_used: bool = False
    status: Literal["complete", "failed"]


class FrozenFinancialBuildManifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    financial_build_id: str
    generated_at: datetime
    data_cutoff: datetime
    source_data_build_id: str
    model_build_id: str
    financial_artifact_path: str
    financial_artifact_hash: str
    network_used: bool = False
    status: Literal["complete", "failed"]


class SiteBuildManifest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    site_build_id: str
    generated_at: datetime
    search_build_id: str
    search_ranking_policy_version: str
    classification_policy_version: str
    large_cap_model_build_id: str | None = None
    mid_cap_model_build_id: str | None = None
    small_cap_model_build_id: str
    financial_build_id: str
    news_cutoff: datetime | None = None
    quote_mode: str
    universe_versions: dict[str, str]
    input_artifact_hashes: dict[str, str]
    output_artifact_hashes: dict[str, str]
    build_configuration_hash: str
    build_mode: Literal["offline", "search-only", "frontend-only"]
    network_used: bool = False
    status: Literal["complete", "failed"] = "complete"
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls, *, generated_at: datetime, search_build_id: str,
        search_ranking_policy_version: str, classification_policy_version: str,
        small_cap_model_build_id: str, financial_build_id: str,
        universe_versions: dict[str, str], input_artifact_hashes: dict[str, str],
        output_artifact_hashes: dict[str, str], build_configuration_hash: str,
        build_mode: Literal["offline", "search-only", "frontend-only"],
        news_cutoff: datetime | None = None, quote_mode: str = "frozen-build-close",
        warnings: list[str] | None = None,
    ) -> "SiteBuildManifest":
        identity = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
            "search_build_id": search_build_id,
            "small_cap_model_build_id": small_cap_model_build_id,
            "financial_build_id": financial_build_id,
            "universe_versions": dict(sorted(universe_versions.items())),
            "input_artifact_hashes": dict(sorted(input_artifact_hashes.items())),
            "output_artifact_hashes": dict(sorted(output_artifact_hashes.items())),
            "build_configuration_hash": build_configuration_hash,
            "build_mode": build_mode,
        }
        site_build_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"mbe-site:{hashlib.sha256(canonical_json(identity)).hexdigest()}",
        ))
        return cls(
            site_build_id=site_build_id, generated_at=generated_at,
            search_build_id=search_build_id,
            search_ranking_policy_version=search_ranking_policy_version,
            classification_policy_version=classification_policy_version,
            small_cap_model_build_id=small_cap_model_build_id,
            financial_build_id=financial_build_id,
            universe_versions=dict(sorted(universe_versions.items())),
            input_artifact_hashes=dict(sorted(input_artifact_hashes.items())),
            output_artifact_hashes=dict(sorted(output_artifact_hashes.items())),
            build_configuration_hash=build_configuration_hash,
            build_mode=build_mode, news_cutoff=news_cutoff, quote_mode=quote_mode,
            warnings=warnings or [], network_used=False, status="complete",
        )
