"""
Rein - Workflow Orchestrator for Multi-Agent AI

Modules:
- models: Data classes (Process, BlockConfig)
- claude: Claude API client (Anthropic, OpenRouter)
- config: Configuration loader (workflows, teams, specialists)
- logic: Logic script runner
- state: SQLite state persistence
- output: Output formatting and saving helpers
- ui: Rich terminal UI
"""

from .models import Process, BlockConfig
from .claude import ClaudeClient
from .config import ConfigLoader
from .logic import LogicRunner
from .state import ReinState
from .output import format_json_as_md, save_readable_output, get_block_dir, get_output_dir

__version__ = "3.3.0"

__all__ = [
    "Process",
    "BlockConfig",
    "ClaudeClient",
    "ConfigLoader",
    "LogicRunner",
    "ReinState",
    "format_json_as_md",
    "save_readable_output",
    "get_block_dir",
    "get_output_dir",
]
