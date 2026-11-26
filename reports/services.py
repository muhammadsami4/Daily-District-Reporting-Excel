"""Glue between the framework-independent core (parser / validator / excel) and the database.

The "draft" is a plain JSON-serialisable dict kept in the user's session between the
text-entry page and the preview page. NOTHING is written to the report tables until
``save_report`` is called with a draft that passes validation.

draft = {
  "report_date": "2026-11-24" | None,
  "raw_text": "...original pasted text...",
  "grid":     {"<district id>": {"<category code>": int | None | "invalid text"}},
  "declared": {"<category code>": int | None},          # totals stated in the text
  "unresolved": [{"idx", "line_no", "raw_name", "category", "value"}],
  "issues":   [Issue.to_dict(), ...],                   # what the parser found
  "revise_report_id": int | None,
}
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction

from .core.excel import build_workbook, workbook_to_bytes
from .core.parser import ERROR, INFO, WARNING, Issue, NameResolver, parse_report
from .core.validator import has_errors, validate_grid
from .models import (DailyReport, District, DistrictReportDetail, ReportCategory, ReportRevision)

audit = logging.getLogger("reports.audit")


# ------------------------------------------------------------------ master data
def get_categories() -> List[ReportCategory]:
    return list(ReportCategory.objects.all())


def get_active_districts() -> List[District]:
    return list(District.objects.filter(is_active=True))


def build_resolvers(districts, categories) -> Tuple[NameResolver, NameResolver]:
    district_resolver = NameResolver([(d.name, d.alias_list()) for d in districts])
    category_resolver = NameResolver(
        [(c.code, [c.label, c.code.replace("_", " "), *c.alias_list()]) for c in categories],
        fuzzy_cutoff=0.9, strip_suffixes=("total",))
    return district_resolver, category_resolver


# ------------------------------------------------------------------ drafts
def parse_text(text: str, form_date: Optional[date] = None):
    districts, categories = get_active_districts(), get_categories()
    dres, cres = build_resolvers(districts, categories)
    parsed = parse_report(text, dres, cres, [c.code for c in categories], form_date,
                          {c.code: c.label for c in categories})
    return draft_from_parsed(parsed, districts, categories)


def draft_from_parsed(parsed, districts, categories) -> dict:
    by_name = {d.name: d for d in districts}
    grid = {str(d.id): {c.code: 0 for c in categories} for d in districts}
    for code, per_district in parsed.entries.items():
        for name, value in per_district.items():
            grid[str(by_name[name].id)][code] = value          # may be None = needs input
    return {
        "report_date": parsed.report_date.isoformat() if parsed.report_date else None,
        "raw_text": parsed.raw_text,
        "grid": grid,
        "declared": dict(parsed.declared),
        "unresolved": [{"idx": i, "line_no": u.line_no, "raw_name": u.raw_name,
                        "category": u.category, "value": u.value} for i, u in enumerate(parsed.unresolved)],
        "issues": [i.to_dict() for i in parsed.issues],
        "revise_report_id": None,
    }


def draft_from_report(report: DailyReport) -> dict:
    """Load a saved report back into an editable draft (used for revisions)."""
    categories = get_categories()
    saved = list(report.details.values_list("district_id", "category__code", "value"))
    ids = {d.id for d in get_active_districts()} | {row[0] for row in saved}
    grid = {str(i): {c.code: 0 for c in categories} for i in ids}
    for district_id, code, value in saved:
        grid[str(district_id)][code] = value
    return {
        "report_date": report.report_date.isoformat(),
        "raw_text": report.raw_text,
        "grid": grid,
        "declared": {c.code: report.declared_totals.get(c.code) for c in categories},
        "unresolved": [],
        "issues": [],
        "revise_report_id": report.id,
    }


def districts_for_draft(draft: dict) -> List[District]:
    return list(District.objects.filter(id__in=[int(k) for k in draft["grid"]]))   # Meta.ordering = sort_order


def _parse_cell(raw):
    text = (raw or "").strip()
    if text == "":
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text            # kept as text so the validator can complain, never silently converted


def apply_post(draft: dict, post) -> dict:
    """Merge the edited preview form into the draft. Values are stored exactly as typed."""
    d = copy.deepcopy(draft)
    d["report_date"] = (post.get("report_date") or "").strip() or None
    for did, per_cat in d["grid"].items():
        for code in per_cat:
            key = f"cell__{did}__{code}"
            if key in post:
                per_cat[code] = _parse_cell(post[key])
    for code in d["declared"]:
        key = f"declared__{code}"
        if key in post:
            d["declared"][code] = _parse_cell(post[key])

    labels = {c.code: c.label for c in get_categories()}
    names = {str(x.id): x.name for x in districts_for_draft(d)}
    remaining = []
    for u in d["unresolved"]:
        choice = (post.get(f"map__{u['idx']}") or "").strip()
        if not choice or (choice != "discard" and choice not in d["grid"]):
            remaining.append(u)
        elif choice == "discard":
            d["issues"].append(Issue(INFO, "discarded_line", f"Line {u['line_no']} ('{u['raw_name']}: {u['value']}' "
                                     f"under {labels.get(u['category'])}) was discarded by the user.",
                                     sticky=True).to_dict())
        else:
            current = d["grid"][choice].get(u["category"])
            if current == 0:
                d["grid"][choice][u["category"]] = u["value"]
            else:      # would overwrite an existing figure -> make the user decide
                d["grid"][choice][u["category"]] = None
                d["issues"].append(Issue(WARNING, "mapping_conflict",
                                         f"Line {u['line_no']}: '{u['raw_name']}' was mapped to {names[choice]}, "
                                         f"which already has a {labels.get(u['category'])} value. Enter the correct "
                                         "figure.", sticky=True).to_dict())
    d["unresolved"] = remaining
    return d


def draft_date(draft: dict) -> Optional[date]:
    try:
        return date.fromisoformat(draft["report_date"]) if draft.get("report_date") else None
    except ValueError:
        return None


def sort_issues(issues: List[Issue]) -> List[Issue]:
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    return sorted(issues, key=lambda i: order.get(i.level, 3))


def validate_draft(draft: dict) -> List[Issue]:
    categories = get_categories()
    labels = {c.code: c.label for c in categories}
    names = {str(d.id): d.name for d in districts_for_draft(draft)}
    issues = [Issue.from_dict(i) for i in draft["issues"] if i.get("sticky")]
    for u in draft["unresolved"]:
        issues.append(Issue(ERROR, "unknown_district",
                            f"Line {u['line_no']}: '{u['raw_name']}' (value {u['value']} under "
                            f"{labels.get(u['category'])}) is not mapped to a district. Map it or discard it below."))
    issues += validate_grid(draft_date(draft), draft["grid"], draft["declared"], labels, names,
                            unconfirmed=[c.code for c in categories if not c.mapping_confirmed])
    return sort_issues(issues)


def preview_matrix(draft: dict) -> dict:
    """Everything the preview template needs, prepared here so templates stay simple."""
    categories, districts = get_categories(), districts_for_draft(draft)
    sums = {c.code: 0 for c in categories}
    rows = []
    for d in districts:
        per_cat = draft["grid"][str(d.id)]
        cells = []
        for c in categories:
            v = per_cat.get(c.code)
            ok = isinstance(v, int) and not isinstance(v, bool) and v >= 0
            if ok:
                sums[c.code] += v
            cells.append({"name": f"cell__{d.id}__{c.code}", "code": c.code, "value": "" if v is None else v,
                          "bad": not ok})
        rows.append({"district": d, "cells": cells})
    columns = []
    for c in categories:
        declared = draft["declared"].get(c.code)
        columns.append({"code": c.code, "label": c.label, "excel_header": c.excel_header,
                        "declared_name": f"declared__{c.code}", "declared": "" if declared is None else declared,
                        "sum": sums[c.code], "confirmed": c.mapping_confirmed})
    labels = {c.code: c.label for c in categories}
    unresolved = [dict(u, category_label=labels.get(u["category"], u["category"])) for u in draft["unresolved"]]
    return {"rows": rows, "columns": columns, "districts": districts, "unresolved": unresolved,
            "parse_issues": [Issue.from_dict(i) for i in draft["issues"]]}


# ------------------------------------------------------------------ saving
def _snapshot(draft: dict, names: Dict[str, str]) -> dict:
    return {"report_date": draft["report_date"], "raw_text": draft["raw_text"],
            "declared": draft["declared"],
            "grid": {names[k]: {c: int(v) for c, v in per.items()} for k, per in draft["grid"].items()}}


@transaction.atomic
def save_report(draft: dict, user, reason: str = "") -> Tuple[DailyReport, bool]:
    """Persist a draft. Re-validates on the server; raises ValueError if it has errors."""
    issues = validate_draft(draft)
    if has_errors(issues):
        raise ValueError("The report still has validation errors and cannot be saved.")
    report_date = draft_date(draft)
    categories = {c.code: c for c in get_categories()}
    districts = {str(d.id): d for d in districts_for_draft(draft)}
    declared = {code: draft["declared"].get(code) for code in categories}

    report = DailyReport.objects.select_for_update().filter(report_date=report_date).first()
    created = report is None
    if created:
        report = DailyReport.objects.create(report_date=report_date, raw_text=draft["raw_text"],
                                            declared_totals=declared, revision=1,
                                            created_by=user, updated_by=user)
    else:
        report.raw_text = draft["raw_text"]
        report.declared_totals = declared
        report.revision += 1
        report.updated_by = user
        report.save()
        report.details.all().delete()

    DistrictReportDetail.objects.bulk_create([
        DistrictReportDetail(report=report, district=districts[did], category=categories[code], value=int(value))
        for did, per_cat in draft["grid"].items() for code, value in per_cat.items()
    ])
    ReportRevision.objects.create(report=report, revision_no=report.revision,
                                  snapshot=_snapshot(draft, {k: d.name for k, d in districts.items()}),
                                  reason=reason[:300], changed_by=user)
    audit.info("report %s date=%s revision=%s user=%s reason=%r", "created" if created else "revised",
               report_date.isoformat(), report.revision, getattr(user, "username", None), reason)
    return report, created


# ------------------------------------------------------------------ reading / export
def report_matrix(report: DailyReport) -> Dict[int, Dict[str, int]]:
    """district id -> {category code: value}"""
    data: Dict[int, Dict[str, int]] = {}
    for did, code, value in report.details.values_list("district_id", "category__code", "value"):
        data.setdefault(did, {})[code] = value
    return data


def report_table(report: DailyReport):
    """(columns, rows) for display: rows = [{'district': District, 'values': [..], 'total': n}]"""
    categories = get_categories()
    matrix = report_matrix(report)
    rows = []
    for d in District.objects.filter(id__in=list(matrix.keys())):
        values = [matrix[d.id].get(c.code, 0) for c in categories]
        rows.append({"district": d, "values": values, "total": sum(values)})
    totals = [sum(r["values"][i] for r in rows) for i in range(len(categories))]
    return categories, rows, totals


def report_excel_bytes(report: DailyReport) -> bytes:
    categories, rows, _ = report_table(report)
    excel_rows = [(r["district"].name, {c.code: v for c, v in zip(categories, r["values"])}) for r in rows]
    wb = build_workbook(report.report_date, excel_rows, [(c.code, c.excel_header) for c in categories],
                        include_totals_row=getattr(settings, "EXPORT_INCLUDE_TOTALS_ROW", False))
    return workbook_to_bytes(wb)


def excel_filename(report: DailyReport) -> str:
    return f"{report.report_date:%d-%m-%Y}_same_day_only.xlsx"      # same naming as the reference file


def diff_snapshots(prev: Optional[dict], cur: dict, labels: Dict[str, str]) -> List[str]:
    if not prev:
        return []
    changes = []
    if prev["report_date"] != cur["report_date"]:
        changes.append(f"Date: {prev['report_date']} → {cur['report_date']}")
    for name, per_cat in cur["grid"].items():
        for code, value in per_cat.items():
            old = prev["grid"].get(name, {}).get(code)
            if old != value:
                changes.append(f"{name} / {labels.get(code, code)}: {old} → {value}")
    for code, value in cur["declared"].items():
        if prev["declared"].get(code) != value:
            changes.append(f"Declared total {labels.get(code, code)}: {prev['declared'].get(code)} → {value}")
    return changes
