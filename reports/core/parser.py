"""Free-text daily report parser (framework independent, no Django imports).

Accepted layout (blank lines, spacing, trailing full stops, upper/lower case are all tolerated)::

    24-11-2026
    Located Total: 23
    Rawalpindi: 1
    Chakwal: 5
    Released Total: 2
    Attock: 02
    UnderProcess: 28
    T.T.Singh: 2

Design rules (accuracy first):
* The parser NEVER changes a number to make totals match.
* Anything ambiguous (duplicate district, negative or missing value, unknown name, date
  conflict) leaves the affected cell empty (``None``) / unresolved and raises an Issue,
  so the user has to decide in the preview screen.
* Misspellings are only auto-corrected when the match is unambiguous, and a warning is
  always raised so the user can see what was assumed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass
class Issue:
    level: str                      # error | warning | info
    code: str
    message: str
    line_no: Optional[int] = None
    category: Optional[str] = None
    district: Optional[str] = None
    # sticky=True: still applies after the user edits the preview grid (e.g. a structural
    # problem in the pasted text). Non-sticky issues are re-derived from the edited grid.
    sticky: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Issue":
        return cls(**data)


@dataclass
class UnresolvedLine:
    line_no: int
    raw_name: str
    category: str
    value: int


@dataclass
class ParsedReport:
    raw_text: str
    report_date: Optional[date] = None
    declared: Dict[str, Optional[int]] = field(default_factory=dict)          # category -> declared total
    entries: Dict[str, Dict[str, Optional[int]]] = field(default_factory=dict)  # category -> district -> value
    categories_present: List[str] = field(default_factory=list)
    unresolved: List[UnresolvedLine] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)


# --------------------------------------------------------------------------- name matching
def normalize(text: str, strip_suffixes: Iterable[str] = ()) -> str:
    """Lower-case and keep letters/digits only: 'T.T. Singh' -> 'ttsingh'."""
    key = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())
    for suffix in strip_suffixes:
        if key.endswith(suffix) and len(key) > len(suffix):
            key = key[: -len(suffix)]
    return key


class NameResolver:
    """Maps spelling variants to a canonical name (district name or category code)."""

    def __init__(self, entries: Iterable[Tuple[str, Iterable[str]]],
                 fuzzy_cutoff: float = 0.86, strip_suffixes: Iterable[str] = ()):
        self._suffixes = tuple(strip_suffixes)
        self._cutoff = fuzzy_cutoff
        self._keys: Dict[str, str] = {}
        for canonical, aliases in entries:
            for variant in (canonical, *aliases):
                key = normalize(variant, self._suffixes)
                if not key:
                    continue
                existing = self._keys.get(key)
                if existing is not None and existing != canonical:
                    raise ValueError(f"Spelling '{variant}' is ambiguous: it belongs to both "
                                     f"'{existing}' and '{canonical}'.")
                self._keys[key] = canonical

    def exact(self, raw: str) -> Optional[str]:
        return self._keys.get(normalize(raw, self._suffixes))

    def fuzzy(self, raw: str) -> Optional[str]:
        """Close-spelling match; returns None unless exactly one candidate stands out."""
        key = normalize(raw, self._suffixes)
        if len(key) < 4:
            return None
        scored = sorted(((SequenceMatcher(None, key, k).ratio(), c) for k, c in self._keys.items()),
                        reverse=True)
        best_score, best = scored[0]
        if best_score < self._cutoff:
            return None
        for score, canonical in scored[1:]:
            if canonical != best and score >= best_score - 0.04:
                return None  # two different districts look equally close -> ambiguous
        return best


# --------------------------------------------------------------------------- line parsing
DATE_ANY_RE = re.compile(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})")
VALUE_RE = re.compile(r"^(?P<name>.*?)\s*[:=]?\s*(?P<num>-?\d+)\s*[.,;]?$")
NAME_STRIP = " \t:.-\u2013=_"


def _clean(raw: str) -> str:
    line = unicodedata.normalize("NFKC", raw)
    line = line.replace("\u200b", "").replace("\ufeff", "").strip()
    line = re.sub(r"^[\u2022\u00b7*]+\s*", "", line)      # bullets
    line = re.sub(r"^[-\u2013\u2014]\s+", "", line)       # "- Attock: 5"
    return line.strip()


def parse_report(text: str, district_resolver: NameResolver, category_resolver: NameResolver,
                 category_codes: List[str], form_date: Optional[date] = None,
                 category_labels: Optional[Dict[str, str]] = None) -> ParsedReport:
    result = ParsedReport(raw_text=text,
                          declared={c: None for c in category_codes},
                          entries={c: {} for c in category_codes})
    issues = result.issues
    labels = category_labels or {}

    def lab(code):
        return labels.get(code, code)
    current: Optional[str] = None
    date_hits: List[Tuple[int, re.Match]] = []

    def add(level, code, message, line_no=None, category=None, district=None, sticky=False):
        issues.append(Issue(level, code, message, line_no, category, district, sticky))

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = _clean(raw)
        if not line:
            continue

        dm = DATE_ANY_RE.search(line)
        if dm and not re.search(r"\d", line[:dm.start()] + " " + line[dm.end():]):
            date_hits.append((line_no, dm))
            continue

        vm = VALUE_RE.match(line)
        if vm:
            name, value = vm.group("name").strip(NAME_STRIP), int(vm.group("num"))
        else:
            name, value = line.strip(NAME_STRIP), None
        has_digit = bool(re.search(r"\d", name))

        # Resolution order: category heading, district, near-miss category, near-miss district.
        category = category_resolver.exact(name)
        district = None
        fuzzy_hit = False
        if category is None and not has_digit:
            district = district_resolver.exact(name)
            if district is None:
                category = category_resolver.fuzzy(name)
                fuzzy_hit = category is not None
            if category is None and district is None:
                district = district_resolver.fuzzy(name)
                fuzzy_hit = district is not None

        # ---- category heading -------------------------------------------------
        if category is not None:
            if fuzzy_hit:
                add(WARNING, "fuzzy_category", f"Line {line_no}: '{name}' was read as category "
                    f"'{lab(category)}' (close spelling). Please check.", line_no, category, sticky=True)
            if category in result.categories_present:
                add(ERROR, "duplicate_category", f"Line {line_no}: category '{name}' appears more than "
                    "once. Fix the pasted text and process it again.", line_no, category, sticky=True)
            else:
                result.categories_present.append(category)
            current = category
            if value is not None:
                if value < 0:
                    add(ERROR, "negative_total", f"Line {line_no}: the total for '{name}' is negative "
                        f"({value}). Fix the pasted text and process it again.", line_no, category, sticky=True)
                elif result.declared[category] is None:
                    result.declared[category] = value
            continue

        # ---- district line ----------------------------------------------------
        if district is not None:
            if current is None:
                add(ERROR, "value_outside_category", f"Line {line_no}: '{line}' appears before any category "
                    "heading. Fix the pasted text and process it again.", line_no, district=district, sticky=True)
                continue
            if fuzzy_hit:
                add(WARNING, "fuzzy_district", f"Line {line_no}: '{name}' was read as district "
                    f"'{district}' (close spelling). Please check.", line_no, current, district, sticky=True)
            bucket = result.entries[current]
            if district in bucket:
                bucket[district] = None
                add(ERROR, "duplicate_entry", f"Line {line_no}: {district} appears more than once under "
                    f"'{lab(current)}'. Enter the correct value in the preview.", line_no, current, district)
            elif value is None:
                bucket[district] = None
                add(ERROR, "missing_value", f"Line {line_no}: {district} has no number under '{lab(current)}'. "
                    "Enter the value in the preview.", line_no, current, district)
            elif value < 0:
                bucket[district] = None
                add(ERROR, "negative_value", f"Line {line_no}: {district} has a negative value ({value}) under "
                    f"'{lab(current)}'. Enter the correct value in the preview.", line_no, current, district)
            else:
                bucket[district] = value
            continue

        # ---- not recognised ---------------------------------------------------
        if value is not None:
            if current is None:
                add(ERROR, "value_outside_category", f"Line {line_no}: '{line}' appears before any category "
                    "heading. Fix the pasted text and process it again.", line_no, sticky=True)
            else:
                result.unresolved.append(UnresolvedLine(line_no, name or line, current, value))
                add(ERROR, "unknown_district", f"Line {line_no}: '{name or line}' is not in the district master "
                    f"list (value {value} under '{lab(current)}'). Map it to a district or discard it in the preview.",
                    line_no, current)
        else:
            add(WARNING, "ignored_line", f"Line {line_no} was not understood and was ignored: '{line}'.",
                line_no, sticky=True)

    _resolve_date(result, date_hits, form_date, add)

    if not result.categories_present:
        add(ERROR, "no_categories", "No category headings (e.g. 'Located Total: 23') were found in the text.",
            sticky=True)
    for code in category_codes:
        if result.categories_present and code not in result.categories_present:
            add(INFO, "category_not_supplied", f"Category '{lab(code)}' was not supplied; zeros are used.",
                category=code, sticky=True)
    return result


def _resolve_date(result: ParsedReport, hits, form_date, add) -> None:
    valid: List[date] = []
    for line_no, m in hits:
        d, mo, y = (int(g) for g in m.groups())
        try:
            valid.append(date(y, mo, d))
        except ValueError:
            add(ERROR, "invalid_date", f"Line {line_no}: '{m.group(0)}' is not a real calendar date "
                "(format is DD-MM-YYYY). Choose the date in the preview.", line_no)
            return
    distinct = sorted(set(valid))
    if len(distinct) > 1:
        add(ERROR, "multiple_dates", "More than one different date was found in the text: "
            + ", ".join(d.strftime("%d-%m-%Y") for d in distinct) + ". Choose the date in the preview.")
        return
    text_date = distinct[0] if distinct else None
    if text_date and form_date and text_date != form_date:
        add(ERROR, "date_mismatch", f"The date in the text ({text_date:%d-%m-%Y}) differs from the date "
            f"entered in the form ({form_date:%d-%m-%Y}). Choose the correct date in the preview.")
        return
    result.report_date = text_date or form_date
    if result.report_date is None:
        add(ERROR, "missing_date", "No reporting date was found. Enter it in the preview.")
