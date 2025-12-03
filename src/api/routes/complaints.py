"""
Endpoints para gerenciamento de reclamações.
Usa Azure Cosmos DB para persistência.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from src.models.schemas import (
    ComplaintRaw,
    ComplaintSource,
    ComplaintState,
    WorkflowStatus,
)
from src.services.mock_data_loader import get_data_loader
from src.services.orchestrator import get_orchestrator
from src.services.cosmos_service import get_cosmos_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ProcessRequest(BaseModel):
    """Request para processar reclamações."""
    source: Optional[str] = None
    limit: Optional[int] = 10


class ProcessResponse(BaseModel):
    """Response do processamento."""
    message: str
    source: str
    total_queued: int
    processing: bool


class ComplaintSummary(BaseModel):
    """Resumo de uma reclamação processada."""
    id: str
    title: str
    source: str
    status: str
    category: Optional[str] = None
    team: Optional[str] = None
    ticket: Optional[str] = None
    processed_at: Optional[datetime] = None


class StatsResponse(BaseModel):
    """Response com estatísticas."""
    total: int
    by_status: Dict[str, int]
    by_source: Dict[str, int]
    by_category: Dict[str, int]
    by_team: Dict[str, int]


async def _ensure_cosmos_initialized():
    """Garante que o CosmosService está inicializado."""
    cosmos = get_cosmos_service()
    if not cosmos.is_initialized():
        await cosmos.initialize()
    return cosmos


@router.get("/complaints", response_model=List[ComplaintSummary])
async def list_complaints(
    source: Optional[str] = Query(None, description="Filtrar por fonte"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Lista reclamações processadas com filtros opcionais."""
    cosmos = await _ensure_cosmos_initialized()

    try:
        complaints = await cosmos.list_complaints(
            source=source,
            status=status,
            limit=limit,
            offset=offset,
        )

        # Converte para resumo
        summaries = []
        for c in complaints:
            summary = ComplaintSummary(
                id=c.complaint_raw.id or c.complaint_raw.external_id,
                title=c.complaint_raw.title,
                source=c.complaint_raw.source.value,
                status=c.workflow_status.value,
                category=c.complaint_analyzed.category.value if c.complaint_analyzed else None,
                team=c.routing_decision.team if c.routing_decision else None,
                ticket=c.ticket_info.jira_key if c.ticket_info else None,
                processed_at=c.completed_at,
            )
            summaries.append(summary)

        return summaries

    except Exception as e:
        logger.error(f"Failed to list complaints: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/complaints/available", response_model=Dict[str, Any])
async def list_available_complaints(
    source: Optional[str] = Query(None, description="Filtrar por fonte"),
    limit: int = Query(20, ge=1, le=100),
):
    """Lista reclamações disponíveis para processamento (dados mock)."""
    loader = get_data_loader()

    sources = None
    if source:
        try:
            sources = [ComplaintSource(source)]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source: {source}. Valid sources: {[s.value for s in ComplaintSource]}"
            )

    complaints = loader.load_all_complaints(sources)
    complaints = complaints[:limit]

    return {
        "total": len(complaints),
        "complaints": [
            {
                "id": c.id or c.external_id,
                "title": c.title,
                "source": c.source.value,
                "created_at": c.created_at.isoformat(),
                "consumer_name": c.consumer_name,
            }
            for c in complaints
        ],
    }


@router.get("/complaints/{complaint_id}", response_model=ComplaintState)
async def get_complaint(complaint_id: str):
    """Busca uma reclamação específica pelo ID."""
    cosmos = await _ensure_cosmos_initialized()

    try:
        state = await cosmos.get_complaint(complaint_id)

        if state is None:
            raise HTTPException(status_code=404, detail="Complaint not found")

        return state

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get complaint {complaint_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complaints/process", response_model=ProcessResponse)
async def process_complaints(
    background_tasks: BackgroundTasks,
    request: ProcessRequest = ProcessRequest(),
):
    """
    Dispara o processamento de reclamações em background.

    Args:
        request: Configurações de processamento
    """
    orchestrator = get_orchestrator()

    # Adiciona tarefa em background
    background_tasks.add_task(
        _process_batch,
        orchestrator,
        request.source,
        request.limit or 10,
    )

    return ProcessResponse(
        message="Processing started in background",
        source=request.source or "all",
        total_queued=request.limit or 10,
        processing=True,
    )


async def _process_batch(
    orchestrator,
    source_filter: Optional[str],
    limit: int,
):
    """Processa lote de reclamações (executa em background)."""
    try:
        logger.info(f"Starting batch processing: source={source_filter}, limit={limit}")

        # Cosmos service para persistência
        cosmos = await _ensure_cosmos_initialized()

        results = await orchestrator.process_batch(
            limit=limit,
            source_filter=source_filter,
        )

        # Salva resultados no Cosmos DB
        for state in results:
            try:
                await cosmos.save_complaint(state)
            except Exception as e:
                logger.error(f"Failed to save complaint to Cosmos: {e}")

        logger.info(f"Batch processing completed: {len(results)} complaints processed and saved")

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")


@router.post("/complaints/process-single")
async def process_single_complaint(complaint: ComplaintRaw):
    """
    Processa uma única reclamação de forma síncrona.

    Args:
        complaint: Reclamação a processar
    """
    orchestrator = get_orchestrator()
    cosmos = await _ensure_cosmos_initialized()

    try:
        result = await orchestrator.process_complaint(complaint)

        # Salva resultado no Cosmos DB
        complaint_id = await cosmos.save_complaint(result)

        return {
            "complaint_id": complaint_id,
            "status": result.workflow_status.value,
            "category": result.complaint_analyzed.category.value if result.complaint_analyzed else None,
            "team": result.routing_decision.team if result.routing_decision else None,
            "ticket": result.ticket_info.jira_key if result.ticket_info else None,
            "errors": result.errors,
            "persisted": True,
        }

    except Exception as e:
        logger.error(f"Failed to process complaint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )


@router.post("/complaints/{complaint_id}/reprocess")
async def reprocess_complaint(complaint_id: str):
    """Reprocessa uma reclamação específica."""
    cosmos = await _ensure_cosmos_initialized()

    # Busca reclamação existente
    state = await cosmos.get_complaint(complaint_id)

    if state is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    # Reseta estado
    state.complaint_analyzed = None
    state.routing_decision = None
    state.ticket_info = None
    state.notification_info = None
    state.workflow_status = WorkflowStatus.NEW
    state.errors = []
    state.completed_at = None

    orchestrator = get_orchestrator()

    try:
        result = await orchestrator.process_complaint(state.complaint_raw)

        # Salva resultado atualizado
        await cosmos.save_complaint(result)

        # Log de auditoria
        await cosmos.log_event(
            complaint_id=complaint_id,
            event_type="reprocessed",
            details={"new_status": result.workflow_status.value}
        )

        return {
            "message": f"Reprocessed complaint {complaint_id}",
            "status": result.workflow_status.value,
            "persisted": True,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Reprocessing failed: {str(e)}"
        )


@router.get("/complaints/stats/summary", response_model=StatsResponse)
async def get_complaints_summary():
    """Retorna estatísticas resumidas das reclamações processadas."""
    cosmos = await _ensure_cosmos_initialized()

    try:
        stats = await cosmos.get_stats()

        # Busca estatísticas adicionais (por categoria e time)
        complaints = await cosmos.list_complaints(limit=1000)

        by_category: Dict[str, int] = {}
        by_team: Dict[str, int] = {}

        for c in complaints:
            if c.complaint_analyzed:
                category = c.complaint_analyzed.category.value
                by_category[category] = by_category.get(category, 0) + 1

            if c.routing_decision:
                team = c.routing_decision.team
                by_team[team] = by_team.get(team, 0) + 1

        return StatsResponse(
            total=stats.get("total", 0),
            by_status=stats.get("by_status", {}),
            by_source=stats.get("by_source", {}),
            by_category=by_category,
            by_team=by_team,
        )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/complaints/orchestrator/stats")
async def get_orchestrator_stats():
    """Retorna estatísticas do orquestrador."""
    orchestrator = get_orchestrator()
    return orchestrator.get_stats()


@router.get("/complaints/audit/{complaint_id}")
async def get_complaint_audit_log(
    complaint_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Retorna o log de auditoria de uma reclamação."""
    cosmos = await _ensure_cosmos_initialized()

    try:
        events = await cosmos.get_audit_log(
            complaint_id=complaint_id,
            limit=limit,
        )

        return {
            "complaint_id": complaint_id,
            "total_events": len(events),
            "events": events,
        }

    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))
