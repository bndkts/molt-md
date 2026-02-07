"""
API views for molt-md backend.
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ParseError,
    Throttled,
    ValidationError,
)
from rest_framework.renderers import JSONRenderer, BaseRenderer
from django.http import HttpResponse
from django.db import transaction
from django.utils import timezone
from cryptography.exceptions import InvalidTag

from .models import Document
from .serializers import (
    DocumentDetailSerializer,
    DocumentCreateSerializer,
    DocumentCreateResponseSerializer,
    DocumentUpdateResponseSerializer,
)
from .encryption import (
    generate_key,
    decode_key,
    encrypt_content,
    decrypt_content,
    verify_key,
)
from .throttling import CreateDocumentThrottle, MonitoringThrottle


# Maximum content size: 5 MB
MAX_CONTENT_SIZE = 5 * 1024 * 1024


class PlainTextRenderer(BaseRenderer):
    """Renderer for plain text/markdown responses."""

    media_type = "text/markdown"
    format = "txt"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, str):
            return data.encode(self.charset)
        return data


def custom_exception_handler(exc, context):
    """Custom exception handler for consistent error responses."""
    from rest_framework.views import exception_handler

    response = exception_handler(exc, context)

    if response is not None:
        error_code = "error"
        message = str(exc)

        if isinstance(exc, Throttled):
            error_code = "rate_limited"
            message = "Too many requests. Please try again later."
            # Preserve the Retry-After header set by DRF
        elif isinstance(exc, NotFound):
            error_code = "not_found"
        elif isinstance(exc, PermissionDenied):
            error_code = "forbidden"
        elif isinstance(exc, ParseError):
            error_code = "bad_request"
        elif isinstance(exc, ValidationError):
            error_code = "bad_request"

        response.data = {"error": error_code, "message": message}

    return response


class HealthCheckView(APIView):
    """Health check endpoint."""

    throttle_classes = [MonitoringThrottle]

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class DocumentCreateView(APIView):
    """Create a new encrypted document."""

    throttle_classes = [CreateDocumentThrottle]

    def post(self, request):
        # Parse request body
        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data.get("content", "")

        # Check content size
        if len(content.encode("utf-8")) > MAX_CONTENT_SIZE:
            return Response(
                {
                    "error": "payload_too_large",
                    "message": "Content exceeds 5 MB limit.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Generate key
        key_b64 = generate_key()
        raw_key = decode_key(key_b64)

        # Encrypt content
        ciphertext, nonce = encrypt_content(content, raw_key)

        # Create document
        document = Document.objects.create(
            content_encrypted=ciphertext, nonce=nonce, version=1
        )

        # Return ID and key
        response_serializer = DocumentCreateResponseSerializer(
            {"id": document.id, "key": key_b64}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    """Read, update, or delete a document."""

    renderer_classes = [JSONRenderer, PlainTextRenderer]

    def _get_document(self, doc_id):
        """Helper to get document or raise 404."""
        try:
            return Document.objects.get(id=doc_id)
        except Document.DoesNotExist:
            raise NotFound("Document not found.")

    def _get_key_from_header(self, request):
        """Helper to extract and decode key from header."""
        key_b64 = request.headers.get("X-Molt-Key")
        if not key_b64:
            raise PermissionDenied("Missing X-Molt-Key header.")

        try:
            raw_key = decode_key(key_b64)
            return raw_key
        except Exception:
            raise PermissionDenied("Invalid X-Molt-Key header.")

    def _verify_key(self, document, raw_key):
        """Helper to verify key by attempting decryption."""
        if not verify_key(document.content_encrypted, document.nonce, raw_key):
            raise PermissionDenied("Invalid encryption key.")

    def _decrypt_document(self, document, raw_key):
        """Helper to decrypt document content."""
        try:
            content = decrypt_content(
                document.content_encrypted, document.nonce, raw_key
            )
            return content
        except (InvalidTag, Exception):
            raise PermissionDenied("Invalid encryption key.")

    def get(self, request, doc_id):
        """Read document content."""
        document = self._get_document(doc_id)
        raw_key = self._get_key_from_header(request)
        content = self._decrypt_document(document, raw_key)

        # Update last_accessed to extend TTL on reads
        Document.objects.filter(id=doc_id).update(last_accessed=timezone.now())

        # Determine response format based on Accept header
        accept = request.headers.get("Accept", "text/markdown")

        if "application/json" in accept:
            # Return JSON response
            response_serializer = DocumentDetailSerializer(
                {"id": document.id, "content": content, "version": document.version}
            )
            response = Response(response_serializer.data, status=status.HTTP_200_OK)
            response["ETag"] = f'"v{document.version}"'
        else:
            # Return plain markdown
            response = HttpResponse(
                content, content_type="text/markdown; charset=utf-8"
            )
            response["ETag"] = f'"v{document.version}"'

        return response

    def put(self, request, doc_id):
        """Update document content (replace)."""
        document = self._get_document(doc_id)
        raw_key = self._get_key_from_header(request)
        self._verify_key(document, raw_key)

        # Get new content from request body
        if request.content_type == "text/markdown":
            new_content = request.body.decode("utf-8")
        else:
            return Response(
                {
                    "error": "bad_request",
                    "message": "Content-Type must be text/markdown.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check content size
        if len(new_content.encode("utf-8")) > MAX_CONTENT_SIZE:
            return Response(
                {
                    "error": "payload_too_large",
                    "message": "Content exceeds 5 MB limit.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Check If-Match header for optimistic concurrency control
        if_match = request.headers.get("If-Match")
        expected_version = None
        if if_match:
            try:
                expected_version = int(if_match.strip('"').replace("v", ""))
            except (ValueError, TypeError):
                return Response(
                    {
                        "error": "bad_request",
                        "message": "Malformed If-Match header. Expected format: \"v<number>\".",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if document.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": document.version},
                    status=status.HTTP_409_CONFLICT,
                )

        # Encrypt new content
        ciphertext, nonce = encrypt_content(new_content, raw_key)

        # Update document with atomic version check
        with transaction.atomic():
            # Re-fetch with lock
            document = Document.objects.select_for_update().get(id=doc_id)

            # Double-check version if If-Match was provided
            if if_match and document.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": document.version},
                    status=status.HTTP_409_CONFLICT,
                )

            document.content_encrypted = ciphertext
            document.nonce = nonce
            document.version += 1
            document.save()

        response_serializer = DocumentUpdateResponseSerializer(
            {"success": True, "version": document.version}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, doc_id):
        """Append to document content."""
        document = self._get_document(doc_id)
        raw_key = self._get_key_from_header(request)
        existing_content = self._decrypt_document(document, raw_key)

        # Get content to append from request body
        if request.content_type == "text/markdown":
            append_content = request.body.decode("utf-8")
        else:
            return Response(
                {
                    "error": "bad_request",
                    "message": "Content-Type must be text/markdown.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Combine content
        new_content = existing_content + "\n" + append_content

        # Check combined content size
        if len(new_content.encode("utf-8")) > MAX_CONTENT_SIZE:
            return Response(
                {
                    "error": "payload_too_large",
                    "message": "Combined content exceeds 5 MB limit.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Check If-Match header for optimistic concurrency control
        if_match = request.headers.get("If-Match")
        expected_version = None
        if if_match:
            try:
                expected_version = int(if_match.strip('"').replace("v", ""))
            except (ValueError, TypeError):
                return Response(
                    {
                        "error": "bad_request",
                        "message": "Malformed If-Match header. Expected format: \"v<number>\".",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if document.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": document.version},
                    status=status.HTTP_409_CONFLICT,
                )

        # Encrypt new content
        ciphertext, nonce = encrypt_content(new_content, raw_key)

        # Update document with atomic version check
        with transaction.atomic():
            # Re-fetch with lock
            document = Document.objects.select_for_update().get(id=doc_id)

            # Double-check version if If-Match was provided
            if if_match and document.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": document.version},
                    status=status.HTTP_409_CONFLICT,
                )

            document.content_encrypted = ciphertext
            document.nonce = nonce
            document.version += 1
            document.save()

        response_serializer = DocumentUpdateResponseSerializer(
            {"success": True, "version": document.version}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, doc_id):
        """Delete a document."""
        document = self._get_document(doc_id)
        raw_key = self._get_key_from_header(request)
        self._verify_key(document, raw_key)

        # Delete the document
        document.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class MetricsView(APIView):
    """Simple metrics endpoint showing database statistics."""

    throttle_classes = [MonitoringThrottle]

    def get(self, request):
        document_count = Document.objects.count()
        return Response({
            "documents": document_count
        }, status=status.HTTP_200_OK)
