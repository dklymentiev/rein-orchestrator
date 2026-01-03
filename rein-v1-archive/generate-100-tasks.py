#!/usr/bin/env python3
"""
Generate large scale test YAML: ~100+ tasks, 10 agents, parallel blocks.

Distribution per wave: 10 - 3 - 10 - 5 - 1 - 1 - 1 - 3 - 2 - 1
3 waves = ~111 total tasks
"""

import yaml

# Parallel block sizes (10 blocks, each with different concurrency)
# This pattern repeats 3 times for ~111 total tasks
blocks_config = [
    (10, "agent-1"),   # 10 parallel tasks, agent-1
    (3, "agent-2"),    # 3 parallel tasks, agent-2
    (10, "agent-3"),   # 10 parallel tasks, agent-3
    (5, "agent-4"),    # 5 parallel tasks, agent-4
    (1, "agent-5"),    # 1 task, agent-5
    (1, "agent-6"),    # 1 task, agent-6
    (1, "agent-7"),    # 1 task, agent-7
    (3, "agent-8"),    # 3 parallel tasks, agent-8
    (2, "agent-9"),    # 2 parallel tasks, agent-9
    (1, "agent-10"),   # 1 task, agent-10
]

num_waves = 3

# Calculate totals
tasks_per_wave = sum(count for count, _ in blocks_config)
total_tasks = tasks_per_wave * num_waves
max_parallel = max(count for count, _ in blocks_config)

print(f"[INFO] Generating {total_tasks} tasks across {num_waves} waves")
print(f"[INFO] Tasks per wave: {tasks_per_wave}")
print(f"[INFO] Max parallelism: {max_parallel}")
print(f"[INFO] Block distribution per wave: {' - '.join(str(c) for c, _ in blocks_config)}")

blocks = []
prev_block_names = []

# Generate 3 waves
for wave in range(1, num_waves + 1):
    print(f"\n[WAVE {wave}/{num_waves}]")

    for block_idx, (num_tasks, agent_name) in enumerate(blocks_config):
        # Vary agent names per wave to use all 10 agents multiple times
        actual_agent = f"{agent_name}-wave{wave}"

        print(f"  [BLOCK {block_idx + 1}] {actual_agent}: {num_tasks} tasks")

        # Create tasks for this block
        block_task_names = []
        for task_idx in range(1, num_tasks + 1):
            task_name = f"{actual_agent}-task-{task_idx}"
            block_task_names.append(task_name)

            task = {
                "name": task_name,
                "command": f"python3 mock-agent.py output.txt {actual_agent} {task_idx} output.txt",
                "agent": actual_agent
            }

            # Dependencies: this block depends on all tasks of previous block
            if prev_block_names:
                task["depends_on"] = prev_block_names

            blocks.append(task)

        prev_block_names = block_task_names

# Create YAML structure
config = {
    "semaphore": max_parallel,
    "timeout": 600,
    "blocks": blocks
}

# Write YAML file
with open("test-100-tasks.yaml", "w") as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print(f"\n[OK] Created test-100-tasks.yaml")
print(f"[STATS] Total tasks: {len(blocks)}")
print(f"[STATS] File location: /server/scripts/agent-pm2-dog/test-100-tasks.yaml")
