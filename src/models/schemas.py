"""
Schemas e modelos de dados do ReclamaAI.
Define as estruturas de dados usadas em todo o sistema.
"""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ComplaintSource(str, Enum):
    """Fontes de reclamações."""
    RECLAME_AQUI = "reclame_aqui"
    JIRA = "jira"
    CHAT = "chat"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    PHONE = "phone"


class Sentiment(str, Enum):
    """Níveis de sentimento do cliente."""
    NEUTRO = "neutro"
    INSATISFEITO = "insatisfeito"
    MUITO_INSATISFEITO = "muito_insatisfeito"


class Urgency(str, Enum):
    """Níveis de urgência."""
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class Priority(str, Enum):
    """Prioridades de ticket."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplaintCategory(str, Enum):
    """Categorias de reclamação."""
    ATRASO_ENTREGA = "Atraso na entrega"
    PRODUTO_NAO_ENTREGUE = "Produto não entregue"
    PRODUTO_DEFEITO = "Produto com defeito"
    PRODUTO_DIFERENTE = "Produto diferente do anunciado"
    COBRANCA_INDEVIDA = "Cobrança indevida"
    REEMBOLSO_NAO_PROCESSADO = "Reembolso não processado"
    ATENDIMENTO_RUIM = "Atendimento ruim"
    PROBLEMA_VENDEDOR = "Problema com vendedor (marketplace)"
    CANCELAMENTO_NEGADO = "Cancelamento negado"
    DIFICULDADE_CONTATO = "Dificuldade de contato"


class WorkflowStatus(str, Enum):
    """Estados do workflow."""
    NEW = "NEW"
    ANONYMIZED = "ANONYMIZED"
    ANALYZED = "ANALYZED"
    QA_APPROVED = "QA_APPROVED"
    QA_REJECTED = "QA_REJECTED"
    ROUTED = "ROUTED"
    TICKET_CREATED = "TICKET_CREATED"
    NOTIFIED = "NOTIFIED"
    COMPLETED = "COMPLETED"
    FAILED_LLM = "FAILED_LLM"
    FAILED_ROUTING = "FAILED_ROUTING"
    FAILED_JIRA = "FAILED_JIRA"
    FAILED_EMAIL = "FAILED_EMAIL"


class ComplaintRaw(BaseModel):
    """Reclamação bruta de qualquer fonte."""

    id: Optional[str] = Field(default=None, description="ID interno")
    external_id: str = Field(..., description="ID na fonte original")
    source: ComplaintSource = Field(..., description="Fonte da reclamação")
    company_name: str = Field(default="TechNova Store")
    title: str = Field(..., description="Título/assunto da reclamação")
    description: str = Field(..., description="Descrição completa")
    consumer_name: str = Field(..., description="Nome do consumidor")
    consumer_contact: Optional[str] = Field(default=None, description="Contato (email/telefone)")
    created_at: datetime = Field(..., description="Data de criação")
    channel: str = Field(..., description="Canal de origem")
    city: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    product_category: Optional[str] = Field(default=None)
    status: str = Field(default="Não Processada")


class ComplaintAnalyzed(BaseModel):
    """Reclamação após análise do LLM."""

    complaint_id: str = Field(..., description="ID da reclamação")
    summary: str = Field(..., description="Resumo gerado pelo LLM")
    category: ComplaintCategory = Field(..., description="Categoria classificada")
    sentiment: Sentiment = Field(..., description="Sentimento detectado")
    urgency: Urgency = Field(..., description="Urgência estimada")
    key_issues: List[str] = Field(default_factory=list, description="Pontos-chave identificados")
    qa_approved: bool = Field(default=False, description="Aprovado pelo QA Agent")
    qa_notes: Optional[str] = Field(default=None, description="Notas do QA")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class RoutingDecision(BaseModel):
    """Decisão de roteamento."""

    complaint_id: str
    team: str = Field(..., description="Time responsável")
    team_id: str = Field(..., description="ID do time")
    responsible_email: str = Field(..., description="Email do responsável")
    priority: Priority = Field(..., description="Prioridade definida")
    justification: str = Field(..., description="Justificativa do roteamento")
    sla_hours: int = Field(..., description="SLA em horas")
    routed_at: datetime = Field(default_factory=datetime.utcnow)


class TicketInfo(BaseModel):
    """Informações do ticket criado."""

    complaint_id: str
    jira_id: str = Field(..., description="ID no Jira")
    jira_key: str = Field(..., description="Key do ticket (ex: SUPORTE-123)")
    jira_link: str = Field(..., description="Link para o ticket")
    status: str = Field(default="Open")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationInfo(BaseModel):
    """Informações da notificação enviada."""

    complaint_id: str
    ticket_id: str
    email_to: str
    email_subject: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["sent", "failed"] = "sent"


class ComplaintState(BaseModel):
    """Estado completo de uma reclamação no workflow."""

    complaint_raw: ComplaintRaw
    complaint_anonymized: Optional[ComplaintRaw] = None
    complaint_analyzed: Optional[ComplaintAnalyzed] = None
    routing_decision: Optional[RoutingDecision] = None
    ticket_info: Optional[TicketInfo] = None
    notification_info: Optional[NotificationInfo] = None
    workflow_status: WorkflowStatus = WorkflowStatus.NEW
    errors: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class TeamInfo(BaseModel):
    """Informações de um time para roteamento."""

    id: str
    name: str
    email: str
    manager: str
    description: str
    responsibilities: List[str]
    categories: List[str]
    sla_hours: dict
    example_cases: List[str]
