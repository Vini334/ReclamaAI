#!/usr/bin/env python3
"""
Script para processar lote de reclamações.
Executa o workflow completo de classificação e roteamento.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import argparse
import logging

from src.services.orchestrator import get_orchestrator
from src.models.schemas import WorkflowStatus


def setup_logging(verbose: bool = False) -> None:
    """Configura logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    # Reduz verbosidade de bibliotecas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def print_header() -> None:
    """Imprime cabeçalho."""
    print("\n" + "=" * 70)
    print("  ReclamaAI - Processamento em Lote")
    print("=" * 70)


def print_result(state) -> None:
    """Imprime resultado de uma reclamação processada."""
    complaint = state.complaint_raw
    status_emoji = "✅" if state.workflow_status == WorkflowStatus.COMPLETED else "❌"

    print(f"\n{status_emoji} {complaint.id or complaint.external_id}")
    print(f"   Fonte: {complaint.source.value}")
    print(f"   Título: {complaint.title[:50]}...")
    print(f"   Status: {state.workflow_status.value}")

    if state.complaint_analyzed:
        print(f"   Categoria: {state.complaint_analyzed.category.value}")
        print(f"   Urgência: {state.complaint_analyzed.urgency.value}")
        print(f"   Sentimento: {state.complaint_analyzed.sentiment.value}")

    if state.routing_decision:
        print(f"   Time: {state.routing_decision.team}")
        print(f"   Prioridade: {state.routing_decision.priority.value}")
        print(f"   SLA: {state.routing_decision.sla_hours}h")

    if state.ticket_info:
        print(f"   Ticket: {state.ticket_info.jira_key}")

    if state.errors:
        print(f"   Erros: {', '.join(state.errors)}")


def print_summary(results: list, elapsed: float) -> None:
    """Imprime resumo do processamento."""
    total = len(results)
    completed = sum(1 for r in results if r.workflow_status == WorkflowStatus.COMPLETED)
    failed = total - completed

    # Contagem por categoria
    categories = {}
    teams = {}
    for r in results:
        if r.complaint_analyzed:
            cat = r.complaint_analyzed.category.value
            categories[cat] = categories.get(cat, 0) + 1
        if r.routing_decision:
            team = r.routing_decision.team
            teams[team] = teams.get(team, 0) + 1

    print("\n" + "=" * 70)
    print("  RESUMO DO PROCESSAMENTO")
    print("=" * 70)

    print(f"\n📊 Estatísticas Gerais:")
    print(f"   Total processado: {total}")
    print(f"   ✅ Sucesso: {completed}")
    print(f"   ❌ Falhou: {failed}")
    print(f"   ⏱️  Tempo: {elapsed:.2f}s ({elapsed/total:.2f}s/reclamação)")

    if categories:
        print(f"\n📁 Por Categoria:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"   {cat}: {count}")

    if teams:
        print(f"\n👥 Por Time:")
        for team, count in sorted(teams.items(), key=lambda x: -x[1]):
            print(f"   {team}: {count}")

    print("\n" + "=" * 70 + "\n")


async def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Processa reclamações em lote usando o workflow ReclamaAI"
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=5,
        help="Número de reclamações a processar (default: 5)"
    )
    parser.add_argument(
        "-s", "--source",
        type=str,
        default=None,
        help="Filtrar por fonte (ex: reclame_aqui, jira, chat)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Modo verboso"
    )
    parser.add_argument(
        "--azure-search",
        action="store_true",
        help="Usar Azure AI Search para roteamento (RAG)"
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    print_header()

    print(f"\n🔧 Configuração:")
    print(f"   Limite: {args.limit} reclamações")
    print(f"   Fonte: {args.source or 'todas'}")
    print(f"   Azure Search RAG: {'sim' if args.azure_search else 'não'}")

    # Inicializa orquestrador
    print("\n⏳ Inicializando orquestrador...")
    orchestrator = get_orchestrator(use_azure_search=args.azure_search)
    await orchestrator.initialize()
    print("   ✅ Orquestrador inicializado")

    # Processa lote
    print(f"\n🚀 Iniciando processamento de {args.limit} reclamações...\n")
    start_time = datetime.now()

    results = await orchestrator.process_batch(
        limit=args.limit,
        source_filter=args.source,
    )

    elapsed = (datetime.now() - start_time).total_seconds()

    # Imprime resultados individuais
    for result in results:
        print_result(result)

    # Imprime resumo
    print_summary(results, elapsed)

    # Retorna código de erro se houve falhas
    failed = sum(1 for r in results if r.workflow_status != WorkflowStatus.COMPLETED)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
