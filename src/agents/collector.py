"""
Agente Coletor (Collector Agent).
Responsável por ingerir reclamações de múltiplas fontes.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from src.agents.base import AgentError, BaseAgent
from src.models.schemas import (
    ComplaintRaw,
    ComplaintSource,
    ComplaintState,
    WorkflowStatus,
)
# Import directly to avoid circular import through src.services
from src.services.mock_data_loader import get_data_loader

logger = logging.getLogger(__name__)


class CollectorAgent(BaseAgent[Optional[List[ComplaintSource]], List[ComplaintState]]):
    """
    Agente responsável por coletar reclamações das fontes configuradas.

    No MVP, coleta dos arquivos mock JSON.
    Em produção, integraria com APIs reais (Reclame Aqui, Jira, etc).
    """

    def __init__(self):
        """Inicializa o agente coletor."""
        super().__init__("collector")
        self.data_loader = None

    async def initialize(self) -> None:
        """Inicializa o data loader."""
        self.data_loader = get_data_loader()
        self.logger.info("Collector agent initialized with mock data loader")

    async def validate_input(self, input_data: Optional[List[ComplaintSource]]) -> bool:
        """
        Valida as fontes de dados solicitadas.

        Args:
            input_data: Lista de fontes ou None para todas

        Returns:
            True sempre (None significa todas as fontes)
        """
        if input_data is None:
            return True

        # Verifica se todas as fontes são válidas
        valid_sources = set(ComplaintSource)
        for source in input_data:
            if source not in valid_sources:
                self.logger.warning(f"Invalid source: {source}")
                return False
        return True

    async def process(
        self, sources: Optional[List[ComplaintSource]] = None
    ) -> List[ComplaintState]:
        """
        Coleta reclamações das fontes especificadas.

        Args:
            sources: Lista de fontes ou None para todas

        Returns:
            Lista de ComplaintState prontos para processamento
        """
        if self.data_loader is None:
            raise AgentError("Data loader not initialized", self.name)

        # Carrega reclamações brutas
        complaints = self.data_loader.load_all_complaints(sources)
        self.logger.info(f"Loaded {len(complaints)} complaints from sources")

        # Converte para ComplaintState
        states = []
        for complaint in complaints:
            # Gera ID interno se não existir
            if not complaint.id:
                complaint.id = str(uuid.uuid4())

            state = ComplaintState(
                complaint_raw=complaint,
                workflow_status=WorkflowStatus.NEW,
                started_at=datetime.utcnow(),
            )
            states.append(state)

        self.logger.info(f"Created {len(states)} complaint states")
        return states

    async def collect_single(self, complaint: ComplaintRaw) -> ComplaintState:
        """
        Cria estado para uma reclamação individual.

        Útil para processamento via API ou em tempo real.

        Args:
            complaint: Reclamação bruta

        Returns:
            ComplaintState inicializado
        """
        if not complaint.id:
            complaint.id = str(uuid.uuid4())

        state = ComplaintState(
            complaint_raw=complaint,
            workflow_status=WorkflowStatus.NEW,
            started_at=datetime.utcnow(),
        )

        self.logger.info(
            f"Created state for complaint {complaint.id} from {complaint.source.value}"
        )
        return state

    async def collect_by_source(self, source: ComplaintSource) -> List[ComplaintState]:
        """
        Coleta reclamações de uma fonte específica.

        Args:
            source: Fonte a coletar

        Returns:
            Lista de ComplaintState
        """
        return await self.process([source])

    def get_stats(self) -> dict:
        """
        Retorna estatísticas do loader.

        Returns:
            Dict com contagens por fonte
        """
        if self.data_loader is None:
            return {"error": "Data loader not initialized"}
        return self.data_loader.get_stats()


# Singleton instance
_collector: Optional[CollectorAgent] = None


def get_collector_agent() -> CollectorAgent:
    """
    Factory function para obter o agente coletor.

    Returns:
        Instância do CollectorAgent
    """
    global _collector
    if _collector is None:
        _collector = CollectorAgent()
    return _collector
