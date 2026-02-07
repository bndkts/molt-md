# molt-md Backend

Django REST API backend for molt-md, a cloud-hosted markdown collaboration tool with end-to-end encryption.

## Features

- Encrypted document storage using AES-256-GCM
- Stateless architecture (no user accounts or sessions)
- RESTful API with versioning
- Optimistic concurrency control
- Automatic document expiry (30 days of inactivity)
- Rate limiting to prevent abuse
- CORS configured for frontend integration

## Tech Stack

- Django 6.0 + Django REST Framework
- PostgreSQL (production) / SQLite (development)
- Cryptography library for AES-256-GCM encryption
- Gunicorn for production server

## Setup

1. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

4. **Run development server:**
   ```bash
   python manage.py runserver
   ```

## API Endpoints

All endpoints are under `/api/v1/`:

- `POST /api/v1/docs` - Create a new encrypted document
- `GET /api/v1/docs/<id>` - Read a document (requires `X-Molt-Key` header)
- `PUT /api/v1/docs/<id>` - Update a document (requires `X-Molt-Key` header)
- `PATCH /api/v1/docs/<id>` - Append to a document (requires `X-Molt-Key` header)
- `DELETE /api/v1/docs/<id>` - Delete a document (requires `X-Molt-Key` header)
- `GET /api/v1/health` - Health check

## Environment Variables

For production deployment:

- `DJANGO_SECRET_KEY` - Django secret key
- `DATABASE_URL` - PostgreSQL connection string
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts (e.g., `molt-md.com`)
- `CORS_ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins (e.g., `https://molt-md.com`)
- `DEBUG` - Set to `False` in production

## Management Commands

### Purge Expired Documents

Run this command on a cron schedule (e.g., daily):

```bash
python manage.py purge_expired
```

By default, documents expire after 30 days of inactivity. You can customize this:

```bash
python manage.py purge_expired --days 60
```

## Deployment (Dokku)

1. **Create app:**
   ```bash
   dokku apps:create molt-md-api
   ```

2. **Provision PostgreSQL:**
   ```bash
   dokku postgres:create molt-md-db
   dokku postgres:link molt-md-db molt-md-api
   ```

3. **Set environment variables:**
   ```bash
   dokku config:set molt-md-api DJANGO_SECRET_KEY="your-secret-key"
   dokku config:set molt-md-api ALLOWED_HOSTS="molt-md.com"
   dokku config:set molt-md-api CORS_ALLOWED_ORIGINS="https://molt-md.com"
   dokku config:set molt-md-api DEBUG="False"
   ```

4. **Deploy:**
   ```bash
   git remote add dokku dokku@your-server:molt-md-api
   git push dokku main
   ```

## Security

- All content is encrypted at rest using AES-256-GCM
- Encryption keys are never stored on the server
- HTTPS only (enforced in production)
- HSTS headers enabled
- CORS configured for frontend origin only
- Rate limiting on all endpoints
- No authentication or user accounts (stateless)

## License

MIT
