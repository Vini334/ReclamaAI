"""
Agente Analista (Analyst Agent).
Responsável por classificar reclamações usando Azure OpenAI.
Inclui integração com LangSmith para tracing detalhado.
"""

import logging
from datetime import datetime
from typing import Optional

from src.agents.base import AgentError, StatefulAgent
from src.integrations.azure_openai import get_openai_client, LLMError
from src.models.schemas import (
    ComplaintAnalyzed,
    ComplaintCategory,
    ComplaintState,
    Sentiment,
    Urgency,
    WorkflowStatus,
)
from src.utils.prompts import PromptTemplates
from src.utils.langsmith_config import get_langsmith_config

logger = logging.getLogger(__name__)


class AnalystAgent(StatefulAgent):
    """
    Agente responsável por analisar e classificar reclamações.

    Utiliza Azure OpenAI (GPT-4o-mini) para:
    - Classificar em uma das 10 categorias
    - Detectar sentimento do cliente
    - Estimar urgência
    - Gerar resumo e pontos-chave
    """

    def __init__(self):
        """Inicializa o agente analista."""
        super().__init__(
            name="analyst",
            success_status=WorkflowStatus.ANALYZED,
            failure_status=WorkflowStatus.FAILED_LLM,
        )
        self.llm_client = None
        self.langsmith_config = get_langsmith_config()

    async def initialize(self) -> None:
        """Inicializa o cliente Azure OpenAI."""
        self.llm_client = get_openai_client()
        self.logger.info("Analyst agent initialized with Azure OpenAI client")

    async def validate_input(self, state: ComplaintState) -> bool:
        """
        Valida se o estado tem os dados necessários para análise.

        Args:
            state: Estado da reclamação

        Returns:
            True se válido
        """
        if not state.complaint_raw:
            self.logger.warning("Missing complaint_raw in state")
            return False

        if not state.complaint_raw.title or not state.complaint_raw.description:
            self.logger.warning("Missing title or description in complaint")
            return False

        # Verifica se já não foi analisado
        if state.complaint_analyzed is not None:
            self.logger.info("Complaint already analyzed, skipping")
            return True

        return True

    async def process(self, state: ComplaintState) -> ComplaintState:
        """
        Analisa a reclamação usando o LLM.

        Args:
            state: Estado com reclamação bruta

        Returns:
            Estado com análise preenchida
        """
        if self.llm_client is None:
            raise AgentError("LLM client not initialized", self.name)

        complaint = state.complaint_raw
        complaint_id = complaint.id or complaint.external_id
        source = complaint.source.value

        # Usa dados anonimizados se disponíveis (LGPD compliance)
        analysis_complaint = state.complaint_anonymized or complaint

        try:
            # Prepara prompts
            system_prompt = PromptTemplates.get_system_prompt()
            user_prompt = PromptTemplates.get_analysis_prompt(
                title=analysis_complaint.title,
                description=analysis_complaint.description,
                source=source,
                created_at=complaint.created_at.isoformat(),
            )

            # Prepara metadata para LangSmith tracing
            tracing_metadata = {
                "complaint_id": complaint_id,
                "source": source,
                "agent": "analyst",
                "operation": "classify_complaint",
            }

            tracing_tags = [
                "reclamaai",
                "analyst",
                f"source:{source}",
            ]

            # Chama o LLM com tracing
            self.logger.debug(f"Calling LLM for complaint {complaint_id}")
            result = await self.llm_client.analyze(
                system_prompt,
                user_prompt,
                run_name=f"analyze_complaint_{complaint_id[:8]}",
                metadata=tracing_metadata,
                tags=tracing_tags,
            )

            # Valida e converte resposta
            analysis = self._parse_llm_response(complaint_id, result)

            # Verifica urgência por keywords (override se necessário)
            keyword_urgency = PromptTemplates.check_urgency_keywords(
                f"{complaint.title} {complaint.description}"
            )
            if keyword_urgency and self._urgency_is_higher(keyword_urgency, analysis.urgency.value):
                self.logger.info(
                    f"Upgrading urgency from {analysis.urgency.value} to {keyword_urgency} "
                    "based on keywords"
                )
                analysis.urgency = Urgency(keyword_urgency)

            # Atualiza estado
            state.complaint_analyzed = analysis

            self.logger.info(
                f"Analyzed complaint {complaint_id}: "
                f"category={analysis.category.value}, "
                f"sentiment={analysis.sentiment.value}, "
                f"urgency={analysis.urgency.value}"
            )

            return state

        except LLMError as e:
            raise AgentError(f"LLM analysis failed: {e}", self.name, recoverable=True)

    def _parse_llm_response(
        self, complaint_id: str, response: dict
    ) -> ComplaintAnalyzed:
        """
        Converte resposta do LLM em ComplaintAnalyzed.

        Args:
            complaint_id: ID da reclamação
            response: Dict da resposta do LLM

        Returns:
            ComplaintAnalyzed validado
        """
        try:
            # Extrai campos com validação
            category_str = response.get("category", "Atendimento ruim")
            category = self._parse_category(category_str)

            sentiment_str = response.get("sentiment", "insatisfeito")
            sentiment = self._parse_sentiment(sentiment_str)

            urgency_str = response.get("urgency", "media")
            urgency = self._parse_urgency(urgency_str)

            summary = response.get("summary", "Resumo não disponível")
            key_issues = response.get("key_issues", [])

            # Garante que key_issues é uma lista
            if isinstance(key_issues, str):
                key_issues = [key_issues]

            return ComplaintAnalyzed(
                complaint_id=complaint_id,
                category=category,
                sentiment=sentiment,
                urgency=urgency,
                summary=summary,
                key_issues=key_issues[:4],  # Máximo 4 itens
                analyzed_at=datetime.utcnow(),
            )

        except Exception as e:
            self.logger.error(f"Failed to parse LLM response: {e}")
            # Retorna análise padrão em caso de erro
            return ComplaintAnalyzed(
                complaint_id=complaint_id,
                category=ComplaintCategory.ATENDIMENTO_RUIM,
                sentiment=Sentiment.INSATISFEITO,
                urgency=Urgency.MEDIA,
                summary="Erro ao processar análise",
                key_issues=["Análise automática falhou"],
                analyzed_at=datetime.utcnow(),
            )

    def _parse_category(self, category_str: str) -> ComplaintCategory:
        """
        Converte string de categoria para enum.

        Args:
            category_str: String da categoria

        Returns:
            ComplaintCategory enum
        """
        # Mapeamento flexível para lidar com variações
        mappings = {
            "atraso na entrega": ComplaintCategory.ATRASO_ENTREGA,
            "atraso entrega": ComplaintCategory.ATRASO_ENTREGA,
            "produto não entregue": ComplaintCategory.PRODUTO_NAO_ENTREGUE,
            "produto nao entregue": ComplaintCategory.PRODUTO_NAO_ENTREGUE,
            "não entregue": ComplaintCategory.PRODUTO_NAO_ENTREGUE,
            "produto com defeito": ComplaintCategory.PRODUTO_DEFEITO,
            "defeito": ComplaintCategory.PRODUTO_DEFEITO,
            "produto diferente do anunciado": ComplaintCategory.PRODUTO_DIFERENTE,
            "produto diferente": ComplaintCategory.PRODUTO_DIFERENTE,
            "cobrança indevida": ComplaintCategory.COBRANCA_INDEVIDA,
            "cobranca indevida": ComplaintCategory.COBRANCA_INDEVIDA,
            "reembolso não processado": ComplaintCategory.REEMBOLSO_NAO_PROCESSADO,
            "reembolso nao processado": ComplaintCategory.REEMBOLSO_NAO_PROCESSADO,
            "reembolso": ComplaintCategory.REEMBOLSO_NAO_PROCESSADO,
            "atendimento ruim": ComplaintCategory.ATENDIMENTO_RUIM,
            "problema com vendedor (marketplace)": ComplaintCategory.PROBLEMA_VENDEDOR,
            "problema com vendedor": ComplaintCategory.PROBLEMA_VENDEDOR,
            "marketplace": ComplaintCategory.PROBLEMA_VENDEDOR,
            "cancelamento negado": ComplaintCategory.CANCELAMENTO_NEGADO,
            "cancelamento": ComplaintCategory.CANCELAMENTO_NEGADO,
            "dificuldade de contato": ComplaintCategory.DIFICULDADE_CONTATO,
            "dificuldade contato": ComplaintCategory.DIFICULDADE_CONTATO,
        }

        normalized = category_str.lower().strip()

        # Tenta mapeamento direto
        if normalized in mappings:
            return mappings[normalized]

        # Tenta encontrar correspondência parcial
        for key, value in mappings.items():
            if key in normalized or normalized in key:
                return value

        # Fallback
        self.logger.warning(f"Unknown category '{category_str}', using fallback")
        return ComplaintCategory.ATENDIMENTO_RUIM

    def _parse_sentiment(self, sentiment_str: str) -> Sentiment:
        """Converte string de sentimento para enum."""
        mappings = {
            "neutro": Sentiment.NEUTRO,
            "insatisfeito": Sentiment.INSATISFEITO,
            "muito_insatisfeito": Sentiment.MUITO_INSATISFEITO,
            "muito insatisfeito": Sentiment.MUITO_INSATISFEITO,
        }

        normalized = sentiment_str.lower().strip()
        return mappings.get(normalized, Sentiment.INSATISFEITO)

    def _parse_urgency(self, urgency_str: str) -> Urgency:
        """Converte string de urgência para enum."""
        mappings = {
            "baixa": Urgency.BAIXA,
            "media": Urgency.MEDIA,
            "média": Urgency.MEDIA,
            "alta": Urgency.ALTA,
            "critica": Urgency.CRITICA,
            "crítica": Urgency.CRITICA,
        }

        normalized = urgency_str.lower().strip()
        return mappings.get(normalized, Urgency.MEDIA)

    def _urgency_is_higher(self, new: str, current: str) -> bool:
        """
        Verifica se nova urgência é maior que a atual.

        Args:
            new: Nova urgência
            current: Urgência atual

        Returns:
            True se new > current
        """
        order = {"baixa": 0, "media": 1, "alta": 2, "critica": 3}
        return order.get(new, 0) > order.get(current, 0)


# Singleton instance
_analyst: Optional[AnalystAgent] = None


def get_analyst_agent() -> AnalystAgent:
    """
    Factory function para obter o agente analista.

    Returns:
        Instância do AnalystAgent
    """
    global _analyst
    if _analyst is None:
        _analyst = AnalystAgent()
    return _analyst
