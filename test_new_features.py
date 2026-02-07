#!/usr/bin/env python
"""
Test script for the new features: Read/Write Keys, Workspaces, and Partial Fetch
"""

import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_document_read_write_keys():
    """Test the dual-key model for documents"""
    print("\n=== Testing Document Read/Write Keys ===")
    
    # Create a document
    print("1. Creating a document...")
    response = requests.post(
        f"{BASE_URL}/docs",
        json={"content": "# Test Document\n\nThis is a test document.\n\nLine 3\nLine 4\nLine 5"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201, f"Failed to create document: {response.text}"
    data = response.json()
    doc_id = data["id"]
    write_key = data["write_key"]
    read_key = data["read_key"]
    print(f"   Document created: {doc_id}")
    print(f"   Write key: {write_key[:20]}...")
    print(f"   Read key: {read_key[:20]}...")
    
    # Read with write key
    print("\n2. Reading with write key...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": write_key, "Accept": "application/json"}
    )
    assert response.status_code == 200, f"Failed to read with write key: {response.text}"
    print(f"   ✓ Read successful with write key")
    
    # Read with read key
    print("\n3. Reading with read key...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": read_key, "Accept": "application/json"}
    )
    assert response.status_code == 200, f"Failed to read with read key: {response.text}"
    print(f"   ✓ Read successful with read key")
    
    # Try to write with read key (should fail)
    print("\n4. Attempting to write with read key (should fail)...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        data="# Modified Content",
        headers={"X-Molt-Key": read_key, "Content-Type": "text/markdown"}
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    error_data = response.json()
    assert "Read-only access" in error_data["message"], f"Unexpected error message: {error_data}"
    print(f"   ✓ Write correctly rejected with read key")
    
    # Write with write key
    print("\n5. Writing with write key...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        data="# Modified Content\n\nThis has been updated!",
        headers={"X-Molt-Key": write_key, "Content-Type": "text/markdown"}
    )
    assert response.status_code == 200, f"Failed to write with write key: {response.text}"
    print(f"   ✓ Write successful with write key")
    
    # Try to delete with read key (should fail)
    print("\n6. Attempting to delete with read key (should fail)...")
    response = requests.delete(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": read_key}
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    print(f"   ✓ Delete correctly rejected with read key")
    
    print("\n✅ All document read/write key tests passed!")
    return doc_id, write_key, read_key


def test_partial_fetch(doc_id, write_key):
    """Test partial fetch feature"""
    print("\n=== Testing Partial Fetch ===")
    
    # Create a document with multiple lines
    print("1. Creating a document with multiple lines...")
    response = requests.post(
        f"{BASE_URL}/docs",
        json={"content": "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8\nLine 9\nLine 10"},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201, f"Failed to create document: {response.text}"
    doc_id = response.json()["id"]
    doc_key = response.json()["write_key"]
    
    # Fetch first line only
    print("\n2. Fetching first line only...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}?lines=1",
        headers={"X-Molt-Key": doc_key, "Accept": "text/markdown"}
    )
    assert response.status_code == 200, f"Failed to fetch: {response.text}"
    content = response.text
    assert content == "Line 1", f"Expected 'Line 1', got '{content}'"
    assert response.headers.get("X-Molt-Truncated") == "true", "Missing truncated header"
    assert response.headers.get("X-Molt-Total-Lines") == "10", f"Expected 10 total lines, got {response.headers.get('X-Molt-Total-Lines')}"
    print(f"   ✓ First line fetched correctly")
    print(f"   ✓ Truncated header present: {response.headers.get('X-Molt-Truncated')}")
    print(f"   ✓ Total lines header: {response.headers.get('X-Molt-Total-Lines')}")
    
    # Fetch first 3 lines
    print("\n3. Fetching first 3 lines...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}?lines=3",
        headers={"X-Molt-Key": doc_key, "Accept": "text/markdown"}
    )
    assert response.status_code == 200, f"Failed to fetch: {response.text}"
    content = response.text
    assert content == "Line 1\nLine 2\nLine 3", f"Unexpected content: '{content}'"
    print(f"   ✓ First 3 lines fetched correctly")
    
    # Fetch all lines (should not be truncated)
    print("\n4. Fetching all lines...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": doc_key, "Accept": "text/markdown"}
    )
    assert response.status_code == 200, f"Failed to fetch: {response.text}"
    assert "X-Molt-Truncated" not in response.headers, "Should not be truncated"
    lines = response.text.split("\n")
    assert len(lines) == 10, f"Expected 10 lines, got {len(lines)}"
    print(f"   ✓ Full document fetched correctly")
    
    # Test invalid lines parameter
    print("\n5. Testing invalid lines parameter...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}?lines=0",
        headers={"X-Molt-Key": doc_key}
    )
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    print(f"   ✓ Invalid parameter correctly rejected")
    
    print("\n✅ All partial fetch tests passed!")


def test_workspaces():
    """Test workspace functionality"""
    print("\n=== Testing Workspaces ===")
    
    # Create some documents first
    print("1. Creating test documents...")
    doc1_response = requests.post(
        f"{BASE_URL}/docs",
        json={"content": "# Document 1\n\nFirst document content"},
        headers={"Content-Type": "application/json"}
    )
    doc1_id = doc1_response.json()["id"]
    doc1_write_key = doc1_response.json()["write_key"]
    doc1_read_key = doc1_response.json()["read_key"]
    
    doc2_response = requests.post(
        f"{BASE_URL}/docs",
        json={"content": "# Document 2\n\nSecond document content"},
        headers={"Content-Type": "application/json"}
    )
    doc2_id = doc2_response.json()["id"]
    doc2_write_key = doc2_response.json()["write_key"]
    doc2_read_key = doc2_response.json()["read_key"]
    print(f"   Documents created: {doc1_id}, {doc2_id}")
    
    # Create a workspace
    print("\n2. Creating a workspace...")
    workspace_data = {
        "name": "Test Workspace",
        "entries": [
            {"type": "md", "id": doc1_id, "key": doc1_write_key},
            {"type": "md", "id": doc2_id, "key": doc2_write_key}
        ]
    }
    response = requests.post(
        f"{BASE_URL}/workspaces",
        json=workspace_data,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201, f"Failed to create workspace: {response.text}"
    ws_data = response.json()
    ws_id = ws_data["id"]
    ws_write_key = ws_data["write_key"]
    ws_read_key = ws_data["read_key"]
    print(f"   Workspace created: {ws_id}")
    print(f"   Write key: {ws_write_key[:20]}...")
    print(f"   Read key: {ws_read_key[:20]}...")
    
    # Read workspace with write key
    print("\n3. Reading workspace with write key...")
    response = requests.get(
        f"{BASE_URL}/workspaces/{ws_id}",
        headers={"X-Molt-Key": ws_write_key}
    )
    assert response.status_code == 200, f"Failed to read workspace: {response.text}"
    data = response.json()
    assert data["name"] == "Test Workspace", f"Unexpected name: {data['name']}"
    assert len(data["entries"]) == 2, f"Expected 2 entries, got {len(data['entries'])}"
    print(f"   ✓ Workspace read successfully")
    print(f"   Name: {data['name']}")
    print(f"   Entries: {len(data['entries'])}")
    
    # Read workspace with read key
    print("\n4. Reading workspace with read key...")
    response = requests.get(
        f"{BASE_URL}/workspaces/{ws_id}",
        headers={"X-Molt-Key": ws_read_key}
    )
    assert response.status_code == 200, f"Failed to read workspace with read key: {response.text}"
    print(f"   ✓ Workspace read successful with read key")
    
    # Try to update with read key (should fail)
    print("\n5. Attempting to update with read key (should fail)...")
    response = requests.put(
        f"{BASE_URL}/workspaces/{ws_id}",
        json={"name": "Modified", "entries": []},
        headers={"X-Molt-Key": ws_read_key, "Content-Type": "application/json"}
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    print(f"   ✓ Update correctly rejected with read key")
    
    # Update with write key
    print("\n6. Updating workspace with write key...")
    updated_data = {
        "name": "Updated Workspace",
        "entries": [
            {"type": "md", "id": doc1_id, "key": doc1_write_key}
        ]
    }
    response = requests.put(
        f"{BASE_URL}/workspaces/{ws_id}",
        json=updated_data,
        headers={"X-Molt-Key": ws_write_key, "Content-Type": "application/json"}
    )
    assert response.status_code == 200, f"Failed to update workspace: {response.text}"
    print(f"   ✓ Workspace updated successfully")
    
    # Test workspace with preview
    print("\n7. Testing workspace with preview_lines...")
    response = requests.get(
        f"{BASE_URL}/workspaces/{ws_id}?preview_lines=1",
        headers={"X-Molt-Key": ws_write_key}
    )
    assert response.status_code == 200, f"Failed to fetch with preview: {response.text}"
    data = response.json()
    assert "preview" in data["entries"][0], "Preview field missing"
    print(f"   ✓ Preview fetched successfully")
    print(f"   Preview: {data['entries'][0]['preview']}")
    
    # Test nested workspace
    print("\n8. Creating nested workspace...")
    nested_workspace_data = {
        "name": "Parent Workspace",
        "entries": [
            {"type": "workspace", "id": ws_id, "key": ws_write_key},
            {"type": "md", "id": doc2_id, "key": doc2_write_key}
        ]
    }
    response = requests.post(
        f"{BASE_URL}/workspaces",
        json=nested_workspace_data,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201, f"Failed to create nested workspace: {response.text}"
    parent_ws_id = response.json()["id"]
    parent_ws_key = response.json()["write_key"]
    print(f"   Parent workspace created: {parent_ws_id}")
    
    # Read parent workspace
    print("\n9. Reading parent workspace...")
    response = requests.get(
        f"{BASE_URL}/workspaces/{parent_ws_id}",
        headers={"X-Molt-Key": parent_ws_key}
    )
    assert response.status_code == 200, f"Failed to read parent workspace: {response.text}"
    data = response.json()
    assert len(data["entries"]) == 2, f"Expected 2 entries, got {len(data['entries'])}"
    workspace_entry = next((e for e in data["entries"] if e["type"] == "workspace"), None)
    assert workspace_entry is not None, "Workspace entry not found"
    print(f"   ✓ Parent workspace read successfully")
    
    # Test delete with write key
    print("\n10. Deleting workspace with write key...")
    response = requests.delete(
        f"{BASE_URL}/workspaces/{ws_id}",
        headers={"X-Molt-Key": ws_write_key}
    )
    assert response.status_code == 204, f"Failed to delete workspace: {response.text}"
    print(f"   ✓ Workspace deleted successfully")
    
    # Verify deletion
    print("\n11. Verifying deletion...")
    response = requests.get(
        f"{BASE_URL}/workspaces/{ws_id}",
        headers={"X-Molt-Key": ws_write_key}
    )
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    print(f"   ✓ Workspace correctly deleted")
    
    print("\n✅ All workspace tests passed!")
    return doc1_id, doc1_write_key, doc1_read_key, doc2_id, doc2_write_key, doc2_read_key


def test_workspace_scoped_access():
    """Test workspace-scoped document access (X-Molt-Workspace header)"""
    print("\n=== Testing Workspace-Scoped Document Access ===")
    
    # Create a document
    print("1. Creating a test document...")
    response = requests.post(
        f"{BASE_URL}/docs",
        json={"content": "# Scoped Doc\n\nContent accessible through workspace."},
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201
    doc_id = response.json()["id"]
    doc_write_key = response.json()["write_key"]
    doc_read_key = response.json()["read_key"]
    print(f"   Document created: {doc_id}")
    
    # Create a workspace containing the document (with write key)
    print("\n2. Creating a workspace with the document...")
    response = requests.post(
        f"{BASE_URL}/workspaces",
        json={
            "name": "Scoped Workspace",
            "entries": [
                {"type": "md", "id": doc_id, "key": doc_write_key}
            ]
        },
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 201
    ws_id = response.json()["id"]
    ws_write_key = response.json()["write_key"]
    ws_read_key = response.json()["read_key"]
    print(f"   Workspace created: {ws_id}")
    
    # Read document through workspace with write key
    print("\n3. Reading document through workspace with write key...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": ws_write_key,
            "X-Molt-Workspace": ws_id,
            "Accept": "application/json"
        }
    )
    assert response.status_code == 200, f"Failed: {response.text}"
    assert "Scoped Doc" in response.json()["content"]
    print(f"   ✓ Read through workspace with write key works")
    
    # Read document through workspace with read key
    print("\n4. Reading document through workspace with read key...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": ws_read_key,
            "X-Molt-Workspace": ws_id,
            "Accept": "application/json"
        }
    )
    assert response.status_code == 200, f"Failed: {response.text}"
    print(f"   ✓ Read through workspace with read key works")
    
    # Partial fetch through workspace
    print("\n5. Partial fetch through workspace...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}?lines=1",
        headers={
            "X-Molt-Key": ws_write_key,
            "X-Molt-Workspace": ws_id,
            "Accept": "text/markdown"
        }
    )
    assert response.status_code == 200, f"Failed: {response.text}"
    assert response.text == "# Scoped Doc", f"Unexpected content: {response.text}"
    assert response.headers.get("X-Molt-Truncated") == "true"
    print(f"   ✓ Partial fetch through workspace works")
    
    # Try to write through workspace with READ key (should fail - permission downgrade)
    print("\n6. Attempting to write through workspace with read key (should fail)...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        data="# Should Not Work",
        headers={
            "X-Molt-Key": ws_read_key,
            "X-Molt-Workspace": ws_id,
            "Content-Type": "text/markdown"
        }
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    print(f"   ✓ Write correctly rejected with workspace read key")
    
    # Write through workspace with WRITE key, then verify doc is still readable with its own key
    print("\n6b. Writing through workspace with write key, then reading with doc key...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        data="# Updated Through Workspace\n\nModified via workspace write key.",
        headers={
            "X-Molt-Key": ws_write_key,
            "X-Molt-Workspace": ws_id,
            "Content-Type": "text/markdown"
        }
    )
    assert response.status_code == 200, f"Failed to write through workspace: {response.text}"
    # Now read with the document's own write key (must still work!)
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": doc_write_key, "Accept": "application/json"}
    )
    assert response.status_code == 200, f"Doc unreadable after workspace PUT: {response.text}"
    assert "Updated Through Workspace" in response.json()["content"]
    # Also verify with the document's read key
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": doc_read_key, "Accept": "application/json"}
    )
    assert response.status_code == 200, f"Doc unreadable with read key after workspace PUT: {response.text}"
    print(f"   ✓ Write through workspace preserves document key access")
    
    # Try to delete through workspace with read key (should fail)
    print("\n7. Attempting to delete through workspace with read key (should fail)...")
    response = requests.delete(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": ws_read_key,
            "X-Molt-Workspace": ws_id
        }
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    print(f"   ✓ Delete correctly rejected with workspace read key")
    
    # Try to access non-existent doc through workspace
    print("\n8. Accessing non-existent doc in workspace (should fail)...")
    response = requests.get(
        f"{BASE_URL}/docs/00000000-0000-0000-0000-000000000000",
        headers={
            "X-Molt-Key": ws_write_key,
            "X-Molt-Workspace": ws_id,
            "Accept": "application/json"
        }
    )
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    print(f"   ✓ Non-existent doc correctly returns 404")
    
    # Cleanup
    requests.delete(f"{BASE_URL}/workspaces/{ws_id}", headers={"X-Molt-Key": ws_write_key})
    requests.delete(f"{BASE_URL}/docs/{doc_id}", headers={"X-Molt-Key": doc_write_key})
    
    print("\n✅ All workspace-scoped access tests passed!")


def test_metrics():
    """Test metrics endpoint"""
    print("\n=== Testing Metrics ===")
    
    response = requests.get(f"{BASE_URL}/metrics")
    assert response.status_code == 200, f"Failed to fetch metrics: {response.text}"
    data = response.json()
    assert "documents" in data, "documents count missing"
    assert "workspaces" in data, "workspaces count missing"
    print(f"   Documents: {data['documents']}")
    print(f"   Workspaces: {data['workspaces']}")
    print("\n✅ Metrics test passed!")


if __name__ == "__main__":
    try:
        print("Starting feature tests...")
        print("=" * 50)
        
        # Test document read/write keys
        doc_id, write_key, read_key = test_document_read_write_keys()
        
        # Test partial fetch
        test_partial_fetch(doc_id, write_key)
        
        # Test workspaces
        test_workspaces()
        
        # Test workspace-scoped document access
        test_workspace_scoped_access()
        
        # Test metrics
        test_metrics()
        
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED! 🎉")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
