"""
Custom throttling classes for molt-md API.
"""

from rest_framework.throttling import AnonRateThrottle


class CreateDocumentThrottle(AnonRateThrottle):
    """
    Stricter rate limit for document creation to prevent spam.
    10 requests per minute per IP.
    """

    rate = "10/min"
    scope = "create"


class MonitoringThrottle(AnonRateThrottle):
    """
    Rate limit for monitoring endpoints (health check, metrics).
    60 requests per minute per IP.
    """

    rate = "60/min"
    scope = "monitoring"
