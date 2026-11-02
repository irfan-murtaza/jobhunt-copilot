from jobhunt.services.normalize import (
    canonical_url,
    content_hash,
    normalize_company,
    normalize_title,
)


def test_company_normalisation_strips_suffixes_and_punctuation() -> None:
    assert normalize_company("Acme Robotics Inc.") == "acme robotics"
    assert normalize_company("Acme Robotics") == "acme robotics"
    assert normalize_company("ACME-Robotics, Ltd") == "acme robotics"
    assert normalize_company("Co-op Bank") == "co op bank"


def test_title_normalisation_drops_location_noise() -> None:
    assert normalize_title("Senior Backend Engineer (Remote)") == "senior backend engineer"
    assert (
        normalize_title("Senior Backend Engineer - Remote, Worldwide") == "senior backend engineer"
    )
    assert normalize_title("Senior Backend Engineer [EMEA]") == normalize_title(
        "Senior Backend Engineer"
    )


def test_canonical_url_removes_tracking_and_normalises_case() -> None:
    assert (
        canonical_url("HTTPS://Boards.Greenhouse.io/iota/jobs/5100001/?gh_src=abc&utm_source=x")
        == "https://boards.greenhouse.io/iota/jobs/5100001"
    )
    assert canonical_url("https://a.test/j?b=2&a=1&ref=hn") == "https://a.test/j?a=1&b=2"


def test_content_hash_is_stable_across_cosmetic_differences() -> None:
    a = content_hash(
        "Senior Backend Engineer (Remote)", "Acme Robotics Inc.", "We hire.\n5+ years Python."
    )
    b = content_hash("Senior Backend Engineer", "Acme Robotics", "we hire. 5+ YEARS python!")
    c = content_hash("Senior Backend Engineer", "Acme Robotics", "We hire. 6+ years Python.")
    assert a == b and a != c
