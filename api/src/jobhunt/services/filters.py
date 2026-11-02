"""Hard filters: cheap, deterministic, explainable reasons for excluding a job.

A job that fails any filter is never scored by the LLM. Every exclusion carries a
human-readable reason so the UI can show *why* a job was hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobhunt.models import Preferences
from jobhunt.schemas.job import JobExtraction, LocationScope, RemoteType, Seniority
from jobhunt.services.geo import region_countries, region_timezone_band, utc_offset_hours

TIMEZONE_TOLERANCE_HOURS = 1


@dataclass(slots=True)
class FilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)  # why it was excluded
    notes: list[str] = field(default_factory=list)  # things we could not verify


@dataclass(slots=True)
class CandidateContext:
    country: str | None  # ISO alpha-2
    timezone: str | None  # IANA

    @property
    def utc_offset(self) -> int | None:
        return utc_offset_hours(self.timezone)


def check_location(
    extraction: JobExtraction, candidate: CandidateContext
) -> tuple[bool, str | None]:
    """Returns (eligible, reason). Unknown facts give the benefit of the doubt with a note."""
    loc = extraction.location
    country = (candidate.country or "").upper()

    if country and country in loc.excluded_countries:
        return False, f"posting excludes candidates in {country}"

    if loc.scope in (LocationScope.WORLDWIDE, LocationScope.UNSPECIFIED):
        return True, None

    if loc.scope == LocationScope.COUNTRIES:
        if not country:
            return True, "candidate country unknown; could not verify country restriction"
        if country in loc.countries:
            return True, None
        return (
            False,
            f"open to {', '.join(loc.countries) or 'listed countries'} only; "
            f"candidate is in {country}",
        )

    if loc.scope == LocationScope.REGIONS:
        if not country:
            return True, "candidate country unknown; could not verify region restriction"
        unknown: list[str] = []
        for region in loc.regions:
            countries = region_countries(region)
            if countries is not None:
                if not countries or country in countries:
                    return True, None
                continue
            band = region_timezone_band(region)
            if band is not None:
                offset = candidate.utc_offset
                if (
                    offset is None
                    or band[0] - TIMEZONE_TOLERANCE_HOURS
                    <= offset
                    <= band[1] + TIMEZONE_TOLERANCE_HOURS
                ):
                    return True, None
                continue
            unknown.append(region)
        if unknown and len(unknown) == len(loc.regions):
            return True, f"unrecognised region(s) {', '.join(unknown)}; not verified"
        return False, f"limited to {', '.join(loc.regions)}; candidate is in {country}"

    if loc.scope == LocationScope.TIMEZONE:
        offset = candidate.utc_offset
        if offset is None:
            return True, "candidate timezone unknown; could not verify timezone band"
        low = loc.timezone_min_utc_offset
        high = loc.timezone_max_utc_offset
        if low is None and high is None:
            return True, "timezone band not stated numerically; not verified"
        low = low if low is not None else -12
        high = high if high is not None else 14
        if low - TIMEZONE_TOLERANCE_HOURS <= offset <= high + TIMEZONE_TOLERANCE_HOURS:
            return True, None
        return False, f"requires UTC{low:+d} to UTC{high:+d}; candidate is at UTC{offset:+d}"

    return True, None


def apply_filters(
    *,
    extraction: JobExtraction,
    title: str,
    description: str,
    preferences: Preferences,
    candidate: CandidateContext,
) -> FilterResult:
    result = FilterResult(passed=True)
    text = f"{title}\n{description}".lower()

    eligible, reason = check_location(extraction, candidate)
    if not eligible:
        result.passed = False
        result.reasons.append(reason or "location not eligible")
    elif reason:
        result.notes.append(reason)

    if extraction.remote in (RemoteType.ONSITE, RemoteType.HYBRID):
        result.passed = False
        result.reasons.append(
            f"role is {extraction.remote.value.replace('_', ' ')}, not fully remote"
        )

    wanted = {s.lower() for s in preferences.seniority_levels or []}
    if (
        wanted
        and extraction.seniority != Seniority.UNSPECIFIED
        and extraction.seniority.value not in wanted
    ):
        result.passed = False
        result.reasons.append(
            f"seniority is {extraction.seniority.value}; you want {', '.join(sorted(wanted))}"
        )

    if preferences.min_salary_usd and extraction.salary:
        salary = extraction.salary
        top = salary.max or salary.min
        if (
            top
            and (salary.currency or "USD").upper() == "USD"
            and (salary.period or "year") == "year"
        ):
            if top < preferences.min_salary_usd:
                result.passed = False
                result.reasons.append(
                    f"salary up to ${top:,} is below your ${preferences.min_salary_usd:,} minimum"
                )
        elif top:
            result.notes.append(
                f"salary {salary.text or top} not in USD/year; minimum not compared"
            )

    for keyword in preferences.excluded_keywords or []:
        if keyword.lower() in text:
            result.passed = False
            result.reasons.append(f"contains excluded keyword {keyword!r}")

    missing_required = [k for k in (preferences.required_keywords or []) if k.lower() not in text]
    if missing_required:
        result.passed = False
        result.reasons.append(
            f"missing required keyword(s) {', '.join(repr(k) for k in missing_required)}"
        )

    return result
