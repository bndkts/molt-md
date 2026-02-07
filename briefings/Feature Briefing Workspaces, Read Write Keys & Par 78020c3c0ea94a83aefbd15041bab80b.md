# Feature Briefing: Workspaces, Read/Write Keys & Partial Fetch

This briefing covers three new features for molt-md that are **cross-dependent** and should be implemented together. It is written for a coding agent and contains all the context needed to build these features on top of the existing molt-md codebase.


📎
**Existing system context:** molt-md is a cloud-hosted `.md` collaboration tool. Django + DRF backend, React frontend, Postgres DB. Documents are encrypted with AES-256-GCM (SSE-C), keys are never stored. Access via `X-Molt-Key` header. Concurrency via ETag/version. See the main spec for full details.

---

# 1. Read/Write Key Model

**This feature touches everything else, so implement it first.**

Currently, each document has a single key. This changes to a **dual-key model** where every `.md` file (and later, every workspace) has two keys: a **read key** and a **write key**.

### Key mechanics

- On `POST /api/v1/docs`, the server generates a **write key** (32-byte, Base64 URL-safe) just like today
- The **read key is derived** from the write key: `read_key = HMAC-SHA256(write_key, "molt-read")`truncated/encoded to the same format
- Both keys are returned in the creation response. This is the only time they are visible.
- The server stores **neither key**, same as today

### How the server validates keys

On every request, the server receives a key via `X-Molt-Key`. It needs to determine *which* key was provided:

1. Try to decrypt with the provided key as **write key** (AES-256-GCM). If decryption succeeds → write access.
2. If that fails, derive the read key candidate: compute `read_key = HMAC-SHA256(provided_key, "molt-read")` ... wait, that's backwards. Let me clarify the actual flow:

Since the server doesn't store keys, it needs a way to check both. The practical approach:

1. Attempt decryption treating the provided key as the **write key**. Success → write access granted.
2. If decryption fails, attempt decryption treating the provided key as the **read key**. To do this, the encrypted content must be decryptable with *either* key.

**Implementation detail:** Store two encrypted blobs, or better: store a single blob encrypted with the write key, plus a **key-check hash** that lets the server verify the read key without a second blob.

Recommended approach:

- Store an additional field `read_key_hash`: `SHA-256(read_key)` (not the key itself, just a hash for verification)
- On request: hash the incoming key and compare to `read_key_hash`. If match → read-only access. If no match → attempt AES decryption with the key as write key. If that succeeds → write access. If both fail → `403`.

### Permission enforcement

- **Write key** → full read + write access (all existing endpoints work as before)
- **Read key** → `GET` endpoints work, `PUT` / `PATCH` / `DELETE` return `403 Forbidden` with `{"error": "forbidden", "message": "Read-only access. Write key required."}`
- **Default is write access.** The creator always gets the write key. Read keys are shared selectively.

### DB model changes

```python
# Add to existing Document model:
read_key_hash = models.BinaryField()  # SHA-256 hash of derived read key, for verification
```

### API changes

**`POST /api/v1/docs` response (201 Created):**

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "write_key": "base64encodedwritekey...",
  "read_key": "base64encodedreadkey..."
}
```

**All mutating endpoints** (`PUT`, `PATCH`, `DELETE`) must check that the provided key is the write key. If it's the read key, return `403`.

### URL fragment update

The frontend URL structure becomes: `/#<id>#<write_key>` or `/#<id>#<read_key>` depending on what was shared. The React app doesn't need to know which one it is. It sends whatever key it has via `X-Molt-Key`, and the server determines access level. The frontend should display a **read-only indicator** (e.g. lock icon, disabled editor) when a `PUT` attempt returns `403`.

---

# 2. Workspaces

Workspaces are a new entity type: JSON objects that bundle multiple `.md` files (and other workspaces) together.

### Data model

```python
class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    content_encrypted = models.BinaryField()  # Encrypted JSON blob
    nonce = models.BinaryField()
    read_key_hash = models.BinaryField()      # Same dual-key model as docs
    version = models.IntegerField(default=1)
    last_accessed = models.DateTimeField(auto_now=True)
```

### Workspace JSON structure (decrypted)

```json
{
  "name": "Project Alpha",
  "entries": [
    { "type": "md", "id": "uuid-1", "key": "base64key..." },
    { "type": "md", "id": "uuid-2", "key": "base64key..." },
    { "type": "workspace", "id": "uuid-3", "key": "base64key..." }
  ]
}
```

- **`name`**: Top-level field. Lets agents quickly understand what's inside without resolving children. Critical for nested workspace navigation.
- **`type`**: Either `"md"` or `"workspace"`. Tells the client what it's resolving.
- **`key`**: The key stored here can be either a read key or write key for the referenced item, depending on what level of access the workspace owner wants to grant.

### Nesting

- Workspaces can reference **sub-workspaces** via `"type": "workspace"` entries
- Sub-workspaces are **separate encrypted JSON objects** in the DB (not inlined). The parent only holds a reference.
- Resolution is **lazy**: the client only fetches a sub-workspace when explicitly navigating into it
- No depth limit enforced, but the `name` field on each workspace makes deep trees navigable

### Encryption & keys

- **Same dual-key model as documents.** Each workspace has its own write key and derived read key.
- Same AES-256-GCM encryption, same SSE-C pattern, same `X-Molt-Key` header.
- Workspace keys are independent from the keys of the documents inside.

### Permission hierarchy

- **Workspace-level permissions override file-level permissions:**
    - Write key for workspace → write access to all files inside, regardless of what file-level key is stored in the entries
    - Read key for workspace → read-only access to all files inside
    - File-level keys only matter when accessing a file directly (outside a workspace context)
- **Granular access via nesting:** Share a sub-workspace's key to grant access to just that branch. No exposure of parent or sibling workspaces.

### API endpoints

All endpoints mirror the document API structure under `/api/v1/workspaces`.

**Create workspace:**

`POST /api/v1/workspaces`

```json
{
  "name": "Project Alpha",
  "entries": []
}
```

Response (201):

```json
{
  "id": "ws-uuid",
  "write_key": "base64...",
  "read_key": "base64..."
}
```

**Read workspace:**

`GET /api/v1/workspaces/<id>`

Header: `X-Molt-Key: <key>`

Returns the decrypted JSON (name + entries list).

**Update workspace:**

`PUT /api/v1/workspaces/<id>`

Header: `X-Molt-Key: <write_key>`, `If-Match: "<version>"`

Body: Full updated JSON.

Same ETag/conflict handling as documents.

**Delete workspace:**

`DELETE /api/v1/workspaces/<id>`

Header: `X-Molt-Key: <write_key>`

Deletes the workspace metadata only. Referenced documents/sub-workspaces are **not** cascade-deleted.

### Workspace-scoped document access

When accessing a document *through* a workspace, the client should include an additional header:

`X-Molt-Workspace: <workspace_id>`

With the workspace key in `X-Molt-Key`.

The server then:

1. Decrypts the workspace with the provided key to determine access level (read/write)
2. Retrieves the document's key from the workspace entries
3. Decrypts the document using that stored key
4. Enforces the **workspace-level permission** (even if the stored key is a write key, a read-only workspace key downgrades access)

---

# 3. Partial Fetch (First X Lines)

A lightweight retrieval mode for agents that only need a preview of a document.

### API changes

**Endpoint:** `GET /api/v1/docs/<id>?lines=<x>`

- **`lines` parameter** (optional, integer, minimum 1)
- If omitted or not provided, returns the full document (existing behavior)
- If `lines=1`, returns only the first line (headline)
- If `lines=5`, returns the first 5 lines
- Lines are split by `\n`

### Implementation

1. Decrypt the document as usual (full decryption is unavoidable due to AES-GCM)
2. Split decrypted content by `\n`
3. Return only the first `x` lines, joined by `\n`
4. Add a response header `X-Molt-Truncated: true` if the document was truncated (so the agent knows there's more)
5. Add `X-Molt-Total-Lines: <n>` header with the total line count

### Workspace integration

Partial fetch also works for workspace-scoped document access:

`GET /api/v1/docs/<id>?lines=1`

With `X-Molt-Workspace: <workspace_id>` and `X-Molt-Key: <workspace_key>`

This is the killer combo for agents: list all entries in a workspace, then `?lines=1` each document to build a quick table of contents without pulling full content.

### Workspace listing with previews

To make this even more agent-friendly, the workspace `GET` endpoint supports an optional preview mode:

`GET /api/v1/workspaces/<id>?preview_lines=<x>`

This returns the workspace JSON with an additional `preview` field on each `"md"` entry, containing the first `x` lines of that document. Sub-workspaces just show their `name`.

```json
{
  "name": "Project Alpha",
  "entries": [
    { "type": "md", "id": "uuid-1", "preview": "# Meeting Notes" },
    { "type": "md", "id": "uuid-2", "preview": "# API Design Draft" },
    { "type": "workspace", "id": "uuid-3", "name": "Archive" }
  ]
}
```

---

# Implementation order

<aside>
⚠️

These features are cross-dependent. Follow this order to avoid rework.

</aside>

### Phase 1: Read/Write Key Model

1. Implement key derivation logic (`read_key = HMAC-SHA256(write_key, "molt-read")`)
2. Add `read_key_hash` field to the Document model + migration
3. Update `POST /api/v1/docs` to generate both keys and return them
4. Update the auth middleware to detect read vs. write key and set access level on the request
5. Guard `PUT`, `PATCH`, `DELETE` to reject read-only keys with `403`
6. Update the React frontend to handle read-only mode (lock icon, disable editor)
7. Update the URL fragment handling (no structural change, just awareness that the key could be either type)

### Phase 2: Workspaces

1. Create the `Workspace` model with the same encryption + dual-key pattern
2. Implement CRUD endpoints under `/api/v1/workspaces`
3. Implement workspace-scoped document access (`X-Molt-Workspace` header)
4. Implement permission hierarchy (workspace key overrides file key)
5. Add workspace UI in the React frontend (listing, navigation, nested workspace support)
6. Add TTL / lifecycle handling (same as documents)

### Phase 3: Partial Fetch

1. Add `?lines=` query parameter to `GET /api/v1/docs/<id>`
2. Add `X-Molt-Truncated` and `X-Molt-Total-Lines` response headers
3. Add `?preview_lines=` to `GET /api/v1/workspaces/<id>`
4. Default behavior when `lines` is omitted: return full document (backwards compatible)

---

# Error handling additions

| Status Code | Meaning | New scenarios |
| --- | --- | --- |
| `403 Forbidden` | Insufficient permissions | Read key used on a write endpoint |
| `400 Bad Request` | Invalid parameter | `lines=0`, `lines=-1`, or non-integer value |
| `404 Not Found` | Entity not found | Workspace ID doesn't exist, or referenced doc not found in workspace |
