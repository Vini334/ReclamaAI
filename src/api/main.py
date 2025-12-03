"""
API Principal do ReclamaAI.
FastAPI application com endpoints para processamento de reclamações.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import complaints, health
from src.core.config import get_settings
from src.utils.langsmith_config import get_langsmith_config, verify_langsmith_connection

settings = get_settings()

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    logger.info("=" * 60)
    logger.info("Iniciando ReclamaAI API...")
    logger.info("=" * 60)
    logger.info(f"Ambiente: {settings.environment}")

    # Verifica LangSmith
    langsmith_config = get_langsmith_config()
    if langsmith_config.is_enabled():
        logger.info("LangSmith Tracing: ENABLED")
        logger.info(f"  Project: {settings.langchain_project}")
        logger.info(f"  Endpoint: {settings.langchain_endpoint}")

        # Tenta verificar conexão
        try:
            connection_status = await verify_langsmith_connection()
            if connection_status.get("connected"):
                logger.info("  Status: ✓ Conectado ao LangSmith")
            else:
                error = connection_status.get("error", "Unknown error")
                logger.warning(f"  Status: ✗ Não conectado ({error})")
        except Exception as e:
            logger.warning(f"  Status: ✗ Erro ao verificar ({e})")
    else:
        logger.info("LangSmith Tracing: DISABLED")
        logger.info("  Configure LANGCHAIN_API_KEY e LANGCHAIN_TRACING_V2=true para habilitar")

    logger.info("=" * 60)
    yield
    logger.info("Encerrando ReclamaAI API...")


app = FastAPI(
    title="ReclamaAI",
    description="Sistema multiagente para gestão automática de reclamações",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas
app.include_router(health.router, tags=["Health"])
app.include_router(complaints.router, prefix="/api/v1", tags=["Complaints"])


@app.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "name": "ReclamaAI",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }
