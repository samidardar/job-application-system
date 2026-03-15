from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.config import settings
from app.database import engine, Base

# Import models so Base.metadata includes all tables
import app.models.site_credential  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables, then patch enum types with new values
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add new platform values added after initial migration
        for val in ("francetravail", "bonne_alternance"):
            try:
                await conn.execute(
                    text(f"ALTER TYPE jobplatformenum ADD VALUE IF NOT EXISTS '{val}'")
                )
            except Exception:
                pass
    yield
    await engine.dispose()


app = FastAPI(
    title="Postulio API",
    description="AI-powered job application platform for France",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    # Only add HSTS in production (not during local dev over HTTP)
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Register routers
from app.api import auth, users, cv, jobs, applications, documents, pipeline, dashboard

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(cv.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(pipeline.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Postulio"}
