# molt-md: Backend Briefing

This is the complete technical briefing for the **backend** of molt-md. It contains everything you need to build the Django API server from scratch.

For the full product concept, see the parent page.

## Project Overview

molt-md is a cloud-hosted markdown collaboration tool for agents and humans. The backend is a **Django REST API** that handles encrypted document storage, retrieval, and lifecycle management. The entire backend is stateless (no sessions, no auth tokens, no user accounts).

**Domain:** [`molt-md.com`](http://molt-md.com)

## Tech Stack

- **Framework:** Django + Django REST Framework
- **Database:** PostgreSQL
- **Encryption:** `cryptography` library (Python)
- **CORS:** `django-cors-headers`
- **Rate Limiting:** `django-ratelimit` or DRF throttling
- **Deployment:** Dokku (separate app from frontend)

## Database Model

Single model: `Document`

```python
class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_encrypted = models.BinaryField()
    nonce = models.BinaryField()
    version = models.IntegerField(default=1)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Important:** There is no key field. The encryption key is generated server-side on document creation, returned **once** in the response, and never stored.

## Encryption Logic

### Algorithm

- **AES-256-GCM** (Authenticated Encryption with Associated Data)
- Library: `cryptography` (use `AESGCM` from `cryptography.hazmat.primitives.ciphers.aead`)

### Key Generation (on `POST /create`)

```python
import os, base64
raw_key = os.urandom(32)  # 256-bit key
key_b64 = base64.urlsafe_b64encode(raw_key).decode()  # URL-safe Base64
```

### Encrypt

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

nonce = os.urandom(12)  # 96-bit nonce for GCM
aesgcm = AESGCM(raw_key)
ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
# Store: content_encrypted=ciphertext, nonce=nonce
```

### Decrypt

```python
aesgcm = AESGCM(raw_key)
plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
```

### Key from Request

The client sends the key via the `X-Molt-Key` header (Base64 URL-safe encoded). Decode it:

```python
raw_key = base64.urlsafe_b64decode(request.headers['X-Molt-Key'])
```

If decryption fails (wrong key), return `403 Forbidden`.

## API Endpoints

All endpoints are under `/api/v1/`.

### 1. `POST /api/v1/docs` (Create Document)

**Auth:** None.

**Request body (optional, JSON):**

```json
{ "content": "# Hello World" }
```

If no body or empty content, create an empty document.

**Logic:**

1. Generate UUID for `id`
2. Generate 32-byte key, encode as Base64 URL-safe
3. Encrypt content (or empty string) with generated key
4. Generate fresh nonce
5. Save `Document(id, content_encrypted, nonce, version=1)`
6. Return `id` and `key` (this is the only time the key is exposed)

**Response (201):**

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "key": "base64urlsafe_encoded_key"
}
```

**Rate limit:** Strict (e.g. 10 creates/min per IP).

---

### 2. `GET /api/v1/docs/<id>` (Read Document)

**Headers:**

- `X-Molt-Key: <key>` (required)
- `Accept: text/markdown` (default) or `application/json`

**Logic:**

1. Look up document by `id`. If not found: `404`.
2. Decode key from header. Attempt decryption. If it fails: `403`.
3. Update `last_accessed` timestamp.
4. Return decrypted content.

**Response headers:**

- `ETag: "v<version>"` (e.g. `ETag: "v5"`)
- `Content-Type: text/markdown` or `application/json`

**Response (200, text/markdown):** Raw markdown content.

**Response (200, application/json):**

```json
{ "id": "...", "content": "# Hello World", "version": 5 }
```

---

### 3. `PUT /api/v1/docs/<id>` (Update Document)

**Headers:**

- `X-Molt-Key: <key>` (required)
- `Content-Type: text/markdown`
- `If-Match: "v<version>"` (optional but recommended)

**Body:** Raw markdown content.

**Logic:**

1. Look up document. If not found: `404`.
2. Decode key, verify by attempting decryption of existing content. If it fails: `403`.
3. If `If-Match` is provided, compare with current version. If mismatch: `409 Conflict`.
4. Validate size (max 5 MB). If exceeded: `413`.
5. Encrypt new content with the provided key + fresh nonce.
6. Update: `content_encrypted`, `nonce`, increment `version`, update `last_accessed`.
7. Use `UPDATE ... WHERE id = X AND version = Y` for atomic conflict detection.

**Response (200):**

```json
{ "success": true, "version": 18 }
```

**Response (409):**

```json
{ "error": "conflict", "current_version": 18 }
```

---

### 4. `PATCH /api/v1/docs/<id>` (Append to Document)

**Headers:**

- `X-Molt-Key: <key>` (required)
- `Content-Type: text/markdown`
- `If-Match: "v<version>"` (optional but recommended)

**Body:** Raw markdown to append.

**Logic:**

1. Same auth + lookup as `PUT`.
2. Decrypt existing content.
3. Append new content separated by `\n`.
4. Validate combined size (max 5 MB). If exceeded: `413`.
5. Encrypt combined content with provided key + fresh nonce.
6. Atomic update with version check (same as `PUT`).

**Response:** Same as `PUT`.

---

### 5. `DELETE /api/v1/docs/<id>` (Delete Document)

**Headers:**

- `X-Molt-Key: <key>` (required)

**Logic:**

1. Look up document. If not found: `404`.
2. Verify key by attempting decryption. If it fails: `403`.
3. Delete the row permanently.

**Response:** `204 No Content`.

---

### 6. `GET /api/v1/health` (Health Check)

**Auth:** None.

**Response (200):**

```json
{ "status": "ok" }
```

## Error Handling

All errors return JSON with a consistent format:

```json
{ "error": "error_code", "message": "Human-readable description." }
```

| Code | `error` value | When |
| --- | --- | --- |
| 400 | `bad_request` | Malformed JSON, missing fields |
| 403 | `forbidden` | Wrong/missing `X-Molt-Key` |
| 404 | `not_found` | Document ID doesn't exist |
| 409 | `conflict` | `If-Match` version mismatch |
| 413 | `payload_too_large` | Content exceeds 5 MB |
| 429 | `rate_limited` | Too many requests from IP |

## CORS Configuration

The frontend runs as a separate Dokku app. You **must** configure CORS.

```python
# settings.py
CORS_ALLOWED_ORIGINS = [
    "https://molt-md.com",  # frontend domain
]
CORS_ALLOW_HEADERS = [
    "content-type",
    "x-molt-key",
    "if-match",
    "accept",
]
CORS_EXPOSE_HEADERS = [
    "etag",
]
```

## HTTPS & Security Headers

- HTTP must be **completely disabled**. No redirect, no fallback. HTTPS only.
- Set `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- Set `X-Content-Type-Options: nosniff`
- Set `X-Frame-Options: DENY`
- Django settings: `SECURE_SSL_REDIRECT = True`, `SECURE_HSTS_SECONDS = 63072000`

## Rate Limiting

Use DRF throttling or `django-ratelimit`.

Suggested defaults:

- `POST /api/v1/docs`: **10 requests/min** per IP (strictest, prevents spam creation)
- `GET/PUT/PATCH/DELETE`: **60 requests/min** per IP
- Return `429 Too Many Requests` with a `Retry-After` header.

## Document Expiry (TTL)

Documents expire after **30 days** of inactivity (no read or write).

**Implementation:**

- The `last_accessed` field is updated on every `GET`, `PUT`, and `PATCH`.
- A Django management command runs on a cron schedule (e.g. daily):

```python
# management/commands/purge_expired.py
from django.utils import timezone
from datetime import timedelta

def handle(self, *args, **options):
    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = Document.objects.filter(last_accessed__lt=cutoff).delete()
    self.stdout.write(f"Purged {deleted} expired documents.")
```

Schedule via Dokku cron or `django-crontab`.

## Deployment Notes (Dokku)

- App name: `molt-md-api` (or similar)
- Procfile: `web: gunicorn molt_md.wsgi --bind 0.0.0.0:$PORT`
- Postgres: provision via `dokku postgres:create molt-md-db` and link.
- Environment variables:
    - `DATABASE_URL` (auto-set by Dokku postgres plugin)
    - `DJANGO_SECRET_KEY`
    - `ALLOWED_HOSTS=[molt-md.com](http://molt-md.com)`
    - `CORS_ALLOWED_ORIGINS=[https://molt-md.com](https://molt-md.com)`
- Run migrations on deploy: add `release: python [manage.py](http://manage.py) migrate` to Procfile.

## Suggested Project Structure

```
molt-md-api/
├── molt_md/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── docs/
│   ├── models.py          # Document model
│   ├── views.py           # API views
│   ├── serializers.py     # DRF serializers
│   ├── encryption.py      # Encrypt/decrypt helpers
│   ├── throttling.py      # Custom rate limit classes
│   └── management/
│       └── commands/
│           └── purge_expired.py
├── Procfile
├── requirements.txt
└── manage.py
```

## Testing Checklist

- [ ]  Create document returns `id` and `key`, key is valid Base64 URL-safe
- [ ]  Read with correct key returns decrypted content
- [ ]  Read with wrong key returns `403`
- [ ]  Read non-existent ID returns `404`
- [ ]  Update with `If-Match` succeeds when version matches
- [ ]  Update with `If-Match` returns `409` when version doesn't match
- [ ]  Update without `If-Match` always succeeds (last-write-wins)
- [ ]  Patch appends content correctly
- [ ]  Patch respects 5 MB limit on combined content
- [ ]  Delete with correct key removes document
- [ ]  Delete with wrong key returns `403`
- [ ]  Payload > 5 MB returns `413`
- [ ]  Rate limit returns `429` with `Retry-After`
- [ ]  ETag header present on all `GET` responses
- [ ]  Version increments on every successful write
- [ ]  `last_accessed` updates on `GET`, `PUT`, `PATCH`
- [ ]  Health endpoint returns `200`
- [ ]  CORS headers present for frontend origin
- [ ]  HSTS header present