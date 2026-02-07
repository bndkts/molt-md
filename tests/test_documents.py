"""
Tests for basic API functionality including health check and document lifecycle.
"""
import pytest


@pytest.mark.django_db
class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, api_client):
        """Test health check endpoint returns 200 OK."""
        response = api_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.django_db
class TestDocumentLifecycle:
    """Tests for document CRUD operations."""

    def test_create_document(self, api_client):
        """Test creating a new document."""
        response = api_client.post(
            "/api/v1/docs",
            {"content": "# Hello World\nThis is a test document."},
            format="json"
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "write_key" in data
        assert "read_key" in data

    def test_create_empty_document(self, api_client):
        """Test creating an empty document."""
        response = api_client.post("/api/v1/docs", {}, format="json")
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "write_key" in data

    def test_read_document_with_write_key(self, api_client):
        """Test reading a document with write key."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Read with write key
        response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="application/json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "# Test Content"
        assert data["version"] == 1

    def test_read_document_as_markdown(self, api_client):
        """Test reading a document with text/markdown accept header."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Content\nLine 2"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Read as markdown
        response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="text/markdown"
        )
        assert response.status_code == 200
        assert response.content.decode() == "# Test Content\nLine 2"
        assert response["Content-Type"].startswith("text/markdown")

    def test_update_document(self, api_client):
        """Test updating a document with PUT."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Original content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Update document
        response = api_client.put(
            f"/api/v1/docs/{doc_id}",
            "Updated content",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_IF_MATCH='"v1"'
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["version"] == 2

    def test_version_conflict(self, api_client):
        """Test that version conflicts are detected."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Original"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Update once
        api_client.put(
            f"/api/v1/docs/{doc_id}",
            "First update",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_IF_MATCH='"v1"'
        )

        # Try to update with old version
        response = api_client.put(
            f"/api/v1/docs/{doc_id}",
            "Second update",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_IF_MATCH='"v1"'  # Old version
        )
        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "conflict"
        assert data["current_version"] == 2

    def test_append_to_document(self, api_client):
        """Test appending content to a document with PATCH."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Original content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Append content
        response = api_client.patch(
            f"/api/v1/docs/{doc_id}",
            "\nAppended content",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_IF_MATCH='"v1"'
        )
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2

        # Verify content (append adds newline separator if not present)
        read_response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="text/markdown"
        )
        content = read_response.content.decode()
        assert "Original content" in content
        assert "Appended content" in content

    def test_wrong_key_rejected(self, api_client):
        """Test that wrong keys are rejected."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Secret content"},
            format="json"
        )
        doc_id = create_response.json()["id"]

        # Try to read with wrong key
        response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY="wrong_key_123"
        )
        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    def test_delete_document(self, api_client):
        """Test deleting a document."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "To be deleted"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Delete document
        response = api_client.delete(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 204

        # Verify it's gone
        read_response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key
        )
        assert read_response.status_code == 404
        assert read_response.json()["error"] == "not_found"
