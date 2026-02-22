---
name: rein
description: Run multi-agent AI workflows using Rein orchestrator
user-invocable: true
command-dispatch: tool
command-tool: rein_run_workflow
---

# Rein -- Multi-Agent Workflow Orchestrator

Rein coordinates multiple AI specialists through structured YAML workflows.
Use it when a task benefits from multiple perspectives or sequential expert analysis.

## When to use

- User asks to "run a workflow", "start a flow", or "use rein"
- User wants multi-perspective analysis ("deliberate on X", "review from multiple angles")
- User asks to coordinate multiple AI specialists on a problem
- User wants structured code review, research, or content generation pipelines

## Available tools

### rein_list_flows
List what workflows are available. Call this first if unsure which flow to use.
Returns flow names, descriptions, block counts, team info, and required inputs.

### rein_run_workflow
Execute a workflow synchronously. Best for workflows that complete in under 10 minutes.
- `flow` (required): name of the flow (e.g. "deliberation", "code-review")
- `input` (optional): key-value object with input parameters

### rein_create_task
Start a workflow as a background task. The Rein daemon picks it up and runs it.
Use this for long-running workflows or when the user does not need to wait.
- `flow` (required): name of the flow
- `question` (required): task description or question
- `input` (optional): structured input parameters

### rein_task_status
Check progress of a background task created with rein_create_task.
- `task_id` (required): the task ID returned by rein_create_task

## Typical usage

1. List available flows: call `rein_list_flows`
2. Pick the appropriate flow based on user's request
3. Run it: call `rein_run_workflow` with the flow name and any required inputs
4. Present the results to the user

For long tasks:
1. Create task: call `rein_create_task` with flow and question
2. Inform user the task is running in background
3. Periodically check with `rein_task_status` when user asks for updates

## Notes

- Flows live in `agents/flows/<name>/<name>.yaml`
- Each flow has a team of specialists that collaborate on the task
- Outputs include structured results from each specialist block
- The daemon must be running (`rein --daemon`) for async tasks to execute
