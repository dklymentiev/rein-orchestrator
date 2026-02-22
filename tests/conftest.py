"""Shared fixtures for Rein test suite."""
import os
import tempfile

import pytest
import yaml


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory, cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_workflow():
    """Return a minimal valid workflow dict."""
    return {
        "schema_version": "2.5.3",
        "name": "test-workflow",
        "team": "test-team",
        "blocks": [
            {
                "name": "step-1",
                "specialist": "test-specialist",
                "prompt": "Do something useful.",
            },
        ],
    }


@pytest.fixture
def sample_workflow_file(tmp_dir, sample_workflow):
    """Write sample_workflow to a YAML file and return its path."""
    path = os.path.join(tmp_dir, "workflow.yaml")
    with open(path, "w") as f:
        yaml.dump(sample_workflow, f)
    return path


@pytest.fixture
def mock_provider():
    """Return a mock provider that echoes back prompts."""
    from unittest.mock import MagicMock
    from rein.providers.base import UsageStats

    provider = MagicMock()
    provider.call.return_value = "mock response"
    provider.last_usage = UsageStats()
    return provider
