"""
Serviço de persistência no Azure Cosmos DB.
Gerencia operações CRUD para reclamações e log de auditoria.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.cosmos.container import ContainerProxy
from azure.cosmos.database import DatabaseProxy

from src.core.config import get_settings
from src.models.schemas import ComplaintState, WorkflowStatus

logger = logging.getLogger(__name__)


class CosmosService:
    """
    Serviço singleton para operações no Azure Cosmos DB.

    Gerencia dois containers:
    - complaints: Armazena estados de reclamações (partition key: /source)
    - audit_log: Log de eventos para auditoria (partition key: /date)
    """

    def __init__(self):
        self._client: Optional[CosmosClient] = None
        self._database: Optional[DatabaseProxy] = None
        self._complaints_container: Optional[ContainerProxy] = None
        self._audit_container: Optional[ContainerProxy] = None
        self._initialized = False
        self.logger = logging.getLogger("cosmos_service")

    async def initialize(self) -> None:
        """
        Inicializa conexão com Cosmos DB e cria containers se necessário.
        """
        if self._initialized:
            return

        settings = get_settings()

        self.logger.info("Initializing Cosmos DB connection...")

        try:
            # Cria cliente
            self._client = CosmosClient(
                url=settings.cosmos_endpoint,
                credential=settings.cosmos_key,
            )

            # Cria/obtém database
            self._database = self._client.create_database_if_not_exists(
                id=settings.cosmos_database_name
            )
            self.logger.info(f"Database '{settings.cosmos_database_name}' ready")

            # Cria/obtém container de reclamações
            # Nota: Não especificar throughput para contas serverless
            self._complaints_container = self._database.create_container_if_not_exists(
                id="complaints",
                partition_key=PartitionKey(path="/source"),
            )
            self.logger.info("Container 'complaints' ready")

            # Cria/obtém container de auditoria
            self._audit_container = self._database.create_container_if_not_exists(
                id="audit_log",
                partition_key=PartitionKey(path="/date"),
            )
            self.logger.info("Container 'audit_log' ready")

            self._initialized = True
            self.logger.info("Cosmos DB initialized successfully")

        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to initialize Cosmos DB: {e.message}")
            raise

    def _ensure_initialized(self) -> None:
        """Verifica se o serviço foi inicializado."""
        if not self._initialized:
            raise RuntimeError("CosmosService not initialized. Call initialize() first.")

    def _state_to_document(self, state: ComplaintState) -> Dict[str, Any]:
        """
        Converte ComplaintState para documento Cosmos DB.

        Args:
            state: Estado da reclamação

        Returns:
            Documento formatado para Cosmos DB
        """
        complaint_id = state.complaint_raw.id or state.complaint_raw.external_id

        # Serializa para dict usando Pydantic
        doc = state.model_dump(mode="json")

        # Adiciona campos obrigatórios do Cosmos
        doc["id"] = complaint_id
        doc["source"] = state.complaint_raw.source.value  # Partition key

        # Adiciona metadados úteis para queries
        doc["_metadata"] = {
            "status": state.workflow_status.value,
            "category": state.complaint_analyzed.category.value if state.complaint_analyzed else None,
            "team": state.routing_decision.team if state.routing_decision else None,
            "created_at": state.started_at.isoformat() if state.started_at else None,
            "updated_at": datetime.utcnow().isoformat(),
        }

        return doc

    def _document_to_state(self, doc: Dict[str, Any]) -> ComplaintState:
        """
        Converte documento Cosmos DB para ComplaintState.

        Args:
            doc: Documento do Cosmos DB

        Returns:
            ComplaintState reconstruído
        """
        # Remove campos do Cosmos que não fazem parte do modelo
        doc.pop("id", None)
        doc.pop("source", None)
        doc.pop("_metadata", None)
        doc.pop("_rid", None)
        doc.pop("_self", None)
        doc.pop("_etag", None)
        doc.pop("_attachments", None)
        doc.pop("_ts", None)

        return ComplaintState.model_validate(doc)

    async def save_complaint(self, state: ComplaintState) -> str:
        """
        Salva ou atualiza uma reclamação no Cosmos DB.

        Args:
            state: Estado da reclamação a salvar

        Returns:
            ID da reclamação salva
        """
        self._ensure_initialized()

        complaint_id = state.complaint_raw.id or state.complaint_raw.external_id
        doc = self._state_to_document(state)

        try:
            # Upsert para criar ou atualizar
            self._complaints_container.upsert_item(doc)
            self.logger.info(f"Saved complaint {complaint_id} to Cosmos DB")

            # Log de auditoria
            await self.log_event(
                complaint_id=complaint_id,
                event_type="complaint_saved",
                details={
                    "status": state.workflow_status.value,
                    "source": state.complaint_raw.source.value,
                }
            )

            return complaint_id

        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to save complaint {complaint_id}: {e.message}")
            raise

    async def get_complaint(self, complaint_id: str, source: str = None) -> Optional[ComplaintState]:
        """
        Busca uma reclamação pelo ID.

        Args:
            complaint_id: ID da reclamação
            source: Fonte da reclamação (partition key) - opcional se usar cross-partition

        Returns:
            ComplaintState ou None se não encontrado
        """
        self._ensure_initialized()

        try:
            if source:
                # Query com partition key (mais eficiente)
                doc = self._complaints_container.read_item(
                    item=complaint_id,
                    partition_key=source
                )
            else:
                # Cross-partition query (mais lento, mas funciona sem saber a fonte)
                query = "SELECT * FROM c WHERE c.id = @id"
                items = list(self._complaints_container.query_items(
                    query=query,
                    parameters=[{"name": "@id", "value": complaint_id}],
                    enable_cross_partition_query=True
                ))
                if not items:
                    return None
                doc = items[0]

            return self._document_to_state(doc)

        except exceptions.CosmosResourceNotFoundError:
            self.logger.debug(f"Complaint {complaint_id} not found")
            return None
        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to get complaint {complaint_id}: {e.message}")
            raise

    async def list_complaints(
        self,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ComplaintState]:
        """
        Lista reclamações com filtros opcionais.

        Args:
            source: Filtrar por fonte
            status: Filtrar por status do workflow
            limit: Número máximo de resultados
            offset: Offset para paginação

        Returns:
            Lista de ComplaintState
        """
        self._ensure_initialized()

        # Constrói query dinamicamente
        conditions = []
        parameters = []

        if source:
            conditions.append("c.source = @source")
            parameters.append({"name": "@source", "value": source})

        if status:
            conditions.append("c._metadata.status = @status")
            parameters.append({"name": "@status", "value": status})

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM c{where_clause} ORDER BY c._metadata.updated_at DESC OFFSET {offset} LIMIT {limit}"

        try:
            items = list(self._complaints_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=(source is None),
            ))

            return [self._document_to_state(doc) for doc in items]

        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to list complaints: {e.message}")
            raise

    async def update_status(self, complaint_id: str, status: str, source: str = None) -> bool:
        """
        Atualiza apenas o status de uma reclamação.

        Args:
            complaint_id: ID da reclamação
            status: Novo status
            source: Fonte da reclamação (partition key)

        Returns:
            True se atualizado com sucesso
        """
        self._ensure_initialized()

        try:
            # Busca o documento atual
            state = await self.get_complaint(complaint_id, source)
            if not state:
                return False

            # Atualiza status
            state.workflow_status = WorkflowStatus(status)
            if status == WorkflowStatus.COMPLETED.value:
                state.completed_at = datetime.utcnow()

            # Salva
            await self.save_complaint(state)

            # Log de auditoria
            await self.log_event(
                complaint_id=complaint_id,
                event_type="status_updated",
                details={"new_status": status}
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to update status for {complaint_id}: {e}")
            return False

    async def log_event(
        self,
        complaint_id: str,
        event_type: str,
        details: Dict[str, Any],
    ) -> None:
        """
        Registra evento no log de auditoria.

        Args:
            complaint_id: ID da reclamação relacionada
            event_type: Tipo do evento (ex: "complaint_saved", "status_updated")
            details: Detalhes adicionais do evento
        """
        self._ensure_initialized()

        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")

        event_doc = {
            "id": f"{complaint_id}-{event_type}-{now.timestamp()}",
            "date": date_str,  # Partition key
            "complaint_id": complaint_id,
            "event_type": event_type,
            "timestamp": now.isoformat(),
            "details": details,
        }

        try:
            self._audit_container.create_item(event_doc)
            self.logger.debug(f"Logged event {event_type} for complaint {complaint_id}")

        except exceptions.CosmosHttpResponseError as e:
            # Log de auditoria não deve falhar a operação principal
            self.logger.warning(f"Failed to log audit event: {e.message}")

    async def get_audit_log(
        self,
        complaint_id: Optional[str] = None,
        event_type: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Busca eventos no log de auditoria.

        Args:
            complaint_id: Filtrar por reclamação
            event_type: Filtrar por tipo de evento
            date: Filtrar por data (formato: YYYY-MM-DD)
            limit: Número máximo de resultados

        Returns:
            Lista de eventos
        """
        self._ensure_initialized()

        conditions = []
        parameters = []

        if complaint_id:
            conditions.append("c.complaint_id = @complaint_id")
            parameters.append({"name": "@complaint_id", "value": complaint_id})

        if event_type:
            conditions.append("c.event_type = @event_type")
            parameters.append({"name": "@event_type", "value": event_type})

        if date:
            conditions.append("c.date = @date")
            parameters.append({"name": "@date", "value": date})

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM c{where_clause} ORDER BY c.timestamp DESC OFFSET 0 LIMIT {limit}"

        try:
            items = list(self._audit_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=(date is None),
            ))

            # Remove campos internos do Cosmos
            for item in items:
                item.pop("_rid", None)
                item.pop("_self", None)
                item.pop("_etag", None)
                item.pop("_attachments", None)
                item.pop("_ts", None)

            return items

        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to get audit log: {e.message}")
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do banco de dados.

        Returns:
            Dict com estatísticas
        """
        self._ensure_initialized()

        try:
            # Busca todos os documentos e calcula estatísticas em memória
            # (GROUP BY cross-partition não é bem suportado no Cosmos DB serverless)
            query = "SELECT c.source, c._metadata.status FROM c"
            items = list(self._complaints_container.query_items(
                query=query,
                enable_cross_partition_query=True,
            ))

            by_status: Dict[str, int] = {}
            by_source: Dict[str, int] = {}

            for item in items:
                # Por status
                status = item.get("_metadata", {}).get("status") if isinstance(item.get("_metadata"), dict) else None
                if status:
                    by_status[status] = by_status.get(status, 0) + 1

                # Por fonte
                source = item.get("source")
                if source:
                    by_source[source] = by_source.get(source, 0) + 1

            return {
                "total": len(items),
                "by_status": by_status,
                "by_source": by_source,
            }

        except exceptions.CosmosHttpResponseError as e:
            self.logger.error(f"Failed to get stats: {e.message}")
            return {"total": 0, "by_status": {}, "by_source": {}}

    def is_initialized(self) -> bool:
        """Retorna se o serviço está inicializado."""
        return self._initialized


# Singleton instance
_cosmos_service: Optional[CosmosService] = None


def get_cosmos_service() -> CosmosService:
    """
    Factory function para obter o serviço Cosmos DB.

    Returns:
        Instância singleton do CosmosService
    """
    global _cosmos_service
    if _cosmos_service is None:
        _cosmos_service = CosmosService()
    return _cosmos_service
