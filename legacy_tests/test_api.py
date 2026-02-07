"""
Simple test script to verify the molt-md API is working.
Run this after starting the development server.
"""

import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"


def test_health_check():
    """Test health check endpoint."""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("✓ Health check passed")


def test_document_lifecycle():
    """Test full document lifecycle: create, read, update, delete."""

    # 1. Create document
    print("\nTesting document creation...")
    response = requests.post(
        f"{BASE_URL}/docs", json={"content": "# Hello World\nThis is a test document."}
    )
    assert response.status_code == 201
    data = response.json()
    doc_id = data["id"]
    key = data["key"]
    print(f"✓ Created document {doc_id}")

    # 2. Read document (JSON)
    print("\nTesting document read (JSON)...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": key, "Accept": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "# Hello World\nThis is a test document."
    assert data["version"] == 1
    etag = response.headers.get("ETag")
    assert etag == '"v1"'
    print(f"✓ Read document (version {data['version']})")

    # 3. Read document (markdown)
    print("\nTesting document read (markdown)...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": key, "Accept": "text/markdown"},
    )
    assert response.status_code == 200, (
        f"Status code: {response.status_code}, Body: {response.text}"
    )
    assert response.text == "# Hello World\nThis is a test document.", (
        f"Got: {repr(response.text)}"
    )
    content_type = response.headers.get("Content-Type")
    assert content_type.startswith("text/markdown"), f"Got Content-Type: {content_type}"
    print("✓ Read document as markdown")

    # 4. Update document
    print("\nTesting document update...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": key,
            "Content-Type": "text/markdown",
            "If-Match": '"v1"',
        },
        data="# Updated Title\nThis content has been updated.",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["version"] == 2
    print(f"✓ Updated document (version {data['version']})")

    # 5. Test version conflict
    print("\nTesting version conflict...")
    response = requests.put(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": key,
            "Content-Type": "text/markdown",
            "If-Match": '"v1"',  # Old version
        },
        data="This should conflict",
    )
    assert response.status_code == 409
    data = response.json()
    assert data["error"] == "conflict"
    assert data["current_version"] == 2
    print("✓ Version conflict detected correctly")

    # 6. Append to document
    print("\nTesting document append...")
    response = requests.patch(
        f"{BASE_URL}/docs/{doc_id}",
        headers={
            "X-Molt-Key": key,
            "Content-Type": "text/markdown",
            "If-Match": '"v2"',
        },
        data="## Appended Section\nThis was appended.",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 3
    print(f"✓ Appended to document (version {data['version']})")

    # 7. Verify appended content
    print("\nVerifying appended content...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}",
        headers={"X-Molt-Key": key, "Accept": "text/markdown"},
    )
    assert response.status_code == 200
    expected = "# Updated Title\nThis content has been updated.\n## Appended Section\nThis was appended."
    assert response.text == expected
    print("✓ Append successful")

    # 8. Test wrong key
    print("\nTesting wrong key...")
    response = requests.get(
        f"{BASE_URL}/docs/{doc_id}", headers={"X-Molt-Key": "wrong_key_123"}
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "forbidden"
    print("✓ Wrong key rejected")

    # 9. Delete document
    print("\nTesting document deletion...")
    response = requests.delete(f"{BASE_URL}/docs/{doc_id}", headers={"X-Molt-Key": key})
    assert response.status_code == 204
    print("✓ Deleted document")

    # 10. Verify document is gone
    print("\nVerifying document is deleted...")
    response = requests.get(f"{BASE_URL}/docs/{doc_id}", headers={"X-Molt-Key": key})
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "not_found"
    print("✓ Document not found (as expected)")


def test_empty_document():
    """Test creating an empty document."""
    print("\nTesting empty document creation...")
    response = requests.post(f"{BASE_URL}/docs", json={})
    assert response.status_code == 201, (
        f"Status: {response.status_code}, Body: {response.text}"
    )
    data = response.json()
    doc_id = data["id"]
    key = data["key"]
    print(f"✓ Created empty document {doc_id}")

    # Read it back
    response = requests.get(f"{BASE_URL}/docs/{doc_id}", headers={"X-Molt-Key": key})
    assert response.status_code == 200, (
        f"Status: {response.status_code}, Body: {response.text}"
    )
    assert response.text == "", f"Got: {repr(response.text)}"
    print("✓ Empty document read successfully")


if __name__ == "__main__":
    try:
        test_health_check()
        test_document_lifecycle()
        test_empty_document()
        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print("\n✗ Could not connect to server. Is it running?")
        print("Start it with: python manage.py runserver")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
