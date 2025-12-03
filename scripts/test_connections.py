"""
Script para testar todas as conexões do .env.
Verifica Azure OpenAI, Azure AI Search e LangSmith.
"""

import asyncio
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os


def print_header(title: str) -> None:
    """Imprime cabeçalho formatado."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, success: bool, message: str = "") -> None:
    """Imprime resultado do teste."""
    status = "✅ OK" if success else "❌ FALHOU"
    print(f"  {name}: {status}")
    if message:
        print(f"     └─ {message}")


async def test_azure_openai() -> bool:
    """Testa conexão com Azure OpenAI."""
    print_header("AZURE OPENAI")

    # Verifica variáveis de ambiente
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    print(f"  Endpoint: {endpoint}")
    print(f"  Deployment: {deployment}")
    print(f"  API Version: {api_version}")
    print(f"  API Key: {'*' * 20}...{api_key[-4:] if api_key else 'NÃO CONFIGURADA'}")
    print()

    if not endpoint or not api_key:
        print_result("Configuração", False, "Endpoint ou API Key não configurados")
        return False

    print_result("Configuração", True, "Variáveis encontradas")

    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": "Responda apenas: OK"}],
            max_tokens=10,
        )

        result = response.choices[0].message.content
        print_result("Conexão LLM", True, f"Resposta: {result}")
        return True

    except Exception as e:
        print_result("Conexão LLM", False, str(e))
        return False


async def test_azure_search() -> bool:
    """Testa conexão com Azure AI Search."""
    print_header("AZURE AI SEARCH")

    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    api_key = os.getenv("AZURE_SEARCH_API_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "teams-index")

    print(f"  Endpoint: {endpoint}")
    print(f"  Index: {index_name}")
    print(f"  API Key: {'*' * 20}...{api_key[-4:] if api_key else 'NÃO CONFIGURADA'}")
    print()

    if not endpoint or not api_key:
        print_result("Configuração", False, "Endpoint ou API Key não configurados")
        return False

    print_result("Configuração", True, "Variáveis encontradas")

    try:
        from azure.search.documents.indexes import SearchIndexClient
        from azure.core.credentials import AzureKeyCredential

        credential = AzureKeyCredential(api_key)
        index_client = SearchIndexClient(endpoint=endpoint, credential=credential)

        # Lista índices existentes
        indexes = []
        for idx in index_client.list_indexes():
            indexes.append(idx.name)

        print_result("Conexão", True, "Conectado ao serviço")
        print(f"     └─ Índices existentes: {indexes if indexes else 'Nenhum'}")

        if index_name in indexes:
            print_result(f"Índice '{index_name}'", True, "Encontrado")
        else:
            print_result(f"Índice '{index_name}'", False, "Não existe (precisa ser criado)")

        return True

    except Exception as e:
        print_result("Conexão", False, str(e))
        return False


async def test_langsmith() -> bool:
    """Testa conexão com LangSmith."""
    print_header("LANGSMITH (Observabilidade)")

    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
    api_key = os.getenv("LANGCHAIN_API_KEY")
    project = os.getenv("LANGCHAIN_PROJECT", "reclamaai")

    print(f"  Tracing Ativo: {tracing}")
    print(f"  Projeto: {project}")
    print(f"  API Key: {'*' * 20}...{api_key[-4:] if api_key else 'NÃO CONFIGURADA'}")
    print()

    if not api_key:
        print_result("Configuração", False, "API Key não configurada")
        return False

    print_result("Configuração", True, "Variáveis encontradas")

    try:
        from langsmith import Client

        client = Client()
        projects = list(client.list_projects())
        project_names = [p.name for p in projects]

        print_result("Conexão", True, "Conectado ao LangSmith")
        print(f"     └─ Projetos: {project_names[:5]}{'...' if len(project_names) > 5 else ''}")

        if project in project_names:
            print_result(f"Projeto '{project}'", True, "Encontrado")
        else:
            print_result(f"Projeto '{project}'", False, "Não existe (será criado automaticamente)")

        return True

    except Exception as e:
        print_result("Conexão", False, str(e))
        return False


async def test_cosmos_db() -> bool:
    """Testa conexão com Cosmos DB."""
    print_header("AZURE COSMOS DB")

    endpoint = os.getenv("COSMOS_ENDPOINT")
    key = os.getenv("COSMOS_KEY")
    database = os.getenv("COSMOS_DATABASE_NAME", "reclamaai")

    print(f"  Endpoint: {endpoint}")
    print(f"  Database: {database}")
    print(f"  Key: {'*' * 20}...{key[-4:] if key else 'NÃO CONFIGURADA'}")
    print()

    if not endpoint or not key:
        print_result("Configuração", False, "Endpoint ou Key não configurados")
        print("     └─ Cosmos DB é opcional para o MVP (dados ficam em memória)")
        return False

    print_result("Configuração", True, "Variáveis encontradas")

    try:
        from azure.cosmos import CosmosClient

        client = CosmosClient(endpoint, key)
        databases = list(client.list_databases())
        db_names = [db['id'] for db in databases]

        print_result("Conexão", True, "Conectado ao Cosmos DB")
        print(f"     └─ Databases: {db_names if db_names else 'Nenhum'}")

        if database in db_names:
            print_result(f"Database '{database}'", True, "Encontrado")
        else:
            print_result(f"Database '{database}'", False, "Não existe (precisa ser criado)")

        return True

    except Exception as e:
        print_result("Conexão", False, str(e))
        return False


async def test_mock_data() -> bool:
    """Testa carregamento dos dados mock."""
    print_header("DADOS MOCK")

    mock_path = os.getenv("MOCK_DATA_PATH", "./data/mock")
    print(f"  Caminho: {mock_path}")
    print()

    try:
        from src.services.mock_data_loader import get_data_loader

        loader = get_data_loader()
        stats = loader.get_stats()

        print_result("Carregamento", True, "Dados carregados com sucesso")
        print(f"     └─ Reclame Aqui: {stats['reclame_aqui']} reclamações")
        print(f"     └─ Jira: {stats['jira']} issues")
        print(f"     └─ Chat: {stats['chat']} transcrições")
        print(f"     └─ Telefone: {stats['phone']} transcrições")
        print(f"     └─ Email: {stats['email']} emails")
        print(f"     └─ TOTAL: {stats['total']} reclamações")

        # Testa carregamento de times
        teams = loader.load_teams()
        print(f"     └─ Times para RAG: {len(teams)}")

        return True

    except Exception as e:
        print_result("Carregamento", False, str(e))
        return False


async def main():
    """Executa todos os testes."""
    print("\n" + "🔍 " + "=" * 56)
    print("   TESTE DE CONEXÕES - ReclamaAI")
    print("=" * 60)

    results = {}

    # Testa cada serviço
    results["Azure OpenAI"] = await test_azure_openai()
    results["Azure AI Search"] = await test_azure_search()
    results["LangSmith"] = await test_langsmith()
    results["Cosmos DB"] = await test_cosmos_db()
    results["Dados Mock"] = await test_mock_data()

    # Resumo
    print_header("RESUMO")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, success in results.items():
        print_result(name, success)

    print()
    print(f"  Resultado: {passed}/{total} conexões OK")

    # Verifica serviços críticos para MVP
    critical = ["Azure OpenAI", "Dados Mock"]
    critical_ok = all(results.get(s, False) for s in critical)

    if critical_ok:
        print("\n  ✅ Serviços críticos para MVP estão funcionando!")
        print("     Você pode prosseguir com a implementação.")
    else:
        print("\n  ⚠️  Alguns serviços críticos não estão funcionando.")
        print("     Verifique as configurações no arquivo .env")

    print("\n" + "=" * 60 + "\n")

    return 0 if critical_ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
