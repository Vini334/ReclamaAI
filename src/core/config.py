"""
Configurações centralizadas do ReclamaAI.
Carrega variáveis de ambiente e define configurações do sistema.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do ambiente."""

    # Application
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str = "2024-02-15-preview"
    azure_openai_deployment_name: str = "gpt-4o-mini"

    # Azure AI Search
    azure_search_endpoint: str
    azure_search_api_key: str
    azure_search_index_name: str = "teams-index"

    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database_name: str = "reclamaai"
    cosmos_container_name: str = "complaints"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str
    langchain_project: str = "reclamaai"

    # Azure Monitor
    applicationinsights_connection_string: str = ""

    # Mock Settings
    use_mock_jira: bool = True
    use_mock_email: bool = True
    mock_data_path: str = "./data/mock"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    return Settings()
