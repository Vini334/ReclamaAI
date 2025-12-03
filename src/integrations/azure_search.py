"""
Cliente para Azure AI Search (RAG).
Gerencia busca semântica de times para roteamento.
"""

import logging
from typing import Any, Dict, List, Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)

from src.core.config import get_settings
from src.models.schemas import TeamInfo

logger = logging.getLogger(__name__)


class SearchError(Exception):
    """Exceção para erros de busca."""
    pass


class AzureSearchClient:
    """Cliente para busca semântica de times."""

    _instance: Optional["AzureSearchClient"] = None

    def __new__(cls) -> "AzureSearchClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Inicializa cliente Azure Search."""
        if self._initialized:
            return

        self.settings = get_settings()
        self.credential = AzureKeyCredential(self.settings.azure_search_api_key)
        self.client = self._create_client()
        self.index_client = self._create_index_client()
        self._initialized = True
        logger.info("Azure Search client initialized")

    def _create_client(self) -> SearchClient:
        """
        Cria cliente de busca.

        Returns:
            SearchClient configurado
        """
        return SearchClient(
            endpoint=self.settings.azure_search_endpoint,
            index_name=self.settings.azure_search_index_name,
            credential=self.credential,
        )

    def _create_index_client(self) -> SearchIndexClient:
        """
        Cria cliente para gerenciamento de índices.

        Returns:
            SearchIndexClient configurado
        """
        return SearchIndexClient(
            endpoint=self.settings.azure_search_endpoint,
            credential=self.credential,
        )

    async def search_team(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 3
    ) -> List[TeamInfo]:
        """
        Busca times relevantes para a reclamação.

        Args:
            query: Texto da reclamação para busca semântica
            category: Categoria classificada pelo analista
            top_k: Número de resultados

        Returns:
            Lista de TeamInfo ordenada por relevância
        """
        try:
            # Constrói filtro se categoria fornecida
            filter_str = None
            if category:
                # Busca exata na lista de categorias
                filter_str = f"categories/any(c: c eq '{category}')"

            # Executa busca
            results = self.client.search(
                search_text=query,
                filter=filter_str,
                top=top_k,
                include_total_count=True,
            )

            teams = []
            for result in results:
                team = self._result_to_team(result)
                if team:
                    teams.append(team)

            logger.debug(f"Search found {len(teams)} teams for query: {query[:50]}...")
            return teams

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise SearchError(f"Search failed: {e}")

    def _result_to_team(self, result: Dict[str, Any]) -> Optional[TeamInfo]:
        """
        Converte resultado de busca para TeamInfo.

        Args:
            result: Resultado do Azure Search

        Returns:
            TeamInfo ou None
        """
        try:
            return TeamInfo(
                id=result.get("id", ""),
                name=result.get("name", ""),
                email=result.get("email", ""),
                manager=result.get("manager", ""),
                description=result.get("description", ""),
                responsibilities=result.get("responsibilities", []),
                categories=result.get("categories", []),
                sla_hours={
                    "baixa": result.get("sla_baixa", 72),
                    "media": result.get("sla_media", 48),
                    "alta": result.get("sla_alta", 24),
                    "critica": result.get("sla_critica", 4),
                },
                example_cases=result.get("example_cases", []),
            )
        except Exception as e:
            logger.warning(f"Failed to parse team result: {e}")
            return None

    async def get_team_by_id(self, team_id: str) -> Optional[TeamInfo]:
        """
        Busca time específico por ID.

        Args:
            team_id: ID do time

        Returns:
            TeamInfo ou None
        """
        try:
            result = self.client.get_document(key=team_id)
            return self._result_to_team(result)
        except Exception as e:
            logger.warning(f"Team {team_id} not found: {e}")
            return None

    async def get_team_by_category(self, category: str) -> Optional[TeamInfo]:
        """
        Busca time que atende uma categoria específica.

        Args:
            category: Nome da categoria

        Returns:
            TeamInfo ou None
        """
        teams = await self.search_team(category, category=category, top_k=1)
        return teams[0] if teams else None

    async def index_teams(self, teams: List[TeamInfo]) -> int:
        """
        Indexa times no Azure Search.

        Args:
            teams: Lista de TeamInfo para indexar

        Returns:
            Número de documentos indexados
        """
        try:
            documents = []
            for team in teams:
                doc = {
                    "id": team.id,
                    "name": team.name,
                    "email": team.email,
                    "manager": team.manager,
                    "description": team.description,
                    "responsibilities": team.responsibilities,
                    "categories": team.categories,
                    "example_cases": team.example_cases,
                    "sla_baixa": team.sla_hours.get("baixa", 72),
                    "sla_media": team.sla_hours.get("media", 48),
                    "sla_alta": team.sla_hours.get("alta", 24),
                    "sla_critica": team.sla_hours.get("critica", 4),
                }
                documents.append(doc)

            result = self.client.upload_documents(documents=documents)
            succeeded = sum(1 for r in result if r.succeeded)
            logger.info(f"Indexed {succeeded}/{len(documents)} teams")
            return succeeded

        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            raise SearchError(f"Indexing failed: {e}")

    async def create_index(self) -> bool:
        """
        Cria o índice teams-index no Azure Search.

        Returns:
            True se criado com sucesso
        """
        try:
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="name", type=SearchFieldDataType.String),
                SimpleField(name="email", type=SearchFieldDataType.String),
                SimpleField(name="manager", type=SearchFieldDataType.String),
                SearchableField(name="description", type=SearchFieldDataType.String),
                SearchableField(
                    name="responsibilities",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                ),
                SearchableField(
                    name="categories",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                    filterable=True,
                ),
                SearchableField(
                    name="example_cases",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                ),
                SimpleField(name="sla_baixa", type=SearchFieldDataType.Int32),
                SimpleField(name="sla_media", type=SearchFieldDataType.Int32),
                SimpleField(name="sla_alta", type=SearchFieldDataType.Int32),
                SimpleField(name="sla_critica", type=SearchFieldDataType.Int32),
            ]

            index = SearchIndex(
                name=self.settings.azure_search_index_name,
                fields=fields,
            )

            self.index_client.create_or_update_index(index)
            logger.info(f"Index '{self.settings.azure_search_index_name}' created/updated")
            return True

        except Exception as e:
            logger.error(f"Index creation failed: {e}")
            raise SearchError(f"Index creation failed: {e}")

    async def delete_index(self) -> bool:
        """
        Deleta o índice.

        Returns:
            True se deletado
        """
        try:
            self.index_client.delete_index(self.settings.azure_search_index_name)
            logger.info(f"Index '{self.settings.azure_search_index_name}' deleted")
            return True
        except Exception as e:
            logger.warning(f"Index deletion failed: {e}")
            return False

    async def health_check(self) -> bool:
        """
        Verifica conectividade com Azure Search.

        Returns:
            True se conectado
        """
        try:
            # Tenta listar índices
            list(self.index_client.list_indexes())
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_index_info(self) -> Dict[str, str]:
        """
        Retorna informações do índice configurado.

        Returns:
            Dict com informações
        """
        return {
            "endpoint": self.settings.azure_search_endpoint,
            "index_name": self.settings.azure_search_index_name,
        }


# Factory function
_client: Optional[AzureSearchClient] = None


def get_search_client() -> AzureSearchClient:
    """
    Factory function para obter cliente.

    Returns:
        Instância do AzureSearchClient
    """
    global _client
    if _client is None:
        _client = AzureSearchClient()
    return _client
