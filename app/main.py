"""FastAPI application entrypoint for the Golden Profile Service."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .database import init_db
from .routers import credential_matches, employees, exclusion_matches, reference, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Golden Profile Service",
    version=__version__,
    description=(
        "Ingests employee, credential-match and exclusion-match data from CAMI, "
        "stores versioned snapshots, and serves as an alternative source of "
        "licensing data for CAMI credentialing searches."
    ),
    lifespan=lifespan,
)

app.include_router(reference.router)
app.include_router(employees.router)
app.include_router(credential_matches.router)
app.include_router(exclusion_matches.router)
app.include_router(search.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": __version__}
