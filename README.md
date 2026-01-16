# Signal-to-Attempt Workbench

A workbench application that ingests GitHub issues as "signals," runs Claude Code attempts against them, and only escalates to humans when stuck.

## Overview

The system follows an "attempt-first" philosophy to shift work from human spec-writing to machine attempts with targeted clarification:

1. **Ingest signals** from GitHub Projects/issues
2. **Run Claude Code attempts** against signals with strict policies
3. **Classify outcomes** as SUCCESS, NEEDS_HUMAN, FAILED, or NOOP
4. **Only escalate** to humans when the attempt is stuck
5. **Allow retry** with clarifications to unblock the attempt

## Tech Stack

- **Frontend**: Next.js 15 (App Router) with TypeScript and Tailwind CSS
- **Backend**: Python FastAPI 3.12 with Poetry
- **Database**: PostgreSQL (also serves as job queue)
- **Attempt Isolation**: Local subprocess with tmpdir
- **GitHub Auth**: Personal Access Token (v0)

## Quick Start

```bash
# 1. Clone and setup
cd agentic-planner
make setup

# 2. Start PostgreSQL
make db-up

# 3. Run migrations
make migrate

# 4. Start all services (in separate terminals)
make backend   # FastAPI on :8000
make frontend  # Next.js on :3000
make worker    # Background worker
```

## Project Structure

```
agentic-planner/
├── frontend/           # Next.js application
│   ├── src/app/       # App Router pages
│   └── src/lib/       # API client
├── backend/           # FastAPI application
│   ├── src/workbench/
│   │   ├── api/       # HTTP routes
│   │   ├── models/    # SQLAlchemy models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   └── worker/    # Attempt runner
├── docker-compose.yml # PostgreSQL
└── Makefile          # Dev commands
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Database
DATABASE_URL=postgresql://workbench:workbench@localhost:5432/workbench

# GitHub Personal Access Token
GITHUB_PAT=ghp_xxxxx

# Claude Code (must be globally installed)
CLAUDE_CODE_PATH=claude
CLAUDE_DEFAULT_MAX_TURNS=50
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Key Concepts

### Attempt Statuses
- `pending` - Created but not started
- `running` - Currently executing
- `success` - Completed with PR created
- `needs_human` - Stuck, requires clarification
- `failed` - Error during execution
- `noop` - No changes needed

### Attempt Budgets (configurable)
- Max wall-clock: 20 minutes
- Max tool calls: 200
- Max turns: 50
- Max diff lines: 800 (soft gate)
- Max files touched: 40 (soft gate)

## Development

```bash
# Run tests
make test

# Run linting
make lint

# Type checking
make typecheck

# Database shell
make shell-db
```

## License

MIT
