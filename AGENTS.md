# AGENTS.md - Guidelines for Agentic Coding Assistants

## Project Overview

AlphaDesk — AI-driven A-share stock recommendation system (MVP). pnpm monorepo managed by Turbo with Next.js 16 frontend and FastAPI backend.

## Build & Development Commands

### Root (pnpm + Turbo)
```bash
pnpm install          # Install all dependencies
pnpm dev              # Start both web and api in dev mode
pnpm build            # Build all apps
pnpm lint             # Lint all apps
```

### Web (apps/web/) - Next.js 16, React 19, TypeScript
```bash
cd apps/web && pnpm dev      # Dev server on http://localhost:3000
cd apps/web && pnpm build    # Production build
cd apps/web && pnpm start    # Start production server
cd apps/web && pnpm lint     # ESLint (Next.js config)
```

### API (apps/api/) - FastAPI, Python 3.12+, uv
```bash
cd apps/api && pnpm dev            # Dev server with hot reload on :8000
cd apps/api && pnpm lint           # Ruff linting
cd apps/api && pnpm db:migrate     # Run pending migrations
cd apps/api && pnpm db:rollback    # Rollback one migration
cd apps/api && pnpm db:revision "msg"  # Create new migration (autogenerate)
```

### Database Backfill
```bash
cd apps/api && uv run python -m scripts.backfill_history --days 180
cd apps/api && uv run python -m scripts.backfill_history --step quotes
```

### Testing
No formal test framework in MVP stage. Test scripts exist in `apps/api/scripts/`:
```bash
cd apps/api && uv run python -m scripts.test_jqdata
cd apps/api && uv run python -m scripts.test_jqdata_news
cd apps/api && uv run python -m scripts.trigger_job <job_id>
```

## Code Style Guidelines

### Python (apps/api/)

**Imports:**
- Order: standard library → third-party → local (src/)
- Use absolute imports from `src/` (e.g., `from src.core.config import settings`)
- Group imports by category with blank lines between groups

**Types:**
- Python 3.12+ type hints everywhere
- Use `Mapped[Type]` for SQLAlchemy columns
- Pydantic v2 for schemas with `model_dump()` (not `.dict()`)
- Return type annotations on all functions

**Naming:**
- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- Leading underscore for private methods: `_helper_function()`
- SQLAlchemy models: singular (`User`, `Stock`)

**Classes & Services:**
- Service pattern: `class UserService` with `db` dependency injected
- Models: inherit from `Base` with `UUIDMixin` or integer PKs
- Use `async/await` with SQLAlchemy async session

**Error Handling:**
- Custom exceptions in `src/core/exceptions.py`
- `AppException` (base), `NotFoundException`, `AlreadyExistsException`
- Raise HTTPExceptions with appropriate status codes
- Try/except with explicit rollback on IntegrityError

**Documentation:**
- Docstrings with `""" triple quotes """` for classes and public methods
- Inline comments in English (codebase uses English + Chinese)

### TypeScript/React (apps/web/)

**Imports:**
- Order: React → Next.js → third-party → local
- Use path alias `@/*` for `./src/*`
- Named exports preferred over default

**Types:**
- TypeScript strict mode enabled
- Use `type` for object types, `interface` for component props
- Explicit return types on functions

**Components:**
- Functional components with hooks only
- Destructure props in parameter: `function Component({ prop }: Props)`
- Use `React.ReactNode` for children prop type

**Naming:**
- `PascalCase` for components
- `camelCase` for functions, variables
- File names match component names

**Styling:**
- Tailwind CSS v4 utility classes
- Use `className` (not `class`)
- Framer Motion for animations

**Files:**
- `.ts` for logic, `.tsx` for React components
- `page.tsx` for Next.js routes, `layout.tsx` for layouts

### General Conventions

**Architecture:**
- Layered: routers → services → models
- Dependency injection via FastAPI `Depends()`
- Pydantic schemas for request/response validation

**Database:**
- SQLAlchemy 2.0 async with `asyncpg`
- Migrations via Alembic (autogenerate)
- Stock tables use integer PKs; user-related tables use UUID

**Environment:**
- `.env` for local dev, `.env.prod` for production
- Pydantic Settings loaded from env files
- See `src/core/config.py` for available settings

**Git:**
- Descriptive commit messages
- No commits unless explicitly requested by user

## Adding New Entity (Checklist)

1. Model: `src/models/new_entity.py` → re-export in `src/models/__init__.py`
2. Schemas: `src/schemas/new_entity.py` → re-export in `src/schemas/__init__.py`
3. Service: `src/services/new_entity.py`
4. Dependency: add to `src/dependencies.py`
5. Router: `src/routers/new_entity.py` → mount in `src/main.py`
6. Migration: `pnpm db:revision "add new_entity table"`

## Key Patterns

**Service Layer:**
```python
class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, id: uuid.UUID) -> User:
        result = await self.db.execute(select(User).where(User.id == id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundException("User", str(id))
        return user
```

**Router Pattern:**
```python
router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=list[UserRead])
async def list_users(service: UserServiceDep):
    return await service.list()
```

**Dependency Injection:**
```python
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
```
