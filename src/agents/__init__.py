"""
Agentes do ReclamaAI.
Exporta os agentes e suas factory functions.
"""

from src.agents.base import AgentError, BaseAgent, StatefulAgent
from src.agents.collector import CollectorAgent, get_collector_agent
from src.agents.privacy import PrivacyAgent, get_privacy_agent
from src.agents.analyst import AnalystAgent, get_analyst_agent
from src.agents.router import RouterAgent, get_router_agent
from src.agents.communicator import CommunicatorAgent, get_communicator_agent

__all__ = [
    "AgentError",
    "BaseAgent",
    "StatefulAgent",
    "CollectorAgent",
    "get_collector_agent",
    "PrivacyAgent",
    "get_privacy_agent",
    "AnalystAgent",
    "get_analyst_agent",
    "RouterAgent",
    "get_router_agent",
    "CommunicatorAgent",
    "get_communicator_agent",
]
