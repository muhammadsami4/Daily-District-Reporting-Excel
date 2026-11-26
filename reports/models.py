"""Relational schema.

District ──< DistrictReportDetail >── ReportCategory
                      │
                 DailyReport ──< ReportRevision
(users are Django's built-in auth.User)

One DistrictReportDetail row per (report, district, category); zeros are stored too, so every
report is complete. Indexes support per-district / per-category history queries as the
number of reports grows.
"""
from django.conf import settings
from django.db import models


def _split(text):
    return [part.strip() for part in text.split(",") if part.strip()]


class District(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveSmallIntegerField(unique=True, help_text="Row order in the Excel export.")
    aliases = models.TextField(blank=True, help_text="Other spellings, comma separated, e.g. 'T.T.Singh, TT Singh'.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.name

    def alias_list(self):
        return _split(self.aliases)


class ReportCategory(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=80, help_text="Name shown in the web app.")
    excel_header = models.CharField(max_length=80, help_text="Column heading in the Excel file (legacy spelling).")
    aliases = models.TextField(blank=True, help_text="Spellings accepted in the pasted text, comma separated.")
    sort_order = models.PositiveSmallIntegerField(unique=True)
    mapping_confirmed = models.BooleanField(default=True, help_text="False = the Excel column mapping still needs "
                                            "an administrator's confirmation before figures can be saved.")

    class Meta:
        ordering = ["sort_order"]
        verbose_name_plural = "report categories"

    def __str__(self):
        return f"{self.label} → {self.excel_header}"

    def alias_list(self):
        return _split(self.aliases)


class DailyReport(models.Model):
    report_date = models.DateField(unique=True)          # one finalised report per date
    raw_text = models.TextField(blank=True)               # original pasted text, kept for audit
    declared_totals = models.JSONField(default=dict)      # {category code: total stated in the text or null}
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date"]

    def __str__(self):
        return f"Report {self.report_date:%d-%m-%Y} (rev {self.revision})"


class DistrictReportDetail(models.Model):
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="details")
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="details")
    category = models.ForeignKey(ReportCategory, on_delete=models.PROTECT, related_name="details")
    value = models.PositiveIntegerField(default=0)       # DB-level check: never negative

    class Meta:
        constraints = [models.UniqueConstraint(fields=["report", "district", "category"],
                                               name="uniq_report_district_category")]
        indexes = [
            models.Index(fields=["district", "category"], name="detail_district_category_idx"),
            models.Index(fields=["category", "report"], name="detail_category_report_idx"),
        ]

    def __str__(self):
        return f"{self.report_id}/{self.district_id}/{self.category_id}={self.value}"


class ReportRevision(models.Model):
    """Full snapshot of the report after every save (revision 1 = first save)."""
    report = models.ForeignKey(DailyReport, on_delete=models.CASCADE, related_name="revisions")
    revision_no = models.PositiveIntegerField()
    snapshot = models.JSONField()
    reason = models.CharField(max_length=300, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revision_no"]
        constraints = [models.UniqueConstraint(fields=["report", "revision_no"], name="uniq_report_revision")]

    def __str__(self):
        return f"{self.report} revision {self.revision_no}"
