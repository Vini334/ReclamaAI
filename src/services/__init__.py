# -*- coding: utf-8 -*-
"""
Servicos do ReclamaAI.
"""

from src.services.mock_data_loader import MockDataLoader, get_data_loader

# Lazy imports to avoid circular dependency with src.agents
# Import orchestrator only when accessed
def __getattr__(name):
    if name in ("ComplaintOrchestrator", "get_orchestrator", "process_single_complaint"):
        from src.services.orchestrator import (
            ComplaintOrchestrator,
            get_orchestrator,
            process_single_complaint,
        )
        globals()[name] = locals()[name]
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "MockDataLoader",
    "get_data_loader",
    "ComplaintOrchestrator",
    "get_orchestrator",
    "process_single_complaint",
]
