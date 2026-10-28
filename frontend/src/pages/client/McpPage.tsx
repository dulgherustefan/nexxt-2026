import { useMemo, useState } from "react";
import { useApi, useResource } from "../../api/runtime";
import type { McpInfo, McpTool } from "../../api/types";
import { cx, EmptyState, ErrorNote, PageHeader, Panel, SectionBoundary, Skeleton, Tabs } from "../../ui/kit";
import { CodeBlock, ro, TABLE } from "./trustUi";

type Snip = "desktop" | "cursor" | "http";
type Server = "client" | "aml" | "all";

function zoneOf(t: McpTool): "client" | "aml" | "both" {
  const z = String(t.zone ?? "").toLowerCase();
  if (z === "aml") return "aml";
  if (z === "client") return "client";
  return "both";
}

const ZONE_WORD = { client: "Zona client", aml: "Zona AML", both: "Ambele zone" } as const;

export default function McpPage() {
  const api = useApi();
  const res = useResource(() => api.mcp(), [api]);
  return (
    <>
      <PageHeader
        title="Conectează VersoML la un asistent"
        description="Serverul MCP expune VersoML ca tool-uri pe care un asistent precum Claude le poate apela: deschide un caz, citește decizia cu ID-ul regulii, verifică un dosar. Fiecare zonă are serverul ei, deci tool-urile AML nu apar niciodată în serverul zonei client."
      />
      {res.error && !res.data ? (
        <ErrorNote error={res.error} what="configurarea MCP" onRetry={res.reload} />
      ) : !res.data ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-48" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <SectionBoundary label="Configurare">
            <Snippets info={res.data} />
          </SectionBoundary>
          <SectionBoundary label="Tool-uri">
            <Tools tools={Array.isArray(res.data.tools) ? res.data.tools : []} />
          </SectionBoundary>
        </div>
      )}
    </>
  );
}

function Snippets({ info }: { info: McpInfo }) {
  const s = info.snippets ?? {};
  const desktop = s.claude_desktop;
  const cursor = s.cursor;
  const cursorDiffers = Boolean(cursor && cursor.trim() !== (desktop ?? "").trim());
  const tabs: Array<{ id: Snip; label: string }> = [
    { id: "desktop", label: cursorDiffers ? "Claude Desktop" : "Claude Desktop / Cursor" },
    ...(cursorDiffers ? [{ id: "cursor" as const, label: "Cursor" }] : []),
    { id: "http", label: "HTTP" },
  ];
  const [tab, setTab] = useState<Snip>("desktop");

  const missing = <EmptyState title="Serverul nu a trimis această configurare.">Folosește altă variantă sau URL-ul HTTP.</EmptyState>;
  let body;
  if (tab === "desktop" || tab === "cursor") {
    const code = tab === "cursor" ? cursor : desktop ?? cursor;
    body = code ? (
      <>
        <p className="mb-3 text-[0.9333rem] text-muted">
          {tab === "cursor"
            ? "Pune blocul în configurarea MCP din Cursor, apoi repornește editorul."
            : "Pune blocul în fișierul de configurare MCP al aplicației (claude_desktop_config.json sau mcp.json la Cursor), apoi repornește aplicația."}
        </p>
        <CodeBlock label="JSON" code={code} />
      </>
    ) : missing;
  } else {
    body = (
      <div className="flex flex-col gap-3">
        {info.http_url ? (
          <>
            <p className="text-[0.9333rem] text-muted">Pentru clienții MCP care se conectează prin HTTP, la serverul zonei client care rulează acum.</p>
            <CodeBlock label="URL" code={info.http_url} />
          </>
        ) : (
          missing
        )}
        {s.http && (
          <>
            <p className="text-[0.9333rem] text-muted">Sau pornește un server HTTP separat:</p>
            <CodeBlock label="Terminal" code={s.http} />
          </>
        )}
      </div>
    );
  }

  return (
    <Panel title="Configurare">
      <Tabs<Snip> label="Alege aplicația" value={tab} onChange={setTab} tabs={tabs} />
      <div className="mt-4">{body}</div>
    </Panel>
  );
}

function Tools({ tools }: { tools: McpTool[] }) {
  const [server, setServer] = useState<Server>("client");
  const counts = useMemo(
    () => ({
      client: tools.filter((t) => zoneOf(t) !== "aml").length,
      aml: tools.filter((t) => zoneOf(t) !== "client").length,
      all: tools.length,
    }),
    [tools],
  );
  const visible = tools.filter((t) => (server === "all" ? true : server === "client" ? zoneOf(t) !== "aml" : zoneOf(t) !== "client"));
  const amlInClient = tools.filter((t) => zoneOf(t) === "aml").length;

  return (
    <Panel title="Tool-uri" bodyClassName="p-0">
      <div className="px-4 pt-3">
        <Tabs<Server>
          label="Alege serverul"
          value={server}
          onChange={setServer}
          tabs={[
            { id: "client", label: "Serverul zonei client", count: counts.client },
            { id: "aml", label: "Serverul zonei AML", count: counts.aml },
            { id: "all", label: "Toate", count: counts.all },
          ]}
        />
        <p className="py-3 text-[0.9333rem] text-muted">
          {server === "client"
            ? `${ro(counts.client, "tool", "tool-uri")} în serverul zonei client; ${ro(amlInClient, "tool AML rămâne", "tool-uri AML rămân")} doar în serverul AML.`
            : server === "aml"
              ? "Serverul AML rulează în procesul zonei AML; nimic din el nu ajunge la client."
              : "Toate tool-urile, cu zona în care rulează."}
        </p>
      </div>
      {tools.length === 0 ? (
        <div className="px-4 pb-4"><EmptyState title="Serverul nu a raportat niciun tool." /></div>
      ) : visible.length === 0 ? (
        <div className="px-4 pb-4"><EmptyState title="Niciun tool în acest server." /></div>
      ) : (
        <div className="overflow-x-auto border-t border-line">
          <table className={cx(TABLE.table, "min-w-[46rem]")}>
            <thead>
              <tr className={TABLE.headRow}>
                <th scope="col" className={TABLE.th}>Tool</th>
                <th scope="col" className={TABLE.th}>Zonă</th>
                <th scope="col" className={TABLE.th}>Ce face</th>
                <th scope="col" className={TABLE.th}>Efect</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => {
                const z = zoneOf(t);
                return (
                  <tr key={`${t.name}-${t.zone}`} className={TABLE.row}>
                    <td className={cx(TABLE.td, "whitespace-nowrap")}><code className="font-mono text-[0.8667rem]">{t.name}</code></td>
                    <td className={cx(TABLE.td, "whitespace-nowrap")}>
                      <span className={cx("inline-flex items-center gap-1.5", z === "aml" && "font-semibold")}>
                        <span aria-hidden className={cx("inline-block size-2 rounded-full", z === "aml" ? "bg-ink" : z === "client" ? "border border-ink bg-paper" : "bg-line-strong")} />
                        {ZONE_WORD[z]}
                      </span>
                    </td>
                    <td className={TABLE.td}>{t.description || "—"}</td>
                    <td className={cx(TABLE.td, "whitespace-nowrap text-ink-soft")}>{t.effect || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
