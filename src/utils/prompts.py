"""
Prompts centralizados para o LLM.
Define templates de prompts para classificação de reclamações.
"""

from typing import Optional


SYSTEM_PROMPT_ANALYST = """Você é um analista especializado em reclamações de e-commerce brasileiro.
Sua função é classificar reclamações com precisão e objetividade.

CATEGORIAS VÁLIDAS (use EXATAMENTE uma dessas):
1. Atraso na entrega
2. Produto não entregue
3. Produto com defeito
4. Produto diferente do anunciado
5. Cobrança indevida
6. Reembolso não processado
7. Atendimento ruim
8. Problema com vendedor (marketplace)
9. Cancelamento negado
10. Dificuldade de contato

NÍVEIS DE SENTIMENTO:
- neutro: cliente objetivo, sem emoção aparente
- insatisfeito: cliente reclamando mas controlado
- muito_insatisfeito: cliente irritado, usa CAPS LOCK, múltiplas exclamações, ameaças

NÍVEIS DE URGÊNCIA:
- baixa: problema menor, sem prazo definido
- media: cliente quer solução mas sem urgência extrema
- alta: menção a prazos, eventos, necessidade imediata
- critica: ameaça PROCON/justiça, fraude, risco à saúde, valores altos (>R$5000)

REGRAS IMPORTANTES:
1. Sempre responda em JSON válido
2. O resumo deve ter no máximo 2 frases
3. Identifique de 2 a 4 pontos-chave
4. Seja objetivo e imparcial na análise"""


CLASSIFICATION_PROMPT_TEMPLATE = """Analise a seguinte reclamação e classifique-a.

**Título:** {title}

**Descrição:**
{description}

**Fonte:** {source}
**Data:** {created_at}

Responda EXATAMENTE neste formato JSON:
{{
    "category": "<categoria exata da lista>",
    "sentiment": "<neutro|insatisfeito|muito_insatisfeito>",
    "urgency": "<baixa|media|alta|critica>",
    "summary": "<resumo objetivo em 1-2 frases>",
    "key_issues": ["<ponto 1>", "<ponto 2>", "<ponto 3>"]
}}"""


URGENCY_KEYWORDS = {
    "critica": [
        "procon", "processo", "justiça", "advogado", "juizado",
        "fraude", "golpe", "roubo", "clonado", "clonaram",
        "saúde", "doença", "alérgico", "vencido", "contaminado",
        "urgente", "urgência", "imediato", "hoje"
    ],
    "alta": [
        "prazo", "evento", "aniversário", "casamento", "viagem",
        "presente", "amanhã", "semana", "dias",
        "precisando", "necessito", "dependo"
    ]
}


class PromptTemplates:
    """Templates de prompts com formatação."""

    @staticmethod
    def get_analysis_prompt(
        title: str,
        description: str,
        source: str = "não informado",
        created_at: str = "não informado"
    ) -> str:
        """
        Retorna prompt formatado para análise de reclamação.

        Args:
            title: Título da reclamação
            description: Descrição completa
            source: Fonte da reclamação (ex: reclame_aqui)
            created_at: Data de criação

        Returns:
            Prompt formatado
        """
        return CLASSIFICATION_PROMPT_TEMPLATE.format(
            title=title,
            description=description,
            source=source,
            created_at=created_at
        )

    @staticmethod
    def get_system_prompt() -> str:
        """Retorna o system prompt para o analista."""
        return SYSTEM_PROMPT_ANALYST

    @staticmethod
    def check_urgency_keywords(text: str) -> Optional[str]:
        """
        Verifica palavras-chave de urgência no texto.

        Args:
            text: Texto para análise

        Returns:
            'critica', 'alta' ou None
        """
        text_lower = text.lower()

        for keyword in URGENCY_KEYWORDS["critica"]:
            if keyword in text_lower:
                return "critica"

        for keyword in URGENCY_KEYWORDS["alta"]:
            if keyword in text_lower:
                return "alta"

        return None

    @staticmethod
    def get_routing_context(
        category: str,
        urgency: str,
        summary: str
    ) -> str:
        """
        Retorna contexto para busca de time no RAG.

        Args:
            category: Categoria classificada
            urgency: Urgência estimada
            summary: Resumo da reclamação

        Returns:
            Texto para busca semântica
        """
        return f"Categoria: {category}. Urgência: {urgency}. {summary}"
