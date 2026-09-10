from django.urls import path

from .views import ReportView

urlpatterns = [
    path("<str:report_type>/", ReportView.as_view(), name="admin-report"),
]