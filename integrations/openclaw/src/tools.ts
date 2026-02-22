import type { ReinClient } from "./rein-client";
import type { ToolDefinition } from "./types";

export function createTools(client: ReinClient): ToolDefinition[] {
  return [
    {
      name: "rein_list_flows",
      description:
        "List available Rein workflows (flows) with descriptions, block counts, and input schemas.",
      parameters: {
        type: "object",
        properties: {},
        required: [],
      },
      handler: async () => {
        return await client.listFlows();
      },
    },
    {
      name: "rein_run_workflow",
      description:
        "Execute a Rein workflow synchronously and return results. " +
        "Use for short workflows (under 10 minutes). " +
        "For long-running workflows, use rein_create_task instead.",
      parameters: {
        type: "object",
        properties: {
          flow: {
            type: "string",
            description: "Name of the flow to run (must exist in agents/flows/)",
          },
          input: {
            type: "object",
            description: "Optional input parameters for the workflow (key-value pairs)",
            additionalProperties: true,
          },
        },
        required: ["flow"],
      },
      handler: async (params: Record<string, unknown>) => {
        const flow = params.flow as string;
        const input = params.input as Record<string, unknown> | undefined;
        return await client.runWorkflow(flow, input);
      },
    },
    {
      name: "rein_create_task",
      description:
        "Create a new asynchronous task for the Rein daemon to execute. " +
        "The daemon (rein --daemon) must be running to pick up tasks. " +
        "Use rein_task_status to check progress.",
      parameters: {
        type: "object",
        properties: {
          flow: {
            type: "string",
            description: "Name of the flow to run (must exist in agents/flows/)",
          },
          question: {
            type: "string",
            description: "The question or task description for the workflow",
          },
          input: {
            type: "object",
            description: "Optional structured input parameters (key-value pairs)",
            additionalProperties: true,
          },
        },
        required: ["flow", "question"],
      },
      handler: async (params: Record<string, unknown>) => {
        const flow = params.flow as string;
        const question = params.question as string;
        const input = params.input as Record<string, unknown> | undefined;
        return await client.createTask(flow, question, input);
      },
    },
    {
      name: "rein_task_status",
      description:
        "Check the status of a Rein task, including block progress and output files.",
      parameters: {
        type: "object",
        properties: {
          task_id: {
            type: "string",
            description: "Task ID (e.g. task-20260220-143022)",
          },
        },
        required: ["task_id"],
      },
      handler: async (params: Record<string, unknown>) => {
        const taskId = params.task_id as string;
        return await client.taskStatus(taskId);
      },
    },
  ];
}
