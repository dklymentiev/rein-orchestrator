"""Tests for v2.6.0 declarative workflow input validation.

Covers:
- InputFieldConfig model validation
- WorkflowConfig with inputs: section
- ProcessManager._validate_task_inputs()
- Unresolved placeholder detection in assemble_prompt()
"""
import os
import json
import pytest
import tempfile

from pydantic import ValidationError as PydanticValidationError

from models.workflow import InputFieldConfig, WorkflowConfig, BlockConfig
from rein.models import Process
from rein.orchestrator import ProcessManager


# ---------------------------------------------------------------------------
# InputFieldConfig
# ---------------------------------------------------------------------------

class TestInputFieldConfig:
    """Tests for InputFieldConfig Pydantic model"""

    def test_required_defaults_true(self):
        """required field defaults to True"""
        cfg = InputFieldConfig()
        assert cfg.required is True

    def test_optional_field(self):
        """Can create optional field with required=False"""
        cfg = InputFieldConfig(required=False)
        assert cfg.required is False

    def test_optional_with_default(self):
        """Optional field can have a default value"""
        cfg = InputFieldConfig(required=False, default="fallback")
        assert cfg.default == "fallback"

    def test_default_rejected_when_required(self):
        """default is rejected when required=True"""
        with pytest.raises(PydanticValidationError, match="default.*only valid when required=false"):
            InputFieldConfig(required=True, default="nope")

    def test_default_rejected_when_required_implicit(self):
        """default is rejected when required is not set (defaults to True)"""
        with pytest.raises(PydanticValidationError, match="default.*only valid when required=false"):
            InputFieldConfig(default="nope")

    def test_description_field(self):
        """description field works"""
        cfg = InputFieldConfig(description="The topic to discuss")
        assert cfg.description == "The topic to discuss"

    def test_description_max_length(self):
        """description respects max_length=500"""
        with pytest.raises(PydanticValidationError):
            InputFieldConfig(description="x" * 501)

    def test_extra_fields_forbidden(self):
        """Extra fields are rejected"""
        with pytest.raises(PydanticValidationError):
            InputFieldConfig(unknown_field="bad")

    def test_no_default_for_required(self):
        """Required field has no default value"""
        cfg = InputFieldConfig(required=True)
        assert cfg.default is None

    def test_optional_without_default(self):
        """Optional field without default is fine"""
        cfg = InputFieldConfig(required=False)
        assert cfg.default is None


# ---------------------------------------------------------------------------
# WorkflowConfig with inputs
# ---------------------------------------------------------------------------

class TestWorkflowConfigInputs:
    """Tests for WorkflowConfig inputs: section"""

    def _make_config(self, inputs=None, blocks=None):
        """Helper to build minimal WorkflowConfig kwargs"""
        if blocks is None:
            blocks = [BlockConfig(
                name="step1",
                specialist="analyzer",
                prompt="Analyze {{ task.input.topic }}"
            )]
        return {
            "name": "test-workflow",
            "team": "team-test",
            "blocks": [
                {"name": b.name, "specialist": b.specialist, "prompt": b.prompt}
                for b in blocks
            ],
            "inputs": inputs,
        }

    def test_valid_inputs_section(self):
        """Workflow with matching inputs: section passes validation"""
        cfg = WorkflowConfig(
            name="test-workflow",
            team="team-test",
            inputs={
                "topic": InputFieldConfig(description="The topic"),
            },
            blocks=[
                BlockConfig(
                    name="step1",
                    specialist="analyzer",
                    prompt="Analyze {{ task.input.topic }}"
                )
            ],
        )
        assert cfg.inputs is not None
        assert "topic" in cfg.inputs

    def test_no_inputs_section_backward_compat(self):
        """Workflow without inputs: section works (backward compat)"""
        cfg = WorkflowConfig(
            name="test-workflow",
            team="team-test",
            blocks=[
                BlockConfig(
                    name="step1",
                    specialist="analyzer",
                    prompt="Analyze {{ task.input.topic }}"
                )
            ],
        )
        assert cfg.inputs is None

    def test_undeclared_input_in_prompt_raises_error(self):
        """Using undeclared input in prompt raises validation error"""
        with pytest.raises(PydanticValidationError, match="undeclared input.*task.input.files"):
            WorkflowConfig(
                name="test-workflow",
                team="team-test",
                inputs={
                    "topic": InputFieldConfig(description="The topic"),
                },
                blocks=[
                    BlockConfig(
                        name="step1",
                        specialist="analyzer",
                        prompt="Analyze {{ task.input.topic }} with {{ task.input.files }}"
                    )
                ],
            )

    def test_all_inputs_declared(self):
        """All used inputs declared passes validation"""
        cfg = WorkflowConfig(
            name="test-workflow",
            team="team-test",
            inputs={
                "topic": InputFieldConfig(description="The topic"),
                "files": InputFieldConfig(description="Files to review"),
            },
            blocks=[
                BlockConfig(
                    name="step1",
                    specialist="analyzer",
                    prompt="Analyze {{ task.input.topic }} with {{ task.input.files }}"
                )
            ],
        )
        assert len(cfg.inputs) == 2

    def test_empty_prompt_no_error(self):
        """Block with empty prompt doesn't trigger input check"""
        cfg = WorkflowConfig(
            name="test-workflow",
            team="team-test",
            inputs={
                "topic": InputFieldConfig(description="The topic"),
            },
            blocks=[
                BlockConfig(
                    name="step1",
                    specialist="analyzer",
                    prompt=""
                )
            ],
        )
        assert cfg.inputs is not None

    def test_extra_declared_inputs_no_error(self):
        """Declaring extra inputs not used in prompts is fine"""
        cfg = WorkflowConfig(
            name="test-workflow",
            team="team-test",
            inputs={
                "topic": InputFieldConfig(description="The topic"),
                "extra": InputFieldConfig(required=False, description="Not used in prompts"),
            },
            blocks=[
                BlockConfig(
                    name="step1",
                    specialist="analyzer",
                    prompt="Analyze {{ task.input.topic }}"
                )
            ],
        )
        assert len(cfg.inputs) == 2


# ---------------------------------------------------------------------------
# ProcessManager._validate_task_inputs
# ---------------------------------------------------------------------------

class TestValidateTaskInputs:
    """Tests for ProcessManager._validate_task_inputs method"""

    @pytest.fixture
    def manager(self):
        """Create ProcessManager with temp directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            mgr = ProcessManager(max_parallel=3, agents_dir=agents_dir)
            yield mgr

    def test_no_inputs_section_skips(self, manager):
        """Config without inputs: section does nothing"""
        manager.task_input = {"topic": "test"}
        config = {"name": "test", "blocks": []}
        # Should not raise
        manager._validate_task_inputs(config)

    def test_all_required_present_passes(self, manager):
        """All required inputs provided passes validation"""
        manager.task_input = {"topic": "AI safety", "files": "main.py"}
        config = {
            "name": "test",
            "inputs": {
                "topic": {"required": True, "description": "The topic"},
                "files": {"required": True, "description": "Files to review"},
            }
        }
        # Should not raise
        manager._validate_task_inputs(config)

    def test_missing_required_exits(self, manager):
        """Missing required input calls sys.exit(1)"""
        manager.task_input = {"topic": "AI safety"}
        config = {
            "name": "test-review",
            "inputs": {
                "topic": {"required": True},
                "files": {"required": True, "description": "Files to review"},
            }
        }
        with pytest.raises(SystemExit) as exc_info:
            manager._validate_task_inputs(config)
        assert exc_info.value.code == 1

    def test_optional_missing_ok(self, manager):
        """Optional field missing does not cause error"""
        manager.task_input = {"topic": "AI safety"}
        config = {
            "name": "test",
            "inputs": {
                "topic": {"required": True},
                "project": {"required": False, "description": "Optional project name"},
            }
        }
        # Should not raise
        manager._validate_task_inputs(config)

    def test_default_injected(self, manager):
        """Optional field with default is injected into task_input"""
        manager.task_input = {"topic": "AI safety"}
        config = {
            "name": "test",
            "inputs": {
                "topic": {"required": True},
                "project": {"required": False, "default": "unknown"},
            }
        }
        manager._validate_task_inputs(config)
        assert manager.task_input["project"] == "unknown"

    def test_default_not_overwritten(self, manager):
        """Provided value is NOT overwritten by default"""
        manager.task_input = {"topic": "AI safety", "project": "my-project"}
        config = {
            "name": "test",
            "inputs": {
                "topic": {"required": True},
                "project": {"required": False, "default": "unknown"},
            }
        }
        manager._validate_task_inputs(config)
        assert manager.task_input["project"] == "my-project"

    def test_extra_inputs_warning(self, manager, capfd):
        """Extra undeclared inputs produce warning"""
        manager.task_input = {"topic": "AI", "garbage": "extra"}
        config = {
            "name": "test",
            "inputs": {
                "topic": {"required": True},
            }
        }
        manager._validate_task_inputs(config)
        captured = capfd.readouterr()
        assert "Extra inputs" in captured.err or "garbage" in captured.err

    def test_multiple_missing_all_reported(self, manager):
        """Multiple missing required fields all reported"""
        manager.task_input = {}
        config = {
            "name": "test-multi",
            "inputs": {
                "topic": {"required": True, "description": "Topic"},
                "files": {"required": True, "description": "Files"},
                "project": {"required": True},
            }
        }
        with pytest.raises(SystemExit):
            manager._validate_task_inputs(config)


# ---------------------------------------------------------------------------
# Unresolved placeholder detection
# ---------------------------------------------------------------------------

class TestUnresolvedPlaceholders:
    """Tests for unresolved placeholder detection in assemble_prompt"""

    @pytest.fixture
    def manager(self):
        """Create ProcessManager with temp directory and minimal setup"""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "agents")
            specs_dir = os.path.join(agents_dir, "specialists")
            os.makedirs(os.path.join(agents_dir, "tasks"), exist_ok=True)
            os.makedirs(specs_dir, exist_ok=True)

            # Create a dummy specialist file
            with open(os.path.join(specs_dir, "test-spec.md"), "w") as f:
                f.write("You are a test specialist.")

            mgr = ProcessManager(max_parallel=3, agents_dir=agents_dir)
            mgr.workflow_dir = tmpdir
            mgr.task_dir = os.path.join(tmpdir, "task")
            os.makedirs(os.path.join(mgr.task_dir, "outputs"), exist_ok=True)
            yield mgr

    def test_unresolved_raises_error(self, manager):
        """Unresolved {{ task.input.X }} raises ValueError"""
        manager.task_input = {}
        block = {
            "specialist": "test-spec",
            "prompt": "Analyze {{ task.input.topic }}"
        }
        with pytest.raises(ValueError, match="Unresolved input placeholders"):
            manager.assemble_prompt(block, "professional")

    def test_all_resolved_ok(self, manager):
        """All placeholders resolved produces valid prompt"""
        manager.task_input = {"topic": "AI safety"}
        block = {
            "specialist": "test-spec",
            "prompt": "Analyze {{ task.input.topic }}"
        }
        result = manager.assemble_prompt(block, "professional")
        assert "AI safety" in result
        assert "task.input" not in result

    def test_file_placeholder_not_flagged(self, manager):
        """{{ file.json }} placeholders are NOT flagged as unresolved task inputs"""
        manager.task_input = {"topic": "test"}
        block = {
            "specialist": "test-spec",
            "prompt": "Analyze {{ task.input.topic }} with {{ analysis.json }}"
        }
        # Should not raise - {{ analysis.json }} is a file placeholder, not task.input
        result = manager.assemble_prompt(block, "professional")
        assert "test" in result

    def test_multiple_unresolved(self, manager):
        """Multiple unresolved placeholders all reported"""
        manager.task_input = {}
        block = {
            "specialist": "test-spec",
            "prompt": "Review {{ task.input.topic }} files {{ task.input.files }}"
        }
        with pytest.raises(ValueError, match="Unresolved input placeholders"):
            manager.assemble_prompt(block, "professional")

    def test_partial_resolution(self, manager):
        """Some resolved, some not - raises for unresolved"""
        manager.task_input = {"topic": "AI safety"}
        block = {
            "specialist": "test-spec",
            "prompt": "Review {{ task.input.topic }} files {{ task.input.files }}"
        }
        with pytest.raises(ValueError, match="files"):
            manager.assemble_prompt(block, "professional")
