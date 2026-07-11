from fastapi import FastAPI

from .schemas import HealthResponse

app = FastAPI(title="AccessIQ", version="0.1.0")


@app.get("/", response_model=HealthResponse)
def read_root() -> HealthResponse:
    return HealthResponse(status="ok", service="accessiq")


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="accessiq")
