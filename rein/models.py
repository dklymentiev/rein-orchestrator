"""
Rein Models - Data classes for workflow state
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class Process:
    """Represents a managed process/block in workflow"""
    pid: Optional[int]
    name: str
    status: str  # running, done, failed, waiting, paused
    start_time: float
    command: str
    uid: str = ""  # Unique ID for this process instance
    exit_code: Optional[int] = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    depends_on: List[str] = field(default_factory=list)
    progress: int = 0  # 0-100
    phase: int = 0  # execution phase number
    blocking_pause: bool = True  # if True, pausing this blocks dependents
    agent: str = ""  # Agent or team executing this process
    next_spec: Optional[Any] = None  # str or List[dict] with conditions
    max_runs: int = 1  # Maximum runs for loop protection
    run_count: int = 0  # How many times this block has run


@dataclass
class BlockConfig:
    """Configuration for a workflow block"""
    name: str
    specialist: Optional[str] = None
    prompt: str = ""
    depends_on: List[str] = field(default_factory=list)
    parallel: bool = False
    phase: int = 0
    logic: Optional[dict] = None
    next: Optional[Any] = None  # str or list of conditions
    max_runs: int = 1
    continue_if_failed: bool = True
    skip_if_previous_failed: bool = False
