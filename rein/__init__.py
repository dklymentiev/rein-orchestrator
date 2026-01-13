"""
Rein - Workflow Orchestrator for Multi-Agent AI

Modules:
- models: Data classes (Process, BlockConfig)
- claude: Claude API client (Anthropic, OpenRouter)
- config: Configuration loader (workflows, teams, specialists)
- logic: Logic script runner
"""

from .models import Process, BlockConfig
from .claude import ClaudeClient
from .config import ConfigLoader
from .logic import LogicRunner

__version__ = "3.2.0"

__all__ = [
    "Process",
    "BlockConfig",
    "ClaudeClient",
    "ConfigLoader",
    "LogicRunner",
]
