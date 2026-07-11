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


def _provider() -> YahooProvider:
    return YahooProvider(DiskCache(CACHE_DIR))


@app.command()
def analyze(
    ticker: str,
    out: Path = typer.Option(Path("reports"), help="Directory for the markdown report"),
):
    """Full research report for one ticker (e.g. RELIANCE.NS)."""
    console.print(f"[bold]Analyzing {ticker}…[/bold]")
    bundle = analyze_ticker(ticker, _provider())
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
    console.print(f"Report: [green]{path}[/green]")


@app.command("screen")
def screen_cmd(
    universe: str,
    top: int = typer.Option(10, help="Show top N"),
    out: Path = typer.Option(Path("reports"), help="Directory for the ranking file"),
):
    """Rank a universe by Multibagger Score."""
    tickers = get_universe(universe)
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
    """List available universes."""
    for name, tickers in UNIVERSES.items():
        console.print(f"[bold]{name}[/bold]: {len(tickers)} tickers")


if __name__ == "__main__":
    app()
