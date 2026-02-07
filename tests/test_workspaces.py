"""
Tests for workspace functionality.
"""
import pytest


@pytest.mark.django_db
class TestWorkspaces:
    """Tests for workspace CRUD operations."""

    def test_create_workspace(self, api_client):
        """Test creating a new workspace."""
        # Create some documents first
        doc1 = api_client.post(
            "/api/v1/docs",
            {"content": "# Document 1"},
            format="json"
        ).json()
        doc2 = api_client.post(
            "/api/v1/docs",
            {"content": "# Document 2"},
            format="json"
        ).json()

        # Create workspace
        workspace_data = {
            "name": "Test Workspace",
            "entries": [
                {"type": "md", "id": doc1["id"], "key": doc1["write_key"]},
                {"type": "md", "id": doc2["id"], "key": doc2["write_key"]}
            ]
        }
        response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "write_key" in data
        assert "read_key" in data

    def test_read_workspace_with_write_key(self, api_client):
        """Test reading a workspace with write key."""
        # Create documents
        doc1 = api_client.post(
            "/api/v1/docs",
            {"content": "# Doc 1"},
            format="json"
        ).json()

        # Create workspace
        workspace_data = {
            "name": "Test Workspace",
            "entries": [
                {"type": "md", "id": doc1["id"], "key": doc1["write_key"]}
            ]
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Read workspace
        response = api_client.get(
            f"/api/v1/workspaces/{ws_id}",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Workspace"
        assert len(data["entries"]) == 1

    def test_read_workspace_with_read_key(self, api_client):
        """Test reading a workspace with read key."""
        # Create documents
        doc1 = api_client.post(
            "/api/v1/docs",
            {"content": "# Doc 1"},
            format="json"
        ).json()

        # Create workspace
        workspace_data = {
            "name": "Test Workspace",
            "entries": [
                {"type": "md", "id": doc1["id"], "key": doc1["write_key"]}
            ]
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Read workspace with read key
        response = api_client.get(
            f"/api/v1/workspaces/{ws_id}",
            HTTP_X_MOLT_KEY=read_key
        )
        assert response.status_code == 200

    def test_update_workspace_with_write_key(self, api_client):
        """Test updating a workspace with write key."""
        # Create workspace
        workspace_data = {
            "name": "Original Name",
            "entries": []
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Update workspace
        update_data = {
            "name": "Updated Name",
            "entries": []
        }
        response = api_client.put(
            f"/api/v1/workspaces/{ws_id}",
            update_data,
            format="json",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 200

    def test_read_key_cannot_update_workspace(self, api_client):
        """Test that read key cannot update workspace."""
        # Create workspace
        workspace_data = {
            "name": "Original Name",
            "entries": []
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Try to update with read key
        update_data = {
            "name": "Updated Name",
            "entries": []
        }
        response = api_client.put(
            f"/api/v1/workspaces/{ws_id}",
            update_data,
            format="json",
            HTTP_X_MOLT_KEY=read_key
        )
        assert response.status_code == 403

    def test_delete_workspace(self, api_client):
        """Test deleting a workspace."""
        # Create workspace
        workspace_data = {
            "name": "To Delete",
            "entries": []
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        write_key = create_response.json()["write_key"]

        # Delete workspace
        response = api_client.delete(
            f"/api/v1/workspaces/{ws_id}",
            HTTP_X_MOLT_KEY=write_key
        )
        assert response.status_code == 204

        # Verify it's gone
        get_response = api_client.get(
            f"/api/v1/workspaces/{ws_id}",
            HTTP_X_MOLT_KEY=write_key
        )
        assert get_response.status_code == 404

    def test_read_key_cannot_delete_workspace(self, api_client):
        """Test that read key cannot delete workspace."""
        # Create workspace
        workspace_data = {
            "name": "Test Workspace",
            "entries": []
        }
        create_response = api_client.post(
            "/api/v1/workspaces",
            workspace_data,
            format="json"
        )
        ws_id = create_response.json()["id"]
        read_key = create_response.json()["read_key"]

        # Try to delete with read key
        response = api_client.delete(
            f"/api/v1/workspaces/{ws_id}",
            HTTP_X_MOLT_KEY=read_key
        )
        assert response.status_code == 403
