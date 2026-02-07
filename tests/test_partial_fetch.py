"""
Tests for partial document fetch functionality.
"""
import pytest


@pytest.mark.django_db
class TestPartialFetch:
    """Tests for fetching partial document content."""

    def test_fetch_first_line_only(self, api_client):
        """Test fetching only the first line of a document."""
        # Create document with multiple lines
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Fetch first line only
        response = api_client.get(
            f"/api/v1/docs/{doc_id}?lines=1",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="text/markdown"
        )
        assert response.status_code == 200
        assert response.content.decode() == "Line 1"
        assert response["X-Molt-Truncated"] == "true"
        assert response["X-Molt-Total-Lines"] == "5"

    def test_fetch_multiple_lines(self, api_client):
        """Test fetching first N lines of a document."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Fetch first 3 lines
        response = api_client.get(
            f"/api/v1/docs/{doc_id}?lines=3",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="text/markdown"
        )
        assert response.status_code == 200
        assert response.content.decode() == "Line 1\nLine 2\nLine 3"
        assert response["X-Molt-Truncated"] == "true"
        assert response["X-Molt-Total-Lines"] == "5"

    def test_fetch_all_lines_not_truncated(self, api_client):
        """Test that fetching full document doesn't add truncation headers."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Line 1\nLine 2\nLine 3"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Fetch without lines parameter
        response = api_client.get(
            f"/api/v1/docs/{doc_id}",
            HTTP_X_MOLT_KEY=write_key,
            HTTP_ACCEPT="text/markdown"
        )
        assert response.status_code == 200
        assert "X-Molt-Truncated" not in response
        assert response.content.decode() == "Line 1\nLine 2\nLine 3"

    def test_invalid_lines_parameter(self, api_client):
        """Test that invalid lines parameter returns 400."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Line 1\nLine 2"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Try with 0 lines
        response = api_client.get(
            f"/api/v1/docs/{doc_id}?lines=0",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 400

        # Try with negative lines
        response = api_client.get(
            f"/api/v1/docs/{doc_id}?lines=-1",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 400

    def test_partial_fetch_with_read_key(self, api_client):
        """Test that partial fetch works with read key."""
        # Create document
        create_response = api_client.post(
            "/api/v1/docs",
            {"content": "Line 1\nLine 2\nLine 3"},
            format="json"
        )
        doc_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Fetch with read key
        response = api_client.get(
            f"/api/v1/docs/{doc_id}?lines=1",
            HTTP_X_MOLT_KEY=read_key,
            HTTP_ACCEPT="text/markdown"
        )
        assert response.status_code == 200
        assert response.content.decode() == "Line 1"
