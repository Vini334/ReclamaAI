"""
Cliente para Azure OpenAI.
Gerencia conexão e chamadas ao LLM para análise de reclamações.
Inclui integração com LangSmith para tracing.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_openai import AzureChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.callbacks.base import BaseCallbackHandler

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Exceção para erros do LLM."""
    pass


class AzureOpenAIClient:
    """Cliente singleton para Azure OpenAI."""

    _instance: Optional["AzureOpenAIClient"] = None

    def __new__(cls) -> "AzureOpenAIClient":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Inicializa o cliente LangChain."""
        if self._initialized:
            return

        self.settings = get_settings()
        self.llm = self._create_llm()
        self._initialized = True
        logger.info("Azure OpenAI client initialized")

    def _create_llm(self) -> AzureChatOpenAI:
        """
        Cria instância do LLM com configurações.

        Returns:
            AzureChatOpenAI configurado
        """
        return AzureChatOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_key=self.settings.azure_openai_api_key,
            api_version=self.settings.azure_openai_api_version,
            azure_deployment=self.settings.azure_openai_deployment_name,
            temperature=0.1,
            max_tokens=1000,
        )

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1000,
        run_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executa análise com o LLM.

        Args:
            system_prompt: Prompt do sistema
            user_prompt: Prompt do usuário
            temperature: Temperatura (0-1)
            max_tokens: Máximo de tokens na resposta
            run_name: Nome do run para LangSmith tracing
            metadata: Metadados para LangSmith (ex: complaint_id, source)
            tags: Tags para categorização no LangSmith

        Returns:
            Dict parseado do JSON de resposta

        Raises:
            LLMError: Se falhar na chamada ou parse
        """
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # Atualiza configurações se diferentes do padrão
            if temperature != 0.1 or max_tokens != 1000:
                self.llm.temperature = temperature
                self.llm.max_tokens = max_tokens

            # Prepara config para LangSmith tracing
            invoke_config = {}

            if run_name:
                invoke_config["run_name"] = run_name

            if metadata:
                invoke_config["metadata"] = metadata

            if tags:
                invoke_config["tags"] = tags

            # Log tracing info
            if invoke_config:
                logger.debug(
                    f"LLM call with tracing: run_name={run_name}, "
                    f"metadata={metadata}, tags={tags}"
                )

            # Chama o LLM com config de tracing
            if invoke_config:
                response = await self.llm.ainvoke(messages, config=invoke_config)
            else:
                response = await self.llm.ainvoke(messages)

            content = response.content

            # Parse do JSON da resposta
            result = self._parse_json_response(content)
            logger.debug(f"LLM response parsed successfully: {result}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise LLMError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise LLMError(f"LLM call failed: {e}")

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Extrai e parseia JSON da resposta do LLM.

        Args:
            content: Conteúdo da resposta

        Returns:
            Dict parseado

        Raises:
            json.JSONDecodeError: Se não conseguir parsear
        """
        # Tenta encontrar JSON na resposta
        content = content.strip()

        # Remove markdown code blocks se presentes
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # Tenta encontrar o JSON
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1

        if start_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx:end_idx]
            return json.loads(json_str)

        # Se não encontrou, tenta parsear diretamente
        return json.loads(content)

    async def analyze_batch(
        self,
        system_prompt: str,
        user_prompts: List[str],
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Executa análise em lote.

        Args:
            system_prompt: Prompt do sistema
            user_prompts: Lista de prompts do usuário
            temperature: Temperatura
            max_tokens: Máximo de tokens

        Returns:
            Lista de resultados
        """
        results = []
        for prompt in user_prompts:
            try:
                result = await self.analyze(
                    system_prompt, prompt, temperature, max_tokens
                )
                results.append(result)
            except LLMError as e:
                logger.warning(f"Batch item failed: {e}")
                results.append({"error": str(e)})
        return results

    async def health_check(self) -> bool:
        """
        Verifica conectividade com Azure OpenAI.

        Returns:
            True se conectado, False caso contrário
        """
        try:
            messages = [HumanMessage(content="Olá")]
            response = await self.llm.ainvoke(messages)
            return bool(response.content)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_model_info(self) -> Dict[str, str]:
        """
        Retorna informações do modelo configurado.

        Returns:
            Dict com informações do modelo
        """
        return {
            "endpoint": self.settings.azure_openai_endpoint,
            "deployment": self.settings.azure_openai_deployment_name,
            "api_version": self.settings.azure_openai_api_version,
        }


# Factory function
_client: Optional[AzureOpenAIClient] = None


def get_openai_client() -> AzureOpenAIClient:
    """
    Factory function para obter cliente.

    Returns:
        Instância do AzureOpenAIClient
    """
    global _client
    if _client is None:
        _client = AzureOpenAIClient()
    return _client
