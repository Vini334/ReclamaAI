"""
Orquestrador do workflow de processamento de reclamações.
Versão simplificada sem LangGraph para compatibilidade com Python 3.8.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agents import (
    get_analyst_agent,
    get_collector_agent,
    get_communicator_agent,
    get_privacy_agent,
    get_router_agent,
)
from src.models.schemas import (
    ComplaintRaw,
    ComplaintState,
    WorkflowStatus,
)

if TYPE_CHECKING:
    from src.services.cosmos_service import CosmosService

logger = logging.getLogger(__name__)


class ComplaintOrchestrator:
    """
    Orquestrador do workflow de processamento de reclamações.

    Coordena a execução dos agentes na sequência:
    1. Collector -> 2. Privacy -> 3. Analyst -> 4. Router -> 5. Communicator

    Nota: Esta versão não usa LangGraph para compatibilidade com Python 3.8.
    Para usar LangGraph, atualize para Python 3.9+.
    """

    def __init__(self, use_azure_search: bool = False, enable_persistence: bool = True):
        """
        Inicializa o orquestrador.

        Args:
            use_azure_search: Se True, Router usa Azure AI Search para RAG
            enable_persistence: Se True, salva estado no Cosmos DB após cada step
        """
        self.use_azure_search = use_azure_search
        self.enable_persistence = enable_persistence
        self._initialized = False
        self.logger = logging.getLogger("orchestrator")

        # Agentes
        self.collector = None
        self.privacy = None
        self.analyst = None
        self.router = None
        self.communicator = None

        # Cosmos DB service (lazy loaded)
        self._cosmos: Optional["CosmosService"] = None

        # Estatísticas
        self._stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "by_status": {},
        }

    async def initialize(self) -> None:
        """Inicializa agentes."""
        if self._initialized:
            return

        self.logger.info("Initializing orchestrator...")

        # Inicializa agentes
        self.collector = get_collector_agent()
        self.privacy = get_privacy_agent()
        self.analyst = get_analyst_agent()
        self.router = get_router_agent(use_azure_search=self.use_azure_search)
        self.communicator = get_communicator_agent()

        # Inicializa cada agente
        await self.collector.initialize()
        await self.privacy.initialize()
        await self.analyst.initialize()
        await self.router.initialize()
        await self.communicator.initialize()

        # Inicializa Cosmos DB se persistência habilitada
        if self.enable_persistence:
            try:
                from src.services.cosmos_service import get_cosmos_service
                self._cosmos = get_cosmos_service()
                await self._cosmos.initialize()
                self.logger.info("Cosmos DB persistence enabled")
            except Exception as e:
                self.logger.warning(f"Cosmos DB initialization failed, persistence disabled: {e}")
                self._cosmos = None

        self._initialized = True
        self.logger.info("Orchestrator initialized successfully")

    async def process_complaint(self, complaint: ComplaintRaw) -> ComplaintState:
        """
        Processa uma única reclamação através do workflow.

        Args:
            complaint: Reclamação bruta a processar

        Returns:
            ComplaintState final
        """
        if not self._initialized:
            await self.initialize()

        # Cria estado inicial
        state = await self.collector.collect_single(complaint)

        self.logger.info(
            f"Processing complaint {state.complaint_raw.id} "
            f"from {complaint.source.value}"
        )

        # Executa workflow sequencial
        state = await self._execute_workflow(state)

        # Atualiza estatísticas
        self._update_stats(state)

        return state

    async def _save_state(self, state: ComplaintState, step_name: str) -> None:
        """
        Salva estado no Cosmos DB após cada step.

        Args:
            state: Estado atual
            step_name: Nome do step para logging
        """
        if self._cosmos is None:
            return

        try:
            complaint_id = state.complaint_raw.id or state.complaint_raw.external_id
            await self._cosmos.save_complaint(state)
            await self._cosmos.log_event(
                complaint_id=complaint_id,
                event_type=f"step_{step_name}",
                details={
                    "status": state.workflow_status.value,
                    "step": step_name,
                }
            )
            self.logger.debug(f"State saved after step '{step_name}'")
        except Exception as e:
            self.logger.warning(f"Failed to save state after step '{step_name}': {e}")

    async def _execute_workflow(self, state: ComplaintState) -> ComplaintState:
        """
        Executa o workflow de processamento.

        Args:
            state: Estado inicial

        Returns:
            Estado final
        """
        complaint_id = state.complaint_raw.id or state.complaint_raw.external_id

        # Step 1: Anonymize (LGPD compliance)
        self.logger.debug(f"Step 1: Anonymizing complaint {complaint_id}")
        state = await self.privacy.process_state(state)
        await self._save_state(state, "anonymize")

        # Step 2: Analyze (using anonymized data)
        self.logger.debug(f"Step 2: Analyzing complaint {complaint_id}")
        state = await self.analyst.execute(state)
        await self._save_state(state, "analyze")

        if state.workflow_status == WorkflowStatus.FAILED_LLM:
            self.logger.warning(f"Analysis failed for {complaint_id}")
            return state

        # Step 3: Route
        self.logger.debug(f"Step 3: Routing complaint {complaint_id}")
        state = await self.router.execute(state)
        await self._save_state(state, "route")

        if state.workflow_status == WorkflowStatus.FAILED_ROUTING:
            self.logger.warning(f"Routing failed for {complaint_id}")
            return state

        # Step 4: Communicate (create ticket + notify)
        self.logger.debug(f"Step 4: Communicating for complaint {complaint_id}")
        state = await self.communicator.execute(state)
        await self._save_state(state, "communicate")

        return state

    async def process_batch(
        self,
        complaints: Optional[List[ComplaintRaw]] = None,
        limit: Optional[int] = None,
        source_filter: Optional[str] = None,
    ) -> List[ComplaintState]:
        """
        Processa lote de reclamações.

        Args:
            complaints: Lista de reclamações ou None para carregar do mock
            limit: Limite de reclamações a processar
            source_filter: Filtro por fonte (ex: "reclame_aqui")

        Returns:
            Lista de ComplaintState finais
        """
        if not self._initialized:
            await self.initialize()

        # Carrega reclamações se não fornecidas
        if complaints is None:
            states = await self.collector.execute(None)

            # Aplica filtro de fonte se especificado
            if source_filter:
                states = [
                    s for s in states
                    if s.complaint_raw.source.value == source_filter
                ]

            # Aplica limite
            if limit:
                states = states[:limit]
        else:
            states = [
                await self.collector.collect_single(c)
                for c in (complaints[:limit] if limit else complaints)
            ]

        self.logger.info(f"Processing batch of {len(states)} complaints")

        # Processa cada reclamação
        results = []
        for i, state in enumerate(states):
            try:
                self.logger.info(
                    f"Processing {i+1}/{len(states)}: "
                    f"{state.complaint_raw.id or state.complaint_raw.external_id}"
                )

                result = await self._execute_workflow(state)

                self._update_stats(result)
                results.append(result)

            except Exception as e:
                self.logger.error(f"Failed to process complaint: {e}")
                state.workflow_status = WorkflowStatus.FAILED_LLM
                state.errors.append(str(e))
                results.append(state)
                self._update_stats(state)

        return results

    def _update_stats(self, state: ComplaintState) -> None:
        """Atualiza estatísticas internas."""
        self._stats["total_processed"] += 1

        status = state.workflow_status.value
        self._stats["by_status"][status] = self._stats["by_status"].get(status, 0) + 1

        if state.workflow_status == WorkflowStatus.COMPLETED:
            self._stats["successful"] += 1
        elif state.workflow_status.value.startswith("FAILED"):
            self._stats["failed"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do orquestrador.

        Returns:
            Dict com estatísticas
        """
        return {
            **self._stats,
            "agents": {
                "collector": self.collector.get_status() if self.collector else None,
                "privacy": self.privacy.get_status() if self.privacy else None,
                "analyst": self.analyst.get_status() if self.analyst else None,
                "router": self.router.get_status() if self.router else None,
                "communicator": self.communicator.get_status() if self.communicator else None,
            }
        }

    def reset_stats(self) -> None:
        """Reseta estatísticas."""
        self._stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "by_status": {},
        }


# Singleton instance
_orchestrator: Optional[ComplaintOrchestrator] = None


def get_orchestrator(
    use_azure_search: bool = False,
    enable_persistence: bool = True,
) -> ComplaintOrchestrator:
    """
    Factory function para obter o orquestrador.

    Args:
        use_azure_search: Se True, habilita RAG com Azure AI Search
        enable_persistence: Se True, salva estado no Cosmos DB

    Returns:
        Instância do ComplaintOrchestrator
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ComplaintOrchestrator(
            use_azure_search=use_azure_search,
            enable_persistence=enable_persistence,
        )
    return _orchestrator


async def process_single_complaint(complaint: ComplaintRaw) -> ComplaintState:
    """
    Função de conveniência para processar uma reclamação.

    Args:
        complaint: Reclamação a processar

    Returns:
        Estado final
    """
    orchestrator = get_orchestrator()
    return await orchestrator.process_complaint(complaint)
