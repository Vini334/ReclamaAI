#!/usr/bin/env python3
"""
Teste End-to-End do ReclamaAI.
Processa 10 reclamações variadas e verifica todo o fluxo.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.orchestrator import ComplaintOrchestrator
from src.services.cosmos_service import get_cosmos_service
from src.services.mock_data_loader import get_data_loader
from src.models.schemas import ComplaintState, ComplaintSource
from src.utils.langsmith_config import get_langsmith_config, verify_langsmith_connection

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("e2e_test")

# Desabilita logs verbosos
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class E2ETestResult:
    """Resultado de um teste individual."""

    def __init__(self, complaint_id: str):
        self.complaint_id = complaint_id
        self.source = ""
        self.original_description = ""
        self.anonymized_description = ""
        self.pii_anonymized = False
        self.category = ""
        self.expected_team = ""
        self.actual_team = ""
        self.routing_correct = False
        self.ticket_created = False
        self.ticket_id = ""
        self.saved_to_cosmos = False
        self.processing_time = 0.0
        self.status = ""
        self.errors: List[str] = []


async def run_e2e_test():
    """Executa teste end-to-end completo."""

    print("=" * 70)
    print("  TESTE END-TO-END DO RECLAMAAI")
    print("=" * 70)
    print(f"  Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Verifica pré-requisitos
    print("\n[1/6] VERIFICANDO PRÉ-REQUISITOS...")
    print("-" * 50)

    # LangSmith
    langsmith = get_langsmith_config()
    if langsmith.is_enabled():
        status = await verify_langsmith_connection()
        if status.get("connected"):
            print(f"  ✓ LangSmith: Conectado (projeto: {langsmith.settings.langchain_project})")
        else:
            print(f"  ⚠ LangSmith: Configurado mas não conectado")
    else:
        print("  ⚠ LangSmith: Não configurado (traces não serão enviados)")

    # Cosmos DB
    cosmos = get_cosmos_service()
    try:
        await cosmos.initialize()
        print("  ✓ Cosmos DB: Conectado")
    except Exception as e:
        print(f"  ✗ Cosmos DB: Erro - {e}")
        return

    # 2. Carrega reclamações variadas
    print("\n[2/6] CARREGANDO RECLAMAÇÕES VARIADAS...")
    print("-" * 50)

    loader = get_data_loader()
    all_complaints = loader.load_all_complaints()

    # Seleciona 10 reclamações de diferentes fontes
    selected = []
    sources_used = set()

    # Tenta pegar 2 de cada fonte
    for complaint in all_complaints:
        source = complaint.source.value
        if source not in sources_used or len([c for c in selected if c.source.value == source]) < 2:
            selected.append(complaint)
            sources_used.add(source)
        if len(selected) >= 10:
            break

    # Completa com mais se necessário
    for complaint in all_complaints:
        if complaint not in selected:
            selected.append(complaint)
        if len(selected) >= 10:
            break

    print(f"  Selecionadas: {len(selected)} reclamações")
    for source in set(c.source.value for c in selected):
        count = len([c for c in selected if c.source.value == source])
        print(f"    - {source}: {count}")

    # 3. Processa reclamações
    print("\n[3/6] PROCESSANDO RECLAMAÇÕES...")
    print("-" * 50)

    orchestrator = ComplaintOrchestrator(enable_persistence=True)
    results: List[E2ETestResult] = []

    for i, complaint in enumerate(selected):
        complaint_id = complaint.id or complaint.external_id
        result = E2ETestResult(complaint_id)
        result.source = complaint.source.value
        result.original_description = complaint.description[:100] + "..." if len(complaint.description) > 100 else complaint.description

        print(f"\n  [{i+1}/10] {complaint_id}")
        print(f"         Fonte: {complaint.source.value}")
        print(f"         Título: {complaint.title[:50]}...")

        start_time = time.time()

        try:
            state = await orchestrator.process_complaint(complaint)
            result.processing_time = time.time() - start_time
            result.status = state.workflow_status.value

            # Verifica anonimização
            if state.complaint_anonymized:
                result.anonymized_description = state.complaint_anonymized.description[:100] + "..."

                # Verifica se PII foi removido
                pii_markers = ["[CPF REMOVIDO]", "[EMAIL REMOVIDO]", "[TELEFONE REMOVIDO]", "[CARTÃO REMOVIDO]"]
                original_has_pii = any(
                    marker.replace("[", "").replace("]", "").replace(" REMOVIDO", "").lower()
                    in complaint.description.lower()
                    for marker in ["cpf", "email", "@", "telefone", "cartão", "cartao"]
                )

                if original_has_pii:
                    result.pii_anonymized = any(marker in state.complaint_anonymized.description for marker in pii_markers)
                else:
                    result.pii_anonymized = True  # Não tinha PII, então está OK

            # Verifica classificação
            if state.complaint_analyzed:
                result.category = state.complaint_analyzed.category.value

            # Verifica roteamento
            if state.routing_decision:
                result.actual_team = state.routing_decision.team

                # Verifica se roteamento faz sentido
                category_team_map = {
                    "Atraso na entrega": "Time de Logística",
                    "Produto não entregue": "Time de Logística",
                    "Produto com defeito": "Time de Produtos",
                    "Produto diferente do anunciado": "Time de Produtos",
                    "Cobrança indevida": "Time Financeiro",
                    "Reembolso não processado": "Time Financeiro",
                    "Atendimento ruim": "Atendimento Nível 2",
                    "Cancelamento negado": "Atendimento Nível 2",
                    "Dificuldade de contato": "Atendimento Nível 2",
                    "Problema com vendedor (marketplace)": "Time Marketplace",
                }

                result.expected_team = category_team_map.get(result.category, "")
                result.routing_correct = result.actual_team == result.expected_team

            # Verifica ticket
            if state.ticket_info:
                result.ticket_created = True
                result.ticket_id = state.ticket_info.jira_key

            # Status
            status_icon = "✓" if state.workflow_status.value == "COMPLETED" else "⚠"
            print(f"         Status: {status_icon} {state.workflow_status.value}")
            print(f"         Categoria: {result.category}")
            print(f"         Time: {result.actual_team}")
            print(f"         Tempo: {result.processing_time:.2f}s")

            if state.errors:
                result.errors = state.errors
                print(f"         Erros: {state.errors}")

        except Exception as e:
            result.processing_time = time.time() - start_time
            result.status = "ERROR"
            result.errors.append(str(e))
            print(f"         ✗ ERRO: {e}")

        results.append(result)

    # 4. Verifica dados no Cosmos DB
    print("\n[4/6] VERIFICANDO DADOS NO COSMOS DB...")
    print("-" * 50)

    cosmos_stats = await cosmos.get_stats()
    print(f"  Total de documentos: {cosmos_stats.get('total', 0)}")

    for result in results:
        try:
            saved = await cosmos.get_complaint(result.complaint_id)
            result.saved_to_cosmos = saved is not None
            status = "✓" if result.saved_to_cosmos else "✗"
            print(f"  {status} {result.complaint_id[:20]}...")
        except Exception as e:
            result.saved_to_cosmos = False
            print(f"  ✗ {result.complaint_id[:20]}... (erro: {e})")

    # 5. Gera resumo
    print("\n[5/6] RESUMO DOS RESULTADOS...")
    print("-" * 50)

    total = len(results)
    successful = len([r for r in results if r.status == "COMPLETED"])
    failed = total - successful

    print(f"\n  PROCESSAMENTO:")
    print(f"    Total processadas: {total}")
    print(f"    Sucesso: {successful} ({successful/total*100:.0f}%)")
    print(f"    Falhas: {failed} ({failed/total*100:.0f}%)")

    print(f"\n  VERIFICAÇÕES:")
    pii_ok = len([r for r in results if r.pii_anonymized])
    routing_ok = len([r for r in results if r.routing_correct])
    tickets_ok = len([r for r in results if r.ticket_created])
    cosmos_ok = len([r for r in results if r.saved_to_cosmos])

    print(f"    PII anonimizado: {pii_ok}/{total} ({pii_ok/total*100:.0f}%)")
    print(f"    Roteamento correto: {routing_ok}/{total} ({routing_ok/total*100:.0f}%)")
    print(f"    Tickets criados: {tickets_ok}/{total} ({tickets_ok/total*100:.0f}%)")
    print(f"    Salvos no Cosmos: {cosmos_ok}/{total} ({cosmos_ok/total*100:.0f}%)")

    print(f"\n  DISTRIBUIÇÃO POR CATEGORIA:")
    categories = {}
    for r in results:
        if r.category:
            categories[r.category] = categories.get(r.category, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    print(f"\n  DISTRIBUIÇÃO POR TIME:")
    teams = {}
    for r in results:
        if r.actual_team:
            teams[r.actual_team] = teams.get(r.actual_team, 0) + 1
    for team, count in sorted(teams.items(), key=lambda x: -x[1]):
        print(f"    {team}: {count}")

    print(f"\n  DISTRIBUIÇÃO POR FONTE:")
    sources = {}
    for r in results:
        sources[r.source] = sources.get(r.source, 0) + 1
    for source, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"    {source}: {count}")

    processing_times = [r.processing_time for r in results if r.processing_time > 0]
    if processing_times:
        avg_time = sum(processing_times) / len(processing_times)
        min_time = min(processing_times)
        max_time = max(processing_times)
        print(f"\n  TEMPO DE PROCESSAMENTO:")
        print(f"    Médio: {avg_time:.2f}s")
        print(f"    Mínimo: {min_time:.2f}s")
        print(f"    Máximo: {max_time:.2f}s")
        print(f"    Total: {sum(processing_times):.2f}s")

    # 6. Instruções finais
    print("\n[6/6] VERIFICAÇÕES MANUAIS...")
    print("-" * 50)

    print("""
  Para verificar no COSMOS DB (Azure Portal):
    1. Acesse: https://portal.azure.com
    2. Navegue até sua conta Cosmos DB
    3. Clique em 'Data Explorer'
    4. Expanda 'reclamaai' > 'complaints'
    5. Você deve ver os documentos processados

  Para verificar no LANGSMITH:
    1. Acesse: https://smith.langchain.com/
    2. Navegue até o projeto: reclamaai
    3. Você deve ver traces com:
       - Run name: analyze_complaint_*
       - Tags: reclamaai, analyst, source:*
    4. Clique em um trace para ver:
       - Prompt enviado
       - Resposta do LLM
       - Tokens usados
       - Latência
""")

    # Tabela detalhada
    print("\n  DETALHES POR RECLAMAÇÃO:")
    print("  " + "-" * 90)
    print(f"  {'ID':<25} {'Fonte':<15} {'Categoria':<25} {'Time':<20} {'OK'}")
    print("  " + "-" * 90)

    for r in results:
        id_short = r.complaint_id[:23] + ".." if len(r.complaint_id) > 25 else r.complaint_id
        cat_short = r.category[:23] + ".." if len(r.category) > 25 else r.category
        team_short = r.actual_team[:18] + ".." if len(r.actual_team) > 20 else r.actual_team

        checks = []
        if r.pii_anonymized: checks.append("PII")
        if r.routing_correct: checks.append("Route")
        if r.ticket_created: checks.append("Ticket")
        if r.saved_to_cosmos: checks.append("Cosmos")

        ok_str = ", ".join(checks) if checks else "FAILED"

        print(f"  {id_short:<25} {r.source:<15} {cat_short:<25} {team_short:<20} {ok_str}")

    print("  " + "-" * 90)

    # Resultado final
    print("\n" + "=" * 70)
    if successful == total and pii_ok == total and cosmos_ok == total:
        print("  ✓ TESTE END-TO-END CONCLUÍDO COM SUCESSO!")
    else:
        print("  ⚠ TESTE END-TO-END CONCLUÍDO COM ALGUNS PROBLEMAS")
    print("=" * 70)

    return results


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
