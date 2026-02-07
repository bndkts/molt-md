"""
URL configuration for docs app.
"""

from django.urls import path
from .views import DocumentCreateView, DocumentDetailView, HealthCheckView

urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health-check"),
    path("docs", DocumentCreateView.as_view(), name="document-create"),
    path("docs/<uuid:doc_id>", DocumentDetailView.as_view(), name="document-detail"),
]
