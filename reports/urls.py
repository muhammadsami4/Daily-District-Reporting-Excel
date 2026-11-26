from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reports/new/", views.new_report, name="new"),
    path("reports/preview/", views.preview, name="preview"),
    path("reports/preview/discard/", views.discard_draft, name="discard"),
    path("reports/history/", views.history, name="history"),
    path("reports/<int:pk>/", views.report_detail, name="detail"),
    path("reports/<int:pk>/excel/", views.report_excel, name="excel"),
    path("reports/<int:pk>/revise/", views.start_revision, name="revise"),
    path("statistics/districts/", views.district_stats, name="district_stats"),
    path("compare/", views.compare, name="compare"),
    path("settings/", views.settings_page, name="settings"),
    path("settings/confirm-mapping/<slug:code>/", views.confirm_mapping, name="confirm_mapping"),
]
