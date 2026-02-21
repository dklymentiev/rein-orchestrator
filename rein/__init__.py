"""
Rein - Workflow Orchestrator for Multi-Agent AI

Modules:
- providers: AI-agnostic LLM provider layer (Anthropic, OpenAI, Ollama, etc.)
- models: Data classes (Process, BlockConfig)
- config: Configuration loader (workflows, teams, specialists)
- logic: Logic script runner
- state: SQLite state persistence
- output: Output formatting and saving helpers
- ui: Rich terminal UI
"""

from .models import Process, BlockConfig
from .config import ConfigLoader
from .logic import LogicRunner
from .state import ReinState
from .output import format_json_as_md, save_readable_output, get_block_dir, get_output_dir
from .providers import create_provider, list_providers

__version__ = "3.2.0"

__all__ = [
    "Process",
    "BlockConfig",
    "ConfigLoader",
    "LogicRunner",
    "ReinState",
    "format_json_as_md",
    "save_readable_output",
    "get_block_dir",
    "get_output_dir",
    "create_provider",
    "list_providers",
]
