"""
API views for molt-md backend.
"""

import hmac
import json

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

from .models import Document, Workspace
from .serializers import (
    DocumentDetailSerializer,
    DocumentCreateSerializer,
    DocumentCreateResponseSerializer,
    DocumentUpdateResponseSerializer,
    WorkspaceSerializer,
    WorkspaceCreateSerializer,
    WorkspaceCreateResponseSerializer,
    WorkspaceDetailSerializer,
    WorkspaceUpdateResponseSerializer,
)
from .encryption import (
    generate_key,
    decode_key,
    encrypt_content,
    decrypt_content,
    verify_key,
    derive_read_key,
    hash_key,
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

        # Generate write key and derive read key
        write_key_b64 = generate_key()
        read_key_b64 = derive_read_key(write_key_b64)
        read_key_raw = decode_key(read_key_b64)
        read_key_hash = hash_key(read_key_b64)

        # Encrypt content with read key
        ciphertext, nonce = encrypt_content(content, read_key_raw)

        # Create document
        document = Document.objects.create(
            content_encrypted=ciphertext, 
            nonce=nonce,
            read_key_hash=read_key_hash,
            version=1
        )

        # Return ID and both keys
        response_serializer = DocumentCreateResponseSerializer(
            {"id": document.id, "write_key": write_key_b64, "read_key": read_key_b64}
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
            return key_b64, raw_key
        except Exception:
            raise PermissionDenied("Invalid X-Molt-Key header.")

    def _check_key_access(self, document, key_b64, raw_key, require_write=False):
        """
        Check key access level and return 'read' or 'write'.
        
        The read key is the actual encryption key.
        The write key is a wrapper that can derive the read key.
        
        Args:
            document: Document instance
            key_b64: Base64-encoded key (either write or read key)
            raw_key: Raw key bytes
            require_write: If True, raise 403 for read-only keys
            
        Returns:
            str: 'read' or 'write'
            
        Raises:
            PermissionDenied: If key is invalid or insufficient permissions
        """
        stored_hash = bytes(document.read_key_hash)
        
        # Try to derive read key from provided key (treating it as write key)
        derived_read_key_b64 = derive_read_key(key_b64)
        derived_read_key_raw = decode_key(derived_read_key_b64)
        
        # Check if derived read key matches stored hash (timing-safe)
        derived_hash = hash_key(derived_read_key_b64)
        if hmac.compare_digest(derived_hash, stored_hash):
            # The provided key is a write key! Try to decrypt with derived read key
            try:
                decrypt_content(document.content_encrypted, document.nonce, derived_read_key_raw)
                return "write"
            except (InvalidTag, Exception):
                raise PermissionDenied("Invalid encryption key.")
        
        # Not a write key. Check if provided key is the read key directly
        provided_hash = hash_key(key_b64)
        if hmac.compare_digest(provided_hash, stored_hash):
            # This is the read key
            if require_write:
                raise PermissionDenied("Read-only access. Write key required.")
            try:
                decrypt_content(document.content_encrypted, document.nonce, raw_key)
                return "read"
            except (InvalidTag, Exception):
                raise PermissionDenied("Invalid encryption key.")
        
        # Neither write nor read key
        raise PermissionDenied("Invalid encryption key.")

    def _decrypt_document(self, document, key_b64, raw_key):
        """Helper to decrypt document content.
        
        Handles both write keys (derives read key) and read keys (uses directly).
        """
        try:
            stored_hash = bytes(document.read_key_hash)
            
            # First try deriving read key (if it's a write key)
            derived_read_key_b64 = derive_read_key(key_b64)
            derived_read_key_raw = decode_key(derived_read_key_b64)
            
            # Check if this matches (timing-safe)
            derived_hash = hash_key(derived_read_key_b64)
            if hmac.compare_digest(derived_hash, stored_hash):
                # It's a write key - decrypt with derived read key
                return decrypt_content(document.content_encrypted, document.nonce, derived_read_key_raw)
            
            # Otherwise try as read key directly
            return decrypt_content(document.content_encrypted, document.nonce, raw_key)
        except (InvalidTag, Exception):
            raise PermissionDenied("Invalid encryption key.")

    def _resolve_workspace_access(self, request, document, doc_id):
        """Handle workspace-scoped document access via X-Molt-Workspace header.
        
        When X-Molt-Workspace is present, the X-Molt-Key is a workspace key.
        The server decrypts the workspace, finds the document's key in entries,
        and enforces workspace-level permissions (read-only workspace downgrades
        write access even if the stored key is a write key).
        
        Returns:
            tuple: (content, access_level) or None if no workspace header
        """
        workspace_id = request.headers.get("X-Molt-Workspace")
        if not workspace_id:
            return None
        
        # Get workspace
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            raise NotFound("Workspace not found.")
        
        ws_key_b64, ws_raw_key = self._get_key_from_header(request)
        
        # Determine workspace access level
        ws_stored_hash = bytes(workspace.read_key_hash)
        derived_ws_read_b64 = derive_read_key(ws_key_b64)
        derived_ws_read_raw = decode_key(derived_ws_read_b64)
        derived_ws_hash = hash_key(derived_ws_read_b64)
        
        if hmac.compare_digest(derived_ws_hash, ws_stored_hash):
            ws_access = "write"
            ws_content_json = decrypt_content(workspace.content_encrypted, workspace.nonce, derived_ws_read_raw)
        else:
            provided_ws_hash = hash_key(ws_key_b64)
            if hmac.compare_digest(provided_ws_hash, ws_stored_hash):
                ws_access = "read"
                ws_content_json = decrypt_content(workspace.content_encrypted, workspace.nonce, ws_raw_key)
            else:
                raise PermissionDenied("Invalid workspace key.")
        
        # Find the document in workspace entries
        workspace_data = json.loads(ws_content_json)
        doc_id_str = str(doc_id)
        entry_key_b64 = None
        for entry in workspace_data.get("entries", []):
            if str(entry.get("id")) == doc_id_str and entry.get("type") == "md":
                entry_key_b64 = entry.get("key")
                break
        
        if not entry_key_b64:
            raise NotFound("Document not found in workspace.")
        
        # Decrypt document using the key from the workspace entry
        entry_raw_key = decode_key(entry_key_b64)
        stored_doc_hash = bytes(document.read_key_hash)
        
        derived_doc_read_b64 = derive_read_key(entry_key_b64)
        derived_doc_read_raw = decode_key(derived_doc_read_b64)
        derived_doc_hash = hash_key(derived_doc_read_b64)
        
        if hmac.compare_digest(derived_doc_hash, stored_doc_hash):
            content = decrypt_content(document.content_encrypted, document.nonce, derived_doc_read_raw)
        else:
            content = decrypt_content(document.content_encrypted, document.nonce, entry_raw_key)
        
        # Workspace-level permission overrides: read-only workspace downgrades access
        access_level = ws_access
        
        return content, access_level

    def get(self, request, doc_id):
        """Read document content."""
        document = self._get_document(doc_id)
        
        # Check for workspace-scoped access
        ws_result = self._resolve_workspace_access(request, document, doc_id)
        if ws_result:
            content, access_level = ws_result
        else:
            key_b64, raw_key = self._get_key_from_header(request)
            # Check key access (read or write is fine for GET)
            self._check_key_access(document, key_b64, raw_key, require_write=False)
            content = self._decrypt_document(document, key_b64, raw_key)

        # Check for partial fetch
        lines_param = request.query_params.get("lines")
        truncated = False
        total_lines = None
        
        if lines_param:
            try:
                lines_count = int(lines_param)
                if lines_count < 1:
                    return Response(
                        {
                            "error": "bad_request",
                            "message": "lines parameter must be >= 1.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                # Split content by newlines
                content_lines = content.split("\n")
                total_lines = len(content_lines)
                
                if lines_count < total_lines:
                    content = "\n".join(content_lines[:lines_count])
                    truncated = True
            except ValueError:
                return Response(
                    {
                        "error": "bad_request",
                        "message": "lines parameter must be an integer.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

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

        # Add truncation headers if applicable
        if truncated:
            response["X-Molt-Truncated"] = "true"
            response["X-Molt-Total-Lines"] = str(total_lines)

        return response

    def put(self, request, doc_id):
        """Update document content (replace)."""
        document = self._get_document(doc_id)
        
        # Check for workspace-scoped access
        ws_result = self._resolve_workspace_access(request, document, doc_id)
        if ws_result:
            _, access_level = ws_result
            if access_level != "write":
                raise PermissionDenied("Read-only access. Write key required.")
            key_b64, raw_key = self._get_key_from_header(request)
        else:
            key_b64, raw_key = self._get_key_from_header(request)
            # Check key access - require write key
            self._check_key_access(document, key_b64, raw_key, require_write=True)

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

        # Encrypt new content with read key (derive from write key)
        read_key_b64 = derive_read_key(key_b64)
        read_key_raw = decode_key(read_key_b64)
        ciphertext, nonce = encrypt_content(new_content, read_key_raw)

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
        
        # Check for workspace-scoped access
        ws_result = self._resolve_workspace_access(request, document, doc_id)
        if ws_result:
            existing_content, access_level = ws_result
            if access_level != "write":
                raise PermissionDenied("Read-only access. Write key required.")
            key_b64, raw_key = self._get_key_from_header(request)
        else:
            key_b64, raw_key = self._get_key_from_header(request)
            # Check key access - require write key
            self._check_key_access(document, key_b64, raw_key, require_write=True)
            existing_content = self._decrypt_document(document, key_b64, raw_key)

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

        # Encrypt new content with read key (derive from write key)
        read_key_b64 = derive_read_key(key_b64)
        read_key_raw = decode_key(read_key_b64)
        ciphertext, nonce = encrypt_content(new_content, read_key_raw)

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
        
        # Check for workspace-scoped access
        ws_result = self._resolve_workspace_access(request, document, doc_id)
        if ws_result:
            _, access_level = ws_result
            if access_level != "write":
                raise PermissionDenied("Read-only access. Write key required.")
        else:
            key_b64, raw_key = self._get_key_from_header(request)
            # Check key access - require write key
            self._check_key_access(document, key_b64, raw_key, require_write=True)

        # Delete the document
        document.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class MetricsView(APIView):
    """Simple metrics endpoint showing database statistics."""

    throttle_classes = [MonitoringThrottle]

    def get(self, request):
        document_count = Document.objects.count()
        workspace_count = Workspace.objects.count()
        return Response({
            "documents": document_count,
            "workspaces": workspace_count
        }, status=status.HTTP_200_OK)


class WorkspaceCreateView(APIView):
    """Create a new encrypted workspace."""

    throttle_classes = [CreateDocumentThrottle]

    def post(self, request):
        # Parse request body
        serializer = WorkspaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        workspace_data = {
            "name": serializer.validated_data.get("name"),
            "entries": serializer.validated_data.get("entries", [])
        }
        
        # Convert to JSON string
        content = json.dumps(workspace_data)

        # Check content size
        if len(content.encode("utf-8")) > MAX_CONTENT_SIZE:
            return Response(
                {
                    "error": "payload_too_large",
                    "message": "Content exceeds 5 MB limit.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Generate write key and derive read key
        write_key_b64 = generate_key()
        read_key_b64 = derive_read_key(write_key_b64)
        read_key_raw = decode_key(read_key_b64)
        read_key_hash = hash_key(read_key_b64)

        # Encrypt content with read key
        ciphertext, nonce = encrypt_content(content, read_key_raw)

        # Create workspace
        workspace = Workspace.objects.create(
            content_encrypted=ciphertext, 
            nonce=nonce, 
            read_key_hash=read_key_hash,
            version=1
        )

        # Return ID and both keys
        response_serializer = WorkspaceCreateResponseSerializer(
            {"id": workspace.id, "write_key": write_key_b64, "read_key": read_key_b64}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class WorkspaceDetailView(APIView):
    """Read, update, or delete a workspace."""

    renderer_classes = [JSONRenderer]

    def _get_workspace(self, ws_id):
        """Helper to get workspace or raise 404."""
        try:
            return Workspace.objects.get(id=ws_id)
        except Workspace.DoesNotExist:
            raise NotFound("Workspace not found.")

    def _get_key_from_header(self, request):
        """Helper to extract and decode key from header."""
        key_b64 = request.headers.get("X-Molt-Key")
        if not key_b64:
            raise PermissionDenied("Missing X-Molt-Key header.")

        try:
            raw_key = decode_key(key_b64)
            return key_b64, raw_key
        except Exception:
            raise PermissionDenied("Invalid X-Molt-Key header.")

    def _check_key_access(self, workspace, key_b64, raw_key, require_write=False):
        """
        Check key access level and return 'read' or 'write'.
        
        The read key is the actual encryption key.
        The write key is a wrapper that can derive the read key.
        
        Args:
            workspace: Workspace instance
            key_b64: Base64-encoded key (either write or read key)
            raw_key: Raw key bytes
            require_write: If True, raise 403 for read-only keys
            
        Returns:
            str: 'read' or 'write'
            
        Raises:
            PermissionDenied: If key is invalid or insufficient permissions
        """
        stored_hash = bytes(workspace.read_key_hash)
        
        # Try to derive read key from provided key (treating it as write key)
        derived_read_key_b64 = derive_read_key(key_b64)
        derived_read_key_raw = decode_key(derived_read_key_b64)
        
        # Check if derived read key matches stored hash (timing-safe)
        derived_hash = hash_key(derived_read_key_b64)
        if hmac.compare_digest(derived_hash, stored_hash):
            # The provided key is a write key!
            try:
                decrypt_content(workspace.content_encrypted, workspace.nonce, derived_read_key_raw)
                return "write"
            except (InvalidTag, Exception):
                raise PermissionDenied("Invalid encryption key.")
        
        # Not a write key. Check if provided key is the read key directly
        provided_hash = hash_key(key_b64)
        if hmac.compare_digest(provided_hash, stored_hash):
            # This is the read key
            if require_write:
                raise PermissionDenied("Read-only access. Write key required.")
            try:
                decrypt_content(workspace.content_encrypted, workspace.nonce, raw_key)
                return "read"
            except (InvalidTag, Exception):
                raise PermissionDenied("Invalid encryption key.")
        
        # Neither write nor read key
        raise PermissionDenied("Invalid encryption key.")

    def _decrypt_workspace(self, workspace, key_b64, raw_key):
        """Helper to decrypt workspace content.
        
        Handles both write keys (derives read key) and read keys (uses directly).
        """
        try:
            stored_hash = bytes(workspace.read_key_hash)
            
            # First try deriving read key (if it's a write key)
            derived_read_key_b64 = derive_read_key(key_b64)
            derived_read_key_raw = decode_key(derived_read_key_b64)
            
            # Check if this matches (timing-safe)
            derived_hash = hash_key(derived_read_key_b64)
            if hmac.compare_digest(derived_hash, stored_hash):
                # It's a write key - decrypt with derived read key
                return decrypt_content(workspace.content_encrypted, workspace.nonce, derived_read_key_raw)
            
            # Otherwise try as read key directly
            return decrypt_content(workspace.content_encrypted, workspace.nonce, raw_key)
        except (InvalidTag, Exception):
            raise PermissionDenied("Invalid encryption key.")

    def get(self, request, ws_id):
        """Read workspace content."""
        workspace = self._get_workspace(ws_id)
        key_b64, raw_key = self._get_key_from_header(request)
        
        # Check key access (read or write is fine for GET)
        access_level = self._check_key_access(workspace, key_b64, raw_key, require_write=False)
        
        content_json = self._decrypt_workspace(workspace, key_b64, raw_key)
        workspace_data = json.loads(content_json)

        # Check for preview_lines parameter
        preview_lines = request.query_params.get("preview_lines")
        
        if preview_lines:
            try:
                lines_count = int(preview_lines)
                if lines_count < 1:
                    return Response(
                        {
                            "error": "bad_request",
                            "message": "preview_lines parameter must be >= 1.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                # Add previews to entries
                for entry in workspace_data.get("entries", []):
                    if entry.get("type") == "md":
                        # Fetch document and add preview
                        try:
                            doc = Document.objects.get(id=entry["id"])
                            entry_key_b64 = entry.get("key")
                            if entry_key_b64:
                                entry_raw_key = decode_key(entry_key_b64)
                                
                                # Try to derive read key first (if it's a write key)
                                derived_read_key_b64 = derive_read_key(entry_key_b64)
                                derived_read_key_raw = decode_key(derived_read_key_b64)
                                derived_hash = hash_key(derived_read_key_b64)
                                doc_stored_hash = bytes(doc.read_key_hash)
                                
                                # Decrypt with appropriate key (timing-safe)
                                if hmac.compare_digest(derived_hash, doc_stored_hash):
                                    # It's a write key - use derived read key
                                    doc_content = decrypt_content(doc.content_encrypted, doc.nonce, derived_read_key_raw)
                                else:
                                    # It's a read key - use directly
                                    doc_content = decrypt_content(doc.content_encrypted, doc.nonce, entry_raw_key)
                                
                                doc_lines = doc_content.split("\n")
                                entry["preview"] = "\n".join(doc_lines[:lines_count])
                        except (Document.DoesNotExist, Exception):
                            # Skip if document not found or can't decrypt
                            pass
                    elif entry.get("type") == "workspace":
                        # For sub-workspaces, try to get the name
                        try:
                            sub_ws = Workspace.objects.get(id=entry["id"])
                            entry_key_b64 = entry.get("key")
                            if entry_key_b64:
                                entry_raw_key = decode_key(entry_key_b64)
                                
                                # Try to derive read key first (if it's a write key)
                                derived_read_key_b64 = derive_read_key(entry_key_b64)
                                derived_read_key_raw = decode_key(derived_read_key_b64)
                                derived_hash = hash_key(derived_read_key_b64)
                                sub_ws_stored_hash = bytes(sub_ws.read_key_hash)
                                
                                # Decrypt with appropriate key (timing-safe)
                                if hmac.compare_digest(derived_hash, sub_ws_stored_hash):
                                    # It's a write key - use derived read key
                                    sub_ws_content = decrypt_content(sub_ws.content_encrypted, sub_ws.nonce, derived_read_key_raw)
                                else:
                                    # It's a read key - use directly
                                    sub_ws_content = decrypt_content(sub_ws.content_encrypted, sub_ws.nonce, entry_raw_key)
                                
                                sub_ws_data = json.loads(sub_ws_content)
                                entry["name"] = sub_ws_data.get("name", "")
                        except (Workspace.DoesNotExist, Exception):
                            # Skip if workspace not found or can't decrypt
                            pass
                            
            except ValueError:
                return Response(
                    {
                        "error": "bad_request",
                        "message": "preview_lines parameter must be an integer.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Update last_accessed to extend TTL on reads
        Workspace.objects.filter(id=ws_id).update(last_accessed=timezone.now())

        # Return JSON response with workspace data
        response_data = {
            "id": workspace.id,
            "name": workspace_data.get("name"),
            "entries": workspace_data.get("entries", []),
            "version": workspace.version
        }
        
        response_serializer = WorkspaceDetailSerializer(response_data)
        response = Response(response_serializer.data, status=status.HTTP_200_OK)
        response["ETag"] = f'"v{workspace.version}"'
        
        return response

    def put(self, request, ws_id):
        """Update workspace content (replace)."""
        workspace = self._get_workspace(ws_id)
        key_b64, raw_key = self._get_key_from_header(request)
        
        # Check key access - require write key
        self._check_key_access(workspace, key_b64, raw_key, require_write=True)

        # Get new content from request body
        serializer = WorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        workspace_data = {
            "name": serializer.validated_data.get("name"),
            "entries": serializer.validated_data.get("entries", [])
        }
        
        new_content = json.dumps(workspace_data)

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
            if workspace.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": workspace.version},
                    status=status.HTTP_409_CONFLICT,
                )

        # Encrypt new content with read key (derive from write key)
        read_key_b64 = derive_read_key(key_b64)
        read_key_raw = decode_key(read_key_b64)
        ciphertext, nonce = encrypt_content(new_content, read_key_raw)

        # Update workspace with atomic version check
        with transaction.atomic():
            # Re-fetch with lock
            workspace = Workspace.objects.select_for_update().get(id=ws_id)

            # Double-check version if If-Match was provided
            if if_match and workspace.version != expected_version:
                return Response(
                    {"error": "conflict", "current_version": workspace.version},
                    status=status.HTTP_409_CONFLICT,
                )

            workspace.content_encrypted = ciphertext
            workspace.nonce = nonce
            workspace.version += 1
            workspace.save()

        response_serializer = WorkspaceUpdateResponseSerializer(
            {"success": True, "version": workspace.version}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, ws_id):
        """Delete a workspace."""
        workspace = self._get_workspace(ws_id)
        key_b64, raw_key = self._get_key_from_header(request)
        
        # Check key access - require write key
        self._check_key_access(workspace, key_b64, raw_key, require_write=True)

        # Delete the workspace (does not cascade to referenced documents/workspaces)
        workspace.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
