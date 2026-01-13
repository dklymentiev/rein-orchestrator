"""
Rein Config Loader - Load workflows, teams, specialists, and env files
"""
import os
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import yaml


class ConfigLoader:
    """Loader for Rein configuration files"""

    def __init__(
        self,
        agents_dir: str = "/server/agents",
        logger: Optional[Callable[[str], None]] = None
    ):
        self.agents_dir = agents_dir
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
