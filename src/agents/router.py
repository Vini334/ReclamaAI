"""
Agente Roteador (Router Agent).
Responsável por rotear reclamações para o time correto usando RAG.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.base import AgentError, StatefulAgent
from src.models.schemas import (
    ComplaintState,
    Priority,
    RoutingDecision,
    TeamInfo,
    Urgency,
    WorkflowStatus,
)
from src.services.mock_data_loader import get_data_loader
from src.utils.prompts import PromptTemplates

logger = logging.getLogger(__name__)


class RouterAgent(StatefulAgent):
    """
    Agente responsável por rotear reclamações para o time correto.

    No MVP, utiliza mapeamento local com dados dos times.
    Quando Azure AI Search estiver disponível, usará busca semântica RAG.
    """

    def __init__(self, use_azure_search: bool = False):
        """
        Inicializa o agente roteador.

        Args:
            use_azure_search: Se True, usa Azure AI Search para RAG
        """
        super().__init__(
            name="router",
            success_status=WorkflowStatus.ROUTED,
            failure_status=WorkflowStatus.FAILED_ROUTING,
        )
        self.use_azure_search = use_azure_search
        self.teams: List[TeamInfo] = []
        self.category_to_team: Dict[str, TeamInfo] = {}
        self.search_client = None

    async def initialize(self) -> None:
        """Inicializa mapeamento de times."""
        # Carrega times do mock data
        loader = get_data_loader()
        self.teams = loader.load_teams()

        # Cria mapeamento categoria -> time
        for team in self.teams:
            for category in team.categories:
                self.category_to_team[category.lower()] = team

        self.logger.info(
            f"Router agent initialized with {len(self.teams)} teams, "
            f"{len(self.category_to_team)} category mappings"
        )

        # Inicializa Azure Search se configurado
        if self.use_azure_search:
            try:
                from src.integrations.azure_search import get_search_client
                self.search_client = get_search_client()
                self.logger.info("Azure AI Search client initialized for RAG")
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize Azure Search, using local routing: {e}"
                )
                self.use_azure_search = False

    async def validate_input(self, state: ComplaintState) -> bool:
        """
        Valida se o estado tem análise para roteamento.

        Args:
            state: Estado da reclamação

        Returns:
            True se válido
        """
        if not state.complaint_analyzed:
            self.logger.warning("Missing complaint_analyzed in state")
            return False

        # Verifica se já não foi roteado
        if state.routing_decision is not None:
            self.logger.info("Complaint already routed, skipping")
            return True

        return True

    async def process(self, state: ComplaintState) -> ComplaintState:
        """
        Roteia a reclamação para o time apropriado.

        Args:
            state: Estado com análise preenchida

        Returns:
            Estado com decisão de roteamento
        """
        analysis = state.complaint_analyzed
        complaint = state.complaint_raw
        complaint_id = complaint.id or complaint.external_id

        try:
            # Encontra time apropriado
            if self.use_azure_search and self.search_client:
                team = await self._route_with_rag(state)
            else:
                team = await self._route_with_mapping(state)

            if not team:
                raise AgentError(
                    f"No team found for category {analysis.category.value}",
                    self.name,
                    recoverable=False
                )

            # Determina prioridade baseada na análise
            priority = self._determine_priority(analysis.urgency, analysis.sentiment.value)

            # Calcula SLA
            sla_hours = self._get_sla_hours(team, analysis.urgency.value)

            # Gera justificativa
            justification = self._generate_justification(analysis, team)

            # Cria decisão de roteamento
            routing = RoutingDecision(
                complaint_id=complaint_id,
                team=team.name,
                team_id=team.id,
                responsible_email=team.email,
                priority=priority,
                justification=justification,
                sla_hours=sla_hours,
                routed_at=datetime.utcnow(),
            )

            state.routing_decision = routing

            self.logger.info(
                f"Routed complaint {complaint_id} to team '{team.name}' "
                f"(priority={priority.value}, SLA={sla_hours}h)"
            )

            return state

        except AgentError:
            raise
        except Exception as e:
            raise AgentError(f"Routing failed: {e}", self.name, recoverable=True)

    async def _route_with_mapping(self, state: ComplaintState) -> Optional[TeamInfo]:
        """
        Roteia usando mapeamento local categoria->time.

        Args:
            state: Estado da reclamação

        Returns:
            TeamInfo ou None
        """
        category = state.complaint_analyzed.category.value.lower()

        # Busca exata
        if category in self.category_to_team:
            return self.category_to_team[category]

        # Busca parcial
        for cat_key, team in self.category_to_team.items():
            if category in cat_key or cat_key in category:
                return team

        # Fallback: retorna time de Atendimento N2
        for team in self.teams:
            if "atendimento" in team.name.lower() or "n2" in team.name.lower():
                self.logger.warning(
                    f"Using fallback team '{team.name}' for category '{category}'"
                )
                return team

        return self.teams[0] if self.teams else None

    async def _route_with_rag(self, state: ComplaintState) -> Optional[TeamInfo]:
        """
        Roteia usando Azure AI Search (RAG).

        Args:
            state: Estado da reclamação

        Returns:
            TeamInfo ou None
        """
        analysis = state.complaint_analyzed

        # Constrói query para busca semântica
        query = PromptTemplates.get_routing_context(
            category=analysis.category.value,
            urgency=analysis.urgency.value,
            summary=analysis.summary,
        )

        try:
            # Busca times relevantes
            teams = await self.search_client.search_team(
                query=query,
                category=analysis.category.value,
                top_k=1
            )

            if teams:
                return teams[0]

            # Fallback para mapeamento local
            self.logger.warning("RAG search returned no results, using local mapping")
            return await self._route_with_mapping(state)

        except Exception as e:
            self.logger.error(f"RAG search failed: {e}")
            return await self._route_with_mapping(state)

    def _determine_priority(self, urgency: Urgency, sentiment: str) -> Priority:
        """
        Determina prioridade baseada em urgência e sentimento.

        Args:
            urgency: Nível de urgência
            sentiment: Sentimento do cliente

        Returns:
            Priority apropriada
        """
        # Matriz de prioridade
        if urgency == Urgency.CRITICA:
            return Priority.CRITICAL

        if urgency == Urgency.ALTA:
            if sentiment == "muito_insatisfeito":
                return Priority.CRITICAL
            return Priority.HIGH

        if urgency == Urgency.MEDIA:
            if sentiment == "muito_insatisfeito":
                return Priority.HIGH
            return Priority.MEDIUM

        # Urgência baixa
        if sentiment == "muito_insatisfeito":
            return Priority.MEDIUM
        return Priority.LOW

    def _get_sla_hours(self, team: TeamInfo, urgency: str) -> int:
        """
        Obtém SLA em horas baseado no time e urgência.

        Args:
            team: Time responsável
            urgency: Nível de urgência

        Returns:
            Horas do SLA
        """
        # Mapeamento de urgência para chave do SLA
        urgency_mapping = {
            "baixa": "baixa",
            "media": "media",
            "alta": "alta",
            "critica": "critica",
        }

        sla_key = urgency_mapping.get(urgency, "media")
        return team.sla_hours.get(sla_key, 48)

    def _generate_justification(
        self, analysis, team: TeamInfo
    ) -> str:
        """
        Gera justificativa para o roteamento.

        Args:
            analysis: Análise da reclamação
            team: Time selecionado

        Returns:
            Texto de justificativa
        """
        return (
            f"Reclamação classificada como '{analysis.category.value}' "
            f"com urgência '{analysis.urgency.value}'. "
            f"Time '{team.name}' é responsável por esta categoria e possui "
            f"expertise em: {', '.join(team.responsibilities[:3])}."
        )

    def get_available_teams(self) -> List[str]:
        """Retorna lista de times disponíveis."""
        return [team.name for team in self.teams]

    def get_team_by_id(self, team_id: str) -> Optional[TeamInfo]:
        """Busca time por ID."""
        for team in self.teams:
            if team.id == team_id:
                return team
        return None


# Singleton instance
_router: Optional[RouterAgent] = None


def get_router_agent(use_azure_search: bool = False) -> RouterAgent:
    """
    Factory function para obter o agente roteador.

    Args:
        use_azure_search: Se True, habilita RAG com Azure AI Search

    Returns:
        Instância do RouterAgent
    """
    global _router
    if _router is None:
        _router = RouterAgent(use_azure_search=use_azure_search)
    return _router
