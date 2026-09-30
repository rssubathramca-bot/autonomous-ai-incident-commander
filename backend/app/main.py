from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Incident Commander API",
    version="0.1.0",
    description="Phase 1 foundation API for the Autonomous AI-Powered Incident Commander.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return a deterministic liveness response for the foundation service."""
    return {
        "status": "ok",
        "service": "incident-commander-api",
        "phase": "foundation",
    }
