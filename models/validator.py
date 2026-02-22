"""
ValidationEngine for Rein workflows.
Orchestrates JSON Schema validation, Pydantic model validation, and cross-reference checks.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
import jsonschema
from pydantic import ValidationError as PydanticValidationError

from .workflow import (
    WorkflowConfig, TeamConfig, ValidationResult, ValidationError
)


class ValidationEngine:
    """
    Multi-layer validation engine for workflows.

    Validation layers:
    1. JSON Schema structural validation
    2. Pydantic model validation with business logic
    3. Cross-reference validation (specialists exist, etc.)
    4. Version compatibility checking
    """

    def __init__(self, schemas_dir: Path = None, registry_dir: Path = None):
        """
        Initialize validation engine.

        Args:
            schemas_dir: Directory containing JSON schema files
            registry_dir: Directory containing registry.json
        """
        if schemas_dir is None:
            try:
                from schemas import SCHEMAS_DIR
                schemas_dir = SCHEMAS_DIR
            except ImportError:
                schemas_dir = Path(__file__).parent.parent / "schemas"

        self.schemas_dir = Path(schemas_dir)
        if registry_dir is None:
            self.registry_dir = self.schemas_dir
        else:
            self.registry_dir = Path(registry_dir)

        # Load schemas
        self.schemas: Dict[str, Dict] = {}
        self.registry: Dict = {}

        self._load_schemas()
        self._load_registry()

    def _load_schemas(self):
        """Load all JSON schemas from schemas directory"""
        schema_files = {
            "workflow": "workflow-v2.6.0.json",
            "team": "team-v2.5.3.json"
        }

        for schema_name, filename in schema_files.items():
            schema_path = self.schemas_dir / filename
            if schema_path.exists():
                with open(schema_path) as f:
                    self.schemas[schema_name] = json.load(f)
            else:
                raise FileNotFoundError(f"Schema file not found: {schema_path}")

    def _load_registry(self):
        """Load schema registry"""
        registry_path = self.schemas_dir / "registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                self.registry = json.load(f)
        else:
            raise FileNotFoundError(f"Registry file not found: {registry_path}")

    def validate_workflow(
        self, workflow_path: Path, cross_reference_check: bool = True
    ) -> ValidationResult:
        """
        Validate a workflow file through all validation layers.

        Args:
            workflow_path: Path to workflow YAML file
            cross_reference_check: Whether to check specialist file existence

        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(is_valid=True)
        workflow_path = Path(workflow_path)

        # Layer 1: Load and parse YAML
        try:
            with open(workflow_path) as f:
                workflow_data = yaml.safe_load(f)
        except FileNotFoundError:
            result.add_error("file", f"Workflow file not found: {workflow_path}")
            return result
        except yaml.YAMLError as e:
            result.add_error("yaml", f"Invalid YAML: {e}")
            return result

        if not isinstance(workflow_data, dict):
            result.add_error("format", "Workflow must be a YAML object")
            return result

        # Layer 2: JSON Schema validation
        try:
            jsonschema.validate(workflow_data, self.schemas["workflow"])
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
            result.add_error("schema", f"Schema validation failed at {path}: {e.message}")
            return result
        except jsonschema.SchemaError as e:
            result.add_error("schema", f"Invalid schema: {e.message}")
            return result

        # Layer 3: Version compatibility check
        version = workflow_data.get("schema_version", "2.5.3")
        if version not in self.registry.get("versions", {}):
            result.add_warning(
                "version",
                f"Unknown schema version: {version}. Current version: {self.registry['current_version']}"
            )

        # Layer 4: Pydantic model validation
        try:
            workflow_config = WorkflowConfig(**workflow_data)
        except PydanticValidationError as e:
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                result.add_error(field_path, error["msg"])
            return result

        # Layer 5: Cross-reference validation
        if cross_reference_check:
            self._validate_cross_references(workflow_config, workflow_path, result)

        # Layer 6: Metadata for successful validation
        if result.is_valid:
            phases = workflow_config.get_execution_order()
            critical_path = workflow_config.get_critical_path()

            result.metadata = {
                "name": workflow_config.name,
                "team": workflow_config.team,
                "blocks_count": len(workflow_config.blocks),
                "phases": len(phases),
                "max_parallel": workflow_config.max_parallel,
                "schema_version": workflow_config.schema_version,
                "critical_path_length": len(critical_path),
                "flow_control_blocks": sum(
                    1 for b in workflow_config.blocks
                    if b.skip_if_previous_failed or b.continue_if_failed
                )
            }

        return result

    def validate_team(self, team_path: Path, cross_reference_check: bool = True) -> ValidationResult:
        """
        Validate a team file through all validation layers.

        Args:
            team_path: Path to team YAML file
            cross_reference_check: Whether to check specialist file existence

        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(is_valid=True)
        team_path = Path(team_path)

        # Layer 1: Load and parse YAML
        try:
            with open(team_path) as f:
                team_data = yaml.safe_load(f)
        except FileNotFoundError:
            result.add_error("file", f"Team file not found: {team_path}")
            return result
        except yaml.YAMLError as e:
            result.add_error("yaml", f"Invalid YAML: {e}")
            return result

        if not isinstance(team_data, dict):
            result.add_error("format", "Team must be a YAML object")
            return result

        # Layer 2: JSON Schema validation
        try:
            jsonschema.validate(team_data, self.schemas["team"])
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
            result.add_error("schema", f"Schema validation failed at {path}: {e.message}")
            return result

        # Layer 3: Pydantic model validation
        try:
            team_config = TeamConfig(**team_data)
        except PydanticValidationError as e:
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                result.add_error(field_path, error["msg"])
            return result

        # Layer 4: Cross-reference validation
        if cross_reference_check:
            self._validate_team_cross_references(team_config, team_path, result)

        # Layer 5: Metadata
        if result.is_valid:
            result.metadata = {
                "name": team_config.name,
                "specialists_count": len(team_config.specialists),
                "schema_version": team_config.schema_version,
                "collaboration_tone": team_config.collaboration_tone
            }

        return result

    def _validate_cross_references(
        self, workflow: WorkflowConfig, workflow_path: Path, result: ValidationResult
    ):
        """
        Cross-reference validation:
        - Check all specialists referenced in workflow exist
        - Check all team files exist
        - Warn if specialist file structure doesn't match
        """
        workflow_dir = workflow_path.parent

        # Check team file exists (look in workflow_dir and agents/teams/)
        team_name = workflow.team
        team_file = workflow_dir / f"{team_name}.yaml"
        team_file_agents = workflow_dir / "agents" / "teams" / f"{team_name}.yaml"
        if not team_file.exists() and not team_file_agents.exists():
            result.add_warning("team", f"Team file not found: {team_file}")

        # Check specialist files exist (look in workflow_dir/specialists/ and agents/specialists/)
        specialists_dir = workflow_dir / "specialists"
        agents_specialists_dir = workflow_dir / "agents" / "specialists"
        if not specialists_dir.exists() and agents_specialists_dir.exists():
            specialists_dir = agents_specialists_dir
        if specialists_dir.exists():
            specialist_files = {f.stem for f in specialists_dir.glob("*.md")}
            for block in workflow.blocks:
                if block.specialist not in specialist_files:
                    result.add_warning(
                        f"blocks.{block.name}.specialist",
                        f"Specialist file not found: {specialists_dir}/{block.specialist}.md"
                    )

        # Check logic scripts exist if referenced
        for block in workflow.blocks:
            if block.logic:
                for phase in ["pre", "post", "validate", "custom"]:
                    script_path = getattr(block.logic, phase, None)
                    # Skip if script_path is boolean (custom: true) or None
                    if script_path and isinstance(script_path, str):
                        # script_path is relative to workflow_dir (e.g., "logic/init.py")
                        full_path = workflow_dir / script_path
                        if not full_path.exists():
                            result.add_warning(
                                f"blocks.{block.name}.logic.{phase}",
                                f"Logic script not found: {full_path}"
                            )

    def _validate_team_cross_references(
        self, team: TeamConfig, team_path: Path, result: ValidationResult
    ):
        """
        Cross-reference validation for teams:
        - Check all specialist files exist
        """
        team_dir = team_path.parent
        specialists_dir = team_dir / "specialists"

        if specialists_dir.exists():
            specialist_files = {f.stem for f in specialists_dir.glob("*.md")}
            for mapping in team.specialists:
                if mapping.specialist not in specialist_files:
                    result.add_warning(
                        f"specialists.{mapping.role}.specialist",
                        f"Specialist file not found: {specialists_dir}/{mapping.specialist}.md"
                    )
        else:
            if team.specialists:
                result.add_warning("specialists_dir", f"Specialists directory not found: {specialists_dir}")

    def check_version_compatibility(self, workflow_version: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a workflow version is compatible with current system.

        Args:
            workflow_version: Schema version from workflow

        Returns:
            (is_compatible, migration_message)
        """
        current_version = self.registry.get("current_version")

        if workflow_version == current_version:
            return True, None

        compatibility = self.registry.get("compatibility_matrix", {}).get(current_version, {})
        can_upgrade_from = compatibility.get("can_upgrade_from", [])

        if workflow_version in can_upgrade_from:
            migration_script = self.registry.get("migration_scripts", {}).get(
                f"{workflow_version}_to_{current_version}", {}
            )
            script_path = migration_script.get("path")
            description = migration_script.get("description", "Migration required")

            return True, f"Migration available: {description} ({script_path})"

        return False, f"Version {workflow_version} cannot be upgraded to {current_version}"


def validate_workflow_file(workflow_path: str, verbose: bool = False) -> bool:
    """
    Convenience function to validate a workflow file.

    Args:
        workflow_path: Path to workflow YAML file
        verbose: Whether to print detailed results

    Returns:
        True if validation passed, False otherwise
    """
    engine = ValidationEngine()
    result = engine.validate_workflow(Path(workflow_path))

    if verbose:
        print(result.format_report())

    return result.is_valid


def validate_team_file(team_path: str, verbose: bool = False) -> bool:
    """
    Convenience function to validate a team file.

    Args:
        team_path: Path to team YAML file
        verbose: Whether to print detailed results

    Returns:
        True if validation passed, False otherwise
    """
    engine = ValidationEngine()
    result = engine.validate_team(Path(team_path))

    if verbose:
        print(result.format_report())

    return result.is_valid
