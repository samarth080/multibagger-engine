import json
from datetime import date

import pytest

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.data.edgar import EdgarFundamentals, parse_companyfacts, resolve_cik

CIK_MAP = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }
)

FACTS = {
    "cik": 320193,
    "entityName": "Test Co",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        # FY2021 original filing
                        {"start": "2021-01-01", "end": "2021-12-31", "val": 100.0,
                         "form": "10-K", "filed": "2022-02-15"},
                        # FY2021 comparative repeated in the next year's 10-K
                        {"start": "2021-01-01", "end": "2021-12-31", "val": 100.0,
                         "form": "10-K", "filed": "2023-02-20"},
                        # FY2022 original
                        {"start": "2022-01-01", "end": "2022-12-31", "val": 120.0,
                         "form": "10-K", "filed": "2023-02-20"},
                        # FY2022 restated in an amendment — must NOT override original
                        {"start": "2022-01-01", "end": "2022-12-31", "val": 125.0,
                         "form": "10-K/A", "filed": "2023-08-01"},
                        # quarterly duration — excluded from annual history
                        {"start": "2022-10-01", "end": "2022-12-31", "val": 30.0,
                         "form": "10-K", "filed": "2023-02-20"},
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {"end": "2021-12-31", "val": 500.0, "form": "10-K",
                         "filed": "2022-02-15"},
                        {"end": "2022-12-31", "val": 600.0, "form": "10-K",
                         "filed": "2023-02-20"},
                    ]
                }
            },
            "NetCashProvidedByUsedInOperatingActivities": {
                "units": {
                    "USD": [
                        {"start": "2022-01-01", "end": "2022-12-31", "val": 40.0,
                         "form": "10-K", "filed": "2023-02-20"},
                    ]
                }
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {
                "units": {
                    "USD": [
                        {"start": "2022-01-01", "end": "2022-12-31", "val": 15.0,
                         "form": "10-K", "filed": "2023-02-20"},
                    ]
                }
            },
        }
    },
}


def test_parse_companyfacts_values_and_original_filing_preference():
    fin = parse_companyfacts(FACTS)
    assert fin.value("revenue", 2021) == 100.0
    assert fin.value("revenue", 2022) == 120.0  # original 10-K, not the /A restatement
    assert fin.value("total_assets", 2022) == 600.0
    # quarterly fact never appears
    assert 30.0 not in fin.data["revenue"].values()


def test_parse_companyfacts_filed_dates():
    fin = parse_companyfacts(FACTS)
    assert fin.filed[2021] == date(2022, 2, 15)
    assert fin.filed[2022] == date(2023, 2, 20)


def test_parse_companyfacts_derives_fcf():
    fin = parse_companyfacts(FACTS)
    assert fin.value("fcf", 2022) == 40.0 - 15.0  # capex normalized positive


def test_parse_companyfacts_tag_fallback():
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [
                        {"start": "2023-01-01", "end": "2023-12-31", "val": 77.0,
                         "form": "10-K", "filed": "2024-02-01"},
                    ]}
                }
            }
        }
    }
    fin = parse_companyfacts(facts)
    assert fin.value("revenue", 2023) == 77.0


def test_resolve_cik(tmp_path):
    cache = DiskCache(tmp_path)
    assert resolve_cik("AAPL", cache, fetcher=lambda url: CIK_MAP) == 320193
    assert resolve_cik("msft", cache, fetcher=lambda url: CIK_MAP) == 789019
    with pytest.raises(ProviderError):
        resolve_cik("NOPE", cache, fetcher=lambda url: CIK_MAP)


def test_edgar_fundamentals_fetches_by_cik(tmp_path):
    urls = []

    def fetcher(url: str) -> str:
        urls.append(url)
        return CIK_MAP if "company_tickers" in url else json.dumps(FACTS)

    provider = EdgarFundamentals(DiskCache(tmp_path), fetcher=fetcher)
    fin = provider.get_financials("AAPL")
    assert fin.value("revenue", 2022) == 120.0
    assert any("CIK0000320193.json" in u for u in urls)


def test_composite_provider_routes(tmp_path):
    import json as _json

    from mbe.data.composite import CompositeProvider
    from tests.test_pipeline import StubProvider

    def fetcher(url: str) -> str:
        return CIK_MAP if "company_tickers" in url else _json.dumps(FACTS)

    market = StubProvider()
    fundamentals = EdgarFundamentals(DiskCache(tmp_path), fetcher=fetcher)
    provider = CompositeProvider(fundamentals=fundamentals, market=market)

    fin = provider.get_financials("AAPL")
    assert fin.value("revenue", 2022) == 120.0  # from EDGAR
    assert fin.filed  # filing dates present
    info = provider.get_info("AAPL")
    assert info.name == "Stub Co"  # from market provider
    assert provider.benchmark_ticker("AAPL") == "^NSEI"  # delegated


def test_tag_fallbacks_merge_across_eras():
    """Companies switch tags over time (e.g. ASC 606 revenue): fallback tags
    must fill years the primary tag lacks, with the primary winning conflicts."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [
                        {"start": "2016-01-01", "end": "2016-12-31", "val": 50.0,
                         "form": "10-K", "filed": "2017-02-01"},
                        # conflicting value for 2018 — primary tag must win
                        {"start": "2018-01-01", "end": "2018-12-31", "val": 70.0,
                         "form": "10-K", "filed": "2019-02-01"},
                    ]}
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [
                        {"start": "2018-01-01", "end": "2018-12-31", "val": 71.0,
                         "form": "10-K", "filed": "2019-02-01"},
                        {"start": "2023-01-01", "end": "2023-12-31", "val": 90.0,
                         "form": "10-K", "filed": "2024-02-01"},
                    ]}
                },
            }
        }
    }
    fin = parse_companyfacts(facts)
    assert fin.value("revenue", 2016) == 50.0   # primary-tag era
    assert fin.value("revenue", 2023) == 90.0   # fallback-tag era merged in
    assert fin.value("revenue", 2018) == 70.0   # primary wins conflicts


def test_share_counts_parse_from_the_shares_unit_not_usd():
    """EDGAR reports share counts under units["shares"]; only USD was read, so
    shares_diluted came back empty for every US ticker. That silently disabled
    the forecast's own-P/E history (which needs EPS) across the whole EDGAR
    path, and left share_count_cagr_3y unmeasurable."""
    facts = {
        "cik": 1,
        "entityName": "Share Co",
        "facts": {
            "us-gaap": {
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"start": "2021-01-01", "end": "2021-12-31",
                             "val": 10_000_000.0, "form": "10-K",
                             "filed": "2022-02-15"},
                            {"start": "2022-01-01", "end": "2022-12-31",
                             "val": 10_500_000.0, "form": "10-K",
                             "filed": "2023-02-20"},
                        ]
                    }
                },
            }
        },
    }
    fin = parse_companyfacts(facts)
    assert fin.series("shares_diluted") == [
        (2021, 10_000_000.0),
        (2022, 10_500_000.0),
    ]


def test_usd_fields_still_ignore_a_shares_unit():
    """The unit choice is per-field, not a free-for-all: a money field must not
    start picking up share-denominated facts."""
    facts = {
        "cik": 1,
        "entityName": "Odd Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "shares": [
                            {"start": "2021-01-01", "end": "2021-12-31",
                             "val": 999.0, "form": "10-K", "filed": "2022-02-15"},
                        ]
                    }
                },
            }
        },
    }
    assert parse_companyfacts(facts).series("revenue") == []
