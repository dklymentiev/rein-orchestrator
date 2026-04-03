"""Tests for rein/agent_config.py -- agent.yaml loading and validation."""
import os
import tempfile

import pytest
import yaml

from rein.agent_config import load_agent_config, validate_forbidden_behavior, AgentConfig


class TestLoadAgentConfig:
    """Tests for loading agent.yaml files."""

    def _make_agent(self, tmpdir, name, config_data):
        """Create agent directory with agent.yaml."""
        agent_dir = os.path.join(tmpdir, name)
        os.makedirs(agent_dir, exist_ok=True)
        with open(os.path.join(agent_dir, "agent.yaml"), "w") as f:
            yaml.dump(config_data, f)
        return agent_dir

    def test_load_by_name(self):
        """Load agent config by name relative to agents_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_agent(tmpdir, "smm", {
                "name": "smm",
                "model": "claude-sonnet-4-20250514",
                "department": "marketing",
            })
            cfg = load_agent_config("smm", agents_dir=tmpdir)
            assert cfg is not None
            assert cfg.name == "smm"
            assert cfg.model == "claude-sonnet-4-20250514"
            assert cfg.department == "marketing"

    def test_load_by_absolute_path(self):
        """Load agent config from absolute path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_dir = self._make_agent(tmpdir, "editor", {
                "name": "editor",
                "model": "gpt-4o",
            })
            cfg = load_agent_config(agent_dir)
            assert cfg is not None
            assert cfg.name == "editor"
            assert cfg.model == "gpt-4o"

    def test_not_found_returns_none(self):
        """Missing agent returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = load_agent_config("nonexistent", agents_dir=tmpdir)
            assert cfg is None

    def test_defaults_for_missing_fields(self):
        """Missing fields get sensible defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_agent(tmpdir, "minimal", {"name": "minimal"})
            cfg = load_agent_config("minimal", agents_dir=tmpdir)
            assert cfg is not None
            assert cfg.model == ""
            assert cfg.linux_user == ""
            assert cfg.groups == []
            assert cfg.forbidden_behavior == []
            assert cfg.directories == {"read": [], "write": []}

    def test_name_inferred_from_directory(self):
        """If name not in YAML, infer from directory name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_agent(tmpdir, "auto-name", {})
            cfg = load_agent_config("auto-name", agents_dir=tmpdir)
            assert cfg.name == "auto-name"

    def test_full_config(self):
        """All fields parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_agent(tmpdir, "full", {
                "name": "full-agent",
                "model": "claude-opus-4-20250514",
                "schedule": "*/5 * * * *",
                "linux_user": "agent-smm",
                "department": "marketing",
                "department_role": "creator",
                "groups": ["social", "content"],
                "tools": ["claude-cli", "mesh"],
                "mcp_servers": ["mesh-server"],
                "mesh_workspace": "marketing",
                "forbidden_fs": ["/etc/*", "/root/*"],
                "forbidden_behavior": ["modify_other_agents", "access_credentials"],
                "directories": {"read": ["/data"], "write": ["/output"]},
                "interactions": {
                    "receives": ["conductor"],
                    "assigns": ["editor"],
                    "escalates": ["conductor"],
                    "notifies": ["telegram"],
                },
            })
            cfg = load_agent_config("full", agents_dir=tmpdir)
            assert cfg.name == "full-agent"
            assert cfg.linux_user == "agent-smm"
            assert cfg.groups == ["social", "content"]
            assert cfg.forbidden_fs == ["/etc/*", "/root/*"]
            assert cfg.interactions["assigns"] == ["editor"]

    def test_source_path_stored(self):
        """_source_path contains path to the loaded file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_agent(tmpdir, "tracked", {"name": "tracked"})
            cfg = load_agent_config("tracked", agents_dir=tmpdir)
            assert cfg._source_path.endswith("agent.yaml")
            assert "tracked" in cfg._source_path


class TestValidateForbiddenBehavior:
    """Tests for forbidden_behavior validation."""

    def test_no_config_passes(self):
        """No agent config -> no violation."""
        result = validate_forbidden_behavior(None, {"prompt": "anything"})
        assert result is None

    def test_no_rules_passes(self):
        """Agent with empty forbidden_behavior -> no violation."""
        cfg = AgentConfig(forbidden_behavior=[])
        result = validate_forbidden_behavior(cfg, {"prompt": "anything"})
        assert result is None

    def test_forbidden_in_prompt_detected(self):
        """Forbidden behavior keyword in prompt is detected."""
        cfg = AgentConfig(forbidden_behavior=["delete_all_data"])
        result = validate_forbidden_behavior(cfg, {
            "prompt": "Please delete_all_data from the database"
        })
        assert result is not None
        assert "delete_all_data" in result

    def test_arbitrary_commands_with_custom_script(self):
        """execute_arbitrary_commands rule catches custom logic scripts."""
        cfg = AgentConfig(forbidden_behavior=["execute_arbitrary_commands"])
        result = validate_forbidden_behavior(cfg, {
            "prompt": "do thing",
            "logic": {"custom": "scripts/evil.sh"},
        })
        assert result is not None
        assert "execute_arbitrary_commands" in result

    def test_clean_block_passes(self):
        """Normal block with strict rules still passes."""
        cfg = AgentConfig(forbidden_behavior=["modify_other_agents", "access_credentials"])
        result = validate_forbidden_behavior(cfg, {
            "prompt": "Write a social media post about Easter",
            "logic": {},
        })
        assert result is None
