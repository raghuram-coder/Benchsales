"""USA-market filter: keep jobs that a US-based bench consultant could take.

Heuristic on the job's location string (and remote flag). Unknown / blank /
bare "Remote" locations are kept — we only drop jobs that clearly name
somewhere outside the US.
"""
import re

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}
STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina", "north dakota",
    "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
]
_US_WORDS = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|us only|americas|north america|"
    r"nationwide|anywhere in the us)\b|\bUS\b", re.I)
_NON_US = re.compile(
    r"\b(europe|emea|apac|asia|africa|latam|latin america|uk|united kingdom|"
    r"england|scotland|ireland|germany|france|spain|italy|netherlands|"
    r"poland|portugal|sweden|norway|denmark|finland|switzerland|austria|"
    r"belgium|czech|romania|ukraine|turkey|israel|india|pakistan|china|japan|"
    r"singapore|australia|new zealand|canada|ontario|quebec|british columbia|"
    r"alberta|toronto|vancouver|mexico|brazil|argentina|colombia|chile|"
    r"philippines|vietnam|indonesia|nigeria|kenya|egypt|south africa|uae|"
    r"dubai|berlin|london|paris|madrid|amsterdam|dublin|bangalore|bengaluru|"
    r"hyderabad|pune|mumbai|chennai|delhi)\b", re.I)
_STATE_ABBR = re.compile(r",\s*([A-Z]{2})\b")
_STATE_NAME = re.compile(r"\b(" + "|".join(STATE_NAMES) + r")\b", re.I)
_WORLDWIDE = re.compile(r"\b(worldwide|anywhere|global|international)\b", re.I)


def has_us_marker(location: str) -> bool:
    loc = location or ""
    if _US_WORDS.search(loc) or _STATE_NAME.search(loc):
        return True
    return any(m.group(1) in US_STATES for m in _STATE_ABBR.finditer(loc))


def is_us_job(job: dict) -> bool:
    """True if the job is plausibly open to a US-based consultant."""
    loc = (job.get("location") or "").strip()
    if not loc:
        return True
    if has_us_marker(loc):
        return True
    if _NON_US.search(loc):
        return False
    # "Remote", "Worldwide", "Anywhere", unknown strings: keep
    return True


def filter_us(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if is_us_job(j)]
