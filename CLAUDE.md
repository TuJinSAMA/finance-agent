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

## API Architecture (Layered)

The API follows a layered architecture under `apps/api/src/`:

- **`core/`** - Infrastructure: config, database engine/session, exceptions, middleware
- **`models/`** - SQLAlchemy ORM models (base mixins + per-entity modules)
- **`schemas/`** - Pydantic request/response schemas (base + per-entity modules)
- **`services/`** - Business logic layer (one service class per entity)
- **`routers/`** - API route handlers (thin layer, delegates to services)
- **`dependencies.py`** - FastAPI dependency injection (DB session, service factories)
- **`main.py`** - Application entry point, middleware registration, router mounting

### Database

PostgreSQL with SQLAlchemy 2.0 async + asyncpg. Migrations via Alembic (`apps/api/alembic/`).
Environment variables loaded from `.env` (dev) or `.env.prod` (prod). See `.env.example`.

### Adding a New Entity

1. Create model in `src/models/new_entity.py`, re-export in `src/models/__init__.py`
2. Create schemas in `src/schemas/new_entity.py`, re-export in `src/schemas/__init__.py`
3. Create service in `src/services/new_entity.py`
4. Add dependency in `src/dependencies.py`
5. Create router in `src/routers/new_entity.py`, mount in `src/main.py`
6. Generate migration: `pnpm db:revision -m "add new_entity table"`

## Code Style & Linting

- **Web**: ESLint with `eslint-config-next` (core-web-vitals and typescript configs)
- **API**: Ruff for Python linting

## Path Aliases

- **Web**: `@/*` maps to `./src/*` (configured in `apps/web/tsconfig.json`)
- **API**: Use absolute imports from `src/` (e.g., `from src.core.config import settings`)
