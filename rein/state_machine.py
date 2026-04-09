"""State machine logic for workflow orchestration.

Pure functions and helpers for:
- Dependency graph manipulation (dependents map, cascade invalidation)
- Routing direction detection (backward vs forward)
- Pending block re-evaluation after cascade
- Orphan detection (blocks that can't make progress)
- Stuck detection (workflow deadlock)
- Sync between Process.status and completed set (thread race fix)

These helpers were extracted from ProcessManager to reduce coupling and
enable unit testing without a full manager instance.
"""

from typing import Any, Callable, Dict, List, Optional, Set


def get_dependents_map(all_blocks: List[dict]) -> Dict[str, List[str]]:
    """Build reverse dependency graph: {block_name: [blocks that depend on it]}"""
    dependents: Dict[str, List[str]] = {}
    for block in all_blocks:
        name = block.get("name") or block.get("stage", "unknown")
        for dep in block.get("depends_on", []):
            if dep not in dependents:
                dependents[dep] = []
            dependents[dep].append(name)
    return dependents


def cascade_invalidation(
    failed_blocks: Set[str],
    dependents_map: Dict[str, List[str]],
    log_fn: Optional[Callable] = None,
) -> Set[str]:
    """BFS from failed blocks through dependents. Returns full set needing re-run."""
    needs_rerun = set(failed_blocks)
    queue = list(failed_blocks)
    while queue:
        current = queue.pop(0)
        for downstream in dependents_map.get(current, []):
            if downstream not in needs_rerun:
                needs_rerun.add(downstream)
                queue.append(downstream)
                if log_fn:
                    log_fn(f"CASCADE | {downstream} | invalidated (depends on {current})")
    return needs_rerun


def compute_routing_skip_set(
    routing: dict,
    chosen: str,
    gate_name: str,
    dependents_map: Dict[str, List[str]],
) -> Set[str]:
    """Compute blocks that must be skipped because routing picked a different branch.

    When a gate uses `routing:` with several branches, only the chosen branch
    should execute. All other named targets (and their exclusive descendants)
    must be marked skipped so the main loop does not spawn them via depends_on
    scheduling (fix #1190).

    A descendant of a non-chosen branch is kept alive if it is also a descendant
    of the chosen branch (i.e., paths reconverge).

    Args:
        routing: dict mapping signal -> target block name (plus optional _default)
        chosen: the target block routing selected
        gate_name: the gate block itself (never skip the gate)
        dependents_map: reverse dep graph

    Returns:
        Set of block names that should be marked skipped.
    """
    # Collect all routing targets except the chosen one and control markers
    non_chosen: Set[str] = set()
    for key, target in routing.items():
        if not target or target == "_stop" or target == chosen:
            continue
        non_chosen.add(target)

    if not non_chosen:
        return set()

    # Descendants reachable from the chosen branch (these must NOT be skipped
    # even if they're also reachable from a non-chosen branch -- reconvergence).
    chosen_reach = cascade_invalidation({chosen}, dependents_map)

    # Descendants of non-chosen branches (including the branches themselves)
    non_chosen_reach = cascade_invalidation(non_chosen, dependents_map)

    # Skip = non-chosen reach minus chosen reach minus gate itself
    skip_set = non_chosen_reach - chosen_reach
    skip_set.discard(gate_name)
    skip_set.discard(chosen)
    return skip_set


def is_backward_routing(
    block_configs: Dict[str, dict],
    source_block: str,
    target_block: str,
) -> bool:
    """Check if routing from source to target is backward (revision loop).

    Backward means target is a transitive predecessor of source in the
    dependency graph. Forward means target is a successor or sibling.
    """
    ancestors: Set[str] = set()
    queue = [source_block]
    while queue:
        current = queue.pop(0)
        block = block_configs.get(current)
        if not block:
            continue
        for dep in block.get("depends_on", []):
            if dep not in ancestors:
                ancestors.add(dep)
                queue.append(dep)
    return target_block in ancestors


def is_stuck(pending: dict, completed: Set[str]) -> bool:
    """Check if workflow is stuck: pending blocks exist but none can run."""
    if not pending:
        return False
    return not any(all(dep in completed for dep in (pending[n].get("depends_on", []) or [])) for n in pending)


def detect_orphans(
    pending: dict,
    completed: Set[str],
    has_running_fn: Callable,
    log_fn: Optional[Callable] = None,
) -> List[str]:
    """Identify blocks whose dependencies can never be satisfied.

    Returns list of orphan names. Caller is responsible for marking them
    completed and removing from pending.

    Note: returns empty list if any block is currently running (don't orphan
    during in-flight execution).
    """
    if has_running_fn():
        return []
    orphans = []
    for name in list(pending.keys()):
        block = pending[name]
        deps = block.get("depends_on", [])
        if not deps:
            continue
        if all(dep in completed for dep in deps):
            continue  # deps met, can run
        orphans.append(name)
    if log_fn:
        for name in orphans:
            log_fn(f"ORPHAN SKIP | {name} | deps unsatisfiable, workflow stuck")
    return orphans


def collect_running_names(processes: Dict[str, Any], lock) -> Set[str]:
    """Get names of currently running blocks (thread-safe)."""
    with lock:
        return {p.name for p in processes.values() if p.status == "running"}


def has_running_or_transitioning(processes: Dict[str, Any], completed: Set[str], lock) -> bool:
    """Returns True if any process is running OR in transitional done->completed state.

    Transitional state: Process.status is 'done' but Process.name not yet in
    completed set. This happens briefly when a thread finishes execution but
    hasn't yet registered completion.
    """
    with lock:
        for p in processes.values():
            if p.status == "running":
                return True
            if p.status == "done" and p.name not in completed:
                return True
    return False


def sync_completed_from_processes(
    processes: Dict[str, Any],
    completed: Set[str],
    lock,
) -> None:
    """Sync done/failed process status into completed set.

    Called before stuck detection to avoid false positives from threads
    that finished but haven't yet registered completion via completed.add().
    Mutates `completed` in place.
    """
    with lock:
        for p in processes.values():
            if p.status in ("done", "failed") and p.name not in completed:
                completed.add(p.name)


def find_blocks_needing_repending(
    all_blocks: List[dict],
    pending: dict,
    completed: Set[str],
    running_names: Set[str],
) -> List[dict]:
    """Find blocks that should be re-added to pending after routing cascade.

    A block needs re-pending if:
    - Not in completed (cascade invalidated it)
    - Not already in pending (would be duplicate)
    - Not currently running (avoid duplicate execution)

    Returns list of block config dicts to add back.
    """
    to_add = []
    for block in all_blocks:
        name = block.get("name") or block.get("stage", "unknown")
        if name not in completed and name not in pending and name not in running_names:
            to_add.append(block)
    return to_add


def find_ready_blocks(
    pending: dict,
    completed: Set[str],
    agent_id: Optional[str] = None,
) -> List[str]:
    """Find blocks whose dependencies are satisfied and ready to spawn.

    Optional agent_id filter: if set, skip blocks assigned to other agents.
    A block with no agent field runs for any agent.
    """
    ready = []
    for name, block in pending.items():
        depends_on = block.get("depends_on", [])
        if depends_on and not all(dep in completed for dep in depends_on):
            continue  # deps not met

        # Agent routing filter
        if agent_id:
            block_agent = block.get("agent", "")
            if block_agent and block_agent != agent_id:
                continue

        ready.append(name)
    return ready


def count_remaining_blocks(all_blocks: List[dict], completed: Set[str]) -> int:
    """Count how many blocks haven't been completed yet."""
    return sum(1 for block in all_blocks if (block.get("name") or block.get("stage", "unknown")) not in completed)


def all_blocks_completed(all_blocks: List[dict], completed: Set[str]) -> bool:
    """Check if all blocks are in the completed set."""
    return all((block.get("name") or block.get("stage", "unknown")) in completed for block in all_blocks)
