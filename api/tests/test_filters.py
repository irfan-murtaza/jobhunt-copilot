from jobhunt.models import Preferences
from jobhunt.schemas.job import (
    JobExtraction,
    LocationEligibility,
    LocationScope,
    RemoteType,
    Salary,
    Seniority,
)
from jobhunt.services.filters import CandidateContext, apply_filters, check_location
from jobhunt.services.geo import region_countries, region_timezone_band, utc_offset_hours

PK = CandidateContext(country="PK", timezone="Asia/Karachi")
PT = CandidateContext(country="PT", timezone="Europe/Lisbon")
UNKNOWN = CandidateContext(country=None, timezone=None)


def loc(**kwargs: object) -> JobExtraction:
    return JobExtraction(title="Engineer", summary="s", location=LocationEligibility(**kwargs))  # type: ignore[arg-type]


def test_region_tables_cover_common_phrasings() -> None:
    assert "PK" in (region_countries("APAC") or set())
    assert "PK" in (region_countries("South Asia") or set())
    assert "PK" not in (region_countries("EMEA") or set())
    assert "PT" in (region_countries("EMEA") or set())
    assert "PT" in (region_countries("European Union") or set())
    assert "GB" not in (region_countries("EU") or set())
    assert region_countries("Worldwide") == frozenset()
    assert region_countries("Remote - Europe") == region_countries("europe")
    assert region_countries("US only") == frozenset({"US"})
    assert region_countries("Narnia") is None
    assert region_timezone_band("US time zones") == (-10, -4)


def test_utc_offset_from_iana_zone() -> None:
    assert utc_offset_hours("Asia/Karachi") == 5
    assert utc_offset_hours("UTC") == 0
    assert utc_offset_hours("Not/AZone") is None
    assert utc_offset_hours(None) is None


def test_location_scopes() -> None:
    assert check_location(loc(scope=LocationScope.WORLDWIDE), PK) == (True, None)
    assert check_location(loc(scope=LocationScope.UNSPECIFIED), PK) == (True, None)

    ok, reason = check_location(loc(scope=LocationScope.COUNTRIES, countries=["US", "CA"]), PK)
    assert not ok and "PK" in (reason or "")
    assert check_location(loc(scope=LocationScope.COUNTRIES, countries=["pk", "IN"]), PK)[0]

    assert check_location(loc(scope=LocationScope.REGIONS, regions=["APAC"]), PK)[0]
    ok, reason = check_location(loc(scope=LocationScope.REGIONS, regions=["EMEA", "Americas"]), PK)
    assert not ok and "EMEA" in (reason or "")
    assert check_location(loc(scope=LocationScope.REGIONS, regions=["EMEA"]), PT)[0]

    # Timezone-phrased regions use the candidate's UTC offset (PK is UTC+5, outside US bands).
    assert not check_location(loc(scope=LocationScope.REGIONS, regions=["US time zones"]), PK)[0]
    assert check_location(loc(scope=LocationScope.REGIONS, regions=["European time zones"]), PT)[0]

    # Explicit timezone bands with 1h tolerance.
    assert check_location(
        loc(scope=LocationScope.TIMEZONE, timezone_min_utc_offset=0, timezone_max_utc_offset=4), PK
    )[0]
    assert not check_location(
        loc(scope=LocationScope.TIMEZONE, timezone_min_utc_offset=-8, timezone_max_utc_offset=-4),
        PK,
    )[0]

    # Explicit exclusion always wins.
    ok, reason = check_location(loc(scope=LocationScope.WORLDWIDE, excluded_countries=["PK"]), PK)
    assert not ok and "excludes" in (reason or "")


def test_unknown_candidate_facts_pass_with_a_note() -> None:
    ok, note = check_location(loc(scope=LocationScope.COUNTRIES, countries=["US"]), UNKNOWN)
    assert ok and note and "unknown" in note
    ok, note = check_location(loc(scope=LocationScope.REGIONS, regions=["Narnia"]), PK)
    assert ok and note and "unrecognised" in note


def prefs(**kwargs: object) -> Preferences:
    base = {"seniority_levels": [], "excluded_keywords": [], "required_keywords": []}
    base.update(kwargs)
    return Preferences(**base)  # type: ignore[arg-type]


def test_preference_filters_each_give_a_reason() -> None:
    ex = JobExtraction(
        title="Senior Backend Engineer",
        summary="s",
        seniority=Seniority.SENIOR,
        remote=RemoteType.FULLY_REMOTE,
        salary=Salary(min=60000, max=80000, currency="USD", period="year"),
    )
    base = {
        "extraction": ex,
        "title": ex.title,
        "description": "Python. On-call rotation. Crypto exchange.",
        "candidate": PK,
    }

    assert apply_filters(preferences=prefs(), **base).passed  # type: ignore[arg-type]

    r = apply_filters(preferences=prefs(seniority_levels=["mid", "junior"]), **base)  # type: ignore[arg-type]
    assert not r.passed and "seniority is senior" in r.reasons[0]

    r = apply_filters(preferences=prefs(min_salary_usd=100_000), **base)  # type: ignore[arg-type]
    assert not r.passed and "$80,000" in r.reasons[0]

    r = apply_filters(preferences=prefs(excluded_keywords=["crypto"]), **base)  # type: ignore[arg-type]
    assert not r.passed and "crypto" in r.reasons[0]

    r = apply_filters(preferences=prefs(required_keywords=["python", "rust"]), **base)  # type: ignore[arg-type]
    assert not r.passed and "'rust'" in r.reasons[0]

    hybrid = ex.model_copy(update={"remote": RemoteType.HYBRID})
    r = apply_filters(preferences=prefs(), **{**base, "extraction": hybrid})  # type: ignore[arg-type]
    assert not r.passed and "hybrid" in r.reasons[0]


def test_non_usd_salary_is_noted_not_filtered() -> None:
    ex = JobExtraction(
        title="E", summary="s", salary=Salary(max=50000, currency="EUR", period="year", text="€50k")
    )
    r = apply_filters(
        extraction=ex,
        title="E",
        description="",
        preferences=prefs(min_salary_usd=100_000),
        candidate=PK,
    )
    assert r.passed and any("not in USD" in n for n in r.notes)
