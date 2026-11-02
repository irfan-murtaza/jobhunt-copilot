import pytest
from pydantic import ValidationError

from jobhunt.schemas.profile import ProfileDocument, Role


def test_dates_accept_year_or_month_and_treat_present_as_null() -> None:
    role = Role(title="Dev", company="Acme", start="2020-01", end="Present")
    assert role.start == "2020-01"
    assert role.end is None
    assert role.period == "2020-01 to present"


def test_bad_dates_rejected() -> None:
    with pytest.raises(ValidationError):
        Role(title="Dev", company="Acme", start="Jan 2020")


def test_skills_deduped_case_insensitively_preserving_order() -> None:
    doc = ProfileDocument(skills=["Python", " python", "FastAPI", "fastapi ", "Redis"])
    assert doc.skills == ["Python", "FastAPI", "Redis"]


def test_years_of_experience_spans_roles() -> None:
    doc = ProfileDocument(
        roles=[
            Role(title="A", company="X", start="2018-06", end="2021-02"),
            Role(title="B", company="Y", start="2021-03", end="2024-03"),
        ]
    )
    assert doc.years_of_experience == 5.8


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileDocument.model_validate({"roles": [], "salary": 100})
