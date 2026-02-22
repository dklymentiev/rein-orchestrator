import { ReinClient } from "./rein-client";
import { createTools } from "./tools";
import type { ReinConfig, ToolDefinition } from "./types";

interface OpenClawPluginAPI {
  registerTool(definition: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
    handler: (params: Record<string, unknown>) => Promise<unknown>;
  }): void;
  getConfig(): Record<string, unknown>;
  log(level: string, message: string): void;
}

export default function register(api: OpenClawPluginAPI): void {
  const rawConfig = api.getConfig();
  const config: ReinConfig = {
    reinPath: (rawConfig.reinPath as string) || undefined,
    agentsDir: (rawConfig.agentsDir as string) || undefined,
    timeout: (rawConfig.timeout as number) || undefined,
    gatewayUrl: (rawConfig.gatewayUrl as string) || undefined,
    apiKey: (rawConfig.apiKey as string) || undefined,
  };

  const client = new ReinClient(config);
  const tools = createTools(client);

  for (const tool of tools) {
    api.registerTool({
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters,
      handler: tool.handler,
    });
  }

  api.log("info", `Rein plugin loaded: ${tools.length} tools registered`);
}

export { ReinClient } from "./rein-client";
export { createTools } from "./tools";
export type { ReinConfig, ToolDefinition } from "./types";
