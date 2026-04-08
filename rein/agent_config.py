"""
Rein Agent Config - Load and validate agent.yaml files.

When a workflow block specifies `agent: smm`, Rein resolves the agent's
configuration from {agents_dir}/{agent_name}/agent.yaml. This provides
model overrides, security constraints, and OS user context.
"""
import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from rein.log import get_logger

logger = get_logger(__name__)

# No fallback paths. Agent resolution requires explicit agents_dir parameter.
# If not provided, only REIN_AGENTS_DIR env var is checked.
AGENT_SEARCH_PATHS = []

# Agent references must be safe filesystem components (HIGH-007).
# Alphanumerics, dash, underscore, dot; no leading dot; no slashes;
# no path traversal segments. This is a strict subset of POSIX path
# characters to match SAFE_FLOW_NAME / SAFE_TASK_NAME conventions
# elsewhere in the codebase.
SAFE_AGENT_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


@dataclass
class AgentConfig:
    """Parsed agent configuration from agent.yaml."""
    name: str = ""
    model: str = ""
    schedule: str = ""
    linux_user: str = ""
    department: str = ""
    department_role: str = ""
    groups: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    mesh_workspace: str = ""
    forbidden_fs: List[str] = field(default_factory=list)
    forbidden_behavior: List[str] = field(default_factory=list)
    directories: Dict[str, List[str]] = field(default_factory=lambda: {"read": [], "write": []})
    interactions: Dict[str, List[str]] = field(default_factory=lambda: {
        "receives": [], "assigns": [], "escalates": [], "notifies": []
    })
    _source_path: str = ""  # Path to agent.yaml (internal)


def load_agent_config(agent_ref: str, agents_dir: str = None) -> Optional[AgentConfig]:
    """Load agent.yaml for a given agent reference.

    Resolution order:
    1. agent_ref is an absolute path -> use directly
    2. {agents_dir}/{agent_ref}/agent.yaml
    3. Search AGENT_SEARCH_PATHS/{agent_ref}/agent.yaml

    Args:
        agent_ref: Agent name or path (e.g. "smm", "/path/to/agents/smm")
        agents_dir: Base directory for agent lookup

    Returns:
        AgentConfig or None if not found.
    """
    yaml_path = _resolve_agent_yaml(agent_ref, agents_dir)
    if not yaml_path:
        return None

    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load agent.yaml at %s: %s", yaml_path, e)
        return None

    config = AgentConfig(
        name=data.get("name", "") or os.path.basename(os.path.dirname(yaml_path)),
        model=data.get("model", "") or "",
        schedule=data.get("schedule", "") or "",
        linux_user=data.get("linux_user", "") or "",
        department=data.get("department", "") or "",
        department_role=data.get("department_role", "") or "",
        groups=data.get("groups") or [],
        tools=data.get("tools") or [],
        mcp_servers=data.get("mcp_servers") or [],
        mesh_workspace=data.get("mesh_workspace", "") or "",
        forbidden_fs=data.get("forbidden_fs") or [],
        forbidden_behavior=data.get("forbidden_behavior") or [],
        directories=data.get("directories") or {"read": [], "write": []},
        interactions=data.get("interactions") or {
            "receives": [], "assigns": [], "escalates": [], "notifies": []
        },
        _source_path=yaml_path,
    )
    return config


def validate_forbidden_behavior(agent_config: AgentConfig, block_config: dict) -> Optional[str]:
    """Check if block violates agent's forbidden_behavior rules.

    Returns error message if violated, None if OK.
    """
    if not agent_config or not agent_config.forbidden_behavior:
        return None

    prompt = block_config.get("prompt", "").lower()
    logic = block_config.get("logic", {})

    for rule in agent_config.forbidden_behavior:
        rule_lower = rule.lower()

        # Check if logic scripts reference forbidden paths
        if rule_lower == "execute_arbitrary_commands":
            if logic.get("custom") and isinstance(logic["custom"], str):
                return f"Forbidden behavior: {rule} (block has custom logic script)"

        # Check prompt for forbidden patterns
        if rule_lower in prompt:
            return f"Forbidden behavior: '{rule}' detected in prompt"

    return None


def _resolve_agent_yaml(agent_ref: str, agents_dir: str = None) -> Optional[str]:
    """Resolve agent reference to agent.yaml path.

    Only accepts SAFE_AGENT_REF names (alphanumerics, dash, underscore,
    dot; no leading dot; no slashes). Absolute paths and path traversal
    segments are rejected (HIGH-007). This closes the vector where a
    workflow could specify agent: '../../../etc' to escape agents_dir.
    """
    if not agent_ref or not SAFE_AGENT_REF.match(agent_ref):
        logger.warning("rejected unsafe agent_ref: %r", agent_ref)
        return None

    # Relative to agents_dir
    if agents_dir:
        # Try agents_dir directly (e.g. {agents_dir}/smm/agent.yaml)
        yaml_path = os.path.join(agents_dir, agent_ref, "agent.yaml")
        if os.path.isfile(yaml_path):
            return yaml_path

        # Try parent of agents_dir (agents_dir might be {agents_dir}/flows/../)
        parent = os.path.dirname(agents_dir)
        yaml_path = os.path.join(parent, agent_ref, "agent.yaml")
        if os.path.isfile(yaml_path):
            return yaml_path

    # Search default paths
    for search_path in AGENT_SEARCH_PATHS:
        yaml_path = os.path.join(search_path, agent_ref, "agent.yaml")
        if os.path.isfile(yaml_path):
            return yaml_path

    return None
