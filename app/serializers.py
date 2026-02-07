"""
Serializers for molt-md API.
"""

from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer for Document model when returning JSON responses."""

    class Meta:
        model = Document
        fields = ["id", "version"]


class DocumentDetailSerializer(serializers.Serializer):
    """Serializer for detailed document responses with decrypted content."""

    id = serializers.UUIDField()
    content = serializers.CharField()
    version = serializers.IntegerField()


class DocumentCreateSerializer(serializers.Serializer):
    """Serializer for document creation requests."""

    content = serializers.CharField(required=False, allow_blank=True, default="")


class DocumentCreateResponseSerializer(serializers.Serializer):
    """Serializer for document creation response."""

    id = serializers.UUIDField()
    key = serializers.CharField()


class DocumentUpdateResponseSerializer(serializers.Serializer):
    """Serializer for document update response."""

    success = serializers.BooleanField(default=True)
    version = serializers.IntegerField()


class ErrorSerializer(serializers.Serializer):
    """Serializer for error responses."""

    error = serializers.CharField()
    message = serializers.CharField()


class ConflictErrorSerializer(serializers.Serializer):
    """Serializer for conflict error responses."""

    error = serializers.CharField()
    current_version = serializers.IntegerField()
