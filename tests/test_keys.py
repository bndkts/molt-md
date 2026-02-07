"""
Tests for read/write key functionality on documents.
"""
import pytest


@pytest.mark.django_db
class TestDocumentReadWriteKeys:
    """Tests for the dual-key model on documents."""

    def test_write_key_has_full_access(self, api_client):
        """Test that write key can read and write."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Document\n\nOriginal content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Read with write key
        read_response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="application/json"
        )
        assert read_response.status_code == 200

        # Write with write key
        write_response = api_client.put(
            f"/api/v1/docs/{doc_id}",
            "Updated content",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=write_key
        )
        assert write_response.status_code == 200

    def test_read_key_can_only_read(self, api_client):
        """Test that read key can read but not write."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Document\n\nOriginal content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Read with read key (should work)
        read_response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=read_key,
            HTTP_ACCEPT="application/json"
        )
        assert read_response.status_code == 200

    def test_read_key_cannot_write(self, api_client):
        """Test that read key cannot write to document."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Document\n\nOriginal content"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Try to write with read key (should fail)
        write_response = api_client.put(
            f"/api/v1/docs/{doc_id}",
            "Updated content",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=read_key
        )
        assert write_response.status_code == 403
        assert "Read-only access" in write_response.json()["message"]

    def test_read_key_cannot_delete(self, api_client):
        """Test that read key cannot delete document."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Document"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Try to delete with read key (should fail)
        delete_response = api_client.delete(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=read_key
        )
        assert delete_response.status_code == 403

    def test_read_key_cannot_append(self, api_client):
        """Test that read key cannot append to document."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "# Test Document"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Try to append with read key (should fail)
        patch_response = api_client.patch(
            f"/api/v1/docs/{doc_id}",
            "\nAppended content",
            content_type="text/markdown",
            HTTP_X_MOLT_KEY=read_key
        )
        assert patch_response.status_code == 403
