"""This file wires the FastAPI application, middleware, lifespan, and routers."""

# Import logging so the backend has a consistent process-wide log format.
import logging
# Import sys so sibling project packages can be imported in local and container runs.
import sys
# Import asynccontextmanager so FastAPI can run setup and cleanup code.
from contextlib import asynccontextmanager
# Import Path so this module can resolve the current project layout.
from pathlib import Path

# Import FastAPI so this module can create the application object.
from fastapi import FastAPI
# Import CORS middleware so the frontend can call this backend from the browser.
from fastapi.middleware.cors import CORSMiddleware

# Import runtime settings from the dedicated configuration module.
from backend.config import get_settings
# Import LLM lifecycle helpers from the dedicated client module.
from backend.llm_client import close_llm_connection, setup_llm_connection

# Resolve likely project roots for local and container runs.
project_root_candidates = [
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[1],
]

# Add roots that contain milestone packages to Python's import path before route imports.
for project_root in project_root_candidates:
    if (project_root / "Memory").exists() and str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

# Import route modules so this file only registers routers.
from backend.routes import blueprint_routes, chat_routes, classification_routes, repo_routes, status_routes

# Import the Graph router after the project root is available on sys.path.
from Graph.api import router as graph_router
# Import the Memory router after the project root is available on sys.path.
from Memory.api import router as memory_router

# Configure the process-wide logging format.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# Define the FastAPI lifespan hook that connects and disconnects the LLM client.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the LLM connection and run the startup ping.
    await setup_llm_connection()
    # Yield control back to FastAPI so the app can serve requests.
    yield
    # Close the LLM connection when the app shuts down.
    await close_llm_connection()


# Load runtime settings once for app creation and middleware setup.
settings = get_settings()
# Create the FastAPI application object.
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Add CORS middleware so configured frontend origins can call this API.
app.add_middleware(
    # Use FastAPI's standard CORS middleware class.
    CORSMiddleware,
    # Allow only the origins configured in settings.
    allow_origins=settings.cors_origins,
    # Allow cookies and authorization headers when needed.
    allow_credentials=True,
    # Allow all HTTP methods for the API.
    allow_methods=["*"],
    # Allow all request headers for the API.
    allow_headers=["*"],
)

# Register status endpoints.
app.include_router(status_routes.router)
# Register repository ingestion and retrieval endpoints.
app.include_router(repo_routes.router)
# Register prompt classification endpoints.
app.include_router(classification_routes.router)
# Register chat endpoints.
app.include_router(chat_routes.router)
# Register context-aware blueprint endpoints.
app.include_router(blueprint_routes.router)
# Register graph helper endpoints under the backend API namespace.
app.include_router(graph_router, prefix="/api")
# Register Memory endpoints.
app.include_router(memory_router)
