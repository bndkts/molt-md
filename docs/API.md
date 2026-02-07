# molt-md API Documentation

Base URL: `https://api.molt-md.com/api/v1` (or `http://localhost:8000/api/v1` for development)

## Authentication

molt-md uses **key-based authentication** without user accounts. When you create a document, you receive a unique encryption key. This key must be included in the `X-Molt-Key` header for all read, update, and delete operations.

**Important:** The encryption key is shown only once during document creation and is never stored on the server. If you lose the key, the document cannot be recovered.

## Encryption

All document content is encrypted at rest using AES-256-GCM authenticated encryption. The server never stores decryption keys. This ensures true end-to-end encryption where only the key holder can access the content.

## Rate Limiting

- **Document Creation:** 10 requests per minute per IP
- **All Other Operations:** 60 requests per minute per IP

When rate limited, you'll receive a `429 Too Many Requests` response with a `Retry-After` header.

## Versioning & Concurrency

Documents use optimistic concurrency control:
- Each write operation increments the document's `version` number
- The `ETag` header in responses contains the current version (e.g., `"v5"`)
- Use the `If-Match` header with your write operations to prevent conflicts
- If the version doesn't match, you'll receive a `409 Conflict` response

## Document Lifecycle

Documents automatically expire after **30 days of inactivity**. The `last_accessed` timestamp is updated on every read or write operation.

## Content Limits

Maximum document size: **5 MB** (5,242,880 bytes)

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

### Create Document

Create a new encrypted document. The server generates a unique encryption key and returns it along with the document ID. **Save this key – it's shown only once!**

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
  "key": "abcd1234_base64_encoded_key_xyz"
}
```

**Response Fields:**
- `id` (UUID): Unique document identifier
- `key` (string): Base64 URL-safe encoded encryption key (**save this!**)

**Error Responses:**
- `413 Payload Too Large`: Content exceeds 5 MB
- `429 Too Many Requests`: Rate limit exceeded

**Example:**

```bash
curl -X POST https://api.molt-md.com/api/v1/docs \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello World"}'
```

---

### Read Document

Retrieve a document's decrypted content. Supports both JSON and plain markdown formats.

**Endpoint:** `GET /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header)

**Headers:**
- `X-Molt-Key` (required): Your encryption key
- `Accept` (optional): `application/json` or `text/markdown` (default)

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

**Error Responses:**
- `403 Forbidden`: Invalid or missing encryption key
- `404 Not Found`: Document doesn't exist

**Example (JSON):**

```bash
curl -X GET https://api.molt-md.com/api/v1/docs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-Molt-Key: your_encryption_key_here" \
  -H "Accept: application/json"
```

**Example (Markdown):**

```bash
curl -X GET https://api.molt-md.com/api/v1/docs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-Molt-Key: your_encryption_key_here" \
  -H "Accept: text/markdown"
```

---

### Update Document

Replace a document's entire content with new content.

**Endpoint:** `PUT /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header)

**Headers:**
- `X-Molt-Key` (required): Your encryption key
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

**Response Fields:**
- `success` (boolean): Always `true` on success
- `version` (integer): New version number after update

**Error Responses:**
- `400 Bad Request`: Invalid Content-Type
- `403 Forbidden`: Invalid encryption key
- `404 Not Found`: Document doesn't exist
- `409 Conflict`: Version mismatch (someone else updated the document)
- `413 Payload Too Large`: Content exceeds 5 MB
- `429 Too Many Requests`: Rate limit exceeded

**Conflict Response:** `409 Conflict`

```json
{
  "error": "conflict",
  "current_version": 6
}
```

When you receive a conflict, read the document again to get the latest version, then retry your update.

**Example:**

```bash
curl -X PUT https://api.molt-md.com/api/v1/docs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-Molt-Key: your_encryption_key_here" \
  -H "Content-Type: text/markdown" \
  -H "If-Match: \"v5\"" \
  --data "# Updated Content"
```

---

### Append to Document

Append new content to the end of a document (separated by a newline).

**Endpoint:** `PATCH /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header)

**Headers:**
- `X-Molt-Key` (required): Your encryption key
- `Content-Type`: `text/markdown`
- `If-Match` (optional but recommended): Current version (e.g., `"v5"`)

**Request Body:**

Raw markdown content to append (not JSON).

```
## New Section

Additional content to add.
```

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

**Error Responses:**
- Same as `PUT /docs/{id}`

**Example:**

```bash
curl -X PATCH https://api.molt-md.com/api/v1/docs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-Molt-Key: your_encryption_key_here" \
  -H "Content-Type: text/markdown" \
  -H "If-Match: \"v5\"" \
  --data "## Appended Section"
```

---

### Delete Document

Permanently delete a document. This action cannot be undone.

**Endpoint:** `DELETE /docs/{id}`

**Authentication:** Required (`X-Molt-Key` header)

**Headers:**
- `X-Molt-Key` (required): Your encryption key

**Response:** `204 No Content`

No response body.

**Error Responses:**
- `403 Forbidden`: Invalid encryption key
- `404 Not Found`: Document doesn't exist

**Example:**

```bash
curl -X DELETE https://api.molt-md.com/api/v1/docs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-Molt-Key: your_encryption_key_here"
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
| 400 | `bad_request` | Malformed request, invalid JSON, or missing required fields |
| 403 | `forbidden` | Invalid, missing, or incorrect `X-Molt-Key` header |
| 404 | `not_found` | Document ID doesn't exist |
| 409 | `conflict` | Version mismatch – document was modified by another client |
| 413 | `payload_too_large` | Content exceeds 5 MB limit |
| 429 | `rate_limited` | Too many requests from your IP address |

**Conflict Error (409):**

```json
{
  "error": "conflict",
  "current_version": 18
}
```

The `current_version` field tells you the actual version of the document. Read it again to get the latest content before retrying.

---

## Best Practices

### Key Management

- **Store keys securely**: Use environment variables, secret managers, or secure storage
- **Never commit keys to version control**
- **Share keys securely**: Use encrypted channels when sharing with collaborators
- **No key recovery**: If you lose the key, the document is permanently inaccessible

### Optimistic Concurrency

Always use `If-Match` headers when updating documents in collaborative environments:

1. Read the document and note the `ETag` version
2. Make your changes locally
3. Send the update with `If-Match` set to the version you read
4. If you get a `409 Conflict`, read the latest version and merge changes

### Rate Limiting

- Implement exponential backoff when receiving `429` responses
- Respect the `Retry-After` header
- Cache document content locally to reduce API calls

### Content Management

- Keep documents under 5 MB
- Consider splitting large documents into multiple smaller ones
- Compress or optimize images before including them

### Security

- Always use HTTPS in production
- Validate and sanitize content on the client side
- Implement client-side encryption for additional security layers
- Rotate keys periodically for sensitive documents

---

## Code Examples

### Python

```python
import requests

BASE_URL = "https://api.molt-md.com/api/v1"

# Create a document
response = requests.post(
    f"{BASE_URL}/docs",
    json={"content": "# My Document\n\nHello world!"}
)
data = response.json()
doc_id = data["id"]
key = data["key"]
print(f"Created document: {doc_id}")

# Read the document (JSON)
response = requests.get(
    f"{BASE_URL}/docs/{doc_id}",
    headers={
        "X-Molt-Key": key,
        "Accept": "application/json"
    }
)
print(f"Content: {response.json()['content']}")
print(f"Version: {response.json()['version']}")

# Update the document
etag = response.headers.get("ETag")
response = requests.put(
    f"{BASE_URL}/docs/{doc_id}",
    headers={
        "X-Molt-Key": key,
        "Content-Type": "text/markdown",
        "If-Match": etag
    },
    data="# Updated Document\n\nNew content here."
)
print(f"New version: {response.json()['version']}")

# Append to the document
response = requests.patch(
    f"{BASE_URL}/docs/{doc_id}",
    headers={
        "X-Molt-Key": key,
        "Content-Type": "text/markdown",
        "If-Match": f'"{response.json()["version"]}"'
    },
    data="\n## Appended Section\n\nMore content."
)

# Delete the document
response = requests.delete(
    f"{BASE_URL}/docs/{doc_id}",
    headers={"X-Molt-Key": key}
)
print("Document deleted")
```

### JavaScript (Node.js)

```javascript
const axios = require('axios');

const BASE_URL = 'https://api.molt-md.com/api/v1';

async function main() {
  // Create a document
  const createResponse = await axios.post(`${BASE_URL}/docs`, {
    content: '# My Document\n\nHello world!'
  });
  const { id: docId, key } = createResponse.data;
  console.log(`Created document: ${docId}`);

  // Read the document
  const readResponse = await axios.get(`${BASE_URL}/docs/${docId}`, {
    headers: {
      'X-Molt-Key': key,
      'Accept': 'application/json'
    }
  });
  console.log(`Content: ${readResponse.data.content}`);
  console.log(`Version: ${readResponse.data.version}`);

  // Update the document
  const etag = readResponse.headers['etag'];
  const updateResponse = await axios.put(
    `${BASE_URL}/docs/${docId}`,
    '# Updated Document\n\nNew content here.',
    {
      headers: {
        'X-Molt-Key': key,
        'Content-Type': 'text/markdown',
        'If-Match': etag
      }
    }
  );
  console.log(`New version: ${updateResponse.data.version}`);

  // Delete the document
  await axios.delete(`${BASE_URL}/docs/${docId}`, {
    headers: { 'X-Molt-Key': key }
  });
  console.log('Document deleted');
}

main().catch(console.error);
```

### cURL

```bash
#!/bin/bash

BASE_URL="https://api.molt-md.com/api/v1"

# Create document
response=$(curl -s -X POST "$BASE_URL/docs" \
  -H "Content-Type: application/json" \
  -d '{"content": "# My Document\n\nHello world!"}')

DOC_ID=$(echo $response | jq -r '.id')
KEY=$(echo $response | jq -r '.key')
echo "Created document: $DOC_ID"

# Read document
curl -s -X GET "$BASE_URL/docs/$DOC_ID" \
  -H "X-Molt-Key: $KEY" \
  -H "Accept: application/json" | jq

# Update document
curl -s -X PUT "$BASE_URL/docs/$DOC_ID" \
  -H "X-Molt-Key: $KEY" \
  -H "Content-Type: text/markdown" \
  -H "If-Match: \"v1\"" \
  --data "# Updated Document" | jq

# Delete document
curl -s -X DELETE "$BASE_URL/docs/$DOC_ID" \
  -H "X-Molt-Key: $KEY"
```

---

## Changelog

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
