"""CLI entry points: mbe analyze / screen / universes."""

from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table

from mbe.data.cache import DiskCache
from mbe.data.yahoo import YahooProvider
from mbe.pipeline import analyze_ticker, screen
from mbe.report.markdown import render_report, render_screen_table
from mbe.universe import UNIVERSES, get_universe

app = typer.Typer(help="Multibagger Engine — evidence-driven equity research")
console = Console()

CACHE_DIR = Path("data/cache")
DB_PATH = Path("data/mbe.duckdb")
DEFAULT_OFFICIAL_PILOT_MANIFEST = Path("universes/phase6-official-pilot-v1.json")
DEFAULT_OFFICIAL_CORPUS_MANIFEST = Path("tests/fixtures/phase6-pilot/corpus-manifest.json")


def _provider(fundamentals: str = "yahoo"):
    yahoo = YahooProvider(DiskCache(CACHE_DIR))
    if fundamentals == "edgar":
        from mbe.data.composite import CompositeProvider
        from mbe.data.edgar import EdgarFundamentals

        return CompositeProvider(
            fundamentals=EdgarFundamentals(DiskCache(CACHE_DIR)), market=yahoo
        )
    if fundamentals == "nse":
        from mbe.data.composite import CompositeProvider
        from mbe.data.nse_xbrl import NseFundamentals

        return CompositeProvider(
            fundamentals=NseFundamentals(DiskCache(CACHE_DIR)), market=yahoo
        )
    return yahoo


@app.command()
def analyze(
    ticker: str,
    out: Path = typer.Option(Path("reports"), help="Directory for the markdown report"),
    fundamentals: str = typer.Option(
        "yahoo", help="Statement source: yahoo | edgar (US tickers, 10y+ history)"
    ),
):
    """Full research report for one ticker (e.g. RELIANCE.NS)."""
    console.print(f"[bold]Analyzing {ticker}…[/bold]")
    bundle = analyze_ticker(ticker, _provider(fundamentals))
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{ticker.replace('.', '_')}_{bundle.as_of}.md"
    from mbe.data.news_rss import company_news, sector_policy

    cache = DiskCache(CACHE_DIR)
    news = company_news(
        bundle.info.name or ticker,
        ticker,
        cache=cache,
        exchange=bundle.info.exchange or "NSE",
        industry=bundle.info.industry,
    )
    policy = sector_policy(bundle.info.sector, bundle.info.industry, cache=cache)
    path.write_text(render_report(bundle, news=news, policy=policy))
    card = bundle.card
    console.print(
        f"Investment [bold]{card.investment_score}[/bold] | "
        f"Multibagger [bold]{card.multibagger_score}[/bold] | "
        f"Confidence {card.confidence:.0%} | Risk {int(bundle.risk.risk_score)}"
    )
    console.print(f"Verdict: {card.verdict}")

    if bundle.thesis and bundle.critique:
        from mbe.models.thesis import InvestmentThesis
        from mbe.storage import RunStore
        from mbe.thesis.engine import diff_theses

        store = RunStore(DB_PATH)
        prior = store.thesis_history(ticker)
        if prior:
            prev = InvestmentThesis(**prior[-1]["thesis"])
            diff = diff_theses(prev, bundle.thesis)
            if diff.changes:
                console.print("[bold]Since last analysis:[/bold]")
                for change in diff.changes:
                    console.print(f"  • {change}")
            else:
                console.print("Thesis unchanged since last analysis.")
        store.save_thesis(bundle.thesis, bundle.critique, as_of=bundle.as_of)

        from mbe.thesis.calibration import learn_calibration_map
        from mbe.thesis.predictions import emit_predictions

        # confidences corrected by the map learned from the resolved ledger
        # (validated out-of-sample: US-learned map improved India Brier ~10%)
        resolved = store.resolved_predictions()
        cmap = learn_calibration_map(
            [(r["confidence"], bool(r["correct"])) for r in resolved]
        ) if len(resolved) >= 200 else None
        n_new = store.save_predictions(
            emit_predictions(bundle.thesis, as_of=bundle.as_of, calibration_map=cmap)
        )
        console.print(
            f"Thesis: {bundle.thesis.classification} | "
            f"{bundle.critique.recommendation}"
        )
        if n_new:
            console.print(
                f"Ledger: {n_new} falsifiable predictions recorded "
                f"(due {bundle.as_of.replace(year=bundle.as_of.year + 1)})"
            )
    console.print(f"Report: [green]{path}[/green]")


@app.command("screen")
def screen_cmd(
    universe: str,
    top: int = typer.Option(10, help="Show top N"),
    out: Path = typer.Option(Path("reports"), help="Directory for the ranking file"),
):
    """Rank a universe by Multibagger Score."""
    tickers = _universe_tickers(universe)
    console.print(f"[bold]Screening {len(tickers)} tickers in {universe}…[/bold]")
    result = screen(tickers, _provider())

    table = Table(title=f"{universe} — ranked by Multibagger Score")
    for col in ("#", "Ticker", "MB", "Inv", "Conf", "Risk", "Trend"):
        table.add_column(col)
    for i, b in enumerate(result.ranked[:top], 1):
        table.add_row(
            str(i), b.card.ticker, f"{b.card.multibagger_score}",
            f"{b.card.investment_score}", f"{b.card.confidence:.2f}",
            f"{int(b.risk.risk_score)}", b.tech.trend_state,
        )
    console.print(table)
    if result.failures:
        console.print(f"[yellow]{len(result.failures)} failures:[/yellow] {list(result.failures)}")

    out.mkdir(parents=True, exist_ok=True)
    path = out / f"screen_{universe}.md"
    path.write_text(render_screen_table(result))
    console.print(f"Full ranking: [green]{path}[/green]")


@app.command()
def sectors(
    universe: str,
    limit: int = typer.Option(0, help="Cap number of tickers (0 = all)"),
):
    """Rank the universe's industries by Sector Momentum (peer-set relative)."""
    from mbe.scoring.sector_themes import CURATED_AS_OF, themes_for

    tickers = _universe_tickers(universe)
    if limit:
        tickers = tickers[:limit]
    console.print(f"[bold]Sector view: {len(tickers)} tickers in {universe}…[/bold]")
    result = screen(tickers, _provider())
    if not result.sector_scores:
        console.print("No sector groups of sufficient size (need >= 4 peers).")
        raise typer.Exit(0)

    table = Table(title=f"{universe} — industries by Sector Momentum (vs screened peers)")
    for col in ("#", "Group", "Level", "Score", "Coverage", "N", "Top members"):
        table.add_column(col)
    for i, s in enumerate(result.sector_scores, 1):
        table.add_row(
            str(i), s.name, s.level, f"{s.score:.0f}",
            f"{s.confidence:.0%}", str(s.n), ", ".join(s.members[:4]),
        )
    console.print(table)

    console.print(
        f"\n[bold]Curated themes (as of {CURATED_AS_OF}, descriptive only — not scored):[/bold]"
    )
    shown = False
    for s in result.sector_scores:
        tags = (
            themes_for(None, s.name)
            if s.level == "industry"
            else themes_for(s.name.removesuffix(" (other)"), None)
        )
        for t in tags:
            arrow = "▲" if t.direction == "tailwind" else "▼"
            console.print(f"  {s.name}: {arrow} {t.theme} — {t.reason}")
            shown = True
    if not shown:
        console.print("  (no curated tags for the groups in this universe)")
    if result.failures:
        console.print(f"[yellow]{len(result.failures)} failures[/yellow]")


@app.command()
def universes():
    """List available universes (curated + dynamic NSE index lists)."""
    from mbe.data.universe_nse import NSE_SOURCES

    for name, tickers in UNIVERSES.items():
        console.print(f"[bold]{name}[/bold]: {len(tickers)} tickers (curated)")
    for name in sorted(NSE_SOURCES):
        console.print(f"[bold]{name}[/bold]: NSE index constituents (downloaded)")


@app.command()
def snapshot(universe: str):
    """Screen a universe and persist the run to the DuckDB store."""
    from mbe.storage import RunStore

    tickers = _universe_tickers(universe)
    console.print(f"[bold]Snapshot: {len(tickers)} tickers in {universe}…[/bold]")
    result = screen(tickers, _provider())
    run_id = RunStore(DB_PATH).save_run(result, universe)
    console.print(
        f"Saved run [green]{run_id}[/green]: {len(result.ranked)} analyzed, "
        f"{len(result.failures)} failed -> {DB_PATH}"
    )


@app.command()
def history(ticker: str):
    """Score history for a ticker from the run store."""
    from mbe.storage import RunStore

    rows = RunStore(DB_PATH).history(ticker)
    if not rows:
        console.print(f"No stored runs for {ticker}. Run `mbe snapshot <universe>` first.")
        raise typer.Exit(1)
    table = Table(title=f"{ticker} — score history")
    for col in ("As of", "Universe", "MB", "Inv", "Conf", "Risk", "Trend"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r["as_of"]), r["universe"], f"{r['multibagger']:.1f}",
            f"{r['investment']:.1f}", f"{r['confidence']:.2f}",
            f"{int(r['risk_score'])}", r["trend_state"],
        )
    console.print(table)


@app.command()
def backtest(
    universe: str,
    cutoffs: str = typer.Option(
        "2024-07-15,2025-07-15",
        help="Comma-separated cutoff dates (fundamentals gated by FY-end + 90d lag)",
    ),
    horizon: int = typer.Option(365, help="Forward-return horizon in days"),
    score: str = typer.Option("multibagger", help="multibagger | investment | momentum"),
    limit: int = typer.Option(0, help="Cap number of tickers (0 = all)"),
    out: Path = typer.Option(Path("reports"), help="Directory for the report"),
    fundamentals: str = typer.Option(
        "yahoo", help="Statement source: yahoo | edgar (US tickers, 10y+ history)"
    ),
):
    """Point-in-time backtest: does the score predict forward returns?"""
    from datetime import date as date_cls

    from mbe.backtest.harness import render_backtest_md, run_backtest
    from mbe.storage import RunStore

    tickers = _universe_tickers(universe)
    if limit:
        tickers = tickers[:limit]
    cutoff_dates = [date_cls.fromisoformat(c.strip()) for c in cutoffs.split(",")]
    console.print(
        f"[bold]Backtesting {score} on {len(tickers)} tickers, "
        f"cutoffs {cutoff_dates}, horizon {horizon}d…[/bold]"
    )
    report = run_backtest(
        tickers, _provider(fundamentals), cutoff_dates, horizon,
        score_name=score, universe_name=universe,
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"backtest_{universe}_{score}.md"
    path.write_text(render_backtest_md(report))

    for c in report.cutoffs:
        ic = "n/a" if c.ic is None else f"{c.ic:.3f}"
        spread = "n/a" if c.spread is None else f"{c.spread * 100:.1f}%"
        console.print(f"  {c.cutoff}: IC {ic} | top-bottom spread {spread} | n={c.n}")
    mean_ic = "n/a" if report.mean_ic is None else f"{report.mean_ic:.3f}"
    console.print(f"Mean IC: [bold]{mean_ic}[/bold] | skipped {len(report.skipped)}")
    RunStore(DB_PATH).save_backtest(
        universe=universe, score_name=score, horizon_days=horizon,
        mean_ic=report.mean_ic if report.mean_ic is not None else float("nan"),
        details={
            "cutoffs": [str(c.cutoff) for c in report.cutoffs],
            "n_per_cutoff": [c.n for c in report.cutoffs],
            "skipped": len(report.skipped),
        },
    )
    console.print(f"Report: [green]{path}[/green]")


@app.command()
def calibration():
    """Is the platform honest about its confidence? Reliability table + Brier."""
    from mbe.storage import RunStore
    from mbe.thesis.calibration import brier_score, reliability_table

    resolved = RunStore(DB_PATH).resolved_predictions()
    if not resolved:
        console.print(
            "No resolved predictions yet. Run `mbe analyze` to record claims, "
            "or `uv run python scripts/retro_calibration.py` for a historical run."
        )
        raise typer.Exit(0)

    pairs = [(r["confidence"], bool(r["correct"])) for r in resolved]
    console.print(
        f"[bold]{len(pairs)} resolved predictions[/bold] | "
        f"Brier score {brier_score(pairs):.3f} "
        f"(0 = perfect, 0.25 = coin-flip at 0.5)"
    )
    table = Table(title="Reliability: stated confidence vs observed frequency")
    for col in ("Bucket", "N", "Stated", "Observed", "Gap"):
        table.add_column(col)
    for row in reliability_table(pairs):
        table.add_row(
            row["bucket"], str(row["n"]), f"{row['stated']:.0%}",
            f"{row['observed']:.0%}", f"{row['gap']:+.0%}",
        )
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port"),
):
    """Launch the local research terminal (web dashboard)."""
    import uvicorn

    from mbe.storage import RunStore
    from mbe.web.app import create_app

    web_app = create_app(
        provider=_provider(), store=RunStore(DB_PATH), reports_dir=Path("reports")
    )
    console.print(f"Research terminal: [green]http://{host}:{port}[/green]")
    uvicorn.run(web_app, host=host, port=port, log_level="warning")


@app.command("api")
def serve_api(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8001, help="Port"),
):
    """Launch the versioned read-only platform API."""
    import uvicorn

    from mbe.api.app import create_app

    console.print(f"Read API: [green]http://{host}:{port}/api/v1/health[/green]")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command("db-migrate")
def db_migrate(
    revision: str = typer.Option("head", help="Alembic revision; use head normally"),
    allow_downgrade: bool = typer.Option(
        False, help="Required when revision requests a downgrade"
    ),
):
    """Apply explicit canonical-database migrations (never runs on API requests)."""
    from alembic import command
    from alembic.config import Config

    if revision.startswith("-") and not allow_downgrade:
        console.print("[red]Downgrade refused without --allow-downgrade.[/red]")
        raise typer.Exit(2)
    config = Config("alembic.ini")
    if revision.startswith("-"):
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)
    console.print(f"Database migrated to [green]{revision}[/green]")


@app.command("db-status")
def db_status():
    """Check connectivity, migration revision and canonical record counts."""
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import inspect
    from sqlalchemy.orm import Session

    from mbe.db.base import create_database_engine
    from mbe.db.repository import PlatformRepository

    engine = create_database_engine()
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        tables = inspect(connection).get_table_names()
    with Session(engine) as session:
        repo = PlatformRepository(session)
        counts = {"instruments": repo.instrument_count()}
    console.print_json(data={
        "connected": True, "migration_revision": revision,
        "table_count": len(tables), **counts,
    })


@app.command("instruments-import")
def instruments_import(
    source: Path | None = typer.Option(
        None, help="Official Nifty constituent CSV; defaults to pinned master snapshot"
    ),
    source_version: str | None = typer.Option(None, help="Source date/version"),
    dry_run: bool = typer.Option(False, help="Validate and summarize, then roll back"),
    download_official: bool = typer.Option(
        False, help="Download the current official Nifty constituent CSV"
    ),
):
    """Idempotently synchronize the India-first instrument master."""
    from sqlalchemy.orm import Session

    from mbe.db.base import create_database_engine
    from mbe.instruments.importer import (
        import_instruments, parse_nifty_instrument_csv, pinned_universe_rows,
    )

    source_timestamp = None
    if source and download_official:
        console.print("[red]Use either --source or --download-official, not both.[/red]")
        raise typer.Exit(2)
    if download_official:
        from mbe.data.instrument_master import NiftyIndexInstrumentProvider

        snapshot = NiftyIndexInstrumentProvider().fetch_instruments()
        rows = snapshot.records
        source_version = source_version or snapshot.source_version
        source_timestamp = snapshot.retrieved_at
        code = "nifty_indices_official"
    elif source:
        rows = parse_nifty_instrument_csv(source.read_text(encoding="utf-8-sig"))
        code = "nifty_indices_official"
    else:
        master_path = Path("universes/nifty-smallcap250-instruments.json")
        if master_path.exists():
            payload = json.loads(master_path.read_text())
            rows = payload["records"]
            source_version = source_version or payload.get("source_version")
            source_timestamp = datetime.fromisoformat(payload["retrieved_at"])
            code = "nifty_indices_pinned_master"
        else:
            payload = json.loads(Path("universes/nifty-smallcap250.json").read_text())
            rows = pinned_universe_rows(payload["tickers"])
            source_version = source_version or payload.get("pinned_at")
            code = "nifty_indices_pinned_symbols"
    with Session(create_database_engine()) as session:
        summary = import_instruments(
            session, rows, source_code=code, source_version=source_version,
            source_timestamp=source_timestamp, index_code="nifty-smallcap250",
            dry_run=dry_run,
        )
    console.print_json(data=summary.model_dump(mode="json"))
    if summary.invalid_records or summary.ambiguous_records:
        raise typer.Exit(1)


@app.command("instruments-validate")
def instruments_validate():
    """Verify every pinned production symbol resolves to exactly one instrument."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from mbe.db.base import create_database_engine
    from mbe.db.models import ProviderSymbolRow

    payload = json.loads(Path("universes/nifty-smallcap250.json").read_text())
    expected = payload["tickers"]
    with Session(create_database_engine()) as session:
        rows = session.scalars(select(ProviderSymbolRow).where(
            ProviderSymbolRow.provider == "yahoo",
            ProviderSymbolRow.provider_symbol.in_(expected),
            ProviderSymbolRow.valid_to.is_(None),
        )).all()
    by_symbol: dict[str, list[str]] = {}
    for row in rows:
        by_symbol.setdefault(row.provider_symbol, []).append(row.instrument_id)
    missing = [ticker for ticker in expected if ticker not in by_symbol]
    collisions = {ticker: ids for ticker, ids in by_symbol.items() if len(ids) != 1}
    console.print_json(data={
        "expected": len(expected), "resolved": len(expected) - len(missing),
        "missing": missing, "collisions": collisions,
    })
    if missing or collisions:
        raise typer.Exit(1)


@app.command("platform-build")
def platform_build(universe: str, limit: int = typer.Option(0, help="Cap symbols; 0 = all")):
    """Run and persist one versioned model build in the canonical database."""
    import time

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from mbe.db.base import create_database_engine
    from mbe.db.models import ProviderSymbolRow
    from mbe.db.repository import PlatformRepository
    from mbe.versioning import build_manifest

    tickers = _universe_tickers(universe)
    if limit:
        tickers = tickers[:limit]
    started = time.monotonic()
    result = screen(tickers, _provider())
    built_at = datetime.now(timezone.utc)
    manifest = build_manifest(
        universe_name=universe, tickers=tickers, built_at=built_at,
        attempted=len(tickers), scored=len(result.ranked), failed=len(result.failures),
        duration_seconds=time.monotonic() - started,
    )
    engine = create_database_engine()
    with Session(engine) as session:
        mappings = session.scalars(select(ProviderSymbolRow).where(
            ProviderSymbolRow.provider == "yahoo",
            ProviderSymbolRow.provider_symbol.in_(tickers),
            ProviderSymbolRow.valid_to.is_(None),
        )).all()
        instrument_ids = {row.provider_symbol: row.instrument_id for row in mappings}
        PlatformRepository(session).persist_build(manifest, result, instrument_ids)
    console.print_json(data={
        "build_id": manifest.build_id, "attempted": len(tickers),
        "scored": len(result.ranked), "failed": len(result.failures),
    })


@app.command("financials-import")
def financials_import(source: Path, dry_run: bool = typer.Option(False, help="Validate and roll back all writes")):
    """Import a deterministic JSON array of typed normalized filing inputs."""
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.financials.domain import FilingInput
    from mbe.financials.importer import import_filings
    payload = json.loads(source.read_text())
    if not isinstance(payload, list):
        console.print("[red]Financial import file must contain a JSON array.[/red]")
        raise typer.Exit(2)
    with Session(create_database_engine()) as session:
        summary = import_filings(session, [FilingInput(**item) for item in payload], dry_run=dry_run)
    console.print_json(data=summary.model_dump(mode="json"))
    if summary.errors or summary.facts_rejected:
        raise typer.Exit(1)


@app.command("financials-coverage")
def financials_coverage():
    """Print the latest financial dataset coverage and quality report."""
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.financials.repository import coverage
    with Session(create_database_engine()) as session:
        data = coverage(session)
    if not data:
        console.print("[yellow]No completed financial dataset build.[/yellow]")
        raise typer.Exit(1)
    console.print_json(data=data)


def _official_fetcher(
    *, max_bytes: int | None = None, force_interval: float | None = None,
    max_requests: int | None = None, max_total_bytes: int | None = None,
    max_runtime_seconds: int | None = None,
):
    from mbe.financials.document_fetch import FetchPolicy, SafeDocumentFetcher
    return SafeDocumentFetcher(FetchPolicy(
        cache_dir=Path(os.environ.get("MBE_NSE_FILING_CACHE_DIR", "data/official-filings")),
        request_interval_seconds=force_interval if force_interval is not None else float(os.environ.get("MBE_NSE_REQUEST_INTERVAL_SECONDS", "0.75")),
        max_document_bytes=max_bytes or int(os.environ.get("MBE_NSE_MAX_DOCUMENT_BYTES", "12000000")),
        max_total_bytes=max_total_bytes or int(os.environ.get("MBE_NSE_MAX_TOTAL_BYTES", "120000000")),
        max_requests=max_requests or int(os.environ.get("MBE_NSE_MAX_REQUESTS_PER_RUN", "100")),
        max_runtime_seconds=max_runtime_seconds or int(os.environ.get("MBE_NSE_MAX_RUNTIME_SECONDS", "1800")),
        user_agent=os.environ.get("MBE_NSE_USER_AGENT", "MultibaggerEngine/0.1 (+official filing research; operator contact required)"),
    ))


def _require_live_pilot_scope(
    *, manifest_path: Path, review_record: Path | None, review_id: str | None,
    symbols: list[str], date_from: datetime, date_to: datetime,
):
    from mbe.financials.pilot import load_pilot_manifest, validate_operator_review
    manifest = load_pilot_manifest(manifest_path)
    allowed = {member.nse_symbol for member in manifest.members}
    if not set(symbols) <= allowed:
        raise ValueError("live symbols must be a subset of the versioned pilot manifest")
    if date_from.date() < manifest.date_from or date_to.date() > manifest.date_to:
        raise ValueError("live date range must remain inside the reviewed pilot manifest")
    validate_operator_review(review_record, manifest, expected_review_id=review_id)
    return manifest


def _fixture_discoveries(fixture_dir: Path):
    from mbe.financials.nse_official import parse_discovery_entry
    retrieved_at = datetime.now(timezone.utc)
    rows = []
    for metadata_path in sorted(fixture_dir.glob("*-metadata.json")):
        payload = json.loads(metadata_path.read_text())
        source_url = payload.get("_fixture_provenance", {}).get("source")
        if not source_url:
            raise ValueError(f"fixture provenance source is missing: {metadata_path.name}")
        rows.append((
            parse_discovery_entry(payload, retrieved_at=retrieved_at, source_url=source_url),
            metadata_path.with_name(metadata_path.name.replace("-metadata.json", "-results.xml")),
        ))
    return rows


@app.command("nse-filings-discover")
def nse_filings_discover(
    symbols: str = typer.Option("", help="Comma-separated NSE symbols; required for live discovery"),
    date_from: datetime = typer.Option(datetime(2024, 1, 1), formats=["%Y-%m-%d"]),
    date_to: datetime = typer.Option(datetime.now(), formats=["%Y-%m-%d"]),
    periods: str = typer.Option("Annual", help="Comma-separated Annual and/or Quarterly"),
    max_filings: int = typer.Option(48, min=1, max=100),
    fixture_dir: Path | None = typer.Option(None, help="Use deterministic captured fixtures; no network"),
    pilot_manifest: Path = typer.Option(DEFAULT_OFFICIAL_PILOT_MANIFEST, help="Versioned live-pilot scope"),
    operator_review_record: Path | None = typer.Option(None, help="Private operator review record; live only"),
    operator_review_id: str | None = typer.Option(None, help="Explicit review ID; live only"),
):
    """Discover bounded official NSE financial-result metadata without DB writes."""
    if fixture_dir:
        filings = [item[0] for item in _fixture_discoveries(fixture_dir)]
    else:
        if os.environ.get("MBE_NSE_INGESTION_ENABLED", "false").lower() != "true":
            console.print("[yellow]Live NSE ingestion is disabled. Set MBE_NSE_INGESTION_ENABLED=true only after operator terms review.[/yellow]")
            raise typer.Exit(2)
        requested = list(dict.fromkeys(item.strip().upper() for item in symbols.split(",") if item.strip()))
        if not requested or len(requested) > 25:
            console.print("[red]Specify between 1 and 25 NSE symbols.[/red]")
            raise typer.Exit(2)
        try:
            manifest = _require_live_pilot_scope(
                manifest_path=pilot_manifest, review_record=operator_review_record,
                review_id=operator_review_id, symbols=requested,
                date_from=date_from, date_to=date_to,
            )
        except (OSError, ValueError, PermissionError) as exc:
            console.print(f"[red]Live pilot gate rejected: {exc}[/red]")
            raise typer.Exit(2) from exc
        manifest_filing_cap = len(requested) * manifest.limits.max_filings_per_company
        if max_filings > manifest_filing_cap:
            console.print("[red]Requested filing cap exceeds the reviewed pilot subset.[/red]")
            raise typer.Exit(2)
        from mbe.financials.nse_official import NseOfficialFilingProvider
        provider = NseOfficialFilingProvider(_official_fetcher(
            max_bytes=manifest.limits.max_document_bytes,
            force_interval=float(manifest.limits.minimum_request_interval_seconds),
            max_requests=manifest.limits.max_requests,
            max_total_bytes=manifest.limits.max_total_bytes,
            max_runtime_seconds=manifest.limits.max_runtime_seconds,
        ))
        filings = []
        for symbol in requested:
            remaining = max_filings - len(filings)
            filings.extend(provider.discover_symbol(
                symbol,
                date_from=date_from.date(),
                date_to=date_to.date(),
                periods=tuple(item.strip() for item in periods.split(",") if item.strip()),
                max_filings=min(manifest.limits.max_filings_per_company, remaining),
            ))
            if len(filings) >= max_filings:
                break
    console.print_json(data={
        "count": len(filings),
        "filings": [item.model_dump(mode="json", exclude={"raw_metadata"}) for item in filings[:max_filings]],
        "fixture_mode": fixture_dir is not None,
    })


@app.command("nse-financials-ingest")
def nse_financials_ingest(
    symbols: str = typer.Option("", help="Comma-separated mapped NSE symbols; required for live ingestion"),
    date_from: datetime = typer.Option(datetime(2024, 1, 1), formats=["%Y-%m-%d"]),
    date_to: datetime = typer.Option(datetime.now(), formats=["%Y-%m-%d"]),
    periods: str = typer.Option("Annual", help="Comma-separated Annual and/or Quarterly"),
    fixture_dir: Path | None = typer.Option(None, help="Use deterministic captured fixtures; no network"),
    metadata_only: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
    force_refetch: bool = typer.Option(False),
    max_documents: int = typer.Option(48, min=1, max=100),
    max_bytes: int = typer.Option(12_000_000, min=1024, max=50_000_000),
    pilot_manifest: Path = typer.Option(DEFAULT_OFFICIAL_PILOT_MANIFEST, help="Versioned live-pilot scope"),
    operator_review_record: Path | None = typer.Option(None, help="Private operator review record; live only"),
    operator_review_id: str | None = typer.Option(None, help="Explicit review ID; live only"),
):
    """Discover, validate, parse and import bounded official NSE result filings."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.db.models import InstrumentListingRow, InstrumentRow
    from mbe.financials.official_importer import ingest_official_filings

    fixture_rows = _fixture_discoveries(fixture_dir) if fixture_dir else []
    if not fixture_dir and os.environ.get("MBE_NSE_INGESTION_ENABLED", "false").lower() != "true":
        console.print("[yellow]Live NSE ingestion is disabled pending operator terms review.[/yellow]")
        raise typer.Exit(2)
    requested = list(dict.fromkeys(item.strip().upper() for item in symbols.split(",") if item.strip()))
    if not fixture_dir and (not requested or len(requested) > 25):
        console.print("[red]Specify between 1 and 25 NSE symbols.[/red]")
        raise typer.Exit(2)
    manifest = None
    if not fixture_dir:
        try:
            manifest = _require_live_pilot_scope(
                manifest_path=pilot_manifest, review_record=operator_review_record,
                review_id=operator_review_id, symbols=requested,
                date_from=date_from, date_to=date_to,
            )
        except (OSError, ValueError, PermissionError) as exc:
            console.print(f"[red]Live pilot gate rejected: {exc}[/red]")
            raise typer.Exit(2) from exc
        if max_documents > manifest.limits.max_documents or max_bytes > manifest.limits.max_document_bytes:
            console.print("[red]Requested document limits exceed the reviewed pilot manifest.[/red]")
            raise typer.Exit(2)
    fetcher = _official_fetcher(
        max_bytes=max_bytes,
        force_interval=float(manifest.limits.minimum_request_interval_seconds) if manifest else None,
        max_requests=manifest.limits.max_requests if manifest else None,
        max_total_bytes=manifest.limits.max_total_bytes if manifest else None,
        max_runtime_seconds=manifest.limits.max_runtime_seconds if manifest else None,
    )
    if fixture_dir:
        discoveries = [item[0] for item in fixture_rows]
    else:
        from mbe.financials.nse_official import NseOfficialFilingProvider
        provider = NseOfficialFilingProvider(fetcher)
        discoveries = []
        for symbol in requested:
            discoveries.extend(provider.discover_symbol(
                symbol,
                date_from=date_from.date(),
                date_to=date_to.date(),
                periods=tuple(item.strip() for item in periods.split(",") if item.strip()),
                max_filings=manifest.limits.max_filings_per_company,
                force=force_refetch,
            ))
    fixture_paths = {item[0].source_filing_id: item[1] for item in fixture_rows}
    with Session(create_database_engine()) as session:
        scoped = []
        for discovery in discoveries:
            listing = session.scalar(select(InstrumentListingRow).where(
                InstrumentListingRow.exchange_code == "NSE",
                InstrumentListingRow.symbol == discovery.nse_symbol,
                InstrumentListingRow.valid_to.is_(None),
            ))
            if listing is None:
                console.print(f"[red]No canonical NSE mapping for {discovery.nse_symbol}.[/red]")
                raise typer.Exit(1)
            instrument = session.get(InstrumentRow, listing.instrument_id)
            scoped.append((discovery, instrument.company_id, instrument.instrument_id))

        def loader(attachment):
            if fixture_dir:
                discovery = next(item for item in discoveries if attachment in item.attachments)
                path = fixture_paths[discovery.source_filing_id]
                body = path.read_bytes()
                from hashlib import sha256
                from mbe.financials.official_domain import AttachmentFormat, FetchedDocument
                return FetchedDocument(
                    source_url=attachment.source_url,
                    filename=attachment.filename,
                    detected_content_type="application/xml",
                    attachment_format=AttachmentFormat.XBRL_XML,
                    content_length=len(body),
                    sha256=sha256(body).hexdigest(),
                    retrieved_at=datetime.now(timezone.utc),
                    cache_hit=True,
                    content=body,
                )
            return fetcher.fetch_document(
                attachment.source_url,
                filename=attachment.filename,
                declared_content_type=attachment.declared_content_type,
                force=force_refetch,
            )

        summary = ingest_official_filings(
            session,
            scoped,
            document_loader=loader,
            metadata_only=metadata_only,
            dry_run=dry_run,
            max_documents=max_documents,
            quarantine_stop_rate=manifest.limits.quarantine_stop_rate if manifest else None,
        )
    summary.request_count = fetcher.stats.requests
    summary.retry_count = fetcher.stats.retries
    summary.bytes_downloaded = fetcher.stats.bytes_downloaded
    summary.throttle_seconds = Decimal(str(round(fetcher.stats.throttle_seconds, 3)))
    console.print_json(data={
        **summary.model_dump(mode="json"),
        "fixture_mode": fixture_dir is not None,
        "dry_run": dry_run,
    })
    if summary.errors or summary.facts_rejected or summary.attachments_corrupt:
        raise typer.Exit(1)


@app.command("financials-reconcile")
def financials_reconcile(source: Path, dry_run: bool = typer.Option(False)):
    """Persist deterministic provider comparisons and source-selection reasons."""
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.financials.domain import ConsolidationBasis, FinancialPeriod
    from mbe.financials.official_repository import persist_reconciliation
    from mbe.financials.reconciliation import reconcile_values
    payload = json.loads(source.read_text())
    if not isinstance(payload, list) or len(payload) > 500:
        console.print("[red]Reconciliation input must be a JSON list of at most 500 rows.[/red]")
        raise typer.Exit(2)
    counts = {}
    with Session(create_database_engine()) as session:
        for item in payload:
            period = FinancialPeriod(**item["official_period"])
            compatibility_period = FinancialPeriod(**item["compatibility_period"]) if item.get("compatibility_period") else None
            result = reconcile_values(
                instrument_id=item["instrument_id"], metric_id=item["metric_id"],
                official_period=period, compatibility_period=compatibility_period,
                official_basis=ConsolidationBasis(item.get("official_basis", "unknown")),
                compatibility_basis=ConsolidationBasis(item.get("compatibility_basis", "unknown")),
                official_value=item.get("official_value"), compatibility_value=item.get("compatibility_value"),
                official_unit=item["official_unit"], compatibility_unit=item["compatibility_unit"],
                official_fact_id=item.get("official_fact_id"), official_quality=item.get("official_quality", "valid"),
                official_publication_state=item.get("official_publication_state", "unreviewed"),
            )
            persist_reconciliation(
                session, result,
                financial_dataset_build_id=item.get("financial_dataset_build_id"),
                source_cutoff=datetime.fromisoformat(item["source_cutoff"]),
            )
            counts[result.status.value] = counts.get(result.status.value, 0) + 1
        session.rollback() if dry_run else session.commit()
    console.print_json(data={"rows": len(payload), "status_counts": counts, "dry_run": dry_run})


@app.command("financials-unsupported")
def financials_unsupported(limit: int = typer.Option(50, min=1, max=500)):
    """List safe metadata for unsupported or quarantined official attachments."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.db.models import OfficialFilingAttachmentRow
    with Session(create_database_engine()) as session:
        rows = session.scalars(select(OfficialFilingAttachmentRow).where(
            OfficialFilingAttachmentRow.parse_status.in_(("unsupported", "quarantined", "corrupt"))
        ).order_by(OfficialFilingAttachmentRow.retrieved_at.desc()).limit(limit)).all()
        data = [{"attachment_id": row.attachment_id, "filename": row.filename,
                 "format": row.attachment_format, "status": row.parse_status,
                 "reason": row.unsupported_reason or row.quarantine_code} for row in rows]
    console.print_json(data={"count": len(data), "attachments": data})


@app.command("financials-conflicts")
def financials_conflicts(limit: int = typer.Option(50, min=1, max=500)):
    """List bounded reconciliation conflicts without raw provider payloads."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from mbe.db.base import create_database_engine
    from mbe.db.models import FinancialReconciliationRow
    with Session(create_database_engine()) as session:
        rows = session.scalars(select(FinancialReconciliationRow).where(
            FinancialReconciliationRow.reconciliation_status.in_((
                "material_difference", "period_mismatch", "basis_mismatch", "unit_mismatch", "unresolved"
            ))
        ).order_by(FinancialReconciliationRow.created_at.desc()).limit(limit)).all()
        data = [{"reconciliation_id": row.reconciliation_id, "instrument_id": row.instrument_id,
                 "metric_id": row.metric_id, "period_end": row.period_end,
                 "status": row.reconciliation_status, "selection_reason": row.selection_reason} for row in rows]
    console.print_json(data={"count": len(data), "conflicts": data})


@app.command("financials-cache-invalidate")
def financials_cache_invalidate(url: str, sha256: str):
    """Safely invalidate exactly one official cache entry by URL and checksum."""
    removed = _official_fetcher().invalidate(url, expected_sha256=sha256)
    console.print_json(data={"removed": removed, "sha256": sha256})


@app.command("official-pilot-validate")
def official_pilot_validate(
    manifest_path: Path = typer.Option(DEFAULT_OFFICIAL_PILOT_MANIFEST),
):
    """Validate the deterministic Phase 6 selection and acquisition bounds."""
    from mbe.financials.pilot import load_pilot_manifest
    try:
        manifest = load_pilot_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Invalid pilot manifest: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(data={
        "pilot_id": manifest.pilot_id,
        "manifest_version": manifest.manifest_version,
        "scope_hash": manifest.scope_hash(),
        "companies": len(manifest.members),
        "symbols": [member.nse_symbol for member in manifest.members],
        "date_from": manifest.date_from.isoformat(),
        "date_to": manifest.date_to.isoformat(),
        "filing_categories": list(manifest.filing_categories),
        "limits": manifest.limits.model_dump(mode="json"),
        "operator_review_status": manifest.operator_review_status,
    })


@app.command("official-pilot-operator-status")
def official_pilot_operator_status(
    record_path: Path | None = typer.Option(None, help="Private review record"),
    review_id: str | None = typer.Option(None, help="Review ID supplied explicitly by the operator"),
    manifest_path: Path = typer.Option(DEFAULT_OFFICIAL_PILOT_MANIFEST),
):
    """Check the legal/usage review gate without making a network request."""
    from mbe.financials.pilot import load_pilot_manifest, validate_operator_review
    manifest = load_pilot_manifest(manifest_path)
    try:
        record = validate_operator_review(record_path, manifest, expected_review_id=review_id)
    except (OSError, ValueError, PermissionError) as exc:
        console.print_json(data={
            "pilot_id": manifest.pilot_id,
            "live_enabled": False,
            "reason": str(exc),
            "legal_conclusion": "none; this gate records operator review only",
        })
        return
    console.print_json(data={
        "pilot_id": manifest.pilot_id,
        "review_id": record.review_id,
        "reviewed_at": record.reviewed_at.isoformat(),
        "expires_at": record.expires_at.isoformat(),
        "live_enabled": True,
        "legal_conclusion": "none; terms can change and must be reviewed again before production",
    })


@app.command("official-pilot-operator-record")
def official_pilot_operator_record(
    operator_id: str = typer.Option(..., help="Local operator identifier; never published"),
    review_id: str = typer.Option(..., help="Unique operator-chosen review ID"),
    acknowledgement: str = typer.Option(..., help="Exact documented acknowledgement text"),
    output: Path = typer.Option(Path("data/official-pilot/operator-review.json")),
    valid_days: int = typer.Option(30, min=1, max=90),
    manifest_path: Path = typer.Option(DEFAULT_OFFICIAL_PILOT_MANIFEST),
):
    """Create a private dated review record; this is not legal approval."""
    from datetime import timedelta
    from mbe.financials.pilot import (
        atomic_write_private_json, build_operator_review_record, load_pilot_manifest,
    )
    manifest = load_pilot_manifest(manifest_path)
    now = datetime.now(timezone.utc)
    try:
        record = build_operator_review_record(
            manifest, operator_id=operator_id, review_id=review_id,
            reviewed_at=now, expires_at=now + timedelta(days=valid_days),
            acknowledgement=acknowledgement,
        )
    except ValueError as exc:
        console.print(f"[red]Review record rejected: {exc}[/red]")
        raise typer.Exit(2) from exc
    atomic_write_private_json(output, record)
    console.print_json(data={
        "review_id": record.review_id,
        "pilot_id": record.pilot_id,
        "expires_at": record.expires_at.isoformat(),
        "recorded": True,
        "public_asset": False,
        "legal_conclusion": "none",
    })


@app.command("official-pilot-corpus-verify")
def official_pilot_corpus_verify(
    corpus_manifest: Path = typer.Option(DEFAULT_OFFICIAL_CORPUS_MANIFEST),
    repository_root: Path = typer.Option(Path(".")),
):
    """Verify every offline corpus artifact by exact size and SHA-256."""
    from mbe.financials.pilot import load_corpus_manifest, verify_corpus_integrity
    try:
        result = verify_corpus_integrity(load_corpus_manifest(corpus_manifest), repository_root)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Corpus verification failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(data=result)
    if not result["ok"]:
        raise typer.Exit(1)


def _official_pilot_fixture_evidence() -> tuple[list[dict], list[dict], list[str]]:
    from mbe.financials.parsers import parse_nse_results_xbrl
    from mbe.financials.official_domain import AttachmentFormat, FetchedDocument
    import hashlib
    fixture_dir = Path("tests/fixtures/nse-official")
    discovery, xml_path = _fixture_discoveries(fixture_dir)[0]
    content = xml_path.read_bytes()
    document = FetchedDocument(
        source_url=discovery.attachments[0].source_url,
        filename=discovery.attachments[0].filename,
        detected_content_type="application/xml",
        attachment_format=AttachmentFormat.XBRL_XML,
        content_length=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cache_hit=True,
        content=content,
    )
    parsed = parse_nse_results_xbrl(document, discovery)
    evidence = []
    for item in parsed.fact_evidence:
        evidence.append({
            **item.model_dump(mode="json"),
            "case_id": "kfintech-fy2024",
            "company": discovery.company_name,
            "filing_id": discovery.source_filing_id,
            "period": parsed.period.period_end.isoformat(),
            "basis": parsed.basis.value,
            "source_filing_checksum": document.sha256,
            "parser_version": parsed.parser_version,
            "taxonomy_status": parsed.taxonomy_status,
            "period_status": "resolved",
            "unit_status": "resolved" if item.unit != "unresolved" else "unresolved",
            "normalization_status": "valid",
            "quality_status": "valid" if not item.quality_warnings else "valid_with_warning",
            "official_identity_verified": True,
            "superseded": False,
            "review_status": "unreviewed",
            "reconciliation_status": "not_comparable_in_single-year_fixture",
        })
    actual = [{
        "case_id": "kfintech-fy2024",
        "metric_id": fact.metric_id,
        "value": str(fact.value) if fact.value is not None else None,
        "period": fact.period.period_end.isoformat(),
        "unit": fact.unit,
        "basis": fact.basis.value,
        "mapping": fact.source_field,
    } for fact in parsed.facts if fact.value is not None]
    return evidence, actual, parsed.warnings


@app.command("official-pilot-parse")
def official_pilot_parse(
    output: Path = typer.Option(Path("data/official-pilot/evidence.json")),
    dry_run: bool = typer.Option(False),
):
    """Parse the checksum-verified captured corpus offline and export evidence."""
    from mbe.financials.pilot import atomic_write_private_json
    evidence, _, warnings = _official_pilot_fixture_evidence()
    payload = {
        "pilot_id": "nse-official-pilot-2026-08-v1",
        "mode": "captured_reduced_fixture",
        "public": False,
        "evidence_count": len(evidence),
        "warnings": warnings,
        "evidence": evidence,
    }
    if not dry_run:
        atomic_write_private_json(output, payload)
    console.print_json(data={key: value for key, value in payload.items() if key != "evidence"} | {"dry_run": dry_run})


@app.command("official-pilot-review-list")
def official_pilot_review_list(
    output: Path = typer.Option(Path("data/official-pilot/review-queue.json")),
    category: str | None = typer.Option(None),
    dry_run: bool = typer.Option(False),
):
    """Generate a bounded private review queue from offline pilot evidence."""
    from mbe.financials.pilot import atomic_write_private_json, stable_review_id
    evidence, _, warnings = _official_pilot_fixture_evidence()
    items = []
    for item in evidence:
        review_category = "taxonomy_mapping" if item["taxonomy_status"] != "supported" else "manual_acceptance"
        items.append({
            "review_id": stable_review_id(item["filing_id"], item["canonical_metric_id"], item["period"], item["basis"]),
            "company": item["company"],
            "filing": item["filing_id"],
            "metric": item["canonical_metric_id"],
            "period": item["period"],
            "severity": "high" if review_category == "taxonomy_mapping" else "medium",
            "category": review_category,
            "evidence_summary": f"{item['concept']} / {item['context_id']} / {item['unit']}; taxonomy={item['taxonomy_status']}",
            "suggested_next_action": "Qualify the full taxonomy namespace from an operator-authorized corpus before accepting the fact.",
            "status": "unreviewed",
            "resolution_note": "",
            "rule_version": item["mapping_version"],
        })
    blockers = (
        ("ground_truth", "Basic EPS is absent from the captured reduced excerpt."),
        ("revision", "No revised official pilot filing is present in the authorized offline corpus."),
        ("comparative", "No comparative XBRL context is present in the captured reduced excerpt."),
    )
    for name, message in blockers:
        items.append({
            "review_id": stable_review_id("pilot", name), "company": None, "filing": None,
            "metric": None, "period": None, "severity": "high", "category": name,
            "evidence_summary": message, "suggested_next_action": "Retain as a production blocker until an operator-authorized filing supplies evidence.",
            "status": "unreviewed", "resolution_note": "", "rule_version": "2026-08-01.1",
        })
    if category:
        items = [item for item in items if item["category"] == category]
    payload = {"pilot_id": "nse-official-pilot-2026-08-v1", "public": False, "count": len(items), "warnings": warnings, "items": items}
    if not dry_run:
        atomic_write_private_json(output, payload)
    console.print_json(data={"pilot_id": payload["pilot_id"], "count": len(items), "category": category, "dry_run": dry_run})


@app.command("official-pilot-review-decide")
def official_pilot_review_decide(
    review_id: str,
    state: str = typer.Option(...),
    operator_id: str = typer.Option(...),
    note: str = typer.Option(""),
    reverses: str | None = typer.Option(None),
    queue_path: Path = typer.Option(Path("data/official-pilot/review-queue.json")),
    decisions_path: Path = typer.Option(Path("data/official-pilot/review-decisions.json")),
):
    """Append an attributed, reversible local review decision."""
    import uuid
    from mbe.financials.pilot import ReviewDecision, ReviewState, atomic_write_private_json
    try:
        review_state = ReviewState(state)
    except ValueError as exc:
        console.print(f"[red]Unknown review state: {state}[/red]")
        raise typer.Exit(2) from exc
    if not queue_path.exists():
        console.print("[red]Generate the review queue before recording a decision.[/red]")
        raise typer.Exit(2)
    queue = json.loads(queue_path.read_text())
    known_review_ids = {item.get("review_id") for item in queue.get("items", [])}
    if review_id not in known_review_ids:
        console.print("[red]Review ID is not present in the current bounded queue.[/red]")
        raise typer.Exit(2)
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else []
    if not isinstance(decisions, list) or len(decisions) >= 1000:
        console.print("[red]Decision history is invalid or exceeds the local safety bound.[/red]")
        raise typer.Exit(1)
    if reverses:
        prior = next((item for item in decisions if item.get("decision_id") == reverses), None)
        if prior is None or prior.get("review_id") != review_id:
            console.print("[red]Reversal must reference a prior decision for the same review item.[/red]")
            raise typer.Exit(2)
    decision = ReviewDecision(
        decision_id=str(uuid.uuid4()), review_id=review_id, state=review_state,
        operator_id=operator_id, decided_at=datetime.now(timezone.utc), note=note,
        reverses_decision_id=reverses,
    )
    decisions.append(decision.model_dump(mode="json"))
    atomic_write_private_json(decisions_path, decisions)
    console.print_json(data={"decision_id": decision.decision_id, "review_id": review_id, "state": state, "recorded": True, "public": False})


@app.command("official-pilot-evaluate")
def official_pilot_evaluate(
    ground_truth: Path = typer.Option(Path("tests/fixtures/phase6-pilot/ground-truth.json")),
    output: Path = typer.Option(Path("data/official-pilot/evaluation.json")),
    dry_run: bool = typer.Option(False),
):
    """Evaluate captured evidence, Tier-A blockers and readiness offline."""
    from mbe.financials.pilot import ReviewState, atomic_write_private_json, evaluate_ground_truth, tier_a_fact_eligibility
    evidence, actual, warnings = _official_pilot_fixture_evidence()
    expected = json.loads(ground_truth.read_text())["rows"]
    accuracy = evaluate_ground_truth(expected, actual)
    eligibility = [tier_a_fact_eligibility(item, ReviewState.UNREVIEWED) for item in evidence]
    result = {
        "pilot_id": "nse-official-pilot-2026-08-v1",
        "evaluation_mode": "captured_reduced_fixture_only",
        "live_companies_attempted": 0,
        "captured_companies": 1,
        "captured_filings": 1,
        "captured_bytes": 2696,
        "ground_truth": accuracy,
        "tier_a_eligible_facts": sum(item["eligible"] for item in eligibility),
        "tier_a_eligible_metrics": 0,
        "revenue_cagr_officially_derivable": 0,
        "roce_officially_derivable": 0,
        "public_values_changed": False,
        "warnings": warnings,
        "production_readiness": "no_go",
        "recommendation_reason": "Operator review is absent and the one captured reduced excerpt cannot measure taxonomy diversity, revisions, comparative contexts, or multi-year derived metrics.",
    }
    if not dry_run:
        atomic_write_private_json(output, result)
    console.print_json(data=result | {"dry_run": dry_run})


@app.command("company-research-validate")
def company_research_validate(
    site_dir: Path = typer.Option(Path("site")),
    instrument_id: str | None = typer.Option(None),
):
    """Validate canonical research JSON, HTML, peer links and private-data boundaries."""
    from mbe.research.operations import validate_research_site
    try:
        result = validate_research_site(site_dir, instrument_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Company research validation failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(data=result)


@app.command("company-research-inspect")
def company_research_inspect(
    instrument_id: str,
    site_dir: Path = typer.Option(Path("site")),
):
    """Print one normalized public company-research payload."""
    from mbe.research.operations import load_research_payloads
    try:
        page = load_research_payloads(site_dir, instrument_id)[instrument_id]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Research payload unavailable: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(data=page.model_dump(mode="json"))


@app.command("company-research-measure")
def company_research_measure(site_dir: Path = typer.Option(Path("site"))):
    """Measure generated company HTML and research JSON payload sizes."""
    from mbe.research.operations import measure_research_site
    console.print_json(data=measure_research_site(site_dir))


@app.command("company-research-build")
def company_research_build(
    site_dir: Path = typer.Option(Path("site")),
    instrument_id: str | None = typer.Option(None),
    rebuild_derived: bool = typer.Option(False, help="Re-run explanation and peer policies from normalized payloads"),
):
    """Rebuild all or one static company page offline from normalized payloads."""
    from mbe.publish import _render_company_page, _static_envelope
    from mbe.research.operations import load_research_payloads, rebuild_research_payloads
    pages = load_research_payloads(site_dir, instrument_id)
    if rebuild_derived:
        corpus = load_research_payloads(site_dir)
        rebuilt = rebuild_research_payloads(corpus)
        pages = ({instrument_id: rebuilt[instrument_id]} if instrument_id else rebuilt)
    for key, page in pages.items():
        payload = page.model_dump(mode="json")
        (site_dir / "company" / f"{key}.html").write_text(_render_company_page(payload))
        if rebuild_derived:
            path = site_dir / "api" / "v1" / "research" / f"{key}.json"
            path.write_text(json.dumps(_static_envelope(payload, warnings=payload["warnings"]), indent=1))
    console.print_json(data={"pages_built": len(pages), "derived_rebuilt": rebuild_derived, "network_requests": 0})


@app.command("company-research-legacy-validate")
def company_research_legacy_validate(site_dir: Path = typer.Option(Path("site"))):
    """Verify every published legacy report route resolves with canonical metadata."""
    import re
    data = json.loads((site_dir / "data.json").read_text())
    failures = []
    for row in data.get("top", []):
        path = site_dir / "reports" / row["ticker_path"]
        text = path.read_text() if path.exists() else ""
        expected = f"/company/{row['instrument_id']}.html"
        if not text or expected not in text or not re.search(r'<link rel="canonical"', text):
            failures.append(row["ticker"])
    console.print_json(data={"legacy_routes": len(data.get("top", [])), "failures": failures})
    if failures:
        raise typer.Exit(1)


@app.command("company-research-parity")
def company_research_parity(
    instrument_id: str,
    site_dir: Path = typer.Option(Path("site")),
):
    """Compare stable static and database-backed research sections."""
    from mbe.db.base import create_database_engine, database_url, session_factory
    from mbe.research.dynamic import build_dynamic_research
    from mbe.research.operations import load_research_payloads
    static = load_research_payloads(site_dir, instrument_id)[instrument_id]
    engine = create_database_engine(database_url(required=True))
    with session_factory(engine)() as session:
        dynamic = build_dynamic_research(session, instrument_id)
    if dynamic is None:
        console.print("[red]Dynamic research payload is unavailable.[/red]")
        raise typer.Exit(1)
    stable = ("identity", "ranking", "explanations", "financials", "technical", "peers", "filings", "warnings")
    differences = [name for name in stable if getattr(static, name) != getattr(dynamic, name)]
    console.print_json(data={"instrument_id": instrument_id, "equivalent": not differences, "differences": differences,
                             "allowed_runtime_differences": ["quote", "news after static cutoff", "lineage.data_mode"]})
    if differences:
        raise typer.Exit(1)


def _universe_tickers(universe: str) -> list[str]:
    from mbe.data.universe_nse import CACHE_TTL_HOURS

    return get_universe(universe, cache=DiskCache(CACHE_DIR, ttl_hours=CACHE_TTL_HOURS))


if __name__ == "__main__":
    app()
