# Backend Development Guidelines

MoonBirdNotes uses Django 6 and Django REST Framework for a private, administrator-only notes application. MySQL stores source data; Qdrant, cached embeddings, and run traces are derived or operational data.

## Guides

| Guide | Scope |
| --- | --- |
| [Directory Structure](./directory-structure.md) | Django app ownership and cross-app boundaries |
| [Database Guidelines](./database-guidelines.md) | ORM queries, transactions, migrations, MySQL/Qdrant roles |
| [Error Handling](./error-handling.md) | DRF validation, stable Agent errors, integration failures |
| [Logging Guidelines](./logging-guidelines.md) | Structured operational logs and redaction |
| [Configuration and Security](./configuration-security.md) | Environment config, authentication, uploads, HTML, media |
| [Quality Guidelines](./quality-guidelines.md) | Tests, review checks, and verification commands |

## Pre-Development Checklist

1. Read [Directory Structure](./directory-structure.md), then the topic guide for the code being changed.
2. Read [Configuration and Security](./configuration-security.md) for any API, authentication, upload, rendered HTML, media, provider, cache, or deployment change.
3. Read [Database Guidelines](./database-guidelines.md) before changing models, querysets, migrations, RAG jobs, or deletion behavior.
4. Read [Error Handling](./error-handling.md) and [Logging Guidelines](./logging-guidelines.md) for Agent/RAG/provider work.
5. Run the narrowest relevant tests, then the broader backend suite when the change crosses apps.

## Project Commands

Run backend commands from `backend/` with the environment described by `backend/.env.example` available:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test accounts notes agent rag
```

Targeted examples include `python manage.py test accounts.tests`, `python manage.py test notes.tests`, `python manage.py test agent.test_api`, and `python manage.py test rag.test_jobs`.

