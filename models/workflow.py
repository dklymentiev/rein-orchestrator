"""
Pydantic models for Rein workflow definitions.
Includes business logic validation for circular dependencies, timeouts, and data flow.
Supports state machine flow control with `next` field.
Supports declarative input validation with `inputs` section.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LogicConfig(BaseModel):
    """Logic phase configuration"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pre: Optional[str] = None
    post: Optional[str] = None
    error: Optional[str] = None  # Per-block error handler script (v3.3)
    validate_script: Optional[str] = Field(None, alias="validate")
    custom: Optional[Union[bool, str]] = None  # True = skip Claude API, str = custom script path


class NextCondition(BaseModel):
    """Conditional transition for state machine flow"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    if_condition: Optional[str] = Field(None, alias="if", pattern=r"^\{\{.*\}\}$")
    else_target: Optional[str] = Field(None, alias="else", pattern=r"^[a-z0-9_]+$")
    goto: Optional[str] = Field(None, pattern=r"^[a-z0-9_]+$")


class BlockConfig(BaseModel):
    """Individual workflow block configuration"""

    name: str = Field(..., pattern=r"^[a-z0-9_]+$", min_length=1, max_length=50)
    phase: Optional[int] = Field(None, ge=1, le=1000)
    specialist: Optional[str] = Field(None, pattern=r"^[a-z0-9-]+$")  # Optional for pure logic blocks
    prompt: Optional[str] = Field(default="", min_length=0)
    depends_on: List[str] = Field(default_factory=list)
    parallel: bool = False
    skip_if_previous_failed: bool = False
    continue_if_failed: bool = False
    timeout: Optional[int] = Field(None, ge=30, le=7200)
    model: Optional[str] = Field(
        default="", description="LLM model override for this block. Empty = use provider default."
    )
    save_as: Optional[str] = Field(None, pattern=r"^[a-z0-9_.-]+\.json$")
    logic: Optional[LogicConfig] = None
    # Agent routing for async step mode (v3.3)
    agent: Optional[str] = Field(None, description="Agent identity for step mode routing")
    routing: Optional[Dict[str, str]] = Field(None, description="Tag-based routing: tag -> next block name")
    # State machine flow control (v2.5.4)
    next: Optional[Union[str, List[NextCondition]]] = None
    max_runs: int = Field(default=1, ge=1, le=10)

    model_config = ConfigDict(extra="forbid")

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, v):
        """Ensure depends_on contains valid block names"""
        if not isinstance(v, list):
            raise ValueError("depends_on must be a list")
        for dep in v:
            if not re.match(r"^[a-z0-9_]+$", dep):
                raise ValueError(f"Invalid block name in depends_on: {dep}")
        return v

    def get_flow_control_strategy(self) -> str:
        """Determine block execution strategy"""
        if self.skip_if_previous_failed and self.continue_if_failed:
            return "resilient"  # Runs despite failures, workflow continues
        elif self.skip_if_previous_failed:
            return "conditional"  # Runs unless deps failed
        elif self.continue_if_failed:
            return "optional"  # Runs normally, but failure doesn't stop workflow
        else:
            return "critical"  # Standard: run normally, failure stops workflow


class InputFieldConfig(BaseModel):
    """Declares a workflow input field for pre-dispatch validation"""

    description: Optional[str] = Field(None, max_length=500)
    required: bool = Field(default=True)
    default: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("default")
    @classmethod
    def default_only_when_optional(cls, v, info):
        if v is not None and info.data.get("required", True):
            raise ValueError("'default' only valid when required=false")
        return v


class WorkflowConfig(BaseModel):
    """Complete workflow configuration with validation"""

    schema_version: str = Field(default="3.3.0")
    name: str = Field(..., pattern=r"^[a-z0-9-]+$", min_length=1, max_length=100)
    team: str = Field(..., pattern=r"^team-[a-z0-9-]+$")
    description: Optional[str] = Field(default="", max_length=1000)
    metadata: Optional[Dict] = None
    timeout: Optional[int] = Field(None, ge=30, le=86400)
    max_parallel: int = Field(default=3, ge=1, le=10)
    readable_outputs: bool = Field(
        default=False, description="Generate human-readable .md files alongside .json outputs"
    )
    provider: Optional[Union[str, Dict]] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = Field(None, ge=1, le=200000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    default_max_runs: Optional[int] = Field(
        None, ge=1, le=100, description="Default max_runs for blocks without explicit max_runs"
    )
    inputs: Optional[Dict[str, InputFieldConfig]] = None
    on_error: Optional[str] = Field(None, description="Global error handler script path (v3.3)")
    blocks: List[BlockConfig] = Field(..., min_length=1, max_length=300)

    model_config = ConfigDict(extra="ignore")

    @field_validator("blocks")
    @classmethod
    def detect_circular_dependencies(cls, blocks):
        """
        Detect circular dependencies in workflow using DFS (Depth-First Search).
        Raises ValidationError if a cycle is detected.
        """
        if not blocks:
            return blocks

        # Build adjacency list
        graph: Dict[str, List[str]] = {block.name: block.depends_on for block in blocks}
        all_names = {block.name for block in blocks}

        # Validate all referenced dependencies exist
        for block_name, deps in graph.items():
            for dep in deps:
                if dep not in all_names:
                    raise ValueError(f"Block '{block_name}' depends on non-existent block '{dep}'")

        # DFS-based cycle detection
        def has_cycle_from(start: str, visited: Set[str], rec_stack: Set[str]) -> Tuple[bool, Optional[str]]:
            visited.add(start)
            rec_stack.add(start)

            for neighbor in graph.get(start, []):
                if neighbor not in visited:
                    cycle, path = has_cycle_from(neighbor, visited, rec_stack)
                    if cycle:
                        return True, f"{start} -> {path}"
                elif neighbor in rec_stack:
                    return True, f"{start} -> {neighbor}"

            rec_stack.remove(start)
            return False, None

        visited: Set[str] = set()
        for block_name in graph:
            if block_name not in visited:
                has_cycle, cycle_path = has_cycle_from(block_name, visited, set())
                if has_cycle:
                    raise ValueError(f"Circular dependency detected: {cycle_path}")

        return blocks

    @field_validator("blocks")
    @classmethod
    def validate_block_name_uniqueness(cls, blocks):
        """Ensure all block names are unique"""
        names = [block.name for block in blocks]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Duplicate block names: {set(duplicates)}")
        return blocks

    @field_validator("blocks")
    @classmethod
    def validate_flow_control_logic(cls, blocks):
        """Validate flow control parameter combinations"""
        for block in blocks:
            # If block is critical (no flow control), it shouldn't have unfulfilled dependencies
            if not block.continue_if_failed and not block.skip_if_previous_failed:
                if block.depends_on:
                    # This is fine - critical block depends on others
                    pass

            # If block has continue_if_failed=True, it should probably have logic for error handling
            if block.continue_if_failed and not block.logic:
                # Warning: might want error handling logic, but not required
                pass

        return blocks

    @field_validator("blocks")
    @classmethod
    def validate_inputs_match_prompts(cls, blocks, info):
        """If inputs: is declared, verify every {{ task.input.X }} in prompts has a matching declaration"""
        inputs = info.data.get("inputs")
        if not inputs:
            return blocks
        declared = set(inputs.keys())
        for block in blocks:
            if not block.prompt:
                continue
            for match in re.finditer(r"\{\{\s*task\.input\.(\w+)\s*\}\}", block.prompt):
                field_name = match.group(1)
                if field_name not in declared:
                    raise ValueError(
                        f"Block '{block.name}' uses undeclared input 'task.input.{field_name}'. "
                        f"Add it to 'inputs:' section."
                    )
        return blocks

    @field_validator("blocks")
    @classmethod
    def validate_block_placeholders(cls, blocks):
        """Validate {{ block_name.format }} placeholders in prompts reference valid blocks and use supported formats"""
        all_names = {block.name for block in blocks}
        block_deps = {block.name: set(block.depends_on) for block in blocks}

        # Build transitive dependency sets (all ancestors, not just direct)
        def get_all_ancestors(name: str, visited: set = None) -> set:
            if visited is None:
                visited = set()
            for dep in block_deps.get(name, set()):
                if dep not in visited:
                    visited.add(dep)
                    get_all_ancestors(dep, visited)
            return visited

        transitive_deps = {name: get_all_ancestors(name) for name in all_names}

        # Match {{ word.word }} patterns, capturing the two parts
        placeholder_re = re.compile(r"\{\{\s*(\w+)\.(\w+)\s*\}\}")

        for block in blocks:
            if not block.prompt:
                continue
            for match in placeholder_re.finditer(block.prompt):
                ref_name = match.group(1)
                ref_format = match.group(2)

                # Skip task.input.X placeholders (handled by validate_inputs_match_prompts)
                if ref_name == "task":
                    continue
                # Skip result.X placeholders (state machine conditions)
                if ref_name == "result":
                    continue
                # Only validate placeholders where ref_name matches an existing block
                if ref_name not in all_names:
                    continue

                # Validate format -- only .json is supported
                if ref_format != "json":
                    raise ValueError(
                        f"Block '{block.name}' uses '{{{{ {ref_name}.{ref_format} }}}}' -- "
                        f"'.{ref_format}' is not supported. Use '.json' instead."
                    )

                # Validate that referenced block is reachable via depends_on (direct or transitive)
                if ref_name not in transitive_deps.get(block.name, set()):
                    raise ValueError(
                        f"Block '{block.name}' references '{{{{ {ref_name}.json }}}}' "
                        f"but '{ref_name}' is not reachable via its depends_on chain."
                    )

        return blocks

    def get_execution_order(self) -> List[List[str]]:
        """
        Compute optimal execution order (phases) respecting dependencies.
        Returns list of block name lists, where each inner list can run in parallel.
        """
        block_dict = {block.name: block for block in self.blocks}
        executed: Set[str] = set()
        phases: List[List[str]] = []

        while len(executed) < len(block_dict):
            current_phase: List[str] = []

            for block in self.blocks:
                if block.name in executed:
                    continue

                # Check if all dependencies are met
                deps_met = all(dep in executed for dep in block.depends_on)

                if deps_met:
                    current_phase.append(block.name)

            if not current_phase:
                # This shouldn't happen if circular dependencies were caught
                raise ValueError("Execution deadlock: remaining blocks have unmet dependencies")

            phases.append(current_phase)
            executed.update(current_phase)

        return phases

    def get_critical_path(self) -> List[str]:
        """
        Get the critical path (longest dependency chain) in the workflow.
        Blocks on critical path cannot fail without stopping workflow.
        """
        block_dict = {block.name: block for block in self.blocks}

        # Memoized depth() -- without the cache, a workflow with shared
        # ancestors and fan-in merges (e.g. 4 parsers -> classify) has
        # exponential behavior because the same node is re-walked at
        # every merge. Memoization turns it into O(V+E).
        depth_cache: Dict[str, int] = {}

        def depth(name: str) -> int:
            cached = depth_cache.get(name)
            if cached is not None:
                return cached
            block = block_dict[name]
            if not block.depends_on:
                depth_cache[name] = 1
                return 1
            result = 1 + max(depth(dep) for dep in block.depends_on)
            depth_cache[name] = result
            return result

        depths = {block.name: depth(block.name) for block in self.blocks}
        max_depth = max(depths.values())

        return [name for name, d in depths.items() if d == max_depth]


class SpecialistMapping(BaseModel):
    """Specialist role mapping in a team"""

    role: str = Field(..., pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=50)
    specialist: str = Field(..., pattern=r"^[a-z0-9-]+$")
    bio: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid")


class TeamConfig(BaseModel):
    """Team configuration"""

    schema_version: str = Field(default="3.3.0")
    name: str = Field(..., pattern=r"^team-[a-z0-9-]+$", min_length=6, max_length=100)
    description: Optional[str] = Field(default="", max_length=1000)
    metadata: Optional[Dict] = None
    collaboration_tone: str = Field(
        default="professional", pattern=r"^(professional|creative|humorous|academic|casual|formal)$"
    )
    specialists: List[SpecialistMapping] = Field(..., min_length=1, max_length=50)
    shared_instructions: Optional[str] = Field(None, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("specialists")
    @classmethod
    def validate_specialist_uniqueness(cls, specialists):
        """Ensure all roles and specialists are unique"""
        roles = [s.role for s in specialists]
        specs = [s.specialist for s in specialists]

        if len(roles) != len(set(roles)):
            duplicates = [r for r in roles if roles.count(r) > 1]
            raise ValueError(f"Duplicate roles: {set(duplicates)}")

        if len(specs) != len(set(specs)):
            duplicates = [s for s in specs if specs.count(s) > 1]
            raise ValueError(f"Duplicate specialists: {set(duplicates)}")

        return specialists


@dataclass
class ValidationError:
    """Represents a validation error"""

    field: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """Result of workflow validation"""

    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def add_error(self, field: str, message: str):
        """Add an error to the result"""
        self.errors.append(ValidationError(field, message, "error"))
        self.is_valid = False

    def add_warning(self, field: str, message: str):
        """Add a warning to the result"""
        self.warnings.append(ValidationError(field, message, "warning"))

    def format_report(self) -> str:
        """Format validation result as human-readable report"""
        lines = []

        if self.is_valid:
            lines.append("[OK] Workflow validation passed")
        else:
            lines.append("[ERROR] Workflow validation failed")

        if self.metadata:
            for key, value in self.metadata.items():
                lines.append(f"[INFO] {key}: {value}")

        if self.errors:
            lines.append("\n[ERRORS]")
            for error in self.errors:
                lines.append(f"  {error.field}: {error.message}")

        if self.warnings:
            lines.append("\n[WARNINGS]")
            for warning in self.warnings:
                lines.append(f"  {warning.field}: {warning.message}")

        return "\n".join(lines)
