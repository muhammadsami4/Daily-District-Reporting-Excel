"""Validation of an (edited) report grid. Framework independent.

Nothing here modifies a value: it only reports problems. A report may be finalised only
when :func:`has_errors` is False.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional

from .parser import ERROR, WARNING, Issue


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(i.level == ERROR for i in issues)


def validate_grid(report_date: Optional[date], grid: Dict[str, Dict[str, object]],
                  declared: Dict[str, object], category_labels: Dict[str, str],
                  district_names: Dict[str, str], unconfirmed: Iterable[str] = (),
                  today: Optional[date] = None) -> List[Issue]:
    """grid: district key -> category code -> int | None | str (str = not a number)."""
    issues: List[Issue] = []
    today = today or date.today()

    if report_date is None:
        issues.append(Issue(ERROR, "missing_date", "A valid reporting date is required."))
    elif report_date > today:
        issues.append(Issue(WARNING, "future_date", f"The reporting date {report_date:%d-%m-%Y} is in the future."))

    sums = {code: 0 for code in category_labels}
    incomplete = set()
    for key, per_cat in grid.items():
        name = district_names.get(key, str(key))
        for code, label in category_labels.items():
            v = per_cat.get(code)
            if v is None:
                issues.append(Issue(ERROR, "missing_value", f"{name} / {label}: a value is required "
                                    "(enter 0 if there is none).", category=code, district=name))
                incomplete.add(code)
            elif isinstance(v, bool) or not isinstance(v, int):
                issues.append(Issue(ERROR, "invalid_number", f"{name} / {label}: '{v}' is not a whole number.",
                                    category=code, district=name))
                incomplete.add(code)
            elif v < 0:
                issues.append(Issue(ERROR, "negative_value", f"{name} / {label}: negative values are not "
                                    f"allowed ({v}).", category=code, district=name))
                incomplete.add(code)
            else:
                sums[code] += v

    for code, label in category_labels.items():
        decl = declared.get(code)
        if decl is None:
            if sums[code] > 0 and code not in incomplete:
                issues.append(Issue(WARNING, "no_declared_total", f"{label}: no total was supplied, so the "
                                    f"district values (sum {sums[code]}) cannot be cross-checked.", category=code))
        elif isinstance(decl, bool) or not isinstance(decl, int):
            issues.append(Issue(ERROR, "invalid_total", f"{label}: declared total '{decl}' is not a whole number.",
                                category=code))
        elif decl < 0:
            issues.append(Issue(ERROR, "negative_total", f"{label}: declared total cannot be negative ({decl}).",
                                category=code))
        elif code not in incomplete and decl != sums[code]:
            issues.append(Issue(ERROR, "total_mismatch",
                                f"{label}: declared total is {decl} but the district values add up to {sums[code]} "
                                f"(difference {sums[code] - decl:+d}). Correct the district values or the total.",
                                category=code))

    for code in unconfirmed:
        if code in category_labels and (sums.get(code, 0) > 0 or (isinstance(declared.get(code), int)
                                                                   and declared.get(code) > 0)):
            issues.append(Issue(ERROR, "mapping_unconfirmed",
                                f"'{category_labels[code]}' contains figures but its Excel column mapping has not "
                                "been confirmed yet. An administrator must confirm it in Settings first.",
                                category=code))
    return issues
