"""Tests for rein/config.py"""
import os
import pytest
import tempfile
import yaml

from rein.config import ConfigLoader


class TestConfigLoader:
    """Tests for ConfigLoader"""

    @pytest.fixture
    def temp_agents_dir(self):
        """Create temporary agents directory structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directories
            os.makedirs(os.path.join(tmpdir, "teams"))
            os.makedirs(os.path.join(tmpdir, "specialists"))
            os.makedirs(os.path.join(tmpdir, "flows", "test-flow"))

            # Create team file
            team_data = {
                "name": "test-team",
                "collaboration_tone": "Professional and focused"
            }
            with open(os.path.join(tmpdir, "teams", "test-team.yaml"), "w") as f:
                yaml.dump(team_data, f)

            # Create team with old 'tone' field
            old_team_data = {
                "name": "old-team",
                "tone": "Old style tone"
            }
            with open(os.path.join(tmpdir, "teams", "old-team.yaml"), "w") as f:
                yaml.dump(old_team_data, f)

            # Create specialist file
            spec_content = "# Test Specialist\n\nYou are a test specialist."
            with open(os.path.join(tmpdir, "specialists", "test-specialist.md"), "w") as f:
                f.write(spec_content)

            # Create workflow file
            workflow_data = {
                "schema_version": "2.5.3",
                "name": "test-flow",
                "team": "test-team",
                "blocks": [
                    {"name": "step1", "specialist": "test-specialist", "prompt": "Test"}
                ]
            }
            with open(os.path.join(tmpdir, "flows", "test-flow", "test-flow.yaml"), "w") as f:
                yaml.dump(workflow_data, f)

            yield tmpdir

    def test_init_default(self):
        """Test default initialization"""
        loader = ConfigLoader()
        # Default is resolved dynamically - just check it's a non-empty string
        assert isinstance(loader.agents_dir, str)
        assert len(loader.agents_dir) > 0

    def test_init_custom_dir(self, temp_agents_dir):
        """Test initialization with custom agents dir"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        assert loader.agents_dir == temp_agents_dir

    def test_init_with_logger(self):
        """Test initialization with custom logger"""
        logs = []
        loader = ConfigLoader(logger=lambda x: logs.append(x))
        assert loader.logger is not None

    def test_load_team(self, temp_agents_dir):
        """Test loading team configuration"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        tone = loader.load_team("test-team")
        assert tone == "Professional and focused"

    def test_load_team_old_format(self, temp_agents_dir):
        """Test loading team with old 'tone' field"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        tone = loader.load_team("old-team")
        assert tone == "Old style tone"

    def test_load_team_not_found(self, temp_agents_dir):
        """Test loading non-existent team returns empty string"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        tone = loader.load_team("nonexistent-team")
        assert tone == ""

    def test_load_specialist(self, temp_agents_dir):
        """Test loading specialist instructions"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        content = loader.load_specialist("test-specialist")
        assert "Test Specialist" in content
        assert "test specialist" in content

    def test_load_specialist_not_found(self, temp_agents_dir):
        """Test loading non-existent specialist returns empty string"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        content = loader.load_specialist("nonexistent")
        assert content == ""

    def test_load_workflow(self, temp_agents_dir):
        """Test loading workflow YAML"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        flow_path = os.path.join(temp_agents_dir, "flows", "test-flow", "test-flow.yaml")
        config = loader.load_workflow(flow_path)

        assert config["name"] == "test-flow"
        assert config["team"] == "test-team"
        assert len(config["blocks"]) == 1

    def test_get_flow_path(self, temp_agents_dir):
        """Test getting flow path"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        path = loader.get_flow_path("test-flow")
        assert path.endswith("test-flow/test-flow.yaml")

    def test_flow_exists(self, temp_agents_dir):
        """Test checking if flow exists"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        assert loader.flow_exists("test-flow") is True
        assert loader.flow_exists("nonexistent") is False

    def test_load_env_file(self, temp_agents_dir):
        """Test loading .env file"""
        # Create .env file
        env_content = "TEST_VAR=test_value\nANOTHER_VAR=123\n# Comment line\n"
        env_path = os.path.join(temp_agents_dir, "flows", "test-flow", ".env")
        with open(env_path, "w") as f:
            f.write(env_content)

        loader = ConfigLoader(agents_dir=temp_agents_dir)
        flow_dir = os.path.join(temp_agents_dir, "flows", "test-flow")

        # Clear env vars first
        if "TEST_VAR" in os.environ:
            del os.environ["TEST_VAR"]

        result = loader.load_env_file(flow_dir)
        assert result is True
        assert os.environ.get("TEST_VAR") == "test_value"
        assert os.environ.get("ANOTHER_VAR") == "123"

    def test_load_env_file_not_found(self, temp_agents_dir):
        """Test loading non-existent .env file"""
        loader = ConfigLoader(agents_dir=temp_agents_dir)
        result = loader.load_env_file("/nonexistent/path")
        assert result is False
