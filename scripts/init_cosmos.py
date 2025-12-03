#!/usr/bin/env python3
"""
Script para inicializar o Azure Cosmos DB.
Cria o database, containers e popula dados iniciais dos times.

Uso:
    python scripts/init_cosmos.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from src.core.config import get_settings

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("init_cosmos")


def init_database():
    """Inicializa database e containers no Cosmos DB."""
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("Iniciando configuração do Azure Cosmos DB")
    logger.info("=" * 60)

    # Conecta ao Cosmos DB
    logger.info(f"Conectando ao endpoint: {settings.cosmos_endpoint[:50]}...")

    client = CosmosClient(
        url=settings.cosmos_endpoint,
        credential=settings.cosmos_key,
    )

    # Cria database
    logger.info(f"\n[1/4] Criando database '{settings.cosmos_database_name}'...")
    try:
        database = client.create_database_if_not_exists(
            id=settings.cosmos_database_name
        )
        logger.info(f"✓ Database '{settings.cosmos_database_name}' pronto")
    except exceptions.CosmosHttpResponseError as e:
        logger.error(f"✗ Falha ao criar database: {e.message}")
        raise

    # Cria container de reclamações
    # Nota: Não especificar throughput para contas serverless
    logger.info("\n[2/4] Criando container 'complaints'...")
    try:
        complaints_container = database.create_container_if_not_exists(
            id="complaints",
            partition_key=PartitionKey(path="/source"),
        )
        logger.info("✓ Container 'complaints' pronto (partition key: /source)")
    except exceptions.CosmosHttpResponseError as e:
        logger.error(f"✗ Falha ao criar container complaints: {e.message}")
        raise

    # Cria container de auditoria
    logger.info("\n[3/4] Criando container 'audit_log'...")
    try:
        audit_container = database.create_container_if_not_exists(
            id="audit_log",
            partition_key=PartitionKey(path="/date"),
        )
        logger.info("✓ Container 'audit_log' pronto (partition key: /date)")
    except exceptions.CosmosHttpResponseError as e:
        logger.error(f"✗ Falha ao criar container audit_log: {e.message}")
        raise

    # Cria container de times (opcional - para cache/lookup rápido)
    logger.info("\n[4/4] Criando container 'teams'...")
    try:
        teams_container = database.create_container_if_not_exists(
            id="teams",
            partition_key=PartitionKey(path="/id"),
        )
        logger.info("✓ Container 'teams' pronto (partition key: /id)")
    except exceptions.CosmosHttpResponseError as e:
        logger.error(f"✗ Falha ao criar container teams: {e.message}")
        raise

    # Popula dados dos times
    logger.info("\n" + "=" * 60)
    logger.info("Populando dados dos times...")
    logger.info("=" * 60)

    teams_file = Path(__file__).parent.parent / "data" / "mock" / "teams.json"

    if teams_file.exists():
        with open(teams_file, "r", encoding="utf-8") as f:
            teams_data = json.load(f)

        for team in teams_data.get("teams", []):
            try:
                # Adiciona company info ao documento
                team["company"] = teams_data.get("company", "TechNova Store")

                teams_container.upsert_item(team)
                logger.info(f"✓ Time '{team['name']}' salvo")

            except exceptions.CosmosHttpResponseError as e:
                logger.warning(f"✗ Falha ao salvar time '{team.get('name')}': {e.message}")

        # Salva regras de roteamento
        routing_rules = {
            "id": "routing-rules",
            "company": teams_data.get("company", "TechNova Store"),
            "rules": teams_data.get("routing_rules", []),
        }

        try:
            teams_container.upsert_item(routing_rules)
            logger.info("✓ Regras de roteamento salvas")
        except exceptions.CosmosHttpResponseError as e:
            logger.warning(f"✗ Falha ao salvar regras: {e.message}")

    else:
        logger.warning(f"Arquivo de times não encontrado: {teams_file}")

    # Resumo final
    logger.info("\n" + "=" * 60)
    logger.info("INICIALIZAÇÃO CONCLUÍDA!")
    logger.info("=" * 60)
    logger.info(f"""
Recursos criados:
  • Database: {settings.cosmos_database_name}
  • Container: complaints (partition: /source)
  • Container: audit_log (partition: /date)
  • Container: teams (partition: /id)

Para verificar no Azure Portal:
  1. Acesse: https://portal.azure.com
  2. Navegue até sua conta Cosmos DB
  3. Clique em 'Data Explorer'
  4. Expanda o database '{settings.cosmos_database_name}'
""")


def verify_connection():
    """Verifica se a conexão com o Cosmos DB está funcionando."""
    settings = get_settings()

    logger.info("Verificando conexão...")

    try:
        client = CosmosClient(
            url=settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )

        # Lista databases para verificar conexão
        databases = list(client.list_databases())
        logger.info(f"✓ Conexão OK. Databases existentes: {len(databases)}")

        return True

    except Exception as e:
        logger.error(f"✗ Falha na conexão: {e}")
        return False


def show_stats():
    """Mostra estatísticas atuais do database."""
    settings = get_settings()

    try:
        client = CosmosClient(
            url=settings.cosmos_endpoint,
            credential=settings.cosmos_key,
        )

        database = client.get_database_client(settings.cosmos_database_name)

        logger.info("\n" + "=" * 60)
        logger.info("ESTATÍSTICAS DO DATABASE")
        logger.info("=" * 60)

        # Container complaints
        try:
            complaints = database.get_container_client("complaints")
            query = "SELECT VALUE COUNT(1) FROM c"
            count = list(complaints.query_items(query, enable_cross_partition_query=True))
            logger.info(f"• Complaints: {count[0] if count else 0} documentos")
        except Exception:
            logger.info("• Complaints: container não encontrado")

        # Container audit_log
        try:
            audit = database.get_container_client("audit_log")
            query = "SELECT VALUE COUNT(1) FROM c"
            count = list(audit.query_items(query, enable_cross_partition_query=True))
            logger.info(f"• Audit Log: {count[0] if count else 0} eventos")
        except Exception:
            logger.info("• Audit Log: container não encontrado")

        # Container teams
        try:
            teams = database.get_container_client("teams")
            query = "SELECT VALUE COUNT(1) FROM c"
            count = list(teams.query_items(query, enable_cross_partition_query=True))
            logger.info(f"• Teams: {count[0] if count else 0} documentos")
        except Exception:
            logger.info("• Teams: container não encontrado")

    except Exception as e:
        logger.error(f"Falha ao obter estatísticas: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Inicializa Azure Cosmos DB para o ReclamaAI"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Apenas verifica a conexão"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostra estatísticas do database"
    )

    args = parser.parse_args()

    if args.verify:
        verify_connection()
    elif args.stats:
        show_stats()
    else:
        if verify_connection():
            init_database()
            show_stats()
        else:
            logger.error("Conexão falhou. Verifique as credenciais no .env")
            sys.exit(1)
