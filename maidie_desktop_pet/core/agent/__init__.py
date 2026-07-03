"""Legacy AI compatibility exports plus the active ConfirmationBroker.

Production AI routing, planning, and execution use :mod:`core.brain`. Do not
add new AI features to this package. ConfirmationBroker remains production
infrastructure and is not deprecated.
"""

from core.agent.core import AgentCore
from core.agent.executor import ToolExecutor
from core.agent.intent import Intent, IntentDetector
from core.agent.planner import Planner
from core.agent.confirmation import ConfirmationBroker

__all__ = ["AgentCore", "ConfirmationBroker", "Intent", "IntentDetector", "Planner", "ToolExecutor"]
