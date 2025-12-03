"""
Simulador de envio de emails.
Simula notificações para desenvolvimento e testes.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.models.schemas import (
    ComplaintRaw,
    NotificationInfo,
    RoutingDecision,
    TicketInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Representa um email simulado."""

    to: str
    subject: str
    body: str
    sent_at: datetime = field(default_factory=datetime.utcnow)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cc: Optional[List[str]] = None
    priority: str = "normal"


class MockEmailClient:
    """Simula envio de emails."""

    _sent_emails: List[EmailMessage] = []

    async def send_team_notification(
        self,
        complaint_id: str,
        complaint: ComplaintRaw,
        routing: RoutingDecision,
        ticket: TicketInfo,
    ) -> NotificationInfo:
        """
        Envia notificação para o time responsável.

        Args:
            complaint_id: ID da reclamação
            complaint: Reclamação original
            routing: Decisão de roteamento
            ticket: Ticket criado

        Returns:
            NotificationInfo com dados do envio
        """
        subject = self._build_subject(routing, ticket)
        body = self._build_team_email_body(complaint, routing, ticket)

        email = EmailMessage(
            to=routing.responsible_email,
            subject=subject,
            body=body,
            priority="high" if routing.priority.value in ["high", "critical"] else "normal",
        )

        MockEmailClient._sent_emails.append(email)

        notification = NotificationInfo(
            complaint_id=complaint_id,
            ticket_id=ticket.jira_id,
            email_to=routing.responsible_email,
            email_subject=subject,
            sent_at=email.sent_at,
            status="sent",
        )

        logger.info(
            f"Sent mock email to {routing.responsible_email} "
            f"for ticket {ticket.jira_key}"
        )

        return notification

    async def send_customer_notification(
        self,
        complaint: ComplaintRaw,
        ticket: TicketInfo,
    ) -> Optional[NotificationInfo]:
        """
        Envia confirmação para o cliente.

        Args:
            complaint: Reclamação original
            ticket: Ticket criado

        Returns:
            NotificationInfo ou None se cliente sem contato
        """
        if not complaint.consumer_contact:
            logger.warning(
                f"No contact info for customer {complaint.consumer_name}, "
                "skipping notification"
            )
            return None

        subject = f"[TechNova] Recebemos sua reclamação - Protocolo {ticket.jira_key}"
        body = self._build_customer_email_body(complaint, ticket)

        email = EmailMessage(
            to=complaint.consumer_contact,
            subject=subject,
            body=body,
        )

        MockEmailClient._sent_emails.append(email)

        notification = NotificationInfo(
            complaint_id=complaint.id or complaint.external_id,
            ticket_id=ticket.jira_id,
            email_to=complaint.consumer_contact,
            email_subject=subject,
            sent_at=email.sent_at,
            status="sent",
        )

        logger.info(f"Sent mock customer notification to {complaint.consumer_contact}")

        return notification

    def _build_subject(self, routing: RoutingDecision, ticket: TicketInfo) -> str:
        """
        Constrói assunto do email.

        Args:
            routing: Decisão de roteamento
            ticket: Ticket criado

        Returns:
            Assunto formatado
        """
        priority_prefix = ""
        if routing.priority.value == "critical":
            priority_prefix = "[URGENTE] "
        elif routing.priority.value == "high":
            priority_prefix = "[ALTA PRIORIDADE] "

        return f"{priority_prefix}Nova reclamação atribuída - {ticket.jira_key}"

    def _build_team_email_body(
        self,
        complaint: ComplaintRaw,
        routing: RoutingDecision,
        ticket: TicketInfo,
    ) -> str:
        """
        Constrói corpo do email para o time.

        Args:
            complaint: Reclamação original
            routing: Decisão de roteamento
            ticket: Ticket criado

        Returns:
            Corpo do email formatado
        """
        return f"""
Olá {routing.team},

Uma nova reclamação foi atribuída à sua equipe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 DETALHES DO TICKET

Ticket: {ticket.jira_key}
Link: {ticket.jira_link}
Prioridade: {routing.priority.value.upper()}
SLA: {routing.sla_hours} horas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 INFORMAÇÕES DO CLIENTE

Nome: {complaint.consumer_name}
Canal: {complaint.channel}
Cidade/Estado: {complaint.city or 'N/I'}/{complaint.state or 'N/I'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 RECLAMAÇÃO

Título: {complaint.title}

{complaint.description[:500]}{'...' if len(complaint.description) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 JUSTIFICATIVA DO ROTEAMENTO

{routing.justification}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por favor, acesse o ticket para mais detalhes e inicie o atendimento.

--
ReclamaAI - Sistema de Gestão de Reclamações
Este é um email automático, não responda.
        """.strip()

    def _build_customer_email_body(
        self,
        complaint: ComplaintRaw,
        ticket: TicketInfo,
    ) -> str:
        """
        Constrói corpo do email para o cliente.

        Args:
            complaint: Reclamação original
            ticket: Ticket criado

        Returns:
            Corpo do email formatado
        """
        return f"""
Olá {complaint.consumer_name},

Recebemos sua reclamação e ela já está sendo tratada pela nossa equipe.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 INFORMAÇÕES DO SEU PROTOCOLO

Número do Protocolo: {ticket.jira_key}
Data de Abertura: {ticket.created_at.strftime('%d/%m/%Y às %H:%M')}

Assunto: {complaint.title}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏰ PRÓXIMOS PASSOS

Nossa equipe analisará sua reclamação e entrará em contato em breve
para fornecer uma solução.

Guarde o número do protocolo para acompanhamento.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Se precisar de mais informações, entre em contato:
📧 suporte@technova.com
📞 0800 123 4567

Atenciosamente,
Equipe TechNova Store

--
Este é um email automático do sistema ReclamaAI.
        """.strip()

    def get_sent_emails(self) -> List[EmailMessage]:
        """
        Retorna emails enviados.

        Returns:
            Lista de EmailMessage
        """
        return MockEmailClient._sent_emails.copy()

    def get_emails_to(self, email_address: str) -> List[EmailMessage]:
        """
        Retorna emails enviados para um endereço específico.

        Args:
            email_address: Endereço de email

        Returns:
            Lista de EmailMessage
        """
        return [e for e in MockEmailClient._sent_emails if e.to == email_address]

    def clear_sent_emails(self) -> None:
        """Limpa histórico de emails (para testes)."""
        MockEmailClient._sent_emails.clear()
        logger.info("Cleared all mock emails")

    def get_stats(self) -> Dict[str, int]:
        """
        Retorna estatísticas dos emails.

        Returns:
            Dict com contagens
        """
        emails = MockEmailClient._sent_emails
        priority_counts: Dict[str, int] = {}
        for email in emails:
            priority_counts[email.priority] = priority_counts.get(email.priority, 0) + 1

        unique_recipients = len(set(e.to for e in emails))

        return {
            "total_sent": len(emails),
            "unique_recipients": unique_recipients,
            "by_priority": priority_counts,
        }


# Singleton instance
_email_client: Optional[MockEmailClient] = None


def get_email_client() -> MockEmailClient:
    """
    Factory function para obter cliente de email.

    Returns:
        Instância do MockEmailClient
    """
    global _email_client
    if _email_client is None:
        _email_client = MockEmailClient()
    return _email_client
