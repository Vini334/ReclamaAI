"""
LangGraph workflow para processamento de reclamações.
Grafo exportado para integração com LangGraph Studio.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


# ==============================================================================
# State Definition
# ==============================================================================

class ComplaintGraphState(TypedDict, total=False):
    """
    Estado compartilhado entre os nós do grafo.
    Usando total=False para permitir campos opcionais.
    """
    # Identificação
    complaint_id: str
    source: str

    # Dados da reclamação
    complaint_raw: Dict[str, Any]
    complaint_anonymized: Optional[Dict[str, Any]]
    complaint_analyzed: Optional[Dict[str, Any]]
    routing_decision: Optional[Dict[str, Any]]
    ticket_info: Optional[Dict[str, Any]]
    notification_info: Optional[Dict[str, Any]]

    # Controle de workflow
    current_step: str
    workflow_status: str
    errors: List[str]

    # Timestamps
    started_at: str
    completed_at: Optional[str]


# ==============================================================================
# Helper Functions
# ==============================================================================

def get_complaint_id(state: dict) -> str:
    """Extrai complaint_id do state de forma segura."""
    # Tenta do nível raiz
    if "complaint_id" in state:
        return state["complaint_id"]
    # Tenta do complaint_raw
    raw = state.get("complaint_raw", {})
    if isinstance(raw, dict):
        return raw.get("id") or raw.get("external_id") or "unknown"
    return "unknown"


def ensure_defaults(state: dict) -> dict:
    """Garante que o state tem todos os campos necessários com defaults."""
    defaults = {
        "complaint_id": get_complaint_id(state),
        "source": state.get("source") or state.get("complaint_raw", {}).get("source", "UNKNOWN"),
        "complaint_raw": state.get("complaint_raw", {}),
        "complaint_anonymized": state.get("complaint_anonymized"),
        "complaint_analyzed": state.get("complaint_analyzed"),
        "routing_decision": state.get("routing_decision"),
        "ticket_info": state.get("ticket_info"),
        "notification_info": state.get("notification_info"),
        "current_step": state.get("current_step", "new"),
        "workflow_status": state.get("workflow_status", "NEW"),
        "errors": state.get("errors", []),
        "started_at": state.get("started_at", datetime.utcnow().isoformat()),
        "completed_at": state.get("completed_at"),
    }
    return defaults


# ==============================================================================
# Node Functions
# ==============================================================================

def anonymize_node(state: dict) -> dict:
    """
    Nó de anonimização - aplica máscaras de PII para LGPD compliance.
    """
    # Garante defaults
    state = ensure_defaults(state)
    complaint_id = state["complaint_id"]

    logger.info(f"[ANONYMIZE] Processing complaint {complaint_id}")

    try:
        from src.agents import get_privacy_agent
        from src.models.schemas import ComplaintRaw, ComplaintState, WorkflowStatus

        # Reconstrói o ComplaintRaw a partir do dict
        raw_data = state["complaint_raw"]
        if not raw_data:
            raise ValueError("complaint_raw is required")

        complaint_raw = ComplaintRaw(**raw_data)

        # Cria estado para o agente
        agent_state = ComplaintState(
            complaint_raw=complaint_raw,
            workflow_status=WorkflowStatus.NEW,
            errors=[],
        )

        # Executa o agente
        privacy_agent = get_privacy_agent()

        async def run_privacy():
            await privacy_agent.initialize()
            return await privacy_agent.process_state(agent_state)

        # Executa async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, run_privacy()).result()
            else:
                result = loop.run_until_complete(run_privacy())
        except RuntimeError:
            result = asyncio.run(run_privacy())

        # Atualiza estado do grafo
        return {
            **state,
            "complaint_anonymized": (
                result.complaint_anonymized.model_dump(mode="json")
                if result.complaint_anonymized else None
            ),
            "current_step": "anonymized",
            "workflow_status": "ANONYMIZED",
        }

    except Exception as e:
        logger.error(f"[ANONYMIZE] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append(f"Anonymization error: {str(e)}")
        return {
            **state,
            "errors": errors,
            "workflow_status": "FAILED_ANONYMIZATION",
        }


def analyze_node(state: dict) -> dict:
    """
    Nó de análise - usa Azure OpenAI para classificar a reclamação.
    """
    state = ensure_defaults(state)
    complaint_id = state["complaint_id"]

    logger.info(f"[ANALYZE] Processing complaint {complaint_id}")

    # Skip se houve erro anterior
    if state.get("workflow_status", "").startswith("FAILED"):
        logger.warning(f"[ANALYZE] Skipping due to previous error")
        return state

    try:
        from src.agents import get_analyst_agent
        from src.models.schemas import ComplaintRaw, ComplaintState, WorkflowStatus

        # Reconstrói os objetos
        raw_data = state["complaint_raw"]
        complaint_raw = ComplaintRaw(**raw_data)

        anonymized_data = state.get("complaint_anonymized")
        complaint_anonymized = ComplaintRaw(**anonymized_data) if anonymized_data else None

        # Cria estado para o agente
        agent_state = ComplaintState(
            complaint_raw=complaint_raw,
            complaint_anonymized=complaint_anonymized,
            workflow_status=WorkflowStatus.ANONYMIZED,
            errors=[],
        )

        # Executa o agente
        analyst_agent = get_analyst_agent()

        async def run_analyst():
            await analyst_agent.initialize()
            return await analyst_agent.execute(agent_state)

        # Executa async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, run_analyst()).result()
            else:
                result = loop.run_until_complete(run_analyst())
        except RuntimeError:
            result = asyncio.run(run_analyst())

        # Atualiza estado do grafo
        analyzed_dict = None
        if result.complaint_analyzed:
            analyzed_dict = result.complaint_analyzed.model_dump(mode="json")
            logger.info(
                f"[ANALYZE] Completed: category={result.complaint_analyzed.category.value}, "
                f"urgency={result.complaint_analyzed.urgency.value}"
            )

        return {
            **state,
            "complaint_analyzed": analyzed_dict,
            "current_step": "analyzed",
            "workflow_status": result.workflow_status.value,
        }

    except Exception as e:
        logger.error(f"[ANALYZE] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append(f"Analysis error: {str(e)}")
        return {
            **state,
            "errors": errors,
            "workflow_status": "FAILED_LLM",
        }


def route_node(state: dict) -> dict:
    """
    Nó de roteamento - determina qual equipe deve tratar a reclamação.
    """
    state = ensure_defaults(state)
    complaint_id = state["complaint_id"]

    logger.info(f"[ROUTE] Processing complaint {complaint_id}")

    # Skip se houve erro anterior
    if state.get("workflow_status", "").startswith("FAILED"):
        logger.warning(f"[ROUTE] Skipping due to previous error")
        return state

    try:
        from src.agents import get_router_agent
        from src.models.schemas import (
            ComplaintRaw, ComplaintAnalyzed, ComplaintState, WorkflowStatus
        )

        # Reconstrói os objetos
        complaint_raw = ComplaintRaw(**state["complaint_raw"])

        analyzed_data = state.get("complaint_analyzed")
        if not analyzed_data:
            raise ValueError("No analysis data available for routing")

        complaint_analyzed = ComplaintAnalyzed(**analyzed_data)

        # Cria estado para o agente
        agent_state = ComplaintState(
            complaint_raw=complaint_raw,
            complaint_analyzed=complaint_analyzed,
            workflow_status=WorkflowStatus.ANALYZED,
            errors=[],
        )

        # Executa o agente (sem Azure Search por padrão no Studio)
        router_agent = get_router_agent(use_azure_search=False)

        async def run_router():
            await router_agent.initialize()
            return await router_agent.execute(agent_state)

        # Executa async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, run_router()).result()
            else:
                result = loop.run_until_complete(run_router())
        except RuntimeError:
            result = asyncio.run(run_router())

        # Atualiza estado do grafo
        routing_dict = None
        if result.routing_decision:
            routing_dict = result.routing_decision.model_dump(mode="json")
            logger.info(
                f"[ROUTE] Completed: team={result.routing_decision.team}, "
                f"priority={result.routing_decision.priority}"
            )

        return {
            **state,
            "routing_decision": routing_dict,
            "current_step": "routed",
            "workflow_status": result.workflow_status.value,
        }

    except Exception as e:
        logger.error(f"[ROUTE] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append(f"Routing error: {str(e)}")
        return {
            **state,
            "errors": errors,
            "workflow_status": "FAILED_ROUTING",
        }


def communicate_node(state: dict) -> dict:
    """
    Nó de comunicação - cria ticket no Jira e envia notificações.
    """
    state = ensure_defaults(state)
    complaint_id = state["complaint_id"]

    logger.info(f"[COMMUNICATE] Processing complaint {complaint_id}")

    # Skip se houve erro anterior
    if state.get("workflow_status", "").startswith("FAILED"):
        logger.warning(f"[COMMUNICATE] Skipping due to previous error")
        return state

    try:
        from src.agents import get_communicator_agent
        from src.models.schemas import (
            ComplaintRaw, ComplaintAnalyzed, RoutingDecision,
            ComplaintState, WorkflowStatus
        )

        # Reconstrói os objetos
        complaint_raw = ComplaintRaw(**state["complaint_raw"])

        analyzed_data = state.get("complaint_analyzed")
        complaint_analyzed = ComplaintAnalyzed(**analyzed_data) if analyzed_data else None

        routing_data = state.get("routing_decision")
        if not routing_data:
            raise ValueError("No routing decision available")

        routing_decision = RoutingDecision(**routing_data)

        # Cria estado para o agente
        agent_state = ComplaintState(
            complaint_raw=complaint_raw,
            complaint_analyzed=complaint_analyzed,
            routing_decision=routing_decision,
            workflow_status=WorkflowStatus.ROUTED,
            errors=[],
        )

        # Executa o agente
        communicator_agent = get_communicator_agent()

        async def run_communicator():
            await communicator_agent.initialize()
            return await communicator_agent.execute(agent_state)

        # Executa async
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, run_communicator()).result()
            else:
                result = loop.run_until_complete(run_communicator())
        except RuntimeError:
            result = asyncio.run(run_communicator())

        # Atualiza estado do grafo
        ticket_dict = None
        notification_dict = None

        if result.ticket_info:
            ticket_dict = result.ticket_info.model_dump(mode="json")
            logger.info(f"[COMMUNICATE] Ticket created: {result.ticket_info.ticket_key}")

        if result.notification_info:
            notification_dict = result.notification_info.model_dump(mode="json")

        return {
            **state,
            "ticket_info": ticket_dict,
            "notification_info": notification_dict,
            "current_step": "completed",
            "workflow_status": result.workflow_status.value,
            "completed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"[COMMUNICATE] Error: {e}", exc_info=True)
        errors = state.get("errors", [])
        errors.append(f"Communication error: {str(e)}")
        return {
            **state,
            "errors": errors,
            "workflow_status": "FAILED_JIRA",
        }


# ==============================================================================
# Graph Definition
# ==============================================================================

def create_complaint_graph() -> StateGraph:
    """
    Cria o grafo de processamento de reclamações.

    Workflow:
    START -> anonymize -> analyze -> route -> communicate -> END
    """
    # Cria o grafo com o tipo de estado
    workflow = StateGraph(ComplaintGraphState)

    # Adiciona nós
    workflow.add_node("anonymize", anonymize_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("route", route_node)
    workflow.add_node("communicate", communicate_node)

    # Define o fluxo linear
    workflow.add_edge(START, "anonymize")
    workflow.add_edge("anonymize", "analyze")
    workflow.add_edge("analyze", "route")
    workflow.add_edge("route", "communicate")
    workflow.add_edge("communicate", END)

    return workflow


# ==============================================================================
# Exported Graph (REQUIRED for LangGraph Studio)
# ==============================================================================

# Compila o grafo - DEVE ser exportado como 'graph'
graph = create_complaint_graph().compile()


# ==============================================================================
# Example Input for LangGraph Studio
# ==============================================================================

# Use este JSON como input no LangGraph Studio:
EXAMPLE_INPUT = {
    "complaint_id": "TEST-001",
    "source": "RECLAME_AQUI",
    "complaint_raw": {
        "id": "TEST-001",
        "external_id": "RA-12345",
        "source": "RECLAME_AQUI",
        "title": "Produto não entregue após 30 dias",
        "description": "Comprei um iPhone 15 no dia 01/11 e até hoje não recebi. Meu CPF é 123.456.789-00 e email joao@gmail.com. Vou ao PROCON!",
        "consumer_name": "João Silva",
        "consumer_contact": "joao@gmail.com",
        "created_at": "2024-11-01T10:30:00Z",
        "raw_data": {}
    },
    "errors": []
}
