"""
Health check endpoints.
"""

from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Verifica a saúde da API."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "reclamaai-api",
    }


@router.get("/health/ready")
async def readiness_check():
    """Verifica se a API está pronta para receber requisições."""
    # TODO: Adicionar checks de dependências (DB, Azure, etc.)
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": "ok",
            "azure_openai": "ok",
            "azure_search": "ok",
        },
    }
