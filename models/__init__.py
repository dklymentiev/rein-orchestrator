"""
Dog v2.5.3 Models Package

Provides:
- Pydantic models for workflow and team validation
- ValidationEngine for multi-layer validation
- Data classes for validation results
"""

from .workflow import (
    BlockConfig,
    WorkflowConfig,
    TeamConfig,
    SpecialistMapping,
    LogicConfig,
    ValidationResult,
    ValidationError,
)

from .validator import (
    ValidationEngine,
    validate_workflow_file,
    validate_team_file,
)

__all__ = [
    "BlockConfig",
    "WorkflowConfig",
    "TeamConfig",
    "SpecialistMapping",
    "LogicConfig",
    "ValidationResult",
    "ValidationError",
    "ValidationEngine",
    "validate_workflow_file",
    "validate_team_file",
]

__version__ = "2.5.3"
