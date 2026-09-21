"""
FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on the path when running from project directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Multi-Agent Urban Traffic Signal Synchronization System",
    description=(
        "Decentralized multi-agent system for emergency vehicle priority. "
        "Five Traffic Signal Agents coordinate via an in-process message bus. "
        "An Emergency Vehicle Agent uses A* to plan routes and create a green corridor."
    ),
    version="1.0.0",
)

# Allow the React dev server (Vite default port 5173) to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": "Multi-Agent Traffic Signal API",
        "version": "1.0.0",
        "docs": "/docs",
    }
