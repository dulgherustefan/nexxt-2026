import { Scales, ShieldCheck, Tray } from "@phosphor-icons/react";
import { useMemo, useState, type ReactNode } from "react";
import { plural } from "../../api/format";
import { useApi, useResource } from "../../api/runtime";
import type { McpInfo, McpTool } from "../../api/types";
import { cx, EmptyState, ErrorNote, PageHeader, Panel, SectionBoundary, Skeleton, Status, Tabs, type Tone } from "../../ui/kit";
import { CodeBlock, withoutT1 } from "./trustUi";

type App = "desktop" | "cursor" | "http";

const isRecord = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === "object" && !Array.isArray(v);

/** The wall between the zones is no longer part of the console, so its status tool isn't listed. */
const HIDDEN_TOOLS = new Set(["versoml_wall_status"]);

/** Only the client zone's server is part of the product. "both" tools run there too. */
function inClientServer(t: McpTool): boolean {
  return String(t.zone ?? "").toLowerCase() !== "aml" && !HIDDEN_TOOLS.has(t.name);
}

/** Plainer wording where the backend description uses terms the console no longer uses. */
const TOOL_TEXT: Record<string, string> = {
  versoml_t1_deadline: "The refund deadline (end of the next business day) and the reply deadline, on the Romanian calendar",
  versoml_check_letter: "A check on a letter’s text before it goes to the customer: banned terms and personal data",
};

const EFFECT: Record<string, { word: string; tone: Tone }> = {
  read: { word: "Read only", tone: "neutral" },
  "public read": { word: "Reads public data", tone: "neutral" },
  compute: { word: "Computes", tone: "neutral" },
  "creates a case": { word: "Opens a case", tone: "dark" },
  "human action": { word: "Needs a person", tone: "now" },
};

function effectOf(effect: string | undefined): { word: string; tone: Tone } {
  const key = String(effect ?? "").trim().toLowerCase();
  if (EFFECT[key]) return EFFECT[key];
  return { word: key ? key.charAt(0).toUpperCase() + key.slice(1) : "Not stated", tone: "neutral" };
}

/** The copied config connects the client zone only: AML servers are dropped from `mcpServers`. */
function withoutAml(snippet: string | undefined): string | undefined {
  if (!snippet) return snippet;
  try {
    const cfg: unknown = JSON.parse(snippet);
    if (isRecord(cfg) && isRecord(cfg.mcpServers)) {
      const servers = Object.entries(cfg.mcpServers).filter(([name, server]) => {
        const args = isRecord(server) && Array.isArray(server.args) ? server.args.map(String).join(" ") : "";
        return !/aml/i.test(name) && !/--zone\s+aml\b/.test(args);
      });
      return JSON.stringify({ ...cfg, mcpServers: Object.fromEntries(servers) }, null, 2);
    }
  } catch {
    /* not JSON: show it as the server sent it */
  }
  return snippet;
}

/** Commands in this project run through uv, like `uv run versoml eval`. */
const withUv = (cmd: string) => (/^versoml\s/.test(cmd.trim()) ? `uv run ${cmd.trim()}` : cmd);

const BENEFITS = [
  {
    icon: Tray,
    title: "Cases from chat",
    text: "Open a case, read its decision and rule IDs, or look at the evidence without switching to the console.",
  },
  {
    icon: Scales,
    title: "Same answers as the console",
    text: "Case tools talk to the VersoML server that’s running, so MCP and the console see the same cases and decisions.",
  },
  {
    icon: ShieldCheck,
    title: "Checked on every call",
    text: "Each call goes through the access policy before it runs. An assistant can only propose approve or reject; a person signs in the console.",
  },
];

export default function McpPage() {
  const api = useApi();
  const res = useResource(() => api.mcp(), [api]);
  const tools = useMemo(() => (Array.isArray(res.data?.tools) ? res.data.tools.filter(inClientServer) : []), [res.data]);
  return (
    <>
      <PageHeader
        title="MCP server"
        description="Use VersoML from Claude Desktop, Cursor or any MCP client, with the same cases and rules as this console."
      />

      <section aria-label="What MCP gives your team">
        <ul className="grid gap-x-8 gap-y-5 border-y border-line py-6 sm:grid-cols-3">
          {BENEFITS.map((b) => (
            <li key={b.title} className="flex gap-3">
              <b.icon aria-hidden size={18} className="mt-0.5 shrink-0 text-subtle" />
              <div>
                <p className="font-medium">{b.title}</p>
                <p className="mt-1 text-[0.9333rem] leading-relaxed text-muted">{b.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="mt-8">
        {res.error && !res.data ? (
          <ErrorNote error={res.error} what="the MCP setup" onRetry={res.reload} />
        ) : !res.data ? (
          <div className="flex flex-col gap-6" aria-busy="true">
            <Skeleton className="h-72 rounded-xl" />
            <Skeleton className="h-96 rounded-xl" />
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <SectionBoundary label="Setup">
              <Setup info={res.data} />
            </SectionBoundary>
            <SectionBoundary label="Tools">
              <Tools tools={tools} />
            </SectionBoundary>
          </div>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------- setup

function NotSent({ what }: { what: string }) {
  return <EmptyState title={`The server didn’t send ${what}`}>Use another tab, or ask whoever runs the server for the details.</EmptyState>;
}

function Snippet({ intro, label, code }: { intro: ReactNode; label: string; code: string }) {
  return (
    <div>
      <p className="mb-3 max-w-[68ch] text-[0.9333rem] text-muted">{intro}</p>
      <CodeBlock label={label} code={code} />
    </div>
  );
}

function Setup({ info }: { info: McpInfo }) {
  const s: McpInfo["snippets"] = isRecord(info.snippets) ? info.snippets : {};
  const desktop = withoutAml(s.claude_desktop ?? s.cursor);
  const cursor = withoutAml(s.cursor ?? s.claude_desktop);
  const [tab, setTab] = useState<App>("desktop");
  const tabs: Array<{ id: App; label: string }> = [
    { id: "desktop", label: "Claude Desktop" },
    { id: "cursor", label: "Cursor" },
    { id: "http", label: "HTTP" },
  ];

  let body: ReactNode;
  if (tab === "desktop") {
    body = desktop ? (
      <Snippet
        label="claude_desktop_config.json"
        code={desktop}
        intro={<>In Claude Desktop, open Settings, then Developer, then Edit Config. Add this to the file and restart the app.</>}
      />
    ) : <NotSent what="a Claude Desktop config" />;
  } else if (tab === "cursor") {
    body = cursor ? (
      <Snippet
        label="mcp.json"
        code={cursor}
        intro={<>Add this to <span className="font-mono text-[0.8667rem]">~/.cursor/mcp.json</span>, or to <span className="font-mono text-[0.8667rem]">.cursor/mcp.json</span> in a project, then restart Cursor.</>}
      />
    ) : <NotSent what="a Cursor config" />;
  } else {
    body = (
      <div className="flex flex-col gap-5">
        {info.public_http_url && (
          <Snippet
            label="Public URL"
            code={info.public_http_url}
            intro={<>From any computer: in Claude, open Settings, then Connectors, and add it as a custom connector; in Cursor, put it as <span className="font-mono text-[0.8667rem]">url</span> in mcp.json. Each person gets a few cases and questions every 10 minutes, so the demo stays up for everyone.</>}
          />
        )}
        {info.http_url ? (
          <Snippet label="URL on this computer" code={info.http_url} intro="For MCP clients on the computer that runs VersoML." />
        ) : (
          <NotSent what="an HTTP address" />
        )}
        {s.http && <Snippet label="Terminal" code={withUv(s.http)} intro="To run a separate HTTP server instead, start it in the project folder:" />}
      </div>
    );
  }

  const active = tabs.find((t) => t.id === tab)?.label ?? "";
  return (
    <Panel title="Set it up" description="Copy the config for the app your team uses.">
      <Tabs<App> label="App to connect" value={tab} onChange={setTab} tabs={tabs} />
      <div key={tab} role="tabpanel" aria-label={active} className="mt-4">
        {body}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- tools

const TOOL_GRID = "md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_9.5rem]";

function Tools({ tools }: { tools: McpTool[] }) {
  return (
    <section aria-labelledby="mcp-tools" className="overflow-clip rounded-xl bg-paper shadow-[var(--shadow-card)]">
      <header className="px-5 pt-4 pb-3">
        <h2 id="mcp-tools" className="text-[0.9333rem] font-semibold">Tools</h2>
        <p className="mt-0.5 text-[0.8667rem] text-muted">{plural(tools.length, "tool", "tools")} on this server</p>
      </header>
      {tools.length === 0 ? (
        <div className="px-5 pb-5">
          <EmptyState title="No tools listed">The server didn’t report any tools for disputes.</EmptyState>
        </div>
      ) : (
        <>
          <div aria-hidden className={cx("hidden gap-x-6 border-t border-line px-5 py-2 text-[0.8rem] text-subtle md:grid", TOOL_GRID)}>
            <span>Tool</span>
            <span>What it does</span>
            <span>Effect</span>
          </div>
          <ul className="divide-y divide-line border-t border-line">
            {tools.map((t) => {
              const effect = effectOf(t.effect);
              return (
                <li key={`${t.name}-${t.zone}`} className={cx("grid gap-x-6 gap-y-1 px-5 py-3 md:items-center", TOOL_GRID)}>
                  <code className="min-w-0 truncate font-mono text-[0.8rem] text-ink" title={t.name}>{t.name}</code>
                  <p className="text-[0.9333rem] text-ink-soft">{TOOL_TEXT[t.name] ?? withoutT1(t.description || "No description")}</p>
                  <span>
                    <Status tone={effect.tone}>{effect.word}</Status>
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
