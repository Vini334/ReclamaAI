"""
Simulador de integração Jira.
Simula criação de tickets para desenvolvimento e testes.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.models.schemas import (
    ComplaintAnalyzed,
    Priority,
    RoutingDecision,
    TicketInfo,
)

logger = logging.getLogger(__name__)


class MockJiraClient:
    """Simula criação de tickets no Jira."""

    _ticket_counter: int = 1000
    _created_tickets: Dict[str, TicketInfo] = {}

    def __init__(self, project_key: str = "SUPORTE") -> None:
        """
        Inicializa o simulador Jira.

        Args:
            project_key: Prefixo dos tickets (ex: SUPORTE-1001)
        """
        self.project_key = project_key

    async def create_ticket(
        self,
        complaint_id: str,
        analysis: ComplaintAnalyzed,
        routing: RoutingDecision,
    ) -> TicketInfo:
        """
        Cria ticket simulado.

        Args:
            complaint_id: ID da reclamação
            analysis: Análise do LLM
            routing: Decisão de roteamento

        Returns:
            TicketInfo com dados do ticket criado
        """
        MockJiraClient._ticket_counter += 1
        jira_key = self._generate_ticket_key()
        jira_id = str(MockJiraClient._ticket_counter)

        ticket = TicketInfo(
            complaint_id=complaint_id,
            jira_id=jira_id,
            jira_key=jira_key,
            jira_link=f"https://jira.technova.com/browse/{jira_key}",
            status="Open",
            created_at=datetime.utcnow(),
        )

        # Armazena para consulta posterior
        MockJiraClient._created_tickets[jira_key] = ticket

        logger.info(
            f"Created mock ticket {jira_key} for complaint {complaint_id} "
            f"(team: {routing.team}, priority: {routing.priority.value})"
        )

        return ticket

    async def get_ticket(self, jira_key: str) -> Optional[TicketInfo]:
        """
        Busca ticket por key.

        Args:
            jira_key: Key do ticket (ex: SUPORTE-1001)

        Returns:
            TicketInfo ou None
        """
        return MockJiraClient._created_tickets.get(jira_key)

    async def update_ticket_status(
        self,
        jira_key: str,
        status: str
    ) -> bool:
        """
        Atualiza status do ticket.

        Args:
            jira_key: Key do ticket
            status: Novo status

        Returns:
            True se atualizado
        """
        ticket = MockJiraClient._created_tickets.get(jira_key)
        if ticket:
            # Cria novo ticket com status atualizado (imutável)
            updated = TicketInfo(
                complaint_id=ticket.complaint_id,
                jira_id=ticket.jira_id,
                jira_key=ticket.jira_key,
                jira_link=ticket.jira_link,
                status=status,
                created_at=ticket.created_at,
            )
            MockJiraClient._created_tickets[jira_key] = updated
            logger.info(f"Updated ticket {jira_key} status to {status}")
            return True
        return False

    def _priority_to_jira(self, priority: Priority) -> str:
        """
        Converte Priority para formato Jira.

        Args:
            priority: Prioridade do sistema

        Returns:
            String no formato Jira
        """
        mapping = {
            Priority.LOW: "Low",
            Priority.MEDIUM: "Medium",
            Priority.HIGH: "High",
            Priority.CRITICAL: "Highest",
        }
        return mapping.get(priority, "Medium")

    def _generate_ticket_key(self) -> str:
        """
        Gera key sequencial.

        Returns:
            Key no formato PROJETO-NUMERO
        """
        return f"{self.project_key}-{MockJiraClient._ticket_counter}"

    def build_ticket_description(
        self,
        complaint_title: str,
        complaint_description: str,
        analysis: ComplaintAnalyzed,
        routing: RoutingDecision,
    ) -> str:
        """
        Constrói descrição formatada do ticket.

        Args:
            complaint_title: Título original
            complaint_description: Descrição original
            analysis: Análise do LLM
            routing: Decisão de roteamento

        Returns:
            Descrição formatada para o Jira
        """
        issues_list = "\n".join(f"- {issue}" for issue in analysis.key_issues)

        return f"""
h2. Resumo
{analysis.summary}

h2. Classificação
* *Categoria:* {analysis.category.value}
* *Sentimento:* {analysis.sentiment.value}
* *Urgência:* {analysis.urgency.value}
* *Prioridade:* {routing.priority.value}

h2. Pontos-Chave
{issues_list}

h2. Roteamento
* *Time:* {routing.team}
* *Responsável:* {routing.responsible_email}
* *SLA:* {routing.sla_hours} horas
* *Justificativa:* {routing.justification}

h2. Reclamação Original
*Título:* {complaint_title}

{complaint_description}

----
_Ticket gerado automaticamente pelo ReclamaAI_
        """.strip()

    def get_all_tickets(self) -> List[TicketInfo]:
        """
        Retorna todos os tickets criados.

        Returns:
            Lista de TicketInfo
        """
        return list(MockJiraClient._created_tickets.values())

    def get_tickets_by_status(self, status: str) -> List[TicketInfo]:
        """
        Retorna tickets filtrados por status.

        Args:
            status: Status para filtrar

        Returns:
            Lista de TicketInfo
        """
        return [
            t for t in MockJiraClient._created_tickets.values()
            if t.status == status
        ]

    def clear_tickets(self) -> None:
        """Limpa todos os tickets (para testes)."""
        MockJiraClient._created_tickets.clear()
        MockJiraClient._ticket_counter = 1000
        logger.info("Cleared all mock tickets")

    def get_stats(self) -> Dict[str, int]:
        """
        Retorna estatísticas dos tickets.

        Returns:
            Dict com contagens
        """
        tickets = MockJiraClient._created_tickets.values()
        status_counts: Dict[str, int] = {}
        for ticket in tickets:
            status_counts[ticket.status] = status_counts.get(ticket.status, 0) + 1

        return {
            "total": len(MockJiraClient._created_tickets),
            "by_status": status_counts,
        }


# Singleton instance
_jira_client: Optional[MockJiraClient] = None


def get_jira_client() -> MockJiraClient:
    """
    Factory function para obter cliente Jira.

    Returns:
        Instância do MockJiraClient
    """
    global _jira_client
    if _jira_client is None:
        _jira_client = MockJiraClient()
    return _jira_client
