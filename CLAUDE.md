# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a pnpm monorepo managed by Turbo with two applications:

- `apps/web` - Next.js 16 frontend (React 19, TypeScript, Tailwind CSS 4)
- `apps/api` - Python FastAPI backend (Python 3.12+, SQLAlchemy, Alembic)

## Development Commands

All commands should be run from the repository root:

```bash
# Install dependencies
pnpm install

# Start both apps in development mode
pnpm dev

# Build all apps
pnpm build

# Lint all apps
pnpm lint
```

### Web App (Next.js)

Located in `apps/web/`:

```bash
# Development server runs on http://localhost:3000
cd apps/web && pnpm dev

# Build for production
cd apps/web && pnpm build

# Start production server
cd apps/web && pnpm start

# Lint with ESLint
cd apps/web && pnpm lint
```

### API App (FastAPI)

Located in `apps/api/`. Uses `uv` for Python package management:

```bash
# Development server runs on http://localhost:8000 with hot reload
cd apps/api && pnpm dev

# Lint with Ruff
cd apps/api && pnpm lint

# Database migrations
cd apps/api && pnpm db:migrate      # Run pending migrations
cd apps/api && pnpm db:rollback     # Rollback one migration
cd apps/api && pnpm db:revision -m "description"  # Create new migration
```

## Database Architecture

The API uses PostgreSQL with SQLAlchemy 2.0 and asyncpg:

- **Configuration**: `apps/api/src/config.py` - Uses pydantic-settings, reads from `.env` file
- **Engine/Session**: `apps/api/src/database.py` - Async engine and session factory
- **Base Models**: `apps/api/src/models.py` - Declarative base with TimestampMixin and UUIDMixin
- **Migrations**: Alembic configuration in `apps/api/alembic.ini` and `apps/api/alembic/`

Environment variables are loaded from `.env` in the api directory. See `.env.example` for required variables.

## Code Style & Linting

- **Web**: ESLint with `eslint-config-next` (core-web-vitals and typescript configs)
- **API**: Ruff for Python linting

## Path Aliases

- **Web**: `@/*` maps to `./src/*` (configured in `apps/web/tsconfig.json`)
- **API**: Use absolute imports from `src/` (e.g., `from src.config import settings`)
