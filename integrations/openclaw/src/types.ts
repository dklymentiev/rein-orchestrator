export interface ReinConfig {
  reinPath?: string;
  agentsDir?: string;
  timeout?: number;
  /** HTTP gateway URL (e.g. "http://localhost:8200"). If set, uses HTTP instead of subprocess. */
  gatewayUrl?: string;
  /** API key for HTTP gateway authentication */
  apiKey?: string;
}

export interface FlowInfo {
  name: string;
  description: string;
  blocks: number;
  team: string;
  provider: string;
  inputs?: Record<string, InputInfo>;
  error?: string;
}

export interface InputInfo {
  required: boolean;
  description: string;
  default?: unknown;
}

export interface SpecialistInfo {
  name: string;
  summary: string;
  error?: string;
}

export interface TeamInfo {
  name: string;
  description: string;
  specialists: string[];
  error?: string;
}

export interface WorkflowResult {
  status: "completed" | "failed";
  exit_code: number;
  outputs: Record<string, unknown>;
  stderr?: string;
  error?: string;
}

export interface TaskCreated {
  task_id: string;
  flow: string;
  status: "pending";
  task_dir: string;
  error?: string;
}

export interface BlockStatus {
  name: string;
  status: string;
  phase: number;
  progress: number;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  config?: Record<string, unknown>;
  blocks?: BlockStatus[];
  total?: number;
  done?: number;
  failed?: number;
  running?: number;
  outputs?: Array<{ file: string; size: number }>;
  error?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  handler: (params: Record<string, unknown>) => Promise<unknown>;
}
