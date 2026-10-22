/**
 * Confirming through the hub's MCP server (`/mcp`, Streamable HTTP).
 *
 * The device signs every MCP request with its key, exactly like `/device/*`.
 * If MCP cannot be reached the same confirm goes to `POST /device/confirm`,
 * and the "Under the hood" panel says so.
 */

import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import type { HubApi } from "./api";
import { hubUrl } from "./config";
import type { ConfirmResult, Receipt } from "./types";

export type McpStatus = "connecting" | "connected" | "failed";

export interface ConfirmOutcome {
  result: ConfirmResult;
  via: "mcp" | "rest";
  /** Why MCP was not used, when it was not. */
  fallbackReason?: string;
}

/** What the UI needs to confirm. Tests pass a fake. */
export interface ConfirmChannel {
  status: McpStatus;
  protocol: string | null;
  connect(): Promise<void>;
  receiptsList(): Promise<Receipt[]>;
  confirm(pending_id: string, evidence_ref: string): Promise<ConfirmOutcome>;
}

/** What an MCP Apps host needs: the raw tool result, the tool's UI resource, and the resource's HTML. */
export interface McpHost {
  callToolRaw(name: string, args: Record<string, unknown>): Promise<ToolResultLike & { _meta?: unknown }>;
  toolUi(name: string): Promise<string | null>;
  readUi(uri: string): Promise<string>;
}

export function isMcpHost(x: unknown): x is McpHost {
  return !!x && typeof (x as McpHost).callToolRaw === "function" && typeof (x as McpHost).readUi === "function";
}

export interface ToolResultLike {
  content?: Array<{ type: string; text?: string }>;
  structuredContent?: unknown;
  isError?: boolean;
}

/** content[0].text is the tool's JSON. */
export function parseToolJson<T>(result: ToolResultLike): T {
  const first = result.content?.find((c) => c.type === "text" && typeof c.text === "string");
  if (first?.text) {
    try {
      return JSON.parse(first.text) as T;
    } catch {
      if (result.isError) throw new Error(first.text);
    }
  }
  const sc = result.structuredContent as { result?: unknown } | undefined;
  if (sc && typeof sc === "object") return ("result" in sc ? sc.result : sc) as T;
  throw new Error("the tool returned no JSON");
}

export class McpGate implements ConfirmChannel, McpHost {
  status: McpStatus = "connecting";
  protocol: string | null = null;
  private client: Client | null = null;
  private connecting: Promise<void> | null = null;

  constructor(private readonly hub: HubApi) {}

  connect(): Promise<void> {
    if (this.client) return Promise.resolve();
    if (!this.connecting) {
      this.connecting = this.open().finally(() => {
        this.connecting = null;
      });
    }
    return this.connecting;
  }

  private async open(): Promise<void> {
    this.status = "connecting";
    // the SDK is loaded after first paint, in its own chunk
    const [{ Client: McpClient }, { StreamableHTTPClientTransport }] = await Promise.all([
      import("@modelcontextprotocol/sdk/client/index.js"),
      import("@modelcontextprotocol/sdk/client/streamableHttp.js"),
    ]).catch((err: unknown) => {
      this.status = "failed";
      throw err;
    });
    const transport = new StreamableHTTPClientTransport(hubUrl("/mcp", this.hub.base), {
      fetch: this.hub.signingFetch,
    });
    const client = new McpClient({ name: "suresay-web", version: "0.1.0" });
    try {
      await client.connect(transport);
    } catch (err) {
      this.status = "failed";
      await client.close().catch(() => undefined);
      throw err;
    }
    this.client = client;
    this.protocol = transport.protocolVersion ?? null;
    this.status = "connected";
  }

  private async call<T>(name: string, args: Record<string, unknown>): Promise<T> {
    await this.connect();
    if (!this.client) throw new Error("MCP is not connected");
    const result = (await this.client.callTool({ name, arguments: args })) as ToolResultLike;
    return parseToolJson<T>(result);
  }

  /** The raw tool result (content, structuredContent, _meta), as an MCP host such as Alexa+ receives it. */
  async callToolRaw(name: string, args: Record<string, unknown>): Promise<ToolResultLike & { _meta?: unknown }> {
    await this.connect();
    if (!this.client) throw new Error("MCP is not connected");
    return (await this.client.callTool({ name, arguments: args })) as ToolResultLike & { _meta?: unknown };
  }

  /** The UI resource a tool declares (`_meta.ui.resourceUri`), for an MCP Apps host. */
  async toolUi(name: string): Promise<string | null> {
    await this.connect();
    if (!this.client) throw new Error("MCP is not connected");
    const { tools } = await this.client.listTools();
    const meta = tools.find((t) => t.name === name)?._meta as { ui?: { resourceUri?: unknown } } | undefined;
    return typeof meta?.ui?.resourceUri === "string" ? meta.ui.resourceUri : null;
  }

  /** The HTML of a `ui://` resource. */
  async readUi(uri: string): Promise<string> {
    await this.connect();
    if (!this.client) throw new Error("MCP is not connected");
    const { contents } = await this.client.readResource({ uri });
    const first = contents[0] as { text?: unknown } | undefined;
    if (typeof first?.text !== "string") throw new Error(`${uri} has no HTML`);
    return first.text;
  }

  async receiptsList(): Promise<Receipt[]> {
    const out = await this.call<{ receipts?: Receipt[] }>("receipts_list", {});
    return out.receipts ?? [];
  }

  async confirm(pending_id: string, evidence_ref: string): Promise<ConfirmOutcome> {
    let reason = "";
    try {
      const result = await this.call<ConfirmResult>("confirm", { pending_id, evidence_ref });
      if (result && typeof result.status === "string") return { result, via: "mcp" };
      reason = "MCP gave an unexpected reply";
    } catch (err) {
      reason = err instanceof Error ? err.message : String(err);
      this.status = "failed";
      this.client = null;
    }
    const result = await this.hub.confirmRest(pending_id, evidence_ref);
    return { result, via: "rest", fallbackReason: reason };
  }
}
