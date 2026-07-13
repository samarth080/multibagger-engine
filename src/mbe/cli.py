"""CLI entry points: mbe analyze / screen / universes."""

from __future__ import annotations

from pathlib import Path

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
    path.write_text(render_report(bundle))
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


def _universe_tickers(universe: str) -> list[str]:
    from mbe.data.universe_nse import CACHE_TTL_HOURS

    return get_universe(universe, cache=DiskCache(CACHE_DIR, ttl_hours=CACHE_TTL_HOURS))


if __name__ == "__main__":
    app()
