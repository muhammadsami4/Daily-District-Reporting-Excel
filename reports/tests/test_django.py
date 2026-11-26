"""Database / view tests. Run with:  python manage.py test
(The framework-independent tests in test_parser / test_validator / test_excel run there too.)"""
import io
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from reports import analytics, services
from reports.core.constants import DISTRICTS
from reports.core.excel import read_sheet_values
from reports.models import (DailyReport, District, DistrictReportDetail, ReportCategory, ReportRevision)
from reports.permissions import EDITOR_GROUP
from .helpers import REFERENCE, sample

PASSWORD = "Str0ng-test-pass-123"
SECOND_DAY = "25-11-2026\nLocated Total: 5\nLahore: 5\nReleased Total: 1\nAttock: 1\n"


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", verbosity=0)
        ReportCategory.objects.filter(code="arrested_lea").update(mapping_confirmed=True)
        User = get_user_model()
        cls.admin = User.objects.create_superuser("admin", "a@example.com", PASSWORD)
        cls.editor = User.objects.create_user("editor", password=PASSWORD)
        cls.editor.groups.add(Group.objects.get(name=EDITOR_GROUP))
        cls.viewer = User.objects.create_user("viewer", password=PASSWORD)

    def save(self, text, user=None, report_date=None):
        draft = services.parse_text(text)
        if report_date:
            draft["report_date"] = report_date
        return services.save_report(draft, user or self.admin, "test")


class MasterDataTests(Base):
    def test_seed_matches_reference_order_and_is_idempotent(self):
        self.assertEqual(list(District.objects.values_list("name", flat=True)), [n for n, _ in DISTRICTS])
        self.assertEqual(District.objects.count(), 38)
        call_command("seed_master_data", verbosity=0)
        self.assertEqual(District.objects.count(), 38)
        self.assertEqual(ReportCategory.objects.count(), 6)


class ModelConstraintTests(Base):
    def test_duplicate_detail_rejected(self):
        report, _ = self.save(sample("example_valid.txt"))
        d = DistrictReportDetail.objects.filter(report=report).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistrictReportDetail.objects.create(report=report, district=d.district, category=d.category, value=1)

    def test_negative_value_rejected_by_database(self):
        report, _ = self.save(sample("example_valid.txt"))
        d = DistrictReportDetail.objects.filter(report=report).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistrictReportDetail.objects.filter(pk=d.pk).update(value=-1)

    def test_one_report_per_date(self):
        self.save(sample("example_valid.txt"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyReport.objects.create(report_date=date(2026, 11, 24))


class ServiceTests(Base):
    def test_save_example_stores_everything(self):
        report, created = self.save(sample("example_valid.txt"))
        self.assertTrue(created)
        self.assertEqual(report.details.count(), 38 * 6)
        self.assertEqual(report.raw_text, sample("example_valid.txt"))
        _, rows, totals = services.report_table(report)
        self.assertEqual(totals, [23, 2, 0, 28, 0, 0])
        self.assertEqual(report.revisions.count(), 1)

    def test_invalid_draft_is_never_saved(self):
        draft = services.parse_text(sample("example_invalid_total.txt"))
        with self.assertRaises(ValueError):
            services.save_report(draft, self.admin)
        self.assertEqual(DailyReport.objects.count(), 0)

    def test_revision_replaces_figures_and_keeps_history(self):
        report, _ = self.save(sample("example_valid.txt"))
        draft = services.draft_from_report(report)
        lahore = District.objects.get(name="Lahore")
        draft["grid"][str(lahore.id)]["added"] = 4
        draft["declared"]["added"] = 27
        report2, created = services.save_report(draft, self.editor, "late figure")
        self.assertFalse(created)
        self.assertEqual(report2.pk, report.pk)
        self.assertEqual(report2.revision, 2)
        self.assertEqual(report2.details.count(), 38 * 6)
        self.assertEqual(services.report_table(report2)[2][0], 27)
        revisions = list(ReportRevision.objects.filter(report=report).order_by("revision_no"))
        self.assertEqual([r.revision_no for r in revisions], [1, 2])
        labels = {c.code: c.label for c in ReportCategory.objects.all()}
        changes = services.diff_snapshots(revisions[0].snapshot, revisions[1].snapshot, labels)
        self.assertIn("Lahore / Located: 0 → 4", changes)

    def test_excel_export_equals_reference_workbook(self):
        report, _ = self.save(sample("example_valid.txt"), report_date="2026-11-25")
        mine = read_sheet_values(io.BytesIO(services.report_excel_bytes(report)))
        self.assertEqual(mine, read_sheet_values(REFERENCE))

    def test_unconfirmed_mapping_blocks_saving_lea_figures(self):
        ReportCategory.objects.filter(code="arrested_lea").update(mapping_confirmed=False)
        draft = services.parse_text("24-11-2026\nTaken by LEA: 2\nLahore: 2")
        self.assertIn("mapping_unconfirmed", [i.code for i in services.validate_draft(draft)])

    def test_unresolved_line_mapping_and_discard(self):
        draft = services.parse_text("24-11-2026\nLocated Total: 5\nLahore: 3\nAtlantis: 2")
        self.assertEqual(len(draft["unresolved"]), 1)
        kasur = District.objects.get(name="Kasur")
        mapped = services.apply_post(draft, {"report_date": "2026-11-24", "map__0": str(kasur.id)})
        self.assertEqual(mapped["grid"][str(kasur.id)]["added"], 2)
        self.assertEqual(mapped["unresolved"], [])
        discarded = services.apply_post(draft, {"report_date": "2026-11-24", "map__0": "discard"})
        self.assertEqual([i.code for i in services.validate_draft(discarded) if i.level == "error"],
                         ["total_mismatch"])


class AnalyticsTests(Base):
    def setUp(self):
        self.r1, _ = self.save(sample("example_valid.txt"))
        self.r2, _ = self.save(SECOND_DAY)

    def test_compare(self):
        result = analytics.compare_reports(self.r1, self.r2)
        by_code = {t["category"].code: t for t in result["totals"]}
        self.assertEqual((by_code["added"]["a"], by_code["added"]["b"], by_code["added"]["delta"]), (23, 5, -18))
        rows = {r["district"].name: r for r in result["rows_for"]("added")}
        self.assertEqual(rows["Gujranwala"]["delta"], -17)
        self.assertEqual(rows["Lahore"]["delta"], 5)
        self.assertIsNone(rows["Lahore"]["pct"])

    def test_dashboard_uses_latest_report(self):
        ctx = analytics.dashboard_context()
        self.assertEqual(ctx["latest"].report_date, date(2026, 11, 25))
        self.assertEqual({c["code"]: c["latest"] for c in ctx["cards"]}["added"], 5)
        self.assertEqual({c["code"]: c["all_time"] for c in ctx["cards"]}["added"], 28)
        self.assertEqual(ctx["reporting_districts"], 2)

    def test_district_statistics_period_filter(self):
        stats = analytics.district_statistics(date(2026, 11, 25), None)
        self.assertEqual(stats["report_count"], 1)
        self.assertEqual(stats["totals"][0], 5)


class ViewTests(Base):
    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def process(self, text):
        return self.client.post(reverse("reports:new"), {"raw_text": text, "action": "process"})

    def confirm(self, date_iso="2026-11-24", action="save", **extra):
        return self.client.post(reverse("reports:preview"), {"report_date": date_iso, "action": action, **extra})

    def test_login_required(self):
        for name in ("reports:dashboard", "reports:history", "reports:new", "reports:compare"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response["Location"])

    def test_viewer_is_read_only(self):
        self.login(self.viewer)
        self.assertEqual(self.client.get(reverse("reports:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("reports:new")).status_code, 403)
        self.assertEqual(self.client.post(reverse("reports:preview"), {}).status_code, 403)

    def test_full_workflow_paste_preview_confirm_download(self):
        self.login(self.editor)
        self.assertRedirects(self.process(sample("example_valid.txt")), reverse("reports:preview"))
        page = self.client.get(reverse("reports:preview"))
        self.assertContains(page, "Ready to save")
        self.assertContains(page, "Attock")
        response = self.confirm(action="save_download")
        report = DailyReport.objects.get()
        self.assertRedirects(response, reverse("reports:detail", args=[report.pk]) + "?autodownload=1")
        download = self.client.get(reverse("reports:excel", args=[report.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn("spreadsheetml", download["Content-Type"])
        self.assertIn("24-11-2026_same_day_only.xlsx", download["Content-Disposition"])
        rows = read_sheet_values(io.BytesIO(download.content))
        self.assertEqual(len(rows), 39)
        self.assertEqual(rows[1][:3], [1, "Attock", "24-11-2026"])

    def test_invalid_report_cannot_be_saved(self):
        self.login(self.editor)
        self.process(sample("example_invalid_total.txt"))
        page = self.client.get(reverse("reports:preview"))
        self.assertContains(page, "declared total is 24")
        self.confirm()
        self.assertEqual(DailyReport.objects.count(), 0)

    def test_editing_value_in_preview_fixes_total(self):
        self.login(self.editor)
        self.process(sample("example_invalid_total.txt"))
        self.confirm(action="revalidate", **{"declared__added": "23"})
        self.assertContains(self.client.get(reverse("reports:preview")), "Ready to save")
        self.confirm()
        self.assertEqual(DailyReport.objects.count(), 1)

    def test_duplicate_date_needs_confirmation_and_reason(self):
        self.login(self.editor)
        self.process(sample("example_valid.txt"))
        self.confirm()
        self.process(sample("example_valid.txt"))
        self.confirm()                                             # no confirmation -> not saved
        self.assertEqual(DailyReport.objects.get().revision, 1)
        self.confirm(confirm_revision="on", reason="")             # no reason -> not saved
        self.assertEqual(DailyReport.objects.get().revision, 1)
        self.confirm(confirm_revision="on", reason="corrected figure")
        self.assertEqual(DailyReport.objects.get().revision, 2)

    def test_revise_flow_from_detail_page(self):
        self.login(self.editor)
        report, _ = self.save(sample("example_valid.txt"))
        self.assertRedirects(self.client.post(reverse("reports:revise", args=[report.pk])), reverse("reports:preview"))
        self.assertContains(self.client.get(reverse("reports:preview")), "Revise report")

    def test_history_search_and_district_filter(self):
        self.save(sample("example_valid.txt"))
        self.save(SECOND_DAY)
        self.login(self.viewer)
        url = reverse("reports:history")
        self.assertEqual(len(self.client.get(url).context["rows"]), 2)
        self.assertEqual(len(self.client.get(url, {"date": "2026-11-25"}).context["rows"]), 1)
        self.assertEqual(len(self.client.get(url, {"date_from": "2026-11-25"}).context["rows"]), 1)
        lahore = District.objects.get(name="Lahore")
        response = self.client.get(url, {"district": lahore.id, "only_nonzero": "1"})
        rows = response.context["rows"]
        self.assertEqual([r.report_date for r in rows], [date(2026, 11, 25)])
        self.assertEqual(rows[0].totals[0], 5)

    def test_compare_page(self):
        self.save(sample("example_valid.txt"))
        self.save(SECOND_DAY)
        self.login(self.viewer)
        response = self.client.get(reverse("reports:compare"), {"a": "2026-11-24", "b": "2026-11-25"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "-18")

    def test_statistics_dashboard_and_settings_pages_render(self):
        self.save(sample("example_valid.txt"))
        self.login(self.viewer)
        for name in ("reports:dashboard", "reports:district_stats", "reports:settings", "reports:history"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_confirm_mapping_is_admin_only(self):
        ReportCategory.objects.filter(code="arrested_lea").update(mapping_confirmed=False)
        url = reverse("reports:confirm_mapping", args=["arrested_lea"])
        self.login(self.editor)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.login(self.admin)
        self.client.post(url)
        self.assertTrue(ReportCategory.objects.get(code="arrested_lea").mapping_confirmed)
