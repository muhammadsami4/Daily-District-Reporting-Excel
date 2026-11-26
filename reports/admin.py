from django.contrib import admin

from .models import DailyReport, District, DistrictReportDetail, ReportCategory, ReportRevision


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("sort_order", "name", "aliases", "is_active")
    list_editable = ("aliases", "is_active")
    search_fields = ("name", "aliases")


@admin.register(ReportCategory)
class ReportCategoryAdmin(admin.ModelAdmin):
    list_display = ("sort_order", "label", "excel_header", "aliases", "mapping_confirmed")


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "revision", "created_by", "updated_at")
    date_hierarchy = "report_date"
    readonly_fields = ("raw_text", "declared_totals", "revision", "created_by", "updated_by")


admin.site.register(DistrictReportDetail)
admin.site.register(ReportRevision)
