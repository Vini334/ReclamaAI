"""
Classe base abstrata para todos os agentes do ReclamaAI.
Define a interface comum e comportamentos compartilhados.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, Optional, TypeVar

from src.models.schemas import ComplaintState, WorkflowStatus

logger = logging.getLogger(__name__)

# Tipos genéricos para entrada e saída dos agentes
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgentError(Exception):
    """Exceção base para erros de agentes."""

    def __init__(self, message: str, agent_name: str, recoverable: bool = False):
        self.message = message
        self.agent_name = agent_name
        self.recoverable = recoverable
        super().__init__(f"[{agent_name}] {message}")


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Classe base abstrata para todos os agentes.

    Cada agente é responsável por uma etapa específica do workflow:
    - CollectorAgent: Coleta reclamações das fontes
    - AnalystAgent: Classifica e analisa reclamações com LLM
    - RouterAgent: Roteia para o time correto usando RAG
    - CommunicatorAgent: Cria tickets e envia notificações
    """

    def __init__(self, name: str):
        """
        Inicializa o agente.

        Args:
            name: Nome identificador do agente
        """
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Inicializa recursos do agente (conexões, clients, etc).
        Deve ser chamado antes de process().
        """
        pass

    @abstractmethod
    async def process(self, input_data: InputT) -> OutputT:
        """
        Processa a entrada e retorna a saída.

        Args:
            input_data: Dados de entrada específicos do agente

        Returns:
            Dados de saída específicos do agente
        """
        pass

    @abstractmethod
    async def validate_input(self, input_data: InputT) -> bool:
        """
        Valida se a entrada é válida para processamento.

        Args:
            input_data: Dados de entrada a validar

        Returns:
            True se válido, False caso contrário
        """
        pass

    async def execute(self, input_data: InputT) -> OutputT:
        """
        Executa o agente com logging e tratamento de erros.

        Args:
            input_data: Dados de entrada

        Returns:
            Dados de saída

        Raises:
            AgentError: Se ocorrer erro no processamento
        """
        start_time = datetime.utcnow()
        self.logger.info(f"Starting execution")

        try:
            # Inicializa se necessário
            if not self._initialized:
                await self.initialize()
                self._initialized = True

            # Valida entrada
            if not await self.validate_input(input_data):
                raise AgentError(
                    "Invalid input data",
                    self.name,
                    recoverable=False
                )

            # Processa
            result = await self.process(input_data)

            # Log de sucesso
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(f"Completed in {elapsed:.2f}s")

            return result

        except AgentError:
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            raise AgentError(str(e), self.name, recoverable=True)

    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status do agente.

        Returns:
            Dict com informações de status
        """
        return {
            "name": self.name,
            "initialized": self._initialized,
        }


class StatefulAgent(BaseAgent[ComplaintState, ComplaintState]):
    """
    Agente que opera sobre ComplaintState.

    Todos os agentes do workflow principal herdam desta classe,
    que garante transições de estado consistentes.
    """

    def __init__(self, name: str, success_status: WorkflowStatus, failure_status: WorkflowStatus):
        """
        Inicializa o agente stateful.

        Args:
            name: Nome do agente
            success_status: Status após sucesso
            failure_status: Status após falha
        """
        super().__init__(name)
        self.success_status = success_status
        self.failure_status = failure_status

    async def execute(self, state: ComplaintState) -> ComplaintState:
        """
        Executa o agente atualizando o estado do workflow.

        Args:
            state: Estado atual da reclamação

        Returns:
            Estado atualizado
        """
        start_time = datetime.utcnow()
        self.logger.info(
            f"Processing complaint {state.complaint_raw.id or state.complaint_raw.external_id}"
        )

        try:
            # Inicializa se necessário
            if not self._initialized:
                await self.initialize()
                self._initialized = True

            # Valida entrada
            if not await self.validate_input(state):
                state.errors.append(f"[{self.name}] Invalid input state")
                state.workflow_status = self.failure_status
                return state

            # Processa
            result = await self.process(state)
            result.workflow_status = self.success_status

            # Log de sucesso
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            self.logger.info(
                f"Completed {state.complaint_raw.id or state.complaint_raw.external_id} "
                f"in {elapsed:.2f}s -> {self.success_status.value}"
            )

            return result

        except AgentError as e:
            self.logger.error(f"Agent error: {e}")
            state.errors.append(f"[{self.name}] {e.message}")
            state.workflow_status = self.failure_status
            return state

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            state.errors.append(f"[{self.name}] Unexpected: {str(e)}")
            state.workflow_status = self.failure_status
            return state
