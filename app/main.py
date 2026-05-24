from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Informal Economy Reputation Infrastructure for Cameroon",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


# ── Registered routers ───────────────────────────────────────────────────────
from app.routers import auth  # noqa: E402

app.include_router(auth.router, prefix="/auth", tags=["Auth"])

# Coming next:
# from app.routers import providers, transactions, search, prices
# app.include_router(providers.router,    prefix="/providers",    tags=["Providers"])
# app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
# app.include_router(search.router,       prefix="/search",       tags=["Search"])
# app.include_router(prices.router,       prefix="/prices",       tags=["Prices"])
