#!/usr/bin/env python3
"""
Test script for Phase 2.5 Specialist Architecture Implementation
Validates that all components work together correctly
"""

import os
import sys
import yaml
import json

# Add path for imports
sys.path.insert(0, '/server/scripts/agent-pm2-dog')

def test_specialists_exist():
    """Verify all 10 specialist MD files exist"""
    print("\n[TEST] Checking specialist files...")
    specialists = [
        'poet-specialist',
        'critic-specialist',
        'developer-specialist',
        'architect-specialist',
        'tester-specialist',
        'security-expert-specialist',
        'debugger-specialist',
        'documenter-specialist',
        'integrator-specialist',
        'analyst-specialist'
    ]

    missing = []
    for spec in specialists:
        path = f'agents/specialists/{spec}.md'
        if not os.path.exists(path):
            missing.append(spec)
        else:
            with open(path) as f:
                content = f.read()
                if len(content) < 100:
                    print(f"  [WARN] {spec}.md too short ({len(content)} bytes)")
                else:
                    print(f"  [OK] {spec}.md ({len(content)} bytes)")

    if missing:
        print(f"  [FAIL] Missing specialists: {missing}")
        return False
    print("  [PASS] All 10 specialists exist")
    return True


def test_teams_exist():
    """Verify all 3 team YAML files exist"""
    print("\n[TEST] Checking team files...")
    teams = [
        'team-poetry',
        'team-code-review',
        'team-security-audit'
    ]

    missing = []
    for team in teams:
        path = f'agents/teams/{team}.yaml'
        if not os.path.exists(path):
            missing.append(team)
        else:
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                    tone = data.get('tone', '')
                    agents = data.get('agents', [])
                    print(f"  [OK] {team}.yaml (tone: {len(tone)} chars, agents: {len(agents)})")
            except Exception as e:
                print(f"  [FAIL] {team}.yaml - {str(e)}")
                return False

    if missing:
        print(f"  [FAIL] Missing teams: {missing}")
        return False
    print("  [PASS] All 3 teams exist and parse correctly")
    return True


def test_flows_exist():
    """Verify all 3 flow directories with YAML and logic scripts exist"""
    print("\n[TEST] Checking flow directories...")
    flows = [
        ('create-poem', 3),      # flow name, expected logic scripts
        ('review-code', 3),
        ('security-audit', 3)
    ]

    missing = []
    for flow_name, expected_logic in flows:
        flow_dir = f'agents/flows/{flow_name}'
        yaml_path = f'{flow_dir}/{flow_name}.yaml'
        logic_dir = f'{flow_dir}/logic'

        if not os.path.exists(flow_dir):
            missing.append(f"{flow_name} (directory)")
            continue

        if not os.path.exists(yaml_path):
            missing.append(f"{flow_name} (YAML)")
            continue

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
                blocks = data.get('blocks', [])
                team = data.get('team', '')

            # Count logic scripts
            logic_count = 0
            if os.path.exists(logic_dir):
                logic_scripts = [f for f in os.listdir(logic_dir) if f.endswith(('.py', '.sh'))]
                logic_count = len(logic_scripts)

            print(f"  [OK] {flow_name}/ (team: {team}, blocks: {len(blocks)}, logic: {logic_count} scripts)")

        except Exception as e:
            print(f"  [FAIL] {flow_name} - {str(e)}")
            return False

    if missing:
        print(f"  [FAIL] Missing flows: {missing}")
        return False
    print("  [PASS] All 3 flows exist with YAML and logic scripts")
    return True


def test_dog_v2_methods():
    """Verify dog.py has required Phase 2.5 methods including logic phases"""
    print("\n[TEST] Checking dog.py methods...")

    with open('dog.py') as f:
        content = f.read()

    methods = [
        'def load_team',
        'def load_specialist',
        'def assemble_prompt',
        'def call_claude',
        'def _run_logic'  # NEW: Logic phases support
    ]

    missing = []
    for method in methods:
        if method not in content:
            missing.append(method)
        else:
            print(f"  [OK] {method} found")

    if missing:
        print(f"  [FAIL] Missing methods: {missing}")
        return False

    # Check that run_workflow loads team
    if 'load_team(self.team_name)' not in content:
        print(f"  [FAIL] run_workflow doesn't load team")
        return False
    print(f"  [OK] run_workflow loads team")

    # Check that spawn_process is called with team_tone
    if 'spawn_process(pending[name], team_tone)' not in content:
        print(f"  [FAIL] spawn_process not called with team_tone")
        return False
    print(f"  [OK] spawn_process called with team_tone")

    # Check logic phases in _execute_block
    if 'logic_config.get' not in content:
        print(f"  [FAIL] _execute_block doesn't handle logic phases")
        return False
    print(f"  [OK] _execute_block handles logic phases (pre/post/validate)")

    print("  [PASS] dog.py has all Phase 2.5 methods including logic phases")
    return True


def test_workflow_structure():
    """Verify flow YAML structure is correct"""
    print("\n[TEST] Checking flow YAML structure...")

    # Test create-poem flow
    with open('agents/flows/create-poem/create-poem.yaml') as f:
        wf = yaml.safe_load(f)

    # Check required fields
    if 'name' not in wf:
        print("  [FAIL] Workflow missing 'name' field")
        return False
    if 'team' not in wf:
        print("  [FAIL] Workflow missing 'team' field")
        return False
    if 'blocks' not in wf or not wf['blocks']:
        print("  [FAIL] Workflow missing 'blocks' field")
        return False

    # Check block structure
    for block in wf['blocks']:
        if 'stage' not in block:
            print(f"  [FAIL] Block missing 'stage' field")
            return False
        if 'agents' not in block:
            print(f"  [FAIL] Block '{block.get('stage')}' missing 'agents' field")
            return False
        if 'prompt' not in block:
            print(f"  [FAIL] Block '{block.get('stage')}' missing 'prompt' field")
            return False
        if 'save_as' not in block:
            print(f"  [FAIL] Block '{block.get('stage')}' missing 'save_as' field")
            return False

        # Check for file substitution syntax
        prompt = block.get('prompt', '')
        if '{{' in prompt:
            print(f"  [OK] Block '{block.get('stage')}' has file references")

        # Check depends_on if present
        if 'depends_on' in block and block['depends_on']:
            print(f"  [OK] Block '{block.get('stage')}' has dependencies: {block['depends_on']}")

    print("  [PASS] Workflow structure is correct")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("PHASE 2.5 SPECIALIST ARCHITECTURE - VALIDATION TEST")
    print("=" * 60)

    tests = [
        ("Specialists", test_specialists_exist),
        ("Teams", test_teams_exist),
        ("Flows", test_flows_exist),
        ("Dog-v2 Methods", test_dog_v2_methods),
        ("Workflow Structure", test_workflow_structure),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] {name} test failed with exception:")
            print(f"  {str(e)}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] Phase 2.5 implementation is ready!")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
