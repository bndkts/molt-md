# molt-md Backend

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Django REST API backend for molt-md, a cloud-hosted markdown collaboration tool with end-to-end encryption.

## Features

- Encrypted document storage using AES-256-GCM
- Stateless architecture (no user accounts or sessions)
- RESTful API with versioning
- Optimistic concurrency control
- Automatic document expiry (30 days of inactivity)
- Rate limiting to prevent abuse
- CORS configured for frontend integration
- Workspace support for organizing multiple documents

## Tech Stack

- Django 6.0 + Django REST Framework
- PostgreSQL (production) / SQLite (development)
- Cryptography library for AES-256-GCM encryption
- Gunicorn for production server

## Quick Start

### Prerequisites

- Python 3.10 or higher
- pip and virtualenv

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/bndkts/molt-md.git
   cd molt-md/backend
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Run development server:**
   ```bash
   python manage.py runserver
   ```

The API will be available at `http://localhost:8000/api/v1/`

## API Documentation

See [docs/API.md](docs/API.md) for complete API documentation.

### Quick Reference

All endpoints are under `/api/v1/`:

**Documents:**
- `POST /api/v1/docs` - Create a new encrypted document
- `GET /api/v1/docs/<id>` - Read a document (requires `X-Molt-Key` header)
- `PUT /api/v1/docs/<id>` - Update a document (requires `X-Molt-Key` header)
- `PATCH /api/v1/docs/<id>` - Append to a document (requires `X-Molt-Key` header)
- `DELETE /api/v1/docs/<id>` - Delete a document (requires `X-Molt-Key` header)

**Workspaces:**
- `POST /api/v1/workspaces` - Create a new workspace
- `GET /api/v1/workspaces/<id>` - Get workspace details
- `PUT /api/v1/workspaces/<id>` - Update workspace
- `DELETE /api/v1/workspaces/<id>` - Delete workspace

**System:**
- `GET /api/v1/health` - Health check
- `GET /api/v1/metrics` - Get database statistics

## Configuration

### Environment Variables

- `DJANGO_SECRET_KEY` - Django secret key (required in production)
- `DATABASE_URL` - PostgreSQL connection string (optional, defaults to SQLite)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts (e.g., `example.com,api.example.com`)
- `CORS_ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins (e.g., `https://example.com,https://app.example.com`)
- `DEBUG` - Set to `True` for development, `False` for production (default: `False`)

### Example Production Configuration

```bash
export DJANGO_SECRET_KEY="your-secret-key-here"
export DATABASE_URL="postgresql://user:password@localhost/dbname"
export ALLOWED_HOSTS="api.example.com"
export CORS_ALLOWED_ORIGINS="https://example.com"
export DEBUG="False"
```

## Testing

Run tests with pytest:

```bash
pytest
```

## Management Commands

### Purge Expired Documents

Run this command on a cron schedule (e.g., daily) to clean up expired documents:

```bash
python manage.py purge_expired
```

By default, documents expire after 30 days of inactivity. You can customize this:

```bash
python manage.py purge_expired --days 60
```

## Deployment

### General Deployment Steps

1. Set environment variables (see Configuration section)
2. Use a production-ready database (PostgreSQL recommended)
3. Collect static files if needed: `python manage.py collectstatic`
4. Run migrations: `python manage.py migrate`
5. Use a production WSGI server (Gunicorn included)

### Example: Deploying with Gunicorn

```bash
gunicorn molt_md.wsgi --bind 0.0.0.0:8000
```

### Platform-Specific Examples

#### Dokku

```bash
# Create app
dokku apps:create your-app-name

# Provision PostgreSQL
dokku postgres:create your-db-name
dokku postgres:link your-db-name your-app-name

# Set environment variables
dokku config:set your-app-name \
  DJANGO_SECRET_KEY="your-secret-key" \
  ALLOWED_HOSTS="api.example.com" \
  CORS_ALLOWED_ORIGINS="https://example.com" \
  DEBUG="False"

# Deploy
git remote add dokku dokku@your-server:your-app-name
git push dokku main
```

#### Heroku

```bash
# Create app
heroku create your-app-name

# Add PostgreSQL
heroku addons:create heroku-postgresql:mini

# Set environment variables
heroku config:set \
  DJANGO_SECRET_KEY="your-secret-key" \
  ALLOWED_HOSTS="your-app-name.herokuapp.com" \
  CORS_ALLOWED_ORIGINS="https://example.com" \
  DEBUG="False"

# Deploy
git push heroku main
```

#### Docker

A `Dockerfile` can be created with:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "molt_md.wsgi", "--bind", "0.0.0.0:8000"]
```

## Security

- All content is encrypted at rest using AES-256-GCM authenticated encryption
- Encryption keys are never stored on the server
- HTTPS only (enforced in production)
- HSTS headers enabled
- CORS configured for specific origins only
- Rate limiting on all endpoints
- No authentication or user accounts (stateless, key-based access)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
