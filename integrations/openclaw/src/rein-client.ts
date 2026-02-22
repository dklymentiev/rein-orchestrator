import { spawn, execSync } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as http from "http";
import * as https from "https";
import type {
  ReinConfig,
  FlowInfo,
  WorkflowResult,
  TaskCreated,
  TaskStatus,
} from "./types";

let yamlParse: (input: string) => unknown;
let yamlStringify: (value: unknown) => string;
try {
  const yaml = require("yaml");
  yamlParse = yaml.parse;
  yamlStringify = yaml.stringify;
} catch {
  yamlParse = (input: string) => {
    const obj: Record<string, string> = {};
    for (const line of input.split("\n")) {
      const match = line.match(/^(\w[\w_-]*)\s*:\s*(.+)$/);
      if (match) obj[match[1]] = match[2].trim().replace(/^["']|["']$/g, "");
    }
    return obj;
  };
  yamlStringify = (value: unknown) =>
    Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
      .join("\n");
}

export class ReinClient {
  private reinPath: string;
  private agentsDir: string;
  private timeout: number;
  private gatewayUrl: string;
  private apiKey: string;

  constructor(config: ReinConfig = {}) {
    this.gatewayUrl = (config.gatewayUrl || "").replace(/\/$/, "");
    this.apiKey = config.apiKey || "";
    this.reinPath = config.reinPath || (this.gatewayUrl ? "" : this.detectReinPath());
    this.agentsDir = config.agentsDir || "";
    this.timeout = (config.timeout || 600) * 1000;
  }

  private get useHttp(): boolean {
    return !!this.gatewayUrl;
  }

  // ---------------------------------------------------------------------------
  // HTTP transport (calls Rein HTTP Gateway)
  // ---------------------------------------------------------------------------

  private httpRequest(method: string, urlPath: string, body?: unknown): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const fullUrl = new URL(urlPath, this.gatewayUrl);
      const isHttps = fullUrl.protocol === "https:";
      const lib = isHttps ? https : http;

      const payload = body ? JSON.stringify(body) : undefined;

      const options: http.RequestOptions = {
        method,
        hostname: fullUrl.hostname,
        port: fullUrl.port || (isHttps ? 443 : 80),
        path: fullUrl.pathname + fullUrl.search,
        headers: {
          "Content-Type": "application/json",
          ...(this.apiKey ? { "X-API-Key": this.apiKey } : {}),
          ...(payload ? { "Content-Length": Buffer.byteLength(payload) } : {}),
        },
        timeout: this.timeout,
      };

      const req = lib.request(options, (res) => {
        let data = "";
        res.on("data", (chunk: Buffer) => { data += chunk.toString(); });
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 400) {
            let detail = data;
            try { detail = JSON.parse(data).detail || data; } catch {}
            reject(new Error(`HTTP ${res.statusCode}: ${detail}`));
            return;
          }
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve(data);
          }
        });
      });

      req.on("error", (err: Error) => reject(err));
      req.on("timeout", () => {
        req.destroy();
        reject(new Error(`HTTP request timed out after ${this.timeout / 1000}s`));
      });

      if (payload) req.write(payload);
      req.end();
    });
  }

  // ---------------------------------------------------------------------------
  // Subprocess transport (local CLI)
  // ---------------------------------------------------------------------------

  private detectReinPath(): string {
    try {
      execSync("which rein", { stdio: "pipe" });
      return "rein";
    } catch {
      return "python -m rein";
    }
  }

  private buildCommand(args: string[]): { cmd: string; cmdArgs: string[] } {
    if (this.reinPath === "rein") {
      return { cmd: "rein", cmdArgs: args };
    }
    const parts = this.reinPath.split(" ");
    return { cmd: parts[0], cmdArgs: [...parts.slice(1), ...args] };
  }

  private runSubprocess(args: string[]): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    return new Promise((resolve, reject) => {
      const { cmd, cmdArgs } = this.buildCommand(args);
      const proc = spawn(cmd, cmdArgs, {
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (data: Buffer) => { stdout += data.toString(); });
      proc.stderr.on("data", (data: Buffer) => { stderr += data.toString(); });

      const timer = setTimeout(() => {
        proc.kill("SIGTERM");
        reject(new Error(`Rein process timed out after ${this.timeout / 1000} seconds`));
      }, this.timeout);

      proc.on("close", (code: number | null) => {
        clearTimeout(timer);
        resolve({ stdout, stderr, exitCode: code ?? 1 });
      });

      proc.on("error", (err: Error) => {
        clearTimeout(timer);
        reject(new Error(`Failed to spawn rein: ${err.message}`));
      });
    });
  }

  private getAgentsDir(): string {
    return this.agentsDir || process.env.REIN_AGENTS_DIR || "";
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  async listFlows(): Promise<{ flows: FlowInfo[]; agents_dir: string }> {
    if (this.useHttp) {
      return (await this.httpRequest("GET", "/api/flows")) as { flows: FlowInfo[]; agents_dir: string };
    }

    // --- subprocess fallback ---
    const agents = this.getAgentsDir();
    const flowsDir = path.join(agents, "flows");

    if (!fs.existsSync(flowsDir)) {
      return { flows: [], agents_dir: agents };
    }

    const flows: FlowInfo[] = [];
    for (const name of fs.readdirSync(flowsDir).sort()) {
      const flowYaml = path.join(flowsDir, name, `${name}.yaml`);
      if (!fs.existsSync(flowYaml)) continue;
      try {
        const content = fs.readFileSync(flowYaml, "utf-8");
        const cfg = yamlParse(content) as Record<string, unknown> | null;
        if (!cfg) continue;

        const inputsRaw = (cfg.inputs as Record<string, unknown>) || {};
        const inputs: Record<string, { required: boolean; description: string; default?: unknown }> = {};
        if (inputsRaw && typeof inputsRaw === "object") {
          for (const [k, v] of Object.entries(inputsRaw)) {
            if (v && typeof v === "object") {
              const spec = v as Record<string, unknown>;
              inputs[k] = { required: spec.required !== false, description: (spec.description as string) || "" };
              if ("default" in spec) inputs[k].default = spec.default;
            } else {
              inputs[k] = { required: true, description: "" };
            }
          }
        }

        const entry: FlowInfo = {
          name,
          description: (cfg.description as string) || "",
          blocks: Array.isArray(cfg.blocks) ? cfg.blocks.length : 0,
          team: (cfg.team as string) || "",
          provider: (cfg.provider as string) || "",
        };
        if (Object.keys(inputs).length > 0) entry.inputs = inputs;
        flows.push(entry);
      } catch (e) {
        flows.push({ name, description: "", blocks: 0, team: "", provider: "", error: String(e) });
      }
    }
    return { flows, agents_dir: agents };
  }

  async runWorkflow(
    flowName: string,
    input?: Record<string, unknown>
  ): Promise<WorkflowResult> {
    if (this.useHttp) {
      return (await this.httpRequest("POST", "/api/run", {
        flow: flowName,
        input,
        timeout: this.timeout / 1000,
      })) as WorkflowResult;
    }

    // --- subprocess fallback ---
    const agents = this.getAgentsDir();
    const workflowPath = path.join(agents, "flows", flowName, `${flowName}.yaml`);

    if (!fs.existsSync(workflowPath)) {
      return { status: "failed", exit_code: 1, outputs: {}, error: `Workflow not found: ${flowName}` };
    }

    const args = [workflowPath, "--agents-dir", agents, "--no-ui"];
    if (input) args.push("--input", JSON.stringify(input));

    try {
      const { stdout, stderr, exitCode } = await this.runSubprocess(args);

      let runDir = "";
      for (const line of stdout.split("\n")) {
        if (line.includes("[DIR] Run Directory:")) {
          runDir = line.split(":").slice(1).join(":").trim();
          break;
        }
      }

      const outputs: Record<string, unknown> = {};
      if (runDir && fs.existsSync(runDir)) {
        for (const blockName of fs.readdirSync(runDir)) {
          const outputDir = path.join(runDir, blockName, "outputs");
          if (!fs.existsSync(outputDir) || !fs.statSync(outputDir).isDirectory()) continue;
          for (const fname of fs.readdirSync(outputDir)) {
            try {
              let content: unknown = fs.readFileSync(path.join(outputDir, fname), "utf-8");
              if (fname.endsWith(".json")) { try { content = JSON.parse(content as string); } catch {} }
              outputs[`${blockName}/${fname}`] = content;
            } catch {}
          }
        }
      }

      const result: WorkflowResult = { status: exitCode === 0 ? "completed" : "failed", exit_code: exitCode, outputs };
      if (exitCode !== 0 && stderr) result.stderr = stderr.slice(-2000);
      return result;
    } catch (e) {
      return { status: "failed", exit_code: 1, outputs: {}, error: String(e) };
    }
  }

  async createTask(
    flow: string,
    question: string,
    input?: Record<string, unknown>
  ): Promise<TaskCreated> {
    if (this.useHttp) {
      return (await this.httpRequest("POST", "/api/tasks", {
        flow, question, input,
      })) as TaskCreated;
    }

    // --- subprocess fallback ---
    const agents = this.getAgentsDir();
    const flowDir = path.join(agents, "flows", flow);
    if (!fs.existsSync(flowDir)) {
      return { task_id: "", flow, status: "pending", task_dir: "", error: `Flow not found: ${flow}` };
    }

    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const taskId = `task-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const taskDir = path.join(agents, "tasks", taskId);

    fs.mkdirSync(path.join(taskDir, "input"), { recursive: true });
    fs.mkdirSync(path.join(taskDir, "output"), { recursive: true });
    fs.mkdirSync(path.join(taskDir, "state"), { recursive: true });

    fs.writeFileSync(path.join(taskDir, "task.yaml"), yamlStringify({
      id: taskId, flow, output_dir: "./output", created_at: now.toISOString(),
    }));
    fs.writeFileSync(path.join(taskDir, "input", "question.txt"), question);
    if (input) {
      fs.writeFileSync(path.join(taskDir, "task.input.json"), JSON.stringify(input, null, 2));
    }
    fs.writeFileSync(path.join(taskDir, "state", "status"), "pending");

    return { task_id: taskId, flow, status: "pending", task_dir: taskDir };
  }

  async taskStatus(taskId: string): Promise<TaskStatus> {
    if (this.useHttp) {
      return (await this.httpRequest("GET", `/api/tasks/${taskId}`)) as TaskStatus;
    }

    // --- subprocess fallback ---
    const agents = this.getAgentsDir();
    const taskDir = path.join(agents, "tasks", taskId);

    if (!fs.existsSync(taskDir)) {
      return { task_id: taskId, status: "unknown", error: `Task not found: ${taskId}` };
    }

    const result: TaskStatus = { task_id: taskId, status: "unknown" };

    const taskYamlPath = path.join(taskDir, "task.yaml");
    if (fs.existsSync(taskYamlPath)) {
      result.config = yamlParse(fs.readFileSync(taskYamlPath, "utf-8")) as Record<string, unknown>;
    }

    const dbPath = path.join(taskDir, "state", "rein.db");
    if (fs.existsSync(dbPath)) {
      try {
        const raw = execSync(
          `sqlite3 -json "${dbPath}" "SELECT name, status, phase, progress FROM processes"`,
          { encoding: "utf-8", timeout: 5000 }
        );
        const blocks = JSON.parse(raw) as Array<{ name: string; status: string; phase: number; progress: number }>;
        const total = blocks.length;
        const done = blocks.filter((b) => b.status === "done").length;
        const failed = blocks.filter((b) => b.status === "failed").length;
        const running = blocks.filter((b) => b.status === "running").length;

        if (total === 0) result.status = "pending";
        else if (failed > 0) result.status = "failed";
        else if (done === total) result.status = "completed";
        else if (running > 0 || done > 0) result.status = "running";
        else result.status = "pending";

        result.blocks = blocks;
        result.total = total;
        result.done = done;
        result.failed = failed;
        result.running = running;
      } catch {}
    }

    if (result.status === "unknown") {
      const statusPath = path.join(taskDir, "state", "status");
      if (fs.existsSync(statusPath)) {
        result.status = fs.readFileSync(statusPath, "utf-8").trim();
      }
    }

    const outputDir = path.join(taskDir, "output");
    if (fs.existsSync(outputDir) && fs.statSync(outputDir).isDirectory()) {
      const outputs: Array<{ file: string; size: number }> = [];
      for (const fname of fs.readdirSync(outputDir).sort()) {
        const fpath = path.join(outputDir, fname);
        if (fs.statSync(fpath).isFile()) {
          outputs.push({ file: fname, size: fs.statSync(fpath).size });
        }
      }
      if (outputs.length > 0) result.outputs = outputs;
    }

    return result;
  }
}
