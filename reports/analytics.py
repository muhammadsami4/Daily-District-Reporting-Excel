"""Read-only queries behind the dashboard, statistics and comparison pages.
All aggregation happens in the database (indexed), never by loading every row."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from django.db.models import Sum

from .models import DailyReport, District, DistrictReportDetail, ReportCategory


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def dashboard_context() -> dict:
    categories = list(ReportCategory.objects.all())
    latest = DailyReport.objects.order_by("-report_date").first()
    ctx = {"categories": categories, "latest": latest,
           "report_count": DailyReport.objects.count(),
           "active_districts": District.objects.filter(is_active=True).count()}
    if latest is None:
        return ctx

    latest_totals = dict(latest.details.values_list("category__code").annotate(s=Sum("value")))
    all_totals = dict(DistrictReportDetail.objects.values_list("category__code").annotate(s=Sum("value")))
    ctx["cards"] = [{"label": c.label, "code": c.code, "latest": latest_totals.get(c.code, 0),
                     "all_time": all_totals.get(c.code, 0)} for c in categories]
    ctx["reporting_districts"] = latest.details.filter(value__gt=0).values("district").distinct().count()

    recent = list(DailyReport.objects.order_by("-report_date")[:30])            # newest first
    by_date = defaultdict(dict)
    for rdate, code, s in (DistrictReportDetail.objects.filter(report_id__in=[r.id for r in recent])
                           .values_list("report__report_date", "category__code").annotate(s=Sum("value"))):
        by_date[rdate][code] = s
    ordered = sorted(by_date)
    ctx["trend_chart"] = {"labels": [_fmt(d) for d in ordered],
                          "datasets": [{"label": c.label, "data": [by_date[d].get(c.code, 0) for d in ordered]}
                                       for c in categories]}
    ctx["previous_reports"] = [{"report": r, "values": [by_date[r.report_date].get(c.code, 0) for c in categories]}
                               for r in recent[:10]]

    per_district = defaultdict(dict)
    order = {}
    for sort_order, name, code, value in latest.details.filter(value__gt=0).values_list(
            "district__sort_order", "district__name", "category__code", "value"):
        per_district[name][code] = value
        order[name] = sort_order
    names = sorted(per_district, key=order.get)
    ctx["district_chart"] = {"labels": names,
                             "datasets": [{"label": c.label, "data": [per_district[n].get(c.code, 0) for n in names]}
                                          for c in categories]}
    return ctx


def district_statistics(date_from: Optional[date], date_to: Optional[date]) -> dict:
    categories = list(ReportCategory.objects.all())
    details = DistrictReportDetail.objects.all()
    reports = DailyReport.objects.all()
    if date_from:
        details, reports = details.filter(report__report_date__gte=date_from), reports.filter(report_date__gte=date_from)
    if date_to:
        details, reports = details.filter(report__report_date__lte=date_to), reports.filter(report_date__lte=date_to)
    sums = defaultdict(dict)
    for did, code, s in details.values_list("district_id", "category__code").annotate(s=Sum("value")):
        sums[did][code] = s
    rows = []
    for d in District.objects.filter(id__in=list(sums.keys())):
        values = [sums[d.id].get(c.code, 0) for c in categories]
        rows.append({"district": d, "values": values, "total": sum(values)})
    totals = [sum(r["values"][i] for r in rows) for i in range(len(categories))]
    return {"categories": categories, "rows": rows, "totals": totals, "report_count": reports.count()}


def district_trend(district_id: int, category_code: str, date_from, date_to) -> dict:
    qs = DistrictReportDetail.objects.filter(district_id=district_id, category__code=category_code)
    if date_from:
        qs = qs.filter(report__report_date__gte=date_from)
    if date_to:
        qs = qs.filter(report__report_date__lte=date_to)
    points = list(qs.order_by("report__report_date").values_list("report__report_date", "value"))
    return {"labels": [_fmt(d) for d, _ in points], "data": [v for _, v in points]}


def compare_reports(report_a: DailyReport, report_b: DailyReport) -> dict:
    categories = list(ReportCategory.objects.all())

    def matrix(report):
        data = defaultdict(dict)
        for did, code, value in report.details.values_list("district_id", "category__code", "value"):
            data[did][code] = value
        return data

    a, b = matrix(report_a), matrix(report_b)
    districts = list(District.objects.filter(id__in=set(a) | set(b)))
    totals = []
    for c in categories:
        ta = sum(v.get(c.code, 0) for v in a.values())
        tb = sum(v.get(c.code, 0) for v in b.values())
        totals.append({"category": c, "a": ta, "b": tb, "delta": tb - ta})

    def rows_for(code):
        rows = []
        for d in districts:
            va, vb = a.get(d.id, {}).get(code, 0), b.get(d.id, {}).get(code, 0)
            rows.append({"district": d, "a": va, "b": vb, "delta": vb - va,
                         "pct": round((vb - va) * 100 / va, 1) if va else None})
        return rows

    return {"categories": categories, "totals": totals, "rows_for": rows_for}
