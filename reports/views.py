"""HTTP views. Business logic lives in services.py / analytics.py / core/."""
from __future__ import annotations

from datetime import date
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, IntegerField, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import analytics, services
from .core.validator import has_errors
from .models import DailyReport, District, DistrictReportDetail, ReportCategory
from .permissions import editor_required, superuser_required

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _date_param(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _int_param(value: Optional[str]) -> Optional[int]:
    return int(value) if value and value.isdigit() else None


# ------------------------------------------------------------------ dashboard
@login_required
def dashboard(request):
    return render(request, "reports/dashboard.html", analytics.dashboard_context())


# ------------------------------------------------------------------ new report / preview
@editor_required
def new_report(request):
    ctx = {"raw_text": "", "report_date": "", "issues": None, "extraction": None}
    if request.method == "POST":
        text = request.POST.get("raw_text", "")
        date_str = request.POST.get("report_date", "").strip()
        action = request.POST.get("action", "process")
        ctx.update(raw_text=text, report_date=date_str)
        form_date = _date_param(date_str)
        if date_str and form_date is None:
            messages.error(request, "The reporting date is not a valid date.")
        elif not text.strip():
            messages.error(request, "Paste the daily report text first.")
        else:
            try:
                draft = services.parse_text(text, form_date)
            except ValueError as exc:       # ambiguous aliases in the master list
                messages.error(request, f"Master-list problem: {exc}")
            else:
                if action == "validate":
                    ctx["extraction"] = services.sort_issues([services.Issue.from_dict(i) for i in draft["issues"]])
                    ctx["issues"] = services.validate_draft(draft)
                    ctx["has_errors"] = has_errors(ctx["issues"])
                else:                        # "process" and "preview" both open the editable preview
                    request.session["draft"] = draft
                    return redirect("reports:preview")
    return render(request, "reports/new_report.html", ctx)


@editor_required
def preview(request):
    draft = request.session.get("draft")
    if not draft:
        messages.info(request, "There is no report in progress. Paste a daily report to start.")
        return redirect("reports:new")

    if request.method == "POST":
        draft = services.apply_post(draft, request.POST)
        request.session["draft"] = draft
        action = request.POST.get("action", "revalidate")
        issues = services.validate_draft(draft)
        report_date = services.draft_date(draft)
        existing = DailyReport.objects.filter(report_date=report_date).first() if report_date else None
        reason = request.POST.get("reason", "").strip()
        if action in ("save", "save_download"):
            if has_errors(issues):
                messages.error(request, "The report has validation errors and was not saved. Fix them below.")
            elif existing and not (request.POST.get("confirm_revision") == "on" and reason):
                messages.error(request, "A report for this date already exists. Tick the confirmation box and give "
                                        "a reason to save your changes as a new revision.")
            else:
                report, created = services.save_report(draft, request.user, reason)
                request.session.pop("draft", None)
                messages.success(request, f"Report for {report.report_date:%d-%m-%Y} "
                                          f"{'saved' if created else f'revised (revision {report.revision})'}.")
                url = reverse("reports:detail", args=[report.pk])
                return redirect(url + ("?autodownload=1" if action == "save_download" else ""))
        elif action == "revalidate":
            messages.info(request, "Report re-validated.")
    else:
        issues = services.validate_draft(draft)
        report_date = services.draft_date(draft)
        existing = DailyReport.objects.filter(report_date=report_date).first() if report_date else None
        reason = ""

    ctx = services.preview_matrix(draft)
    ctx.update(issues=issues, has_errors=has_errors(issues), report_date=draft.get("report_date") or "",
               existing=existing, reason=reason, revising=bool(draft.get("revise_report_id")))
    return render(request, "reports/preview.html", ctx)


@editor_required
@require_POST
def discard_draft(request):
    request.session.pop("draft", None)
    messages.info(request, "Draft discarded.")
    return redirect("reports:new")


# ------------------------------------------------------------------ history / detail / export
@login_required
def history(request):
    categories = list(ReportCategory.objects.all())
    exact = _date_param(request.GET.get("date"))
    date_from, date_to = _date_param(request.GET.get("date_from")), _date_param(request.GET.get("date_to"))
    district_id = _int_param(request.GET.get("district"))
    only_nonzero = request.GET.get("only_nonzero") == "1"

    qs = DailyReport.objects.select_related("updated_by")
    if exact:
        qs = qs.filter(report_date=exact)
    if date_from:
        qs = qs.filter(report_date__gte=date_from)
    if date_to:
        qs = qs.filter(report_date__lte=date_to)
    if district_id and only_nonzero:
        qs = qs.filter(Exists(DistrictReportDetail.objects.filter(report=OuterRef("pk"), district_id=district_id,
                                                                  value__gt=0)))
    for c in categories:                      # per-category totals (restricted to one district if chosen)
        cond = Q(details__category_id=c.id)
        if district_id:
            cond &= Q(details__district_id=district_id)
        qs = qs.annotate(**{f"t_{c.code}": Coalesce(Sum("details__value", filter=cond), 0, output_field=IntegerField())})

    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    rows = list(page.object_list)
    for r in rows:
        r.totals = [getattr(r, f"t_{c.code}") for c in categories]
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "reports/history.html", {
        "categories": categories, "rows": rows, "page": page, "districts": District.objects.all(),
        "filters": {"date": request.GET.get("date", ""), "date_from": request.GET.get("date_from", ""),
                    "date_to": request.GET.get("date_to", ""), "district": district_id, "only_nonzero": only_nonzero},
        "querystring": query.urlencode(),
        "district_name": District.objects.filter(pk=district_id).values_list("name", flat=True).first(),
    })


@login_required
def report_detail(request, pk):
    report = get_object_or_404(DailyReport.objects.select_related("created_by", "updated_by"), pk=pk)
    categories, rows, totals = services.report_table(report)
    labels = {c.code: c.label for c in categories}
    revisions = list(report.revisions.select_related("changed_by"))      # newest first
    for i, rev in enumerate(revisions):
        prev = revisions[i + 1].snapshot if i + 1 < len(revisions) else None
        rev.changes = services.diff_snapshots(prev, rev.snapshot, labels)
    declared = [report.declared_totals.get(c.code) for c in categories]
    return render(request, "reports/detail.html", {
        "report": report, "categories": categories, "rows": rows, "totals": totals, "declared": declared,
        "revisions": revisions, "autodownload": request.GET.get("autodownload") == "1"})


@login_required
def report_excel(request, pk):
    report = get_object_or_404(DailyReport, pk=pk)
    response = HttpResponse(services.report_excel_bytes(report), content_type=XLSX_MIME)
    response["Content-Disposition"] = f'attachment; filename="{services.excel_filename(report)}"'
    return response


@editor_required
@require_POST
def start_revision(request, pk):
    report = get_object_or_404(DailyReport, pk=pk)
    request.session["draft"] = services.draft_from_report(report)
    messages.info(request, f"Editing the report for {report.report_date:%d-%m-%Y}. Nothing changes until you save.")
    return redirect("reports:preview")


# ------------------------------------------------------------------ statistics / comparison
@login_required
def district_stats(request):
    date_from, date_to = _date_param(request.GET.get("date_from")), _date_param(request.GET.get("date_to"))
    data = analytics.district_statistics(date_from, date_to)
    categories = data["categories"]
    chart_code = request.GET.get("category") or (categories[0].code if categories else "")
    idx = next((i for i, c in enumerate(categories) if c.code == chart_code), 0) if categories else 0
    bar = [(r["district"].name, r["values"][idx]) for r in data["rows"] if categories and r["values"][idx] > 0]
    data["chart_label"] = categories[idx].label if categories else ""
    data["bar_chart"] = {"labels": [n for n, _ in bar],
                         "datasets": [{"label": data["chart_label"], "data": [v for _, v in bar]}]}
    district_id = _int_param(request.GET.get("district"))
    if district_id and categories:
        trend = analytics.district_trend(district_id, categories[idx].code, date_from, date_to)
        data["trend_chart"] = {"labels": trend["labels"],
                               "datasets": [{"label": data["chart_label"], "data": trend["data"]}]}
        data["trend_district"] = District.objects.filter(pk=district_id).first()
    data.update(districts=District.objects.all(), chart_code=categories[idx].code if categories else "",
                filters={"date_from": request.GET.get("date_from", ""), "date_to": request.GET.get("date_to", ""),
                         "district": district_id})
    return render(request, "reports/district_stats.html", data)


@login_required
def compare(request):
    reports = list(DailyReport.objects.all())
    ctx = {"reports": reports, "a": request.GET.get("a", ""), "b": request.GET.get("b", "")}
    a = DailyReport.objects.filter(report_date=_date_param(ctx["a"])).first() if ctx["a"] else None
    b = DailyReport.objects.filter(report_date=_date_param(ctx["b"])).first() if ctx["b"] else None
    if (ctx["a"] or ctx["b"]) and not (a and b):
        messages.error(request, "Choose two existing report dates to compare.")
    if a and b:
        result = analytics.compare_reports(a, b)
        cats = result["categories"]
        code = request.GET.get("category") or cats[0].code
        ctx.update(report_a=a, report_b=b, totals=result["totals"], category_code=code,
                   category_label=next((c.label for c in cats if c.code == code), ""),
                   categories=cats, rows=result["rows_for"](code))
    return render(request, "reports/compare.html", ctx)


# ------------------------------------------------------------------ settings
@login_required
def settings_page(request):
    from django.conf import settings as dj_settings
    return render(request, "reports/settings.html", {
        "categories": ReportCategory.objects.all(), "districts": District.objects.all(),
        "report_count": DailyReport.objects.count(),
        "db_engine": dj_settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]})


@superuser_required
@require_POST
def confirm_mapping(request, code):
    category = get_object_or_404(ReportCategory, code=code)
    category.mapping_confirmed = True
    category.save(update_fields=["mapping_confirmed"])
    services.audit.info("mapping confirmed category=%s excel_header=%r user=%s", category.code,
                        category.excel_header, request.user.username)
    messages.success(request, f"Mapping confirmed: {category.label} → Excel column '{category.excel_header}'.")
    return redirect("reports:settings")
