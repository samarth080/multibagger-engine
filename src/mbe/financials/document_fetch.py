"""Bounded cache-first retrieval for untrusted official filing documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import random
import re
import tempfile
import threading
import time
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request

from mbe.data.provider import ProviderError
from mbe.financials.official_domain import AttachmentFormat, FetchedDocument


OFFICIAL_ALLOWED_HOSTS = frozenset({
    "www.nseindia.com",
    "nseindia.com",
    "nsearchives.nseindia.com",
    "archives.nseindia.com",
})
DEFAULT_USER_AGENT = "MultibaggerEngine/0.1 (+official filing research; operator contact required)"
RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class FetchPolicy:
    cache_dir: Path = Path("data/official-filings")
    request_interval_seconds: float = 0.75
    connection_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 25.0
    max_document_bytes: int = 12_000_000
    max_total_bytes: int = 120_000_000
    max_requests: int = 100
    max_retries: int = 2
    max_redirects: int = 3
    max_runtime_seconds: int = 1800
    user_agent: str = DEFAULT_USER_AGENT
    allowed_hosts: frozenset[str] = OFFICIAL_ALLOWED_HOSTS


@dataclass(frozen=True)
class HttpResult:
    status: int
    final_url: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FetchStats:
    requests: int = 0
    cache_hits: int = 0
    retries: int = 0
    bytes_downloaded: int = 0
    throttle_seconds: float = 0.0
    status_counts: dict[int, int] | None = None

    def __post_init__(self) -> None:
        if self.status_counts is None:
            self.status_counts = {}


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: FetchPolicy):
        self.policy = policy
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirects += 1
        if self.redirects > self.policy.max_redirects:
            raise ProviderError("official document exceeded redirect limit")
        validate_official_url(newurl, self.policy.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_official_url(url: str, allowed_hosts: frozenset[str] = OFFICIAL_ALLOWED_HOSTS) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host not in allowed_hosts:
        raise ProviderError("official document URL is not on the HTTPS NSE allowlist")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ProviderError("official document URL contains disallowed authority components")
    return url


def sanitize_filename(value: str) -> str:
    name = Path(urllib.parse.unquote(value)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:160]
    return name or "official-filing"


def detect_format(body: bytes, declared_type: str | None, filename: str) -> tuple[str, AttachmentFormat]:
    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    lowered = body[:512].lstrip().lower()
    suffix = Path(filename).suffix.lower()
    if body.startswith(b"%PDF-"):
        return "application/pdf", AttachmentFormat.TEXT_PDF
    if body.startswith(b"PK\x03\x04"):
        return (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            AttachmentFormat.XLSX if suffix == ".xlsx" else AttachmentFormat.ZIP,
        )
    if body.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "application/vnd.ms-excel", AttachmentFormat.XLS
    if lowered.startswith((b"{", b"[")):
        return "application/json", AttachmentFormat.JSON
    if lowered.startswith(b"<"):
        if b"<html" in lowered or b"<!doctype html" in lowered:
            return "text/html", AttachmentFormat.HTML
        return "application/xml", AttachmentFormat.XBRL_XML
    if suffix == ".csv" and declared in {"text/csv", "application/csv", "text/plain"}:
        return "text/csv", AttachmentFormat.CSV
    guessed = declared or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return guessed, AttachmentFormat.OTHER


def _default_transport(url: str, headers: dict[str, str], timeout: float, policy: FetchPolicy) -> HttpResult:
    handler = _BoundedRedirectHandler(policy)
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > policy.max_document_bytes:
            raise ProviderError("official document exceeds configured byte limit")
        body = response.read(policy.max_document_bytes + 1)
        if len(body) > policy.max_document_bytes:
            raise ProviderError("official document exceeds configured byte limit")
        if length and length.isdigit() and len(body) != int(length):
            raise ProviderError("official document download was partial")
        return HttpResult(
            status=response.status,
            final_url=response.geturl(),
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
        )


class SafeDocumentFetcher:
    """Retrieve NSE bytes without executing content or exposing cache paths."""

    def __init__(
        self,
        policy: FetchPolicy | None = None,
        *,
        transport: Callable[[str, dict[str, str], float, FetchPolicy], HttpResult] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.policy = policy or FetchPolicy()
        if not self.policy.user_agent or len(self.policy.user_agent) > 300 or any(
            character in self.policy.user_agent for character in "\r\n"
        ):
            raise ValueError("official user agent must be a single bounded line")
        self.transport = transport or _default_transport
        self.sleeper = sleeper
        self.stats = FetchStats()
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._started = time.monotonic()
        self._access_denials = 0

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()
        root = self.policy.cache_dir
        return root / "documents" / key, root / "metadata" / f"{key}.json"

    def _cached(self, url: str) -> FetchedDocument | None:
        data_path, meta_path = self._cache_paths(url)
        if not data_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text())
            body = data_path.read_bytes()
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        checksum = hashlib.sha256(body).hexdigest()
        if checksum != meta.get("sha256") or len(body) != meta.get("content_length"):
            return None
        self.stats.cache_hits += 1
        return FetchedDocument(
            source_url=url,
            filename=meta["filename"],
            detected_content_type=meta["detected_content_type"],
            attachment_format=meta["attachment_format"],
            content_length=len(body),
            sha256=checksum,
            retrieved_at=datetime.fromisoformat(meta["retrieved_at"]),
            cache_hit=True,
            etag=meta.get("etag"),
            last_modified=meta.get("last_modified"),
            content=body,
        )

    def _throttle(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request
            wait_for = max(0.0, self.policy.request_interval_seconds - elapsed)
            if wait_for:
                self.sleeper(wait_for)
                self.stats.throttle_seconds += wait_for
            self._last_request = time.monotonic()

    def _request(self, url: str, headers: dict[str, str]) -> HttpResult:
        if self.stats.requests >= self.policy.max_requests:
            raise ProviderError("official request cap reached")
        if time.monotonic() - self._started >= self.policy.max_runtime_seconds:
            raise ProviderError("official runtime cap reached")
        if self._access_denials >= 2:
            raise ProviderError("official access stopped after repeated 403/429 responses")
        last_error: Exception | None = None
        for attempt in range(self.policy.max_retries + 1):
            self._throttle()
            self.stats.requests += 1
            try:
                result = self.transport(
                    url,
                    headers,
                    self.policy.connection_timeout_seconds + self.policy.read_timeout_seconds,
                    self.policy,
                )
                validate_official_url(result.final_url, self.policy.allowed_hosts)
                if len(result.body) > self.policy.max_document_bytes:
                    raise ProviderError("official document exceeds configured byte limit")
                if self.stats.bytes_downloaded + len(result.body) > self.policy.max_total_bytes:
                    raise ProviderError("official run exceeds configured total byte limit")
                assert self.stats.status_counts is not None
                self.stats.status_counts[result.status] = self.stats.status_counts.get(result.status, 0) + 1
                if result.status >= 400:
                    raise urllib.error.HTTPError(url, result.status, "official request failed", {}, None)
                return result
            except urllib.error.HTTPError as exc:
                last_error = exc
                assert self.stats.status_counts is not None
                self.stats.status_counts[exc.code] = self.stats.status_counts.get(exc.code, 0) + 1
                if exc.code in {403, 429}:
                    self._access_denials += 1
                    if self._access_denials >= 2:
                        break
                if exc.code == 304:
                    return HttpResult(
                        status=304,
                        final_url=url,
                        headers={key.lower(): value for key, value in (exc.headers or {}).items()},
                        body=b"",
                    )
                if exc.code not in RETRYABLE_HTTP_STATUSES or attempt >= self.policy.max_retries:
                    break
            except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
                last_error = exc
                if attempt >= self.policy.max_retries:
                    break
            if attempt < self.policy.max_retries:
                self.stats.retries += 1
                delay = min(8.0, (2 ** attempt) + random.uniform(0, 0.25))
                self.sleeper(delay)
        raise ProviderError(f"official request failed safely: {type(last_error).__name__}") from last_error

    def fetch_bytes(self, url: str, *, accept: str, force: bool = False) -> HttpResult:
        validate_official_url(url, self.policy.allowed_hosts)
        cached = self._cached(url) if not force else None
        headers = {"User-Agent": self.policy.user_agent, "Accept": accept}
        if cached:
            return HttpResult(
                status=200,
                final_url=url,
                headers={
                    "content-type": cached.detected_content_type,
                    "x-mbe-cache": "hit",
                    "etag": cached.etag or "",
                    "last-modified": cached.last_modified or "",
                },
                body=cached.content,
            )
        return self._request(url, headers)

    def fetch_document(
        self,
        url: str,
        *,
        filename: str,
        declared_content_type: str | None = None,
        force: bool = False,
    ) -> FetchedDocument:
        validate_official_url(url, self.policy.allowed_hosts)
        cached = self._cached(url)
        if not force and cached:
            return cached
        headers = {
            "User-Agent": self.policy.user_agent,
            "Accept": "application/xml,application/json,text/html,text/csv,application/pdf,application/zip,application/octet-stream",
        }
        if cached and cached.etag:
            headers["If-None-Match"] = cached.etag
        if cached and cached.last_modified:
            headers["If-Modified-Since"] = cached.last_modified
        result = self._request(url, headers)
        if result.status == 304 and cached:
            return cached
        if not result.body:
            raise ProviderError("official document was empty or partially downloaded")
        content_type, attachment_format = detect_format(
            result.body,
            result.headers.get("content-type") or declared_content_type,
            filename,
        )
        declared = (declared_content_type or result.headers.get("content-type") or "").lower()
        if "pdf" in declared and attachment_format not in {AttachmentFormat.TEXT_PDF, AttachmentFormat.IMAGE_PDF}:
            raise ProviderError("official document MIME/signature mismatch")
        if "xml" in declared and attachment_format != AttachmentFormat.XBRL_XML:
            raise ProviderError("official document MIME/signature mismatch")
        safe_name = sanitize_filename(filename)
        checksum = hashlib.sha256(result.body).hexdigest()
        retrieved_at = datetime.now(timezone.utc)
        data_path, meta_path = self._cache_paths(url)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "source_url": url,
            "filename": safe_name,
            "detected_content_type": content_type,
            "attachment_format": attachment_format.value,
            "content_length": len(result.body),
            "sha256": checksum,
            "retrieved_at": retrieved_at.isoformat(),
            "etag": result.headers.get("etag"),
            "last_modified": result.headers.get("last-modified"),
        }
        for target, payload, binary in (
            (data_path, result.body, True),
            (meta_path, json.dumps(metadata, sort_keys=True).encode(), False),
        ):
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                handle.write(payload)
                temp_name = handle.name
            os.replace(temp_name, target)
        self.stats.bytes_downloaded += len(result.body)
        return FetchedDocument(
            source_url=url,
            filename=safe_name,
            detected_content_type=content_type,
            attachment_format=attachment_format,
            content_length=len(result.body),
            sha256=checksum,
            retrieved_at=retrieved_at,
            cache_hit=False,
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
            content=result.body,
        )

    def invalidate(self, url: str, *, expected_sha256: str) -> bool:
        """Remove exactly one verified cache entry; callers must name its checksum."""
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
        data_path, meta_path = self._cache_paths(validate_official_url(url, self.policy.allowed_hosts))
        cached = self._cached(url)
        if not cached:
            return False
        if cached.sha256 != expected_sha256:
            raise ValueError("cache checksum does not match the requested invalidation target")
        data_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return True
