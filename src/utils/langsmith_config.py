"""
Configuração e utilitários para LangSmith tracing.
Fornece funções para verificar status e criar runs com metadata.
"""

import logging
import os
from typing import Any, Dict, Optional
from functools import lru_cache

from langsmith import Client
from langchain.callbacks.tracers import LangChainTracer
from langchain.callbacks.manager import CallbackManager

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class LangSmithConfig:
    """Configuração e utilitários para LangSmith."""

    _instance: Optional["LangSmithConfig"] = None
    _client: Optional[Client] = None
    _tracer: Optional[LangChainTracer] = None

    def __new__(cls) -> "LangSmithConfig":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Inicializa a configuração."""
        if self._initialized:
            return

        self.settings = get_settings()
        self._setup_environment()
        self._initialized = True

    def _setup_environment(self) -> None:
        """Configura variáveis de ambiente para LangSmith."""
        # Garante que as variáveis estão setadas
        os.environ["LANGCHAIN_TRACING_V2"] = str(self.settings.langchain_tracing_v2).lower()
        os.environ["LANGCHAIN_ENDPOINT"] = self.settings.langchain_endpoint
        os.environ["LANGCHAIN_API_KEY"] = self.settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = self.settings.langchain_project

        logger.debug(f"LangSmith environment configured for project: {self.settings.langchain_project}")

    def is_enabled(self) -> bool:
        """
        Verifica se o LangSmith está habilitado.

        Returns:
            True se tracing está ativo
        """
        return self.settings.langchain_tracing_v2 and bool(self.settings.langchain_api_key)

    def get_client(self) -> Optional[Client]:
        """
        Obtém cliente LangSmith.

        Returns:
            Cliente LangSmith ou None se não configurado
        """
        if not self.is_enabled():
            return None

        if self._client is None:
            try:
                self._client = Client(
                    api_url=self.settings.langchain_endpoint,
                    api_key=self.settings.langchain_api_key,
                )
            except Exception as e:
                logger.warning(f"Failed to create LangSmith client: {e}")
                return None

        return self._client

    def get_tracer(self, project_name: Optional[str] = None) -> Optional[LangChainTracer]:
        """
        Obtém tracer configurado para LangSmith.

        Args:
            project_name: Nome do projeto (opcional, usa config se não fornecido)

        Returns:
            LangChainTracer configurado ou None
        """
        if not self.is_enabled():
            return None

        project = project_name or self.settings.langchain_project

        try:
            return LangChainTracer(
                project_name=project,
                client=self.get_client(),
            )
        except Exception as e:
            logger.warning(f"Failed to create LangSmith tracer: {e}")
            return None

    def get_callback_manager(
        self,
        run_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list] = None,
    ) -> Optional[CallbackManager]:
        """
        Cria CallbackManager com tracer LangSmith.

        Args:
            run_name: Nome identificador do run
            metadata: Metadados customizados
            tags: Tags para categorização

        Returns:
            CallbackManager configurado ou None
        """
        tracer = self.get_tracer()
        if tracer is None:
            return None

        # Configura metadata e tags no tracer
        if metadata:
            tracer.metadata = metadata
        if tags:
            tracer.tags = tags
        if run_name:
            tracer.run_name = run_name

        return CallbackManager([tracer])

    async def verify_connection(self) -> Dict[str, Any]:
        """
        Verifica conexão com LangSmith.

        Returns:
            Dict com status da conexão
        """
        result = {
            "enabled": self.is_enabled(),
            "project": self.settings.langchain_project,
            "endpoint": self.settings.langchain_endpoint,
            "connected": False,
            "error": None,
        }

        if not self.is_enabled():
            result["error"] = "LangSmith tracing not enabled"
            return result

        client = self.get_client()
        if client is None:
            result["error"] = "Failed to create client"
            return result

        try:
            # Tenta listar projetos para verificar conexão
            # list_projects() retorna um generator, precisamos consumir
            projects = list(client.list_projects(limit=1))
            result["connected"] = True
            result["projects_accessible"] = len(projects) >= 0
        except Exception as e:
            result["error"] = str(e)

        return result

    def get_run_config(
        self,
        run_name: str,
        complaint_id: Optional[str] = None,
        source: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cria configuração para um run com metadata.

        Args:
            run_name: Nome do run (ex: "analyze_complaint")
            complaint_id: ID da reclamação
            source: Fonte da reclamação
            extra_metadata: Metadados adicionais

        Returns:
            Dict de configuração para passar ao LLM
        """
        if not self.is_enabled():
            return {}

        metadata = {
            "application": "reclamaai",
            "version": "0.1.0",
        }

        if complaint_id:
            metadata["complaint_id"] = complaint_id
        if source:
            metadata["source"] = source
        if extra_metadata:
            metadata.update(extra_metadata)

        tags = ["reclamaai"]
        if source:
            tags.append(f"source:{source}")

        return {
            "run_name": run_name,
            "metadata": metadata,
            "tags": tags,
        }


# Singleton instance
_config: Optional[LangSmithConfig] = None


def get_langsmith_config() -> LangSmithConfig:
    """
    Factory function para obter configuração LangSmith.

    Returns:
        Instância do LangSmithConfig
    """
    global _config
    if _config is None:
        _config = LangSmithConfig()
    return _config


def is_langsmith_enabled() -> bool:
    """
    Verifica rapidamente se LangSmith está habilitado.

    Returns:
        True se habilitado
    """
    return get_langsmith_config().is_enabled()


async def verify_langsmith_connection() -> Dict[str, Any]:
    """
    Verifica conexão com LangSmith.

    Returns:
        Dict com status
    """
    return await get_langsmith_config().verify_connection()
