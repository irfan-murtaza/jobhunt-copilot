"""Country and region tables for location eligibility.

Job postings name regions loosely ("EMEA", "Europe", "US time zones"). This maps a
candidate's ISO country to the region names a posting might use, so the hard filter can
answer "may someone in PK apply to an EMEA-only role?" without an LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EUROPE = {
    "AL",
    "AD",
    "AT",
    "BA",
    "BE",
    "BG",
    "BY",
    "CH",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "GR",
    "HR",
    "HU",
    "IE",
    "IS",
    "IT",
    "LI",
    "LT",
    "LU",
    "LV",
    "MC",
    "MD",
    "ME",
    "MK",
    "MT",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "RS",
    "SE",
    "SI",
    "SK",
    "SM",
    "UA",
    "VA",
    "XK",
}
EU = EUROPE - {
    "AL",
    "BA",
    "BY",
    "CH",
    "GB",
    "IS",
    "LI",
    "MC",
    "MD",
    "ME",
    "MK",
    "NO",
    "RS",
    "SM",
    "UA",
    "VA",
    "XK",
    "AD",
}
MIDDLE_EAST = {
    "AE",
    "BH",
    "EG",
    "IL",
    "IQ",
    "IR",
    "JO",
    "KW",
    "LB",
    "OM",
    "PS",
    "QA",
    "SA",
    "SY",
    "TR",
    "YE",
}
AFRICA = {
    "AO",
    "BF",
    "BI",
    "BJ",
    "BW",
    "CD",
    "CF",
    "CG",
    "CI",
    "CM",
    "CV",
    "DJ",
    "DZ",
    "ER",
    "ET",
    "GA",
    "GH",
    "GM",
    "GN",
    "GQ",
    "GW",
    "KE",
    "KM",
    "LR",
    "LS",
    "LY",
    "MA",
    "MG",
    "ML",
    "MR",
    "MU",
    "MW",
    "MZ",
    "NA",
    "NE",
    "NG",
    "RW",
    "SC",
    "SD",
    "SL",
    "SN",
    "SO",
    "SS",
    "ST",
    "SZ",
    "TD",
    "TG",
    "TN",
    "TZ",
    "UG",
    "ZA",
    "ZM",
    "ZW",
}
NORTH_AMERICA = {"US", "CA", "MX"}
LATAM = {
    "AR",
    "BO",
    "BR",
    "CL",
    "CO",
    "CR",
    "CU",
    "DO",
    "EC",
    "GT",
    "HN",
    "HT",
    "JM",
    "MX",
    "NI",
    "PA",
    "PE",
    "PR",
    "PY",
    "SV",
    "TT",
    "UY",
    "VE",
    "BZ",
    "GY",
    "SR",
}
SOUTH_ASIA = {"PK", "IN", "BD", "LK", "NP", "BT", "MV", "AF"}
EAST_ASIA = {"CN", "JP", "KR", "TW", "HK", "MO", "MN"}
SOUTHEAST_ASIA = {"SG", "MY", "ID", "TH", "VN", "PH", "KH", "LA", "MM", "BN", "TL"}
CENTRAL_ASIA = {"KZ", "UZ", "KG", "TJ", "TM"}
OCEANIA = {"AU", "NZ", "FJ", "PG", "WS", "TO", "VU", "SB"}
ASIA = SOUTH_ASIA | EAST_ASIA | SOUTHEAST_ASIA | CENTRAL_ASIA | MIDDLE_EAST
APAC = ASIA - MIDDLE_EAST | OCEANIA
AMERICAS = NORTH_AMERICA | LATAM
EMEA = EUROPE | MIDDLE_EAST | AFRICA

REGIONS: dict[str, frozenset[str]] = {
    "worldwide": frozenset(),
    "global": frozenset(),
    "anywhere": frozenset(),
    "europe": frozenset(EUROPE),
    "european union": frozenset(EU),
    "eu": frozenset(EU),
    "eea": frozenset(EU | {"IS", "LI", "NO"}),
    "uk": frozenset({"GB"}),
    "united kingdom": frozenset({"GB"}),
    "emea": frozenset(EMEA),
    "middle east": frozenset(MIDDLE_EAST),
    "mena": frozenset(MIDDLE_EAST | {"DZ", "LY", "MA", "TN", "SD"}),
    "africa": frozenset(AFRICA),
    "americas": frozenset(AMERICAS),
    "north america": frozenset(NORTH_AMERICA),
    "latam": frozenset(LATAM),
    "latin america": frozenset(LATAM),
    "south america": frozenset(
        LATAM - {"MX", "CR", "GT", "HN", "NI", "PA", "SV", "BZ", "CU", "DO", "HT", "JM", "PR", "TT"}
    ),
    "central america": frozenset({"CR", "GT", "HN", "NI", "PA", "SV", "BZ"}),
    "apac": frozenset(APAC),
    "asia pacific": frozenset(APAC),
    "asia-pacific": frozenset(APAC),
    "asia": frozenset(ASIA),
    "south asia": frozenset(SOUTH_ASIA),
    "southeast asia": frozenset(SOUTHEAST_ASIA),
    "east asia": frozenset(EAST_ASIA),
    "oceania": frozenset(OCEANIA),
    "australia": frozenset({"AU"}),
    "new zealand": frozenset({"NZ"}),
    "us": frozenset({"US"}),
    "usa": frozenset({"US"}),
    "united states": frozenset({"US"}),
    "canada": frozenset({"CA"}),
    "us and canada": frozenset({"US", "CA"}),
    "us/canada": frozenset({"US", "CA"}),
    "india": frozenset({"IN"}),
    "pakistan": frozenset({"PK"}),
    "germany": frozenset({"DE"}),
    "france": frozenset({"FR"}),
    "spain": frozenset({"ES"}),
    "portugal": frozenset({"PT"}),
    "netherlands": frozenset({"NL"}),
    "poland": frozenset({"PL"}),
    "ireland": frozenset({"IE"}),
    "brazil": frozenset({"BR"}),
    "mexico": frozenset({"MX"}),
    "argentina": frozenset({"AR"}),
    "singapore": frozenset({"SG"}),
    "philippines": frozenset({"PH"}),
    "japan": frozenset({"JP"}),
}

# Regions phrased as time zones rather than places.
TIMEZONE_REGIONS: dict[str, tuple[int, int]] = {
    "us time zones": (-10, -4),
    "us timezones": (-10, -4),
    "north american time zones": (-10, -3),
    "american time zones": (-10, -3),
    "european time zones": (-1, 3),
    "european timezones": (-1, 3),
    "eu time zones": (0, 3),
    "cet": (1, 2),
    "est": (-5, -4),
    "pst": (-8, -7),
    "gmt": (0, 1),
    "utc": (0, 0),
}


def normalise_region(name: str) -> str:
    cleaned = (
        name.lower().replace("&", "and").replace("+", " ").replace("-", " ").replace("/", " / ")
    )
    return " ".join(cleaned.split()).strip(" .,")


def region_countries(name: str) -> frozenset[str] | None:
    """Countries covered by a region name, empty set for 'worldwide', None if unknown."""
    key = normalise_region(name)
    if key in REGIONS:
        return REGIONS[key]
    for prefix in ("remote ", "remote-", "only ", "within "):
        if key.startswith(prefix) and key[len(prefix) :] in REGIONS:
            return REGIONS[key[len(prefix) :]]
    for suffix in (" only", " based", "-based", " residents", " region"):
        if key.endswith(suffix) and key[: -len(suffix)] in REGIONS:
            return REGIONS[key[: -len(suffix)]]
    return None


def region_timezone_band(name: str) -> tuple[int, int] | None:
    key = normalise_region(name)
    for phrase, band in TIMEZONE_REGIONS.items():
        if phrase in key:
            return band
    return None


def utc_offset_hours(timezone: str | None) -> int | None:
    if not timezone:
        return None
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    offset = datetime.now(UTC).astimezone(zone).utcoffset()
    return round(offset.total_seconds() / 3600) if offset is not None else None
