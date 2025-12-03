"""
Agente de Privacidade para conformidade LGPD.
Responsável por anonimizar dados pessoais antes do processamento LLM.
"""

import re
from copy import deepcopy
from typing import Tuple

from src.agents.base import BaseAgent
from src.models.schemas import ComplaintRaw, ComplaintState, WorkflowStatus


# Padrões de PII para mascaramento
# IMPORTANTE: A ordem importa! Padrões mais específicos devem vir antes.
# Usamos lista de tuplas para garantir a ordem de processamento.
PII_PATTERNS = [
    # Cartão de crédito deve vir PRIMEIRO (16 dígitos, mais específico)
    ("cartao", (
        r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "[CARTÃO REMOVIDO]"
    )),
    # CPF (11 dígitos com formatação específica)
    ("cpf", (
        r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}",
        "[CPF REMOVIDO]"
    )),
    # Email
    ("email", (
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "[EMAIL REMOVIDO]"
    )),
    # Telefone (deve vir por último pois é mais genérico)
    ("telefone", (
        r"\(?\d{2}\)?[\s-]?\d{4,5}-?\d{4}",
        "[TELEFONE REMOVIDO]"
    )),
]


class PrivacyAgent(BaseAgent[ComplaintRaw, ComplaintRaw]):
    """
    Agente responsável por anonimizar PII para conformidade LGPD.

    Detecta e mascara:
    - CPF (ex: 123.456.789-00 -> [CPF REMOVIDO])
    - Email (ex: joao@gmail.com -> [EMAIL REMOVIDO])
    - Telefone (ex: (11) 98765-4321 -> [TELEFONE REMOVIDO])
    - Cartão de crédito (ex: 1234-5678-9012-3456 -> [CARTÃO REMOVIDO])
    """

    def __init__(self):
        super().__init__("privacy")
        # Mantém a ordem dos padrões usando lista
        self._patterns = [
            (name, (re.compile(pattern), replacement))
            for name, (pattern, replacement) in PII_PATTERNS
        ]

    async def initialize(self) -> None:
        """Inicializa o agente (nenhum recurso externo necessário)."""
        self.logger.info("Privacy agent initialized")
        self._initialized = True

    async def validate_input(self, input_data: ComplaintRaw) -> bool:
        """Valida se a entrada é uma ComplaintRaw válida."""
        return (
            input_data is not None
            and isinstance(input_data, ComplaintRaw)
            and input_data.description is not None
        )

    def _mask_pii(self, text: str) -> Tuple[str, int]:
        """
        Mascara todos os PIIs encontrados no texto.

        Args:
            text: Texto a ser processado

        Returns:
            Tupla (texto mascarado, número de substituições)
        """
        if not text:
            return text, 0

        total_replacements = 0
        masked_text = text

        # Processa na ordem definida (mais específico primeiro)
        for name, (pattern, replacement) in self._patterns:
            new_text, count = pattern.subn(replacement, masked_text)
            if count > 0:
                self.logger.debug(f"Masked {count} {name}(s)")
                total_replacements += count
            masked_text = new_text

        return masked_text, total_replacements

    async def process(self, complaint: ComplaintRaw) -> ComplaintRaw:
        """
        Processa uma reclamação e retorna cópia com PII mascarado.

        Args:
            complaint: Reclamação original

        Returns:
            Cópia da reclamação com dados anonimizados
        """
        # Cria cópia profunda para não modificar o original
        anonymized = deepcopy(complaint)

        total_masked = 0

        # Mascara descrição (campo principal)
        anonymized.description, count = self._mask_pii(anonymized.description)
        total_masked += count

        # Mascara título se existir
        if anonymized.title:
            anonymized.title, count = self._mask_pii(anonymized.title)
            total_masked += count

        # Mascara contato do consumidor
        if anonymized.consumer_contact:
            anonymized.consumer_contact, count = self._mask_pii(anonymized.consumer_contact)
            total_masked += count

        self.logger.info(
            f"Anonymized complaint {complaint.id or complaint.external_id}: "
            f"{total_masked} PII(s) masked"
        )

        return anonymized

    async def process_state(self, state: ComplaintState) -> ComplaintState:
        """
        Processa o estado do workflow, anonimizando a reclamação.

        Args:
            state: Estado atual do workflow

        Returns:
            Estado atualizado com complaint_anonymized preenchido
        """
        # Anonimiza a reclamação
        anonymized = await self.process(state.complaint_raw)

        # Atualiza o estado
        state.complaint_anonymized = anonymized
        state.workflow_status = WorkflowStatus.ANONYMIZED

        return state


# Singleton instance
_privacy_agent = None


def get_privacy_agent() -> PrivacyAgent:
    """
    Factory function para obter o agente de privacidade.

    Returns:
        Instância do PrivacyAgent
    """
    global _privacy_agent
    if _privacy_agent is None:
        _privacy_agent = PrivacyAgent()
    return _privacy_agent
