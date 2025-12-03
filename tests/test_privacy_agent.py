"""
Testes para o PrivacyAgent.
Verifica anonimização de PII para conformidade LGPD.
"""

import pytest
import sys
import os
from datetime import datetime

# Add project root to path to avoid circular imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.schemas import ComplaintRaw, ComplaintSource, ComplaintState, WorkflowStatus


@pytest.fixture
def privacy_agent():
    """Fixture para o agente de privacidade."""
    # Import here to avoid circular import issues
    from src.agents.privacy import PrivacyAgent
    return PrivacyAgent()


@pytest.fixture
def sample_complaint():
    """Fixture para uma reclamação de exemplo com PII."""
    return ComplaintRaw(
        external_id="TEST-001",
        source=ComplaintSource.RECLAME_AQUI,
        title="Pedido não entregue",
        description="Não recebi meu pedido. Meu CPF é 123.456.789-00 e email joao@gmail.com",
        consumer_name="João Silva",
        consumer_contact="joao@gmail.com",
        created_at=datetime.utcnow(),
        channel="web",
    )


class TestCPFMasking:
    """Testes para mascaramento de CPF."""

    @pytest.mark.asyncio
    async def test_cpf_with_dots_and_dash(self, privacy_agent):
        """Testa CPF no formato 123.456.789-00."""
        complaint = ComplaintRaw(
            external_id="TEST-CPF-1",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="Meu CPF é 123.456.789-00",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "123.456.789-00" not in result.description
        assert "[CPF REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_cpf_without_formatting(self, privacy_agent):
        """Testa CPF sem formatação: 12345678900."""
        complaint = ComplaintRaw(
            external_id="TEST-CPF-2",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="CPF: 12345678900",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "12345678900" not in result.description
        assert "[CPF REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_multiple_cpfs(self, privacy_agent):
        """Testa múltiplos CPFs no mesmo texto."""
        complaint = ComplaintRaw(
            external_id="TEST-CPF-3",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="CPF titular: 111.222.333-44, CPF dependente: 555.666.777-88",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "111.222.333-44" not in result.description
        assert "555.666.777-88" not in result.description
        assert result.description.count("[CPF REMOVIDO]") == 2


class TestEmailMasking:
    """Testes para mascaramento de email."""

    @pytest.mark.asyncio
    async def test_simple_email(self, privacy_agent):
        """Testa email simples."""
        complaint = ComplaintRaw(
            external_id="TEST-EMAIL-1",
            source=ComplaintSource.CHAT,
            title="Teste",
            description="Entre em contato: joao@gmail.com",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="chat",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "joao@gmail.com" not in result.description
        assert "[EMAIL REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_complex_email(self, privacy_agent):
        """Testa email com caracteres especiais."""
        complaint = ComplaintRaw(
            external_id="TEST-EMAIL-2",
            source=ComplaintSource.CHAT,
            title="Teste",
            description="Email: joao.silva_123+test@empresa-tech.com.br",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="chat",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "joao.silva_123+test@empresa-tech.com.br" not in result.description
        assert "[EMAIL REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_email_in_consumer_contact(self, privacy_agent):
        """Testa mascaramento do campo consumer_contact."""
        complaint = ComplaintRaw(
            external_id="TEST-EMAIL-3",
            source=ComplaintSource.CHAT,
            title="Teste",
            description="Teste sem email",
            consumer_name="Teste",
            consumer_contact="cliente@teste.com",
            created_at=datetime.utcnow(),
            channel="chat",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "cliente@teste.com" not in result.consumer_contact
        assert "[EMAIL REMOVIDO]" in result.consumer_contact


class TestPhoneMasking:
    """Testes para mascaramento de telefone."""

    @pytest.mark.asyncio
    async def test_phone_with_parentheses(self, privacy_agent):
        """Testa telefone com parênteses: (11) 98765-4321."""
        complaint = ComplaintRaw(
            external_id="TEST-PHONE-1",
            source=ComplaintSource.PHONE,
            title="Teste",
            description="Meu telefone é (11) 98765-4321",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="phone",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "(11) 98765-4321" not in result.description
        assert "[TELEFONE REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_phone_without_parentheses(self, privacy_agent):
        """Testa telefone sem parênteses: 11 98765-4321."""
        complaint = ComplaintRaw(
            external_id="TEST-PHONE-2",
            source=ComplaintSource.PHONE,
            title="Teste",
            description="Ligar para 11 98765-4321",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="phone",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "11 98765-4321" not in result.description
        assert "[TELEFONE REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_landline_phone(self, privacy_agent):
        """Testa telefone fixo: (11) 3456-7890."""
        complaint = ComplaintRaw(
            external_id="TEST-PHONE-3",
            source=ComplaintSource.PHONE,
            title="Teste",
            description="Telefone fixo: (11) 3456-7890",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="phone",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "(11) 3456-7890" not in result.description
        assert "[TELEFONE REMOVIDO]" in result.description


class TestCardMasking:
    """Testes para mascaramento de cartão de crédito."""

    @pytest.mark.asyncio
    async def test_card_with_spaces(self, privacy_agent):
        """Testa cartão com espaços: 1234 5678 9012 3456."""
        complaint = ComplaintRaw(
            external_id="TEST-CARD-1",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="Cartão: 1234 5678 9012 3456",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "1234 5678 9012 3456" not in result.description
        assert "[CARTÃO REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_card_with_dashes(self, privacy_agent):
        """Testa cartão com traços: 1234-5678-9012-3456."""
        complaint = ComplaintRaw(
            external_id="TEST-CARD-2",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="Número do cartão: 1234-5678-9012-3456",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "1234-5678-9012-3456" not in result.description
        assert "[CARTÃO REMOVIDO]" in result.description

    @pytest.mark.asyncio
    async def test_card_without_formatting(self, privacy_agent):
        """Testa cartão sem formatação: 1234567890123456."""
        complaint = ComplaintRaw(
            external_id="TEST-CARD-3",
            source=ComplaintSource.EMAIL,
            title="Teste",
            description="Cartão 1234567890123456",
            consumer_name="Teste",
            created_at=datetime.utcnow(),
            channel="email",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert "1234567890123456" not in result.description
        assert "[CARTÃO REMOVIDO]" in result.description


class TestMixedPII:
    """Testes para textos com múltiplos tipos de PII."""

    @pytest.mark.asyncio
    async def test_all_pii_types(self, privacy_agent):
        """Testa texto com todos os tipos de PII."""
        complaint = ComplaintRaw(
            external_id="TEST-MIXED-1",
            source=ComplaintSource.RECLAME_AQUI,
            title="Reclamação urgente - CPF 111.222.333-44",
            description=(
                "Olá, meu nome é João. "
                "Meu CPF é 123.456.789-00, "
                "email joao@teste.com, "
                "telefone (11) 98765-4321 e "
                "cartão 1234-5678-9012-3456. "
                "Aguardo contato!"
            ),
            consumer_name="João",
            consumer_contact="joao@teste.com",
            created_at=datetime.utcnow(),
            channel="web",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        # Verifica que nenhum PII permanece
        assert "123.456.789-00" not in result.description
        assert "joao@teste.com" not in result.description
        assert "(11) 98765-4321" not in result.description
        assert "1234-5678-9012-3456" not in result.description

        # Verifica que todos os placeholders estão presentes
        assert "[CPF REMOVIDO]" in result.description
        assert "[EMAIL REMOVIDO]" in result.description
        assert "[TELEFONE REMOVIDO]" in result.description
        assert "[CARTÃO REMOVIDO]" in result.description

        # Verifica título também anonimizado
        assert "111.222.333-44" not in result.title
        assert "[CPF REMOVIDO]" in result.title

        # Verifica consumer_contact
        assert "joao@teste.com" not in result.consumer_contact

    @pytest.mark.asyncio
    async def test_text_without_pii(self, privacy_agent):
        """Testa texto sem PII - deve permanecer inalterado."""
        original_description = "Meu pedido #12345 não chegou. Comprei há 15 dias."
        complaint = ComplaintRaw(
            external_id="TEST-MIXED-2",
            source=ComplaintSource.CHAT,
            title="Pedido atrasado",
            description=original_description,
            consumer_name="Cliente",
            created_at=datetime.utcnow(),
            channel="chat",
        )
        await privacy_agent.initialize()
        result = await privacy_agent.process(complaint)

        assert result.description == original_description


class TestProcessState:
    """Testes para processamento de ComplaintState."""

    @pytest.mark.asyncio
    async def test_process_state_updates_correctly(self, privacy_agent, sample_complaint):
        """Testa que process_state atualiza o estado corretamente."""
        state = ComplaintState(complaint_raw=sample_complaint)

        await privacy_agent.initialize()
        result = await privacy_agent.process_state(state)

        # Verifica que o estado foi atualizado
        assert result.workflow_status == WorkflowStatus.ANONYMIZED
        assert result.complaint_anonymized is not None

        # Verifica que o original permanece inalterado
        assert "123.456.789-00" in result.complaint_raw.description
        assert "joao@gmail.com" in result.complaint_raw.description

        # Verifica que o anonimizado não tem PII
        assert "123.456.789-00" not in result.complaint_anonymized.description
        assert "joao@gmail.com" not in result.complaint_anonymized.description

    @pytest.mark.asyncio
    async def test_original_complaint_unchanged(self, privacy_agent, sample_complaint):
        """Testa que a reclamação original não é modificada."""
        original_description = sample_complaint.description

        await privacy_agent.initialize()
        result = await privacy_agent.process(sample_complaint)

        # Original não deve mudar
        assert sample_complaint.description == original_description
        # Resultado deve ser diferente
        assert result.description != original_description


class TestFactoryFunction:
    """Testes para a factory function."""

    def test_get_privacy_agent_singleton(self):
        """Testa que get_privacy_agent retorna singleton."""
        from src.agents.privacy import get_privacy_agent
        agent1 = get_privacy_agent()
        agent2 = get_privacy_agent()

        assert agent1 is agent2

    def test_get_privacy_agent_returns_correct_type(self):
        """Testa que get_privacy_agent retorna PrivacyAgent."""
        from src.agents.privacy import PrivacyAgent, get_privacy_agent
        agent = get_privacy_agent()
        assert isinstance(agent, PrivacyAgent)


class TestValidation:
    """Testes para validação de entrada."""

    @pytest.mark.asyncio
    async def test_validate_input_valid(self, privacy_agent, sample_complaint):
        """Testa validação com entrada válida."""
        await privacy_agent.initialize()
        result = await privacy_agent.validate_input(sample_complaint)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_input_none(self, privacy_agent):
        """Testa validação com None."""
        await privacy_agent.initialize()
        result = await privacy_agent.validate_input(None)
        assert result is False
