"""
Custom throttling classes for molt-md API.
"""

from rest_framework.throttling import AnonRateThrottle


class CreateDocumentThrottle(AnonRateThrottle):
    """
    Stricter rate limit for document creation to prevent spam.
    Default: 10 requests per minute per IP.
    Configurable via THROTTLE_RATE_CREATE environment variable.
    """

    scope = "create"


class MonitoringThrottle(AnonRateThrottle):
    """
    Rate limit for monitoring endpoints (health check, metrics).
    Default: 60 requests per minute per IP.
    Configurable via THROTTLE_RATE_MONITORING environment variable.
    """

    scope = "monitoring"
