# molt-md API Documentation

Base URL: `http://localhost:8000/api/v1` (or `http://localhost:8000/api/v1` for development)

## Authentication

molt-md uses **key-based authentication** without user accounts. When you create a document or workspace, you receive two unique encryption keys:

- **Write key** — full read + write access
- **Read key** — read-only access

Include the appropriate key in the `X-Molt-Key` header for all operations.

**Important:** Both keys are shown only once during creation and are never stored on the server. If you lose the keys, the document cannot be recovered.

### Read/Write Key Model

Every document and workspace uses a dual-key model:

- On creation, the server generates a **write key** (32-byte, Base64 URL-safe)
- The **read key** is derived from the write key using `HMAC-SHA256(write_key, "molt-read")`
- The server stores only a hash of the read key for verification — neither key is stored
- On each request, the server determines which key was provided and grants the appropriate access level

**Permission enforcement:**

| Key Type | `GET` | `PUT` / `PATCH` / `DELETE` |
|----------|-------|----------------------------|
| Write key | ✅ Allowed | ✅ Allowed |
| Read key | ✅ Allowed | ❌ `403 Forbidden` |

## Encryption

All document and workspace content is encrypted at rest using AES-256-GCM authenticated encryption. The server never stores decryption keys. This ensures true end-to-end encryption where only the key holder can access the content.

## Rate Limiting

- **Document/Workspace Creation:** 10 requests per minute per IP
- **All Other Operations:** 60 requests per minute per IP

When rate limited, you'll receive a `429 Too Many Requests` response with a `Retry-After` header.

## Versioning & Concurrency

Documents and workspaces use optimistic concurrency control:
- Each write operation increments the `version` number
- The `ETag` header in responses contains the current version (e.g., `"v5"`)
- Use the `If-Match` header with your write operations to prevent conflicts
- If the version doesn't match, you'll receive a `409 Conflict` response

## Document & Workspace Lifecycle

Documents and workspaces automatically expire after **30 days of inactivity**. The `last_accessed` timestamp is updated on every read or write operation.

## Content Limits

Maximum content size: **5 MB** (5,242,880 bytes)

---

## Endpoints

### Health Check

Check if the API is available.

**Endpoint:** `GET /health`

**Authentication:** None required

**Response:** `200 OK`

```json
{
  "status": "ok"
}
```

---

### Metrics

Get database statistics.

**Endpoint:** `GET /metrics`

**Authentication:** None required

**Response:** `200 OK`

```json
{
  "documents": 42,
  "workspaces": 5
}
```

---

## Document Endpoints

### Create Document

Create a new encrypted document. The server generates write and read keys and returns them along with the document ID. **Save these keys – they are shown only once!**

**Endpoint:** `POST /docs`

**Authentication:** None required

**Rate Limit:** 10 requests/minute

**Request Body (optional):**

```json
{
  "content": "# My Document\n\nInitial content here."
}
```

If no body is provided or `content` is empty, an empty document is created.

**Response:** `201 Created`

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "write_key": "base64encodedwritekey...",
  "read_key": "base64encodedreadkey..."
}
```

**Response Fields:**
- `id` (UUID): Unique document identifier
- `write_key` (string): Base64 URL-safe encoded write key — full read + write access (**save this!**)
- `read_key` (string): Base64 URL-safe encoded read key — read-only access (share this for read-only collaborators)

**Error Responses:**
- `413 Payload Too Large`: Content exceeds 5 MB
- `429 Too Many Requests`: Rate limit exceeded

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/docs \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello World"}'
```

---

### Read Document

Retrieve a document's decrypted content. Supports both JSON and plain markdown formats.

**Endpoint:** `GET /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key or read key)

**Headers:**
- `X-Molt-Key` (required): Your write key or read key
- `Accept` (optional): `application/json` or `text/markdown` (default)

**Query Parameters:**
- `lines` (optional, integer, minimum 1): Return only the first N lines of the document. If omitted, the full document is returned.

**Response:** `200 OK`

**As JSON:**

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "content": "# Hello World\n\nDocument content here.",
  "version": 5
}
```

**As Markdown:**

```
# Hello World

Document content here.
```

**Response Headers:**
- `ETag`: Current version (e.g., `"v5"`)
- `Content-Type`: `application/json` or `text/markdown`
- `X-Molt-Truncated`: `"true"` if the document was truncated by the `lines` parameter
- `X-Molt-Total-Lines`: Total number of lines in the full document (only present when truncated)

**Error Responses:**
- `400 Bad Request`: Invalid `lines` parameter (0, negative, or non-integer)
- `403 Forbidden`: Invalid or missing encryption key
- `404 Not Found`: Document doesn't exist

**Example (JSON):**

```bash
curl -X GET http://localhost:8000/api/v1/docs/{id} \
  -H "X-Molt-Key: your_write_or_read_key" \
  -H "Accept: application/json"
```

**Example (Partial fetch — first line only):**

```bash
curl -X GET "http://localhost:8000/api/v1/docs/{id}?lines=1" \
  -H "X-Molt-Key: your_key" \
  -H "Accept: text/markdown"
```

---

### Workspace-Scoped Document Access

Documents can be accessed through a workspace by including the `X-Molt-Workspace` header. In this mode, the `X-Molt-Key` contains the **workspace key** (not the document key). The server decrypts the workspace, retrieves the document's key from the workspace entries, and enforces workspace-level permissions.

**Headers:**
- `X-Molt-Key` (required): Your workspace write key or read key
- `X-Molt-Workspace` (required): The workspace UUID containing the document

**Permission hierarchy:**
- Write key for workspace → write access to documents inside (regardless of stored file-level key)
- Read key for workspace → read-only access to documents inside (even if stored key is a write key)

This applies to `GET`, `PUT`, `PATCH`, and `DELETE` operations on documents.

**Example:**

```bash
# Read a document through a workspace
curl -X GET http://localhost:8000/api/v1/docs/{doc_id} \
  -H "X-Molt-Key: workspace_key_here" \
  -H "X-Molt-Workspace: workspace_uuid_here"
```

**Example (Partial fetch through workspace):**

```bash
# Get first line of a document for a table of contents
curl -X GET "http://localhost:8000/api/v1/docs/{doc_id}?lines=1" \
  -H "X-Molt-Key: workspace_key_here" \
  -H "X-Molt-Workspace: workspace_uuid_here"
```

---

### Update Document

Replace a document's entire content with new content. **Requires write key.**

**Endpoint:** `PUT /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key only)

**Headers:**
- `X-Molt-Key` (required): Your **write key**
- `Content-Type`: `text/markdown`
- `If-Match` (optional but recommended): Current version (e.g., `"v5"`)

**Request Body:**

Raw markdown content (not JSON).

```
# Updated Title

This is the new content.
```

**Response:** `200 OK`

```json
{
  "success": true,
  "version": 6
}
```

**Error Responses:**
- `400 Bad Request`: Invalid Content-Type or malformed If-Match header
- `403 Forbidden`: Invalid key, or read key used (write key required)
- `404 Not Found`: Document doesn't exist
- `409 Conflict`: Version mismatch (someone else updated the document)
- `413 Payload Too Large`: Content exceeds 5 MB

**Conflict Response:** `409 Conflict`

```json
{
  "error": "conflict",
  "current_version": 6
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/v1/docs/{id} \
  -H "X-Molt-Key: your_write_key" \
  -H "Content-Type: text/markdown" \
  -H "If-Match: \"v5\"" \
  --data "# Updated Content"
```

---

### Append to Document

Append new content to the end of a document (separated by a newline). **Requires write key.**

**Endpoint:** `PATCH /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key only)

**Headers:**
- `X-Molt-Key` (required): Your **write key**
- `Content-Type`: `text/markdown`
- `If-Match` (optional but recommended): Current version (e.g., `"v5"`)

**Request Body:**

Raw markdown content to append (not JSON).

**Response:** `200 OK`

```json
{
  "success": true,
  "version": 6
}
```

**Behavior:**
- Existing content and new content are joined with `\n`
- The combined content must not exceed 5 MB

**Example:**

```bash
curl -X PATCH http://localhost:8000/api/v1/docs/{id} \
  -H "X-Molt-Key: your_write_key" \
  -H "Content-Type: text/markdown" \
  -H "If-Match: \"v5\"" \
  --data "## Appended Section"
```

---

### Delete Document

Permanently delete a document. This action cannot be undone. **Requires write key.**

**Endpoint:** `DELETE /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key only)

**Headers:**
- `X-Molt-Key` (required): Your **write key**

**Response:** `204 No Content`

**Error Responses:**
- `403 Forbidden`: Invalid key, or read key used (write key required)
- `404 Not Found`: Document doesn't exist

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/v1/docs/{id} \
  -H "X-Molt-Key: your_write_key"
```

---

## Workspace Endpoints

Workspaces are encrypted JSON objects that bundle multiple documents (and other workspaces) together. They use the same dual-key model and encryption as documents.

### Create Workspace

Create a new encrypted workspace.

**Endpoint:** `POST /workspaces`

**Authentication:** None required

**Rate Limit:** 10 requests/minute

**Request Body:**

```json
{
  "name": "Project Alpha",
  "entries": [
    { "type": "md", "id": "doc-uuid-1", "key": "base64key..." },
    { "type": "md", "id": "doc-uuid-2", "key": "base64key..." },
    { "type": "workspace", "id": "ws-uuid-3", "key": "base64key..." }
  ]
}
```

**Fields:**
- `name` (string, required): Human-readable workspace name
- `entries` (array, optional): List of entries. Each entry has:
  - `type`: `"md"` for documents, `"workspace"` for sub-workspaces
  - `id`: UUID of the referenced document or workspace
  - `key`: The write key or read key for the referenced item

**Response:** `201 Created`

```json
{
  "id": "ws-uuid",
  "write_key": "base64encodedwritekey...",
  "read_key": "base64encodedreadkey..."
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "entries": []}'
```

---

### Read Workspace

Retrieve a workspace's decrypted content (name + entries).

**Endpoint:** `GET /workspaces/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key or read key)

**Query Parameters:**
- `preview_lines` (optional, integer, minimum 1): For each `"md"` entry, include a `preview` field with the first N lines. For `"workspace"` entries, include the sub-workspace `name`.

**Response:** `200 OK`

```json
{
  "id": "ws-uuid",
  "name": "Project Alpha",
  "entries": [
    { "type": "md", "id": "uuid-1", "key": "base64key..." },
    { "type": "md", "id": "uuid-2", "key": "base64key..." }
  ],
  "version": 1
}
```

**With `preview_lines=1`:**

```json
{
  "id": "ws-uuid",
  "name": "Project Alpha",
  "entries": [
    { "type": "md", "id": "uuid-1", "key": "...", "preview": "# Meeting Notes" },
    { "type": "workspace", "id": "uuid-3", "key": "...", "name": "Archive" }
  ],
  "version": 1
}
```

**Response Headers:**
- `ETag`: Current version (e.g., `"v1"`)

**Example:**

```bash
curl -X GET "http://localhost:8000/api/v1/workspaces/{id}?preview_lines=1" \
  -H "X-Molt-Key: your_key"
```

---

### Update Workspace

Replace a workspace's entire content. **Requires write key.**

**Endpoint:** `PUT /workspaces/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key only)

**Headers:**
- `X-Molt-Key` (required): Your **write key**
- `Content-Type`: `application/json`
- `If-Match` (optional but recommended): Current version

**Request Body:**

```json
{
  "name": "Updated Project Alpha",
  "entries": [
    { "type": "md", "id": "doc-uuid", "key": "base64key..." }
  ]
}
```

**Response:** `200 OK`

```json
{
  "success": true,
  "version": 2
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/v1/workspaces/{id} \
  -H "X-Molt-Key: your_write_key" \
  -H "Content-Type: application/json" \
  -H "If-Match: \"v1\"" \
  -d '{"name": "Updated Name", "entries": []}'
```

---

### Delete Workspace

Permanently delete a workspace. Referenced documents and sub-workspaces are **not** deleted. **Requires write key.**

**Endpoint:** `DELETE /workspaces/{id}`

**Authentication:** Required (`X-Molt-Key` header — write key only)

**Response:** `204 No Content`

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/v1/workspaces/{id} \
  -H "X-Molt-Key: your_write_key"
```

---

## Error Format

All errors return JSON with a consistent structure:

```json
{
  "error": "error_code",
  "message": "Human-readable error description."
}
```

### Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `bad_request` | Malformed request, invalid parameters, or missing required fields |
| 403 | `forbidden` | Invalid/missing key, or read key used on a write endpoint |
| 404 | `not_found` | Document/workspace not found, or document not found in workspace |
| 409 | `conflict` | Version mismatch – modified by another client |
| 413 | `payload_too_large` | Content exceeds 5 MB limit |
| 429 | `rate_limited` | Too many requests from your IP address |

---

## Best Practices

### Key Management

- **Store keys securely**: Use environment variables, secret managers, or secure storage
- **Never commit keys to version control**
- **Share read keys** for read-only collaborators, **write keys** only for editors
- **No key recovery**: If you lose the key, the content is permanently inaccessible

### Workspace Organization

- Use workspaces to group related documents
- Nest workspaces for hierarchical organization
- Store **read keys** in entries for read-only access; **write keys** for full access
- Workspace-level permissions always override file-level permissions

### Partial Fetch for Agents

- Use `?lines=1` to quickly fetch document headlines
- Use `?preview_lines=1` on workspace GET to build a table of contents in one request
- Check `X-Molt-Truncated` and `X-Molt-Total-Lines` headers

### Optimistic Concurrency

Always use `If-Match` headers when updating in collaborative environments:

1. Read the document/workspace and note the `ETag`
2. Make your changes locally
3. Send the update with `If-Match` set to the version you read
4. If you get a `409 Conflict`, re-read and merge changes

---

## Code Examples

### Python

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Create a document
response = requests.post(
    f"{BASE_URL}/docs",
    json={"content": "# My Document\n\nHello world!"}
)
data = response.json()
doc_id = data["id"]
write_key = data["write_key"]
read_key = data["read_key"]
print(f"Created document: {doc_id}")

# Read with write key (JSON)
response = requests.get(
    f"{BASE_URL}/docs/{doc_id}",
    headers={"X-Molt-Key": write_key, "Accept": "application/json"}
)
print(f"Content: {response.json()['content']}")

# Partial fetch — first line only
response = requests.get(
    f"{BASE_URL}/docs/{doc_id}?lines=1",
    headers={"X-Molt-Key": read_key, "Accept": "text/markdown"}
)
print(f"First line: {response.text}")
print(f"Truncated: {response.headers.get('X-Molt-Truncated')}")

# Update (requires write key)
etag = response.headers.get("ETag")
response = requests.put(
    f"{BASE_URL}/docs/{doc_id}",
    headers={
        "X-Molt-Key": write_key,
        "Content-Type": "text/markdown",
        "If-Match": etag
    },
    data="# Updated Document\n\nNew content."
)

# Create a workspace
response = requests.post(
    f"{BASE_URL}/workspaces",
    json={
        "name": "My Project",
        "entries": [{"type": "md", "id": doc_id, "key": write_key}]
    }
)
ws = response.json()

# Read workspace with previews
response = requests.get(
    f"{BASE_URL}/workspaces/{ws['id']}?preview_lines=1",
    headers={"X-Molt-Key": ws["write_key"]}
)
print(response.json())

# Access document through workspace
response = requests.get(
    f"{BASE_URL}/docs/{doc_id}",
    headers={
        "X-Molt-Key": ws["read_key"],
        "X-Molt-Workspace": ws["id"]
    }
)
```

---

## Changelog

### Version 1.1 (February 2026)

- **Read/Write Key Model**: Dual-key system with derived read keys for granular access control
- **Workspaces**: Encrypted JSON containers for bundling documents and sub-workspaces
- **Workspace-Scoped Access**: Access documents through workspaces with permission hierarchy
- **Partial Fetch**: `?lines=N` parameter for lightweight document previews
- **Workspace Previews**: `?preview_lines=N` for agent-friendly table of contents
- Timing-safe key comparison for enhanced security
- Workspace TTL / auto-expiry (same 30-day rule as documents)

### Version 1.0 (February 2026)

- Initial release
- Document CRUD operations
- AES-256-GCM encryption
- Optimistic concurrency control
- 30-day auto-expiry
- Rate limiting

---

## Support

For issues, feature requests, or questions:
- GitHub: [github.com/bndkts/molt-md](https://github.com/bndkts/molt-md)
- Documentation: [molt-md.com/docs](https://molt-md.com/docs)
