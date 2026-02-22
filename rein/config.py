"""
Rein Config Loader - Load workflows, teams, specialists, and env files
"""
import os
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import yaml


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
            env_file = os.path.join(workflow_dir, '.env')
            if os.path.exists(env_file):
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
            flow_name: Name of the flow

        Returns:
            Full path to flow YAML file
        """
        return os.path.join(self.agents_dir, "flows", flow_name, f"{flow_name}.yaml")

    def flow_exists(self, flow_name: str) -> bool:
        """Check if flow exists"""
        return os.path.exists(self.get_flow_path(flow_name))
