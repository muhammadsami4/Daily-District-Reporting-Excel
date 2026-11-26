"""Shared helpers for the framework-independent tests."""
from datetime import date
from pathlib import Path

from reports.core.constants import CATEGORIES, DISTRICTS
from reports.core.parser import NameResolver, parse_report

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "sample_data"
REFERENCE = SAMPLES / "reference_template.xlsx"

CODES = [c["code"] for c in CATEGORIES]
LABELS = {c["code"]: c["label"] for c in CATEGORIES}
DISTRICT_RESOLVER = NameResolver(DISTRICTS)
CATEGORY_RESOLVER = NameResolver([(c["code"], [c["label"], *c["aliases"]]) for c in CATEGORIES],
                                 fuzzy_cutoff=0.9, strip_suffixes=("total",))


def parse(text, form_date=None):
    return parse_report(text, DISTRICT_RESOLVER, CATEGORY_RESOLVER, CODES, form_date, LABELS)


def sample(name):
    return (SAMPLES / name).read_text(encoding="utf-8")


def codes(issues):
    return [i.code for i in issues]


def grid_rows(parsed):
    """Reference-ordered (district, {code: value}) rows from a parsed report (blanks -> 0)."""
    return [(name, {c: (parsed.entries[c].get(name) or 0) for c in CODES}) for name, _ in DISTRICTS]
