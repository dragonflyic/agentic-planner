# Workbench Backend

FastAPI backend for the Signal-to-Attempt Workbench.

## Setup

```bash
# Install dependencies
poetry install

# Run migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn workbench.main:app --reload
```

## Structure

```
src/workbench/
├── main.py           # FastAPI application
├── config.py         # Configuration settings
├── api/              # HTTP routes
├── models/           # SQLAlchemy models
├── schemas/          # Pydantic schemas
├── services/         # Business logic
├── db/               # Database setup
└── worker/           # Background worker
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
