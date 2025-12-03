"""
Agente Comunicador (Communicator Agent).
Responsável por criar tickets e enviar notificações.
"""

import logging
from datetime import datetime
from typing import Optional

from src.agents.base import AgentError, StatefulAgent
from src.integrations.mock_email import get_email_client, MockEmailClient
from src.integrations.mock_jira import get_jira_client, MockJiraClient
from src.models.schemas import (
    ComplaintState,
    NotificationInfo,
    TicketInfo,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)


class CommunicatorAgent(StatefulAgent):
    """
    Agente responsável por criar tickets e enviar notificações.

    Executa duas ações principais:
    1. Cria ticket no Jira (mock)
    2. Envia notificações por email (mock)
       - Para o time responsável
       - Para o cliente (se tiver contato)
    """

    def __init__(self):
        """Inicializa o agente comunicador."""
        super().__init__(
            name="communicator",
            success_status=WorkflowStatus.COMPLETED,
            failure_status=WorkflowStatus.FAILED_JIRA,
        )
        self.jira_client: Optional[MockJiraClient] = None
        self.email_client: Optional[MockEmailClient] = None

    async def initialize(self) -> None:
        """Inicializa os clientes de Jira e Email."""
        self.jira_client = get_jira_client()
        self.email_client = get_email_client()
        self.logger.info("Communicator agent initialized with mock clients")

    async def validate_input(self, state: ComplaintState) -> bool:
        """
        Valida se o estado tem roteamento para criar ticket.

        Args:
            state: Estado da reclamação

        Returns:
            True se válido
        """
        if not state.routing_decision:
            self.logger.warning("Missing routing_decision in state")
            return False

        if not state.complaint_analyzed:
            self.logger.warning("Missing complaint_analyzed in state")
            return False

        # Verifica se já não foi processado
        if state.ticket_info is not None:
            self.logger.info("Ticket already created, skipping")
            return True

        return True

    async def process(self, state: ComplaintState) -> ComplaintState:
        """
        Cria ticket e envia notificações.

        Args:
            state: Estado com roteamento preenchido

        Returns:
            Estado com ticket e notificações
        """
        complaint = state.complaint_raw
        analysis = state.complaint_analyzed
        routing = state.routing_decision
        complaint_id = complaint.id or complaint.external_id

        try:
            # 1. Cria ticket no Jira
            ticket = await self._create_ticket(complaint_id, state)
            state.ticket_info = ticket

            # Atualiza status para TICKET_CREATED
            state.workflow_status = WorkflowStatus.TICKET_CREATED

            self.logger.info(
                f"Created ticket {ticket.jira_key} for complaint {complaint_id}"
            )

            # 2. Envia notificação para o time
            team_notification = await self._notify_team(complaint_id, state)

            # 3. Envia notificação para o cliente (se tiver contato)
            customer_notification = await self._notify_customer(state)

            # Registra primeira notificação (time)
            state.notification_info = team_notification

            # Atualiza status para NOTIFIED
            state.workflow_status = WorkflowStatus.NOTIFIED

            # Marca como completo
            state.workflow_status = WorkflowStatus.COMPLETED
            state.completed_at = datetime.utcnow()

            self.logger.info(
                f"Completed processing complaint {complaint_id}: "
                f"ticket={ticket.jira_key}, "
                f"team_notified={routing.responsible_email}"
            )

            return state

        except Exception as e:
            # Determina tipo de falha
            if "ticket" in str(e).lower() or "jira" in str(e).lower():
                state.workflow_status = WorkflowStatus.FAILED_JIRA
            else:
                state.workflow_status = WorkflowStatus.FAILED_EMAIL

            raise AgentError(f"Communication failed: {e}", self.name, recoverable=True)

    async def _create_ticket(
        self, complaint_id: str, state: ComplaintState
    ) -> TicketInfo:
        """
        Cria ticket no Jira.

        Args:
            complaint_id: ID da reclamação
            state: Estado completo

        Returns:
            TicketInfo criado
        """
        if self.jira_client is None:
            raise AgentError("Jira client not initialized", self.name)

        ticket = await self.jira_client.create_ticket(
            complaint_id=complaint_id,
            analysis=state.complaint_analyzed,
            routing=state.routing_decision,
        )

        return ticket

    async def _notify_team(
        self, complaint_id: str, state: ComplaintState
    ) -> NotificationInfo:
        """
        Envia notificação para o time responsável.

        Args:
            complaint_id: ID da reclamação
            state: Estado completo

        Returns:
            NotificationInfo do envio
        """
        if self.email_client is None:
            raise AgentError("Email client not initialized", self.name)

        notification = await self.email_client.send_team_notification(
            complaint_id=complaint_id,
            complaint=state.complaint_raw,
            routing=state.routing_decision,
            ticket=state.ticket_info,
        )

        return notification

    async def _notify_customer(
        self, state: ComplaintState
    ) -> Optional[NotificationInfo]:
        """
        Envia notificação para o cliente.

        Args:
            state: Estado completo

        Returns:
            NotificationInfo ou None se cliente sem contato
        """
        if self.email_client is None:
            return None

        notification = await self.email_client.send_customer_notification(
            complaint=state.complaint_raw,
            ticket=state.ticket_info,
        )

        if notification:
            self.logger.info(
                f"Customer notification sent to {state.complaint_raw.consumer_contact}"
            )

        return notification

    def get_stats(self) -> dict:
        """
        Retorna estatísticas combinadas de tickets e emails.

        Returns:
            Dict com estatísticas
        """
        stats = {
            "tickets": {},
            "emails": {},
        }

        if self.jira_client:
            stats["tickets"] = self.jira_client.get_stats()

        if self.email_client:
            stats["emails"] = self.email_client.get_stats()

        return stats


# Singleton instance
_communicator: Optional[CommunicatorAgent] = None


def get_communicator_agent() -> CommunicatorAgent:
    """
    Factory function para obter o agente comunicador.

    Returns:
        Instância do CommunicatorAgent
    """
    global _communicator
    if _communicator is None:
        _communicator = CommunicatorAgent()
    return _communicator
