"""
URL configuration for docs app.
"""

from django.urls import path
from .views import (
    DocumentCreateView, 
    DocumentDetailView, 
    HealthCheckView, 
    MetricsView,
    WorkspaceCreateView,
    WorkspaceDetailView,
)

urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health-check"),
    path("metrics", MetricsView.as_view(), name="metrics"),
    path("docs", DocumentCreateView.as_view(), name="document-create"),
    path("docs/<uuid:doc_id>", DocumentDetailView.as_view(), name="document-detail"),
    path("workspaces", WorkspaceCreateView.as_view(), name="workspace-create"),
    path("workspaces/<uuid:ws_id>", WorkspaceDetailView.as_view(), name="workspace-detail"),
]
