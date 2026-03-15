"""
FacePay — FastAPI app entry point.
Run: uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FacePay API",
    description="Face-based transit boarding and payment",
    version="0.1.0",
)

# CORS: allow frontend dev and production
# Add your exact Vercel URL in Phase 5 (e.g. https://facepay-abc123.vercel.app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        # "https://your-vercel-url.vercel.app",  # uncomment and set when deploying
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — uncomment as each file is created
from routers import auth, embed, gtfs, identify, payments

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(embed.router, tags=["embed"])
app.include_router(identify.router, tags=["identify"])
app.include_router(payments.router, prefix="/pay", tags=["payments"])
app.include_router(gtfs.router, prefix="/gtfs", tags=["gtfs"])


@app.get("/health")
def health():
    """Always returns instantly. Used by Railway and load balancers."""
    return {"status": "ok", "service": "facepay-api"}
