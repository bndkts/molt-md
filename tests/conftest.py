"""
Pytest configuration and fixtures for molt-md tests.
"""
import pytest
from django.test import Client
from rest_framework.test import APIClient
from unittest.mock import patch


# Disable throttling for all tests
@pytest.fixture(scope="session", autouse=True)
def django_db_setup(django_db_setup, django_db_blocker):
    """Setup test database and configure settings."""
    pass


@pytest.fixture(autouse=True)
def disable_throttling(settings, monkeypatch):
    """Disable rate limiting for all tests."""
    # Remove all throttle classes from settings
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}
    
    # Mock the throttle classes to always allow requests
    from app.throttling import CreateDocumentThrottle, MonitoringThrottle
    
    def mock_allow_request(self, request, view):
        return True
    
    monkeypatch.setattr(CreateDocumentThrottle, 'allow_request', mock_allow_request)
    monkeypatch.setattr(MonitoringThrottle, 'allow_request', mock_allow_request)


@pytest.fixture
def api_client():
    """Return a Django REST Framework API client."""
    return APIClient()


@pytest.fixture
def django_client():
    """Return a Django test client."""
    return Client()
