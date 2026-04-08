"""
Rein Config Loader - Load workflows, teams, specialists, and env files
"""
import os
import re
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import yaml


# Flow names must be safe filesystem components: alphanumerics, dash,
# underscore, dot. No slashes, no leading dots (HIGH-004). Applied to
# values sourced from task.yaml or external callers before any path join.
SAFE_FLOW_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


# Default agents directory - overridden by --agents-dir CLI arg or REIN_AGENTS_DIR env
def _resolve_default_agents_dir() -> str:
    """Resolve default agents directory with smart fallback."""
    # 1. Explicit env var
    env_dir = os.environ.get("REIN_AGENTS_DIR")
    if env_dir:
        return env_dir
    # 2. ./agents relative to CWD (for standalone projects)
    cwd_agents = os.path.join(os.getcwd(), "agents")
    if os.path.isdir(cwd_agents):
        return cwd_agents
    # 3. agents/ next to the rein package (for pip installs / dev)
    pkg_agents = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents")
    if os.path.isdir(pkg_agents):
        return pkg_agents
    # 4. Fallback to ./agents (will be created or error at runtime)
    return cwd_agents

DEFAULT_AGENTS_DIR = _resolve_default_agents_dir()


class ConfigLoader:
    """Loader for Rein configuration files"""

    def __init__(
        self,
        agents_dir: str = "",
        logger: Optional[Callable[[str], None]] = None
    ):
        self.agents_dir = agents_dir or DEFAULT_AGENTS_DIR
        self.logger = logger or (lambda x: None)

    def load_workflow(self, path: str) -> Dict[str, Any]:
        """
        Load workflow YAML file

        Args:
            path: Path to workflow YAML file

        Returns:
            Parsed workflow configuration dict
        """
        with open(path) as f:
            config = yaml.safe_load(f)
        self.logger(f"WORKFLOW LOADED | {path}")
        return config

    def get_provider_config(self, workflow_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract provider configuration from workflow YAML.

        Workflow YAML can specify provider at top level:
            provider: anthropic
            model: claude-sonnet-4-20250514
            max_tokens: 4096
            temperature: 0.7

        Or in a provider section:
            provider:
              name: anthropic
              model: claude-sonnet-4-20250514
              api_key: ...  # optional, env vars preferred
              max_tokens: 8192

        Returns:
            Dict with keys: provider, model, max_tokens, temperature, and
            any provider-specific kwargs (api_key, base_url, etc.)
        """
        provider_cfg = workflow_config.get("provider", "")
        result = {
            "max_tokens": int(os.environ.get("MAX_TOKENS", workflow_config.get("max_tokens", 4096))),
            "temperature": float(os.environ.get("TEMPERATURE", workflow_config.get("temperature", 0.7))),
        }

        if isinstance(provider_cfg, dict):
            # Nested provider config
            result["provider"] = provider_cfg.get("name", "")
            result["model"] = provider_cfg.get("model", workflow_config.get("model", ""))
            # Pass through extra keys (api_key, base_url, etc.)
            for key in provider_cfg:
                if key not in ("name", "model", "max_tokens", "temperature"):
                    result[key] = provider_cfg[key]
            if "max_tokens" in provider_cfg:
                result["max_tokens"] = int(provider_cfg["max_tokens"])
            if "temperature" in provider_cfg:
                result["temperature"] = float(provider_cfg["temperature"])
        elif isinstance(provider_cfg, str):
            # Simple: provider: anthropic
            result["provider"] = provider_cfg
            result["model"] = workflow_config.get("model", "")
        else:
            result["provider"] = ""
            result["model"] = workflow_config.get("model", "")

        return result

    def load_team(self, team_name: str) -> str:
        """
        Load team configuration and return tone

        Args:
            team_name: Name of the team (without .yaml extension)

        Returns:
            Team tone/style string or empty string on error
        """
        try:
            team_file = os.path.join(self.agents_dir, "teams", f"{team_name}.yaml")
            with open(team_file) as f:
                team_data = yaml.safe_load(f)

            # Support both old 'tone' and new 'collaboration_tone' field names
            tone = team_data.get('collaboration_tone') or team_data.get('tone', '')
            self.logger(f"TEAM LOADED | {team_name} | tone={tone}")
            return tone
        except Exception as e:
            self.logger(f"TEAM LOAD ERROR | {team_name} | {str(e)}")
            return ""

    def load_specialist(self, specialist_name: str) -> str:
        """
        Load specialist instructions from MD file

        Args:
            specialist_name: Name of specialist (without .md extension)

        Returns:
            Specialist instructions text or empty string on error
        """
        try:
            spec_file = os.path.join(self.agents_dir, "specialists", f"{specialist_name}.md")
            with open(spec_file) as f:
                content = f.read()
            return content
        except Exception as e:
            self.logger(f"SPECIALIST LOAD ERROR | {specialist_name} | {str(e)}")
            return ""

    def load_env_file(self, workflow_dir: str) -> bool:
        """
        Load .env file from workflow directory into environment

        Args:
            workflow_dir: Directory containing .env file

        Returns:
            True if env file was loaded, False otherwise
        """
        try:
            # Search workflow dir and parent directories for .env
            search_dir = workflow_dir
            env_file = None
            for _ in range(3):
                candidate = os.path.join(search_dir, '.env')
                if os.path.exists(candidate):
                    env_file = candidate
                    break
                parent = os.path.dirname(search_dir)
                if parent == search_dir:
                    break
                search_dir = parent

            if env_file:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                os.environ[key.strip()] = value.strip()
                self.logger(f"ENV LOADED | {env_file}")
                return True
            else:
                self.logger(f"ENV NOT FOUND | using system env")
                return False
        except Exception as e:
            self.logger(f"ENV LOAD ERROR | {str(e)}")
            return False

    def get_flow_path(self, flow_name: str) -> str:
        """
        Get full path to flow YAML file

        Args:
            flow_name: Name of the flow. Must match SAFE_FLOW_NAME regex
                -- alphanumerics, dots, dashes, underscores only, no
                leading dot. Rejects path traversal (HIGH-004).

        Returns:
            Full path to flow YAML file

        Raises:
            ValueError: if flow_name contains unsafe characters
        """
        if not flow_name or not SAFE_FLOW_NAME.match(flow_name):
            raise ValueError(f"Invalid flow name: {flow_name!r}")
        return os.path.join(self.agents_dir, "flows", flow_name, f"{flow_name}.yaml")

    def flow_exists(self, flow_name: str) -> bool:
        """Check if flow exists. Returns False for unsafe flow names."""
        try:
            return os.path.exists(self.get_flow_path(flow_name))
        except ValueError:
            return False

    def run_preflight_validation(
        self,
        workflow_file: str,
        console_info: Optional[Callable[..., None]] = None,
        console_error: Optional[Callable[..., None]] = None,
        pkg_logger: Optional[Any] = None,
    ) -> bool:
        """Run JSON schema + Pydantic validation on a workflow file.

        Returns True if valid. On failure, prints error and calls sys.exit(1).
        On validator exception, logs warning and returns True (continue anyway).

        Args:
            workflow_file: Path to workflow YAML
            console_info: Optional rich console info callback (for user output)
            console_error: Optional rich console error callback
            pkg_logger: Optional logging.Logger for warnings
        """
        try:
            from models.validator import ValidationEngine
            engine = ValidationEngine()
            result = engine.validate_workflow(Path(workflow_file), cross_reference_check=True)

            if result.is_valid:
                self.logger(
                    f"VALIDATE OK | schema_version={result.metadata.get('schema_version')} "
                    f"| blocks={result.metadata.get('blocks_count')} "
                    f"| phases={result.metadata.get('phases')}"
                )
                if console_info:
                    console_info("")
                    console_info("[VALIDATE] Workflow: %s", result.metadata.get('name'))
                    console_info("[VALIDATE] Team: %s", result.metadata.get('team'))
                    console_info("[VALIDATE] Schema Version: %s", result.metadata.get('schema_version'))
                    console_info("[VALIDATE] Blocks: %s", result.metadata.get('blocks_count'))
                    console_info("[VALIDATE] Execution Phases: %s", result.metadata.get('phases'))
                    console_info("[VALIDATE] Flow Control Blocks: %s", result.metadata.get('flow_control_blocks'))
                    console_info("[VALIDATE] Status: OK\n")
            else:
                self.logger(f"VALIDATE FAILED | errors={len(result.errors)} | warnings={len(result.warnings)}")
                if console_error:
                    console_error("\n[ERROR] Workflow validation failed!")
                    console_error(result.format_report())
                if console_info:
                    console_info("")
                import sys as _sys
                _sys.exit(1)

            if result.warnings and pkg_logger:
                pkg_logger.warning("%d validation warnings:", len(result.warnings))
                for warning in result.warnings:
                    pkg_logger.warning("  - %s: %s", warning.field, warning.message)

            return True
        except SystemExit:
            raise
        except Exception as e:
            self.logger(f"VALIDATE ERROR | {str(e)}")
            if pkg_logger:
                pkg_logger.warning("Validation engine error (continuing anyway): %s", e)
            return True

    def validate_task_inputs(
        self,
        config: Dict[str, Any],
        task_input: Dict[str, Any],
        console_error: Optional[Callable[..., None]] = None,
        pkg_logger: Optional[Any] = None,
    ) -> None:
        """Validate task inputs against declarative inputs: section (v2.6.0).

        - If no inputs: section, skip entirely (backward compat).
        - For each declared required field: check if present in task_input.
        - For optional fields with default: inject into task_input if missing.
        - Log warning for extra (undeclared) inputs.
        - On missing required: print error and sys.exit(1).

        Mutates task_input in place (injects defaults).
        """
        inputs_spec = config.get('inputs')
        if not inputs_spec:
            return  # Backward compatible

        errors = []
        declared = set(inputs_spec.keys())
        provided = set(task_input.keys())

        for field_name, field_config in inputs_spec.items():
            if isinstance(field_config, dict):
                is_required = field_config.get('required', True)
                default_val = field_config.get('default')
            else:
                is_required = field_config.required
                default_val = field_config.default

            if field_name not in task_input:
                if is_required:
                    desc = ""
                    if isinstance(field_config, dict):
                        desc = field_config.get('description', '')
                    elif hasattr(field_config, 'description'):
                        desc = field_config.description or ''
                    hint = f" ({desc})" if desc else ""
                    errors.append(f"  - '{field_name}'{hint}")
                elif default_val is not None:
                    task_input[field_name] = default_val
                    self.logger(f"INPUT DEFAULT | {field_name} = {default_val}")

        # Warn about extra (undeclared) inputs
        extra = provided - declared
        if extra:
            self.logger(f"INPUT WARNING | Extra undeclared inputs: {sorted(extra)}")
            if pkg_logger:
                pkg_logger.warning("Extra inputs not declared in workflow: %s", sorted(extra))

        if errors:
            workflow_name = config.get('name', 'unknown')
            msg = (
                f"\n[ERROR] Missing required inputs for workflow '{workflow_name}':\n"
                + "\n".join(errors)
                + f"\n\nDeclared inputs: {sorted(declared)}"
                + f"\nProvided inputs: {sorted(provided)}"
                + "\n\nProvide inputs via --input '{\"field\": \"value\"}' or task.input.json\n"
            )
            if console_error:
                console_error(msg)
            missing_names = [e.strip().lstrip("- '").split("'")[0] for e in errors]
            self.logger(f"INPUT VALIDATION FAILED | missing: {missing_names}")
            import sys as _sys
            _sys.exit(1)

        self.logger(f"INPUT VALIDATION OK | declared={sorted(declared)} | provided={sorted(provided)}")
