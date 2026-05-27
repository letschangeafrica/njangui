"""
Njangui — FastAPI application entry point.

This file:
  1. Creates the FastAPI app instance with full OpenAPI metadata
  2. Registers middleware (CORS)
  3. Mounts all routers under their URL prefixes
  4. Defines the /health endpoint
  5. Overrides the default 422 handler to return French error messages
     in the same shape as all other API errors

To run locally:
    uvicorn app.main:app --reload

To run in production (via Docker):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import auth as auth_router
from app.routers import providers as providers_router


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan — startup / shutdown logic
# ═══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup (before the first request) and once on shutdown.

    Startup: log environment so it's obvious at a glance what mode we're in.
    Shutdown: nothing to close yet (SQLAlchemy pool disposes itself).
    """
    env   = settings.ENVIRONMENT
    debug = settings.DEBUG
    print(f"\n{'='*55}")
    print(f"  {settings.APP_NAME} API — starting")
    print(f"  Environment : {env}")
    print(f"  Debug mode  : {debug}")
    if debug:
        print("  WARNING: DEBUG=True — OTP codes visible in responses. Never use in production.")
    print(f"{'='*55}\n")
    yield
    print(f"\n[{settings.APP_NAME}] shutting down.\n")


# ═══════════════════════════════════════════════════════════════════════════════
# App instance
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "**Njangui** — Informal Economy Reputation Infrastructure for Cameroon.\n\n"
        "A lightweight, offline-first portable professional identity layer that turns "
        "real-world transactions into verified reputations for Cameroonian informal workers.\n\n"
        "### Authentication flow\n"
        "1. `POST /auth/otp/request` — request a 6-digit OTP sent to your phone\n"
        "2. `POST /auth/register` *(new users)* or `POST /auth/login` *(returning users)*\n"
        "3. Include the returned `access_token` as `Authorization: Bearer <token>` "
        "on protected routes\n\n"
        "All error messages are in French."
    ),
    version="0.1.0",
    lifespan=lifespan,
    # In production, disable the interactive docs to reduce attack surface.
    # Set ENVIRONMENT=production to hide them.
    docs_url="/docs"   if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Middleware
# ═══════════════════════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    # In development: allow all origins (Flutter dev server / Postman / etc.)
    # In production: replace "*" with your actual domain(s) e.g. ["https://njangui.cm"]
    allow_origins=["*"] if settings.ENVIRONMENT != "production" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Exception handlers
# ═══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Override FastAPI's default 422 handler.

    Default FastAPI returns a nested `detail` list which is hard to display
    in the mobile app. This flattens it into a single human-readable French
    string, consistent with all other API error responses.

    Example output:
        {"detail": "phone_number: Numéro invalide. Format requis: +237XXXXXXXXX"}
    """
    errors = exc.errors()
    if errors:
        first = errors[0]
        # loc is a tuple like ("body", "phone_number") — take the last meaningful part
        field = first["loc"][-1] if first["loc"] else "champ"
        message = first["msg"].replace("Value error, ", "")  # strip Pydantic prefix
        detail = f"{field}: {message}"
    else:
        detail = "Données invalides."

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Routers
# ═══════════════════════════════════════════════════════════════════════════════

app.include_router(
    auth_router.router,
    prefix="/auth",
    tags=["Auth"],
)

app.include_router(
    providers_router.router,
    prefix="/providers",
    tags=["Providers"],
)

# Phase 3 routers — added here as each module is built:
# app.include_router(transactions_router.router, prefix="/transactions", tags=["Transactions"])
# app.include_router(ratings_router.router, prefix="/ratings", tags=["Ratings"])
# app.include_router(flags_router.router, prefix="/flags", tags=["Fraud Flags"])


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    description="Returns 200 when the API is up. Used by Docker, load balancers, and CI.",
)
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}
