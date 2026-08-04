from mbe.universal.classification import classify_company_type
from mbe.universal.domain import CompanyType


def test_bank_detected_from_industry_keyword():
    assert classify_company_type("Financial Services", "Banks—Regional") == CompanyType.BANK
    assert classify_company_type("Financial Services", "Banks—Diversified") == CompanyType.BANK


def test_insurance_detected_from_industry_keyword():
    assert classify_company_type("Financial Services", "Insurance—Life") == CompanyType.INSURANCE


def test_nbfc_detected_from_credit_services():
    assert classify_company_type("Financial Services", "Credit Services") == CompanyType.NBFC


def test_asset_management_detected():
    assert classify_company_type("Financial Services", "Asset Management") == CompanyType.ASSET_MANAGEMENT


def test_other_financial_is_conservative_default_for_unmatched_financial_industry():
    assert classify_company_type("Financial Services", "Financial Data & Stock Exchanges") == CompanyType.OTHER_FINANCIAL
    assert classify_company_type("Financial Services", None) == CompanyType.OTHER_FINANCIAL


def test_general_corporate_for_non_financial_sector():
    assert classify_company_type("Technology", "Software—Application") == CompanyType.GENERAL_CORPORATE
    assert classify_company_type("Industrials", "Specialty Industrial Machinery") == CompanyType.GENERAL_CORPORATE


def test_unknown_limited_data_when_no_sector_or_industry():
    assert classify_company_type(None, None) == CompanyType.UNKNOWN_LIMITED_DATA
    assert classify_company_type("", "") == CompanyType.UNKNOWN_LIMITED_DATA


def test_case_insensitive_matching():
    assert classify_company_type("financial services", "BANKS—REGIONAL") == CompanyType.BANK
