# Agent protocols, the MCP ecosystem, and security/privacy controls for LLM agents in regulated settings (state of the art, 2025 to Oct 2026)

Context: design input for a two-zone multi-agent system for a Romanian bank (NEXXT Summit 2026, Raiffeisen track). Zone 1 is the "Judge" (customer payment-fraud dispute). Zone 2 is the "Investigator" (AML lead on the beneficiary account). The two zones are separated by a Chinese wall (anti tipping-off), data carries a CaMeL-style "data passport", and every claim has an evidence trail. Research date: 28 Oct 2026. Items marked **[UNVERIFIED]** come from background knowledge or secondary sources and were not confirmed against a primary source in this session.

---

## Q1. MCP: current spec version, changes since mid-2025, security issues and mitigations, and relevant servers

### Takeaway
The current MCP specification is **2026-07-28**, released 28 July 2026. It is a breaking redesign: MCP is now stateless (no `initialize` handshake, no `Mcp-Session-Id`), server-initiated requests are replaced by Multi Round-Trip Requests (MRTR), Tasks and MCP Apps are official extensions, Roots, Sampling, Logging and Dynamic Client Registration are deprecated, and OAuth is hardened (RFC 9207 `iss`, issuer-bound credentials, CIMD). The official security best-practices page covers OAuth and transport attacks (confused deputy, token passthrough, SSRF, state-handle hijacking, local server compromise). It does not cover tool poisoning or rug pulls, so those need separate controls such as tool-description pinning.

### Cited Findings

**Spec versions and timeline**
- The current changelog lists changes "since the previous revision, 2025-11-25" and links to the `2026-07-28` spec pages. The previous revisions are therefore 2025-11-25 and, before that, 2025-06-18 — [MCP changelog](https://modelcontextprotocol.io/specification/latest/changelog)
- The 2026-07-28 spec was officially released on July 28, 2026. All four Tier 1 SDKs (TypeScript, Python, Go, C#) "speak" 2026-07-28 on release day, and the Rust SDK supports it in beta — [MCP blog, 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- A release candidate was public by late May 2026 (secondary source) — [Codex CLI migration guide, 30 May 2026](https://codex.danielvaughan.com/2026/05/30/mcp-2026-07-28-spec-rc-stateless-protocol-codex-cli-migration-guide/)
- Adopters announced support: Anthropic ([Claude blog](https://claude.com/blog/bringing-mcp-2026-07-28-to-claude)), Cloudflare ([Cloudflare blog](https://blog.cloudflare.com/mcp-v2/)) and Stacklok ([enterprise readiness guide](https://stacklok.com/resources/enterprise-readiness-guide-for-the-july-2026-mcp-spec-update/)). The Agentic AI Foundation publishes MCP migration guidance — [AAIF blog](https://aaif.io/blog/mcp-2026-07-28-whats-changing-and-how-to-migrate)
- Secondary sources say that adding 2026-07-28 to a gateway that also advertises 2025-11-25 does not change behaviour for clients requesting the older version (search summary, not verified on the official page) — [MCP blog tag page](https://blog.modelcontextprotocol.io/tags/mcp/)

**Major changes in 2026-07-28 (vs 2025-11-25)** — all from the [MCP changelog](https://modelcontextprotocol.io/specification/latest/changelog):
- **Stateless protocol.** The `initialize`/`notifications/initialized` handshake is removed. Each request carries `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` in `_meta`, and clients SHOULD send `clientInfo` (SEP-2575). Protocol-level sessions and the `Mcp-Session-Id` header are removed. Servers needing cross-call state mint explicit handles passed as ordinary tool arguments (SEP-2567).
- **New `server/discover` RPC.** Servers MUST implement it to advertise versions, capabilities and identity (SEP-2575).
- **`subscriptions/listen`** replaces the HTTP GET stream and `resources/subscribe` (SEP-2575). `ping`, `logging/setLevel` and `notifications/roots/list_changed` are removed, and log level is now set per request.
- **Tasks moved to an official extension, `io.modelcontextprotocol/tasks`.** Results are polled with `tasks/get`, a new `tasks/update` carries client-to-server input, `tasks/list` is removed, and servers may return task handles unsolicited (SEP-2663).
- **Multi Round-Trip Requests (MRTR)** replace server-initiated `roots/list`, `sampling/createMessage` and `elicitation/create`. The server returns `InputRequiredResult` (`resultType: "input_required"`) with `inputRequests`, and the client retries the original request with `inputResponses`. Every result now carries a required `resultType` (SEP-2322).
- **URL-mode elicitation simplified.** The `notifications/elicitation/complete` notification and `elicitationId`, both introduced in 2025-11-25, are removed. Correlation now goes in `requestState`.
- **SSE resumability removed** (`Last-Event-ID`). A broken stream loses the in-flight request, which must be re-issued.
- **Minor changes:**
  - An `extensions` field in client and server capabilities.
  - OpenTelemetry trace-context propagation (`traceparent`, `tracestate`, `baggage`) in `_meta` (SEP-414).
  - A SHOULD for deterministic `tools/list` order.
  - Required `Mcp-Method` and `Mcp-Name` HTTP headers, plus `x-mcp-header` for custom headers taken from tool parameters (SEP-2243).
  - `ttlMs` and `cacheScope` on list and read results (SEP-2549).
  - `inputSchema`/`outputSchema` may use any JSON Schema 2020-12 keyword, and `structuredContent` may be any JSON value (SEP-2106).
- **Authorization hardening:**
  - Authorization servers SHOULD send `iss` (RFC 9207), and clients MUST validate it (SEP-2468).
  - Clients MUST send `application_type` in DCR (SEP-837).
  - Client credentials are bound to their issuer and MUST NOT be reused with another authorization server (SEP-2352).
- **Deprecated:**
  - Roots, Sampling and Logging (SEP-2577). Suggested migrations: pass paths as tool parameters, call LLM provider APIs directly, and use stderr or OpenTelemetry for logs.
  - The HTTP+SSE transport.
  - `includeContext` values `thisServer` and `allServers`.
  - OAuth Dynamic Client Registration (RFC 7591), in favour of Client ID Metadata Documents (PR #2858).
  - A formal feature lifecycle with a minimum 12-month deprecation window (SEP-2596).
- The official blog names **Tasks, MCP Apps and Enterprise Managed Authorization (EMA)** as extensions joining the new extensions framework, but gives no detail on EMA. The post does not mention the Registry — [MCP blog, 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- Secondary sources put DCR removal "after summer 2027" — [search summary of multiple sources incl. Stacklok guide](https://stacklok.com/resources/enterprise-readiness-guide-for-the-july-2026-mcp-spec-update/) **[UNVERIFIED date]**

**MCP Apps (interactive UI extension)**
- SEP-1865 "MCP Apps: Interactive User Interfaces for MCP" has **Final** status. It introduces UI resources predeclared with the `ui://` URI scheme, and tools reference them through metadata — [SEP-1865](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp)
- It was announced on 21 Nov 2025 — [MCP blog, MCP Apps](https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/)
- UI templates are ordinary resources with a `ui://` URI and MIME type `text/html;profile=mcp-app`, rendered in sandboxed iframes — [mcp_server hexdocs](https://hexdocs.pm/mcp_server/mcp_apps.html); [issoh.co.jp explainer (calls it "Stable" as of 2026-01-26)](https://www.issoh.co.jp/tech/details/16397/)

**MCP Registry**
- The Registry launched in preview on 8 Sep 2025 — [MCP blog, registry preview](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)
- The registry terms say it "is currently in preview" and that breaking changes or data resets may occur before GA. That page is dated 2025-09-02 — [Registry terms of service](https://modelcontextprotocol.io/registry/terms-of-service)
- I found no official GA announcement as of Oct 2026. Third-party guides from April and July 2026 still describe it as preview — [Towards AI, mid-2026](https://pub.towardsai.net/mcp-registries-in-mid-2026-one-upstream-won-2ce541b92036)

**Security: official best practices (latest)** — all from [MCP Security Best Practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices):
- **Confused deputy** (MCP proxy with a static client ID, DCR and a consent cookie):
  - Proxies MUST implement per-client consent before forwarding to the third-party authorization server.
  - Consent UI MUST show the client name, scopes and `redirect_uri`.
  - Exact `redirect_uri` matching is required.
  - `state` MUST be single-use, set only after consent, with a short expiry.
- **Token passthrough:** MCP servers "MUST NOT accept any tokens that were not explicitly issued for the MCP server" (audience validation).
- **SSRF during OAuth discovery:** HTTPS SHOULD be required, private and link-local ranges (incl. 169.254.169.254) SHOULD be blocked, redirect hops SHOULD be validated, and egress proxies such as Stripe Smokescreen SHOULD be used. The same applies to authorization servers fetching CIMD documents.
- **State handle hijacking** (new because MCP is stateless): servers "MUST NOT treat possession of a state handle as authentication". Handles SHOULD be random and bound server-side to the user ID taken from the verified token (`<user_id>:<handle>`).
- **Local MCP server compromise:**
  - One-click install MUST show the full command and get explicit consent.
  - Clients SHOULD sandbox servers and restrict their filesystem and network access.
  - Local servers SHOULD prefer stdio.
- **Other attacks covered:**
  - OAuth URL validation: allow only `http`/`https`, never open URLs through a shell.
  - stdio proxy escalation.
  - Mix-up attacks (RFC 9207).
  - Localhost redirect URI impersonation under CIMD.
  - CIMD trust policies.
  - Scope minimisation: minimal initial scopes plus step-up via `WWW-Authenticate` scope challenges, and no wildcard scopes.
- The page has **no section on tool poisoning, rug pulls or prompt injection**. Its attack catalogue is OAuth/transport focused (observation from the full page text) — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices)

**Security: tool poisoning, rug pulls and real CVEs**
- Invariant Labs' **mcp-scan** scans for Tool Poisoning Attacks and "MCP Rug Pulls", where a server changes a tool description after the user approved it. It has built-in **tool pinning**, which hashes tool descriptions and flags changes. It runs as `uvx mcp-scan@latest` — [Invariant Labs, Introducing mcp-scan](https://invariantlabs.ai/blog/introducing-mcp-scan)
- Per Invariant, sandboxing the server does not mitigate poisoning, because the attack works through the agent following instructions in descriptions — [mcpbundles guide (secondary)](https://www.mcpbundles.com/guides/tool-poisoning-rug-pulls)
- **CVE-2025-6514** in `mcp-remote` (CVSS 9.6, July 2025) — [The Hacker News](https://thehackernews.com/2025/07/critical-mcp-remote-vulnerability.html)
- **CVE-2025-53109 / CVE-2025-53110 ("EscapeRoute")** in the reference Filesystem MCP server: a symlink bypass and a directory-containment bypass. CVSS is reported between 7.3 and 8.4 depending on source; verify on NVD — [Zealynx MCP breach index 2025-2026](https://www.zealynx.io/blogs/mcp-breach-index-2025-2026)
- **CVE-2025-68143/68144/68145** in Anthropic's reference Git MCP server, disclosed January 2026 by Cyata: unrestricted `git_init`, argument injection, and a path-validation bypass, chainable via prompt injection — [Zealynx MCP breach index](https://www.zealynx.io/blogs/mcp-breach-index-2025-2026)

**Relevant MCP servers (fraud/AML/OSINT)**
- **Neo4j (official, `github.com/neo4j/mcp`):**
  - `read-cypher` rejects writes, schema/admin operations and PROFILE queries.
  - `NEO4J_READ_ONLY=true` hides the write tools.
  - It is published as the "Official MCP server for Neo4j" on Docker Hub — [Docker Hub, neo4j MCP](https://hub.docker.com/mcp/server/neo4j/overview); [LobeHub listing](https://lobehub.com/en/mcp/neo4j-mcp)
  - Status was described as "BETA … not yet suitable for production" in an undated community post, which may be stale — [Neo4j community forum](https://community.neo4j.com/t/mcp-server-neo4j-official-or-neo4j-contrib/75545)
  - The licence appears as GPL-3.0 on a Gitee mirror — [Gitee mirror](https://gitee.com/mirrors_neo4j/mcp) **[UNVERIFIED licence]**
- **Neo4j Labs `mcp-neo4j-cypher`:** MIT licence, with no SLAs and no guarantees on backward compatibility — [mcpservers.org, neo4j-contrib](https://mcpservers.org/en/servers/neo4j-contrib/mcp-neo4j); [Neo4j blog, production-proofing the Cypher MCP server](https://neo4j.com/?p=394827)
- **OpenSanctions / yente:**
  - yente is OpenSanctions' open-source screening API. It searches, retrieves and matches FollowTheMoney entities (people, companies, vessels) and has a sanctions-only matching mode — [yente docs](https://www.opensanctions.org/docs/yente); [matching API](https://www.opensanctions.org/docs/api/matching)
  - I found **no official OpenSanctions MCP server**. The community `opensanctions-mcp` (npm, MIT) can target the hosted API or a self-hosted yente via `OPENSANCTIONS_API_URL`. Adoption is small (about 21 weekly downloads) — [Socket.dev, opensanctions-mcp](https://socket.dev/npm/package/opensanctions-mcp)
  - The data licence is **CC BY-NC 4.0**. Banks need a screening licence (flat rate, internal use, covers transaction monitoring) or use the pay-per-query Screening API, which has free credits on sign-up. Data can be integrated and tested before signing a licence — [OpenSanctions licensing](https://www.opensanctions.org/licensing/)

### Inferences
- **Use 2026-07-28 features as trust levers for the jury:**
  - (a) The `Mcp-Method` and `Mcp-Name` headers let a gateway allow or deny calls per zone and per tool without parsing JSON bodies. A Cedar policy keyed on (zone principal, tool name) can sit at that gateway.
  - (b) `_meta.traceparent` (SEP-414) links each tool call to an OpenTelemetry span. That span ID can be stored in the evidence ledger next to the content hash.
  - (c) Deterministic `tools/list` ordering makes a hash of the tool catalogue stable, which makes rug-pull pinning straightforward: compare one hash per server at startup.
  - (d) `outputSchema`/`structuredContent` with full JSON Schema 2020-12 lets the Judge→Investigator referral be a strictly validated object.
  - (e) The MRTR `InputRequiredResult` is the standard way to put a human approval step (elicitation) into a tool call.
- **Give each zone its own MCP servers and OAuth audience.** Token-passthrough MUST NOT means a Judge-issued token is rejected by Investigator servers. The State Handle Hijacking guidance means AML case handles must be bound server-side to the Zone 2 principal, so a Judge presenting an AML case ID fails closed.
- **Build against 2026-07-28 semantics, not deprecated features.** Do not build on Sampling (deprecated). Call the LLM directly from each zone's orchestrator so that each zone controls which model and endpoint sees which data.
- **Reference servers are not hardened.** The Filesystem and Git servers had path-containment CVEs. Run any filesystem/fetch server in a container with read-only mounts and an egress allowlist, and pin versions.
- **Licensing for the demo.** The OpenSanctions data licence is non-commercial. For the demo, use the Screening API's free credits or a self-hosted yente under evaluation terms, and say on a slide that production requires a bank screening licence.

### Gaps
- **[UNVERIFIED] 2025-06-18 and 2025-11-25 content.** Not re-fetched this session. From background knowledge, 2025-06-18 introduced structured tool output (`outputSchema`/`structuredContent`), form elicitation, resource links in tool results, OAuth resource-server classification with RFC 8707 resource indicators, and removed JSON-RPC batching. From background knowledge, 2025-11-25 added experimental Tasks (SEP-1686), URL-mode elicitation, CIMD (SEP-991), tool calling inside sampling, and icons. The 2026-07-28 changelog does confirm that experimental tasks, URL-mode elicitation (`elicitationId`) and the soft-deprecated `includeContext` existed in 2025-11-25.
- **MCP governance.** It is [UNVERIFIED] that MCP was donated to the Linux Foundation's Agentic AI Foundation in Dec 2025. The only support found here is AAIF publishing MCP migration posts.
- **Registry GA.** No GA date found. The registry is still described as preview.
- **Python SDK version numbers** for 2026-07-28 support were not found.
- **Not verified this session.** Playwright MCP (`microsoft/playwright-mcp`; believed Apache-2.0), the official fetch and filesystem servers (`modelcontextprotocol/servers`; licence not checked), and the AWS MCP servers (`awslabs/mcp`; believed Apache-2.0) were not checked for maturity or licence.
- **Neo4j official MCP.** Licence and GA status are unconfirmed.

---

## Q2. A2A (Agent2Agent): status, Agent Cards, security model, adoption, and whether it can enforce a one-way schema-restricted channel

### Takeaway
A2A reached **v1.0.0 on 12 March 2026**, with a v1.0.1 patch on 28 May 2026. It is a Linux Foundation project with more than 150 supporting organisations and integrations in Azure AI Foundry, Copilot Studio and Bedrock AgentCore. Its security model covers authentication: Agent Card `securitySchemes` (API key, HTTP auth, OAuth2, OIDC, mTLS), signed Agent Cards since v0.3.0, and an authenticated extended card. A2A has **no information-flow control and no directional-channel primitive**. A one-way, schema-restricted barrier must be built around it, using a gateway that validates payloads and blocks reverse reads. A plain one-way queue is the simpler and more defensible option.

### Cited Findings
- **Releases:** v1.0.0 on 12 Mar 2026, v1.0.1 on 28 May 2026 (changelog dated 2026-05-26; spec bug fixes for HTTP binding content-type and TaskStatus values), and v0.3.0 on 30 Jul 2025 — [A2A GitHub releases](https://github.com/a2aproject/A2A/releases)
- **v1.0.0 headline changes:**
  - The application protocol is separated from its transport mappings (breaking).
  - Multi-tenancy via a scope field on gRPC requests.
  - A new `tasks/list` with filtering and pagination.
  - Push-notification config types merged and list responses pluralised (breaking).
  - OAuth implicit and password flows removed; device code and PKCE added.
  - **Signed Agent Cards were added in v0.3.0, not v1.0** — [A2A GitHub releases](https://github.com/a2aproject/A2A/releases)
- **Spec 1.0.0** defines three bindings (JSON-RPC, gRPC, HTTP+JSON/REST) plus custom-binding guidelines. Agent Card objects are AgentCard, AgentCapabilities, AgentExtension, AgentSkill, AgentInterface and AgentCardSignature, with fields `securitySchemes`, `security`, `capabilities.streaming`, `capabilities.pushNotifications` and `capabilities.extendedAgentCard`. Security schemes are API Key, HTTP Auth, OAuth2 (authorization code, client credentials, device code), OpenID Connect and Mutual TLS. Section 7.6 covers "in-task authorization" — [A2A specification (latest)](https://a2a-protocol.org/latest/specification/)
- **Opaque execution:** agents collaborate "without needing access to each other's internal state, memory, or tools". The **Extended Agent Card** is returned only to clients that authenticate with the declared schemes, and it may expose additional skills — [A2A specification](https://a2a-protocol.org/latest/specification/)
- **Adoption (LF press release, 9 Apr 2026):**
  - More than 150 supporting organisations, up from more than 50 in April 2025.
  - Integrated into Microsoft Azure AI Foundry and Copilot Studio, and AWS Bedrock AgentCore Runtime.
  - Production-ready SDKs in Python, JavaScript, Java, Go and .NET.
  - Signed Agent Cards for cryptographic identity.
  - More than 60 payments and financial-services organisations support AP2 (Agent Payments Protocol), an A2A extension.
  - **No bank is named as a production user** — [Linux Foundation press release](https://linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)
- Google published an A2A anniversary post in April 2026 — [Google Open Source Blog](https://opensource.googleblog.com/2026/04/a-year-of-open-collaboration-celebrating-the-anniversary-of-a2a.html?m=0)
- **Governance after Aug 2026:** secondary sources report that A2A became a hosted project of the Agentic AI Foundation (AAIF) at the Linux Foundation on 17 Aug 2026 — [dailyaiworld](https://dailyaiworld.com/public/blogs/a2a-10-joins-agentic-ai-foundation-internet-agents); [alicelabs guide](https://alicelabs.ai/en/insights/a2a-protocol-guide-2026) **[UNVERIFIED; not confirmed on an LF/AAIF page]**
- **Per-agent defences do not compose.** Research on multi-agent prompt-injection security found that per-agent CaMeL does not hold in hierarchical multi-agent systems, because a downstream agent can treat untrusted data as trusted input. The proposed "multi-CaMeL" agent-to-agent protocol preserves provenance across agent boundaries by sending trusted instructions and untrusted data over separate channels — [Peters-Gill et al., "Can CaMeLs Talk?", arXiv 2610.05640, 5 Oct 2026](https://arxiv.org/abs/2610.05640)

### Inferences
- **A2A by itself cannot enforce a one-way barrier.** It is request/response with task state. If the Judge is an A2A client of the Investigator, the Judge can read Investigator task status and artifacts through `GetTask`, `tasks/list`, streaming or push notifications. Even a status change ("working" to "completed") or response timing is a tipping-off side channel.
- **A defensible A2A setup needs five controls:**
  - (1) The Investigator is the A2A server, and the Judge is a client allowed exactly one skill, `submit_referral`.
  - (2) A gateway validates the outbound DataPart against a pinned JSON Schema (beneficiary IBAN, amount, timestamp, pseudonymous case ID) and drops free text.
  - (3) The gateway blocks every read method (`GetTask`, `tasks/list`, subscribe, push config) for the Judge principal.
  - (4) Every response is a constant-shape acknowledgement with no task ID, sent after a fixed delay.
  - (5) Agent Card signatures and mTLS pin the identity of both ends.
- **A simpler and more provable alternative is a data diode.** The Judge writes the schema-validated referral to an append-only outbox (queue or table) that only Zone 2 can read, and the Judge has no read path back. A2A can still be used inside Zone 2, between the Investigator and its sub-agents.
- **Data crossing the wall must stay labelled as data.** Following multi-CaMeL, the Investigator should treat the referral as untrusted data on a data channel, never as instructions, because the customer's dispute narrative is attacker-controllable text.

### Gaps
- **AgentSkill fields.** The truncated spec fetch did not show whether `AgentSkill` can declare JSON Schemas for DataParts. From background knowledge it has `inputModes`/`outputModes` (MIME types) and no JSON Schema [UNVERIFIED], so schema enforcement would need an A2A extension or a gateway.
- **In-task authorization.** The text of spec section 7.6 was not read.
- **Bank deployments.** No bank production deployment of A2A was found.

---

## Q3. AG-UI (CopilotKit) and alternatives for streaming agent state and events to a live UI

### Takeaway
AG-UI is an open, event-based agent↔user protocol, complementary to MCP (agent↔tools) and A2A (agent↔agent). It has first-party integrations in most major agent frameworks, including Microsoft Agent Framework, Google ADK, AWS Strands, Bedrock AgentCore, Pydantic AI and LangGraph, and well-funded stewardship (CopilotKit's $27M Series A, May 2026). The ecosystem is still evolving, and the docs I read showed no protocol version number. For the bank demo, the main design point is per-zone streams: the customer UI must never subscribe to Zone 2 events.

### Cited Findings
- **What AG-UI is:**
  - An open, lightweight, event-based protocol that carries agent state, UI intents and user interactions.
  - It builds on HTTP and WebSockets.
  - Capabilities include streaming, shared state with event-sourced diffs, thinking steps, tool-output streaming, custom events, frontend tool calls, agent steering and "Interrupts (human in the loop)". Interrupts are listed under "today & upcoming".
  - Positioning: AG-UI for agent↔user, MCP for agent↔tools, A2A for agent↔agent — [AG-UI docs, introduction](https://docs.ag-ui.com/introduction)
- **Integrations listed:**
  - Partnerships: LangGraph, CrewAI.
  - First-party: Microsoft Agent Framework, Google ADK, Google Antigravity, AWS Strands Agents, AWS Bedrock AgentCore, Mastra, Pydantic AI, Agno, LlamaIndex, AG2.
  - Community: Claude Agent SDK, Cloudflare Agents.
  - In progress: OpenAI Agent SDK, Bedrock Agents.
  - Community SDKs: Kotlin, Go, Dart, Java, Rust, Ruby, C++, .NET — [AG-UI docs](https://docs.ag-ui.com/introduction)
- **Funding:** CopilotKit raised a $27M Series A, announced 5 May 2026 — [TechCrunch](https://techcrunch.com/2026/05/05/copilotkit-raises-27m-to-help-devs-deploy-app-native-ai-agents/); [GeekWire](https://www.geekwire.com/2026/seattles-copilotkit-raises-27m-as-some-of-the-biggest-names-in-tech-adopt-its-ai-agent-protocol/)
- **Vendor support:** a May 2026 report says Google, Microsoft, Amazon and Oracle ship native AG-UI support — [beri.net, 7 May 2026 (secondary)](https://www.beri.net/article/2026-05-07-ag-ui-big-four-cloud-chatbot-ux-over)
- **CopilotKit release:** v1.62.2 dated 2026-07-02, and the listing notes the protocol is "still in active evolution" — [dev.co listing (secondary)](https://dev.co/ai/frameworks/copilotkit)
- **Alternative: MCP Apps.** This is the in-host UI path, with `ui://` resources rendered in sandboxed iframes inside MCP hosts — [SEP-1865](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp)

### Inferences
- **AG-UI vs MCP Apps.** For a custom analyst dashboard showing two zones live, AG-UI, or plain SSE carrying AG-UI-shaped events, fits better than MCP Apps. MCP Apps is for rendering inside third-party chat hosts.
- **Separate streams per zone and audience.** The customer channel carries only Zone 1 events. The fraud-ops view carries Zone 1 events. The AML analyst view carries Zone 2 events, plus a one-way "referral received" event. The barrier then shows on screen: an "AML investigation" panel that the customer view cannot subscribe to.
- **Barrier as a live UI moment.** AG-UI interrupts and human-in-the-loop events map naturally onto Cedar or FIDES "approval on violation" prompts. For example, a blocked egress becomes an analyst approval card in the UI, which demonstrates the barrier live.

### Gaps
- **Event names.** The exact AG-UI event names were not verified on the events page. From background knowledge they include RUN_STARTED/RUN_FINISHED, TEXT_MESSAGE_START/CONTENT/END, TOOL_CALL_START/ARGS/END, STATE_SNAPSHOT, STATE_DELTA (JSON Patch), STEP_STARTED and CUSTOM [UNVERIFIED]. The protocol version number was not found.
- **SDKs.** TypeScript and Python are believed to be the core first-party SDKs [UNVERIFIED]; the intro page's SDK table listed only community SDKs.
- **Other alternatives** (Vercel AI SDK stream protocol, Google A2UI) were not researched.

---

## Q4. Prompt-injection defences by design: CaMeL and successors, FIDES/IFC, Dual-LLM, design patterns, AgentDojo results, and what is reusable in Python within a day

### Takeaway
The 2025-2026 consensus moved from detection to architectural guarantees. CaMeL (Google DeepMind / ETH; SaTML 2026) solves 77% of AgentDojo tasks with provable security, against 84% undefended. Microsoft's FIDES adds confidentiality and integrity labels plus a quarantined LLM, and since May 2026 **ships experimentally in `agent-framework-core` (`agent_framework.security`)**. That is the most realistic "reuse in a day" Python option. The six design patterns from Beurer-Kellner et al. (2025) give vocabulary that juries recognise. A new Oct 2026 paper shows per-agent defences break in multi-agent systems unless provenance crosses agent boundaries, which applies directly to a two-zone design.

### Cited Findings
- **CaMeL** ("Defeating Prompt Injections by Design", Debenedetti, Shumailov, Fan, Hayes, Carlini, Fabian, Kern, Shi, Terzis, Tramèr):
  - arXiv v1 on 24 Mar 2025, v2 on 24 Jun 2025.
  - It solves **77%** of AgentDojo tasks with provable security, against **84%** undefended — [arXiv 2503.18813](https://arxiv.org/abs/2503.18813)
  - Published at SaTML 2026 — [IEEE CSDL, SaTML 2026](https://www.computer.org/csdl/proceedings-article/satml/2026/785900a587/2jZks3ksGT6)
  - April 2025 coverage cited an earlier 67% figure from v1 — [InfoQ](https://www.infoq.com/news/2025/04/deepmind-camel-promt-injection/) (figure from search snippet)
- **CaMeL code** (`google-research/camel-prompt-injection`):
  - Apache-2.0 and Python, run with `uv`, against AgentDojo; about 411 stars.
  - Explicitly "a research artifact": "not a Google product", not maintained.
  - The interpreter "likely contains bugs" and "might not be fully secure", so it is not for production — [GitHub](https://github.com/google-research/camel-prompt-injection)
- **FIDES** ("Securing AI Agents with Information-Flow Control", Costa, Köpf et al., Microsoft Research, arXiv 2505.23643):
  - A planner that tracks confidentiality and integrity labels, enforces policies deterministically, and can selectively hide information from the LLM.
  - Evaluated on AgentDojo.
  - Reference implementation at `microsoft/fides` — [arXiv 2505.23643v2](https://arxiv.org/pdf/2505.23643v2); [Microsoft Research publication page](https://www.microsoft.com/en-us/research/publication/securing-ai-agents-with-information-flow-control/)
- **FIDES in Microsoft Agent Framework (Python), from the post of 20 May 2026** — [Microsoft Agent Framework devblog](https://devblogs.microsoft.com/agent-framework/wp-json/wp/v2/posts/5414):
  - Shipped experimental in `agent-framework-core` ≥ 1.3.0 (`pip install agent-framework`), module `agent_framework.security`.
  - **Labels:** integrity is `trusted` or `untrusted`; confidentiality is `public`, `private` or `user_identity`. Each label is attached as `security_label` on `Content`.
  - **Propagation:** `LabelTrackingFunctionMiddleware` gives each tool result the most restrictive combination of its inputs.
  - **Enforcement:** `PolicyEnforcementFunctionMiddleware` checks tool properties such as `accepts_untrusted: False` and `max_allowed_confidentiality: "public"` before each call. `approval_on_violation=True` turns a block into a human-approval request.
  - **Hiding data:** `store_untrusted_content(...)` swaps untrusted text for `var_<id>` references held in a `ContentVariableStore`. `quarantined_llm(prompt, var_ids=[...])` runs on a separate `quarantine_chat_client` with no tools, and its output is labelled untrusted. `SecureAgentConfig(auto_hide_untrusted=True)` is the default.
- **Design Patterns for Securing LLM Agents against Prompt Injections** (Beurer-Kellner, Buesser, Creţu, Debenedetti, Dobos, Fabian, Fischer, Froelicher, Grosse, Naeff, Ozoani, Paverd, Tramèr, Volhejn): v1 on 10 Jun 2025, v3 on 27 Jun 2025 — [arXiv 2506.08837](https://arxiv.org/abs/2506.08837)
  - **The six patterns** — [Simon Willison, 13 Jun 2025](https://simonwillison.net/2025/Jun/13/prompt-injection-design-patterns/):
    - **Action-Selector:** the agent triggers actions but never sees their outputs.
    - **Plan-Then-Execute:** the plan is fixed before untrusted data is seen.
    - **LLM Map-Reduce:** sub-agents process untrusted items and return constrained outputs, e.g. booleans.
    - **Dual LLM:** a privileged LLM plus a quarantined LLM, exchanging symbolic variables.
    - **Code-Then-Execute:** a DSL program with data-flow tracking, i.e. CaMeL.
    - **Context-Minimization:** strip unneeded content, including the user prompt, before responding.
  - **Core principle:** "once an LLM agent has ingested untrusted input, it must be constrained" so that input cannot trigger consequential actions. The ten case studies include a customer service chatbot, an SQL agent and an email/calendar assistant.
- **Multi-CaMeL** (5 Oct 2026): an attack succeeds even when every agent individually runs CaMeL. Multi-CaMeL keeps trusted instructions and untrusted data in separate channels across agents. It is evaluated on a new **MultiAgentDojo**, plus AssetOpsBench for utility. Utility cost shrinks as models get stronger. No code link is given — [arXiv 2610.05640](https://arxiv.org/abs/2610.05640)

  | Setting | Average ASR across models |
  |---|---|
  | No CaMeL | 12.9% |
  | Per-agent CaMeL | 0.2% |
  | Multi-CaMeL | 0.0% |

- **Other systems:** a 2026 adaptive-evaluation paper groups CaMeL, FIDES, Progent, RTBAS and FORGE as capability, IFC-label or reference-monitor defences. It reports Progent cutting AgentDojo indirect-injection success from 39.9% to 1.0% (seen in a search snippet only) — [arXiv 2606.26479](https://arxiv.org/html/2606.26479v1)
- **CaMeLoT** adds temporal logic to CaMeL for static verification and liveness — [arXiv 2609.18674](https://arxiv.org/pdf/2609.18674)

### Inferences
- **The best one-day path:**
  - (1) Use Microsoft Agent Framework's FIDES middleware as the IFC engine. Map the "data passport" to its labels: integrity, confidentiality, and a custom `allowed_sinks` attribute enforced in a small extra middleware.
  - (2) Structure the Investigator's OSINT ingestion as Plan-Then-Execute plus Dual LLM. The quarantined LLM extracts only schema-bound fields (company name, registration number, dates) from hostile web pages and never has tools.
  - (3) Cite CaMeL and multi-CaMeL as the formal basis rather than running the CaMeL interpreter, which is an unmaintained research artifact.
- **Mapping the zones to the patterns:**
  - The Judge is close to Action-Selector / Context-Minimization: its customer-facing reply is generated from a fixed template with slots filled only from Zone 1-labelled data.
  - The Investigator is Plan-Then-Execute with LLM Map-Reduce over transactions and pages.
  - The wall between them follows the multi-CaMeL "separate data channel" principle.
- **Jury-ready metrics:**
  - Report your own mini-AgentDojo-style numbers: attack success rate (ASR) and utility on 20-50 injected OSINT pages and adversarial customer messages, with and without labels.
  - Add a **non-interference test**: run the Judge on the same dispute with the Zone 2 state varied (no investigation, investigation open, SAR filed) and show its outputs and tool calls are identical. This is the textbook IFC property and is very persuasive.

### Gaps
- **FIDES licences.** The licence of `microsoft/fides` and of the Agent Framework security module was not checked; Agent Framework is believed MIT [UNVERIFIED].
- **FIDES numbers.** FIDES' own AgentDojo numbers were not extracted.
- **Progent details.** Progent's paper (arXiv 2504.11703, believed [UNVERIFIED]) and its policy DSL were not read.
- **Adaptive-evaluation conclusions.** The adaptive-evaluation paper (2606.26479) was not read beyond the snippet, so which defences survive adaptive attacks is unknown.

---

## Q5. Authorization for agent tools: Cedar, OPA/Rego, capability tokens, provenance labels

### Takeaway
Cedar has become the de facto policy language for agent-tool authorization in 2026:
- AWS Bedrock AgentCore Policy (Cedar at the MCP gateway; GA reported 3 Mar 2026).
- Strands Agents' built-in Cedar handler.
- Stacklok ToolHive's Cedar gating of MCP `tools/call`.
- TrueFoundry's Cedar guardrails.

The common pattern is principal = agent/user, action = tool, resource and context = arguments and session, with default deny and forbid overriding permit. Argument-level conditions must be written explicitly.

### Cited Findings
- **AgentCore Policy (AWS):**
  - Uses Cedar to give "precise, verifiable access control for gateway tools". Each MCP tool maps to a Cedar action entity, and Cedar has no wildcard actions — [AWS AgentCore docs, core concepts](https://docs.aws.amazon.com/de_de/bedrock-agentcore/latest/devguide/policy-core-concepts.html); [getting started](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-getting-started.html)
  - A tool-level allow does not restrict arguments unless conditions are added — [AWS Thailand blog](https://aws.amazon.com/th/blogs/thailand/agentcore-in-action-part4-fine-grain-control/)
  - Natural-language-to-Cedar authoring is offered (search summary of AWS docs).
  - GA date reported as 3 Mar 2026 — [third-party implementation guide](https://hidekazu-konishi.com/entry/amazon_bedrock_agentcore_policy_implementation_guide.html) **[UNVERIFIED on an AWS page]**
- **Strands Agents:** a built-in Cedar Authorization intervention evaluates policies before each tool call. Each tool is a Cedar action, and the context includes tool input and session data — [Strands docs](https://strandsagents.com/docs/user-guide/concepts/agents/interventions/cedar-authorization/)
- **Stacklok ToolHive:** Cedar policies gate MCP `tools/call`. Some methods bypass authorization (`initialize`/`ping` in older spec versions) and others are denied by default — [ToolHive Cedar policies](https://docs.stacklok.com/toolhive/concepts/cedar-policies)
- **TrueFoundry AI Gateway:** Cedar guardrails run at the MCP pre-tool hook, and forbid overrides permit — [TrueFoundry docs](https://truefoundry.com/docs/ai-gateway/cedar-guardrails)
- **Provenance labels:** FIDES labels (integrity, confidentiality) attach to content and propagate with "most restrictive wins" — [Microsoft Agent Framework devblog](https://devblogs.microsoft.com/agent-framework/wp-json/wp/v2/posts/5414)
- **MCP scope model:** a minimal initial scope plus step-up via `WWW-Authenticate` scope challenges, with no wildcard scopes — [MCP Security Best Practices](https://modelcontextprotocol.io/specification/latest/basic/security_best_practices)

### Inferences
- **Two complementary decision points:**
  - (1) A **Cedar policy at the MCP gateway**, keyed on the zone principal and tool name, available from the `Mcp-Name` header in 2026-07-28. Example: `forbid (principal in Zone::"Judge", action, resource) when { resource.zone == "AML" };`
  - (2) An **IFC/passport check inside the agent runtime** (FIDES middleware). This decides whether this specific datum may flow to this sink, e.g. `customer_reply`, `external_llm`, `public_search`.
  - Cedar answers "may this agent call this tool?". Labels answer "may this data reach this sink?". The jury should see both.
- **Data passport as a capability object.** Each datum carries `{source_uri, retrieved_at, sha256, integrity, confidentiality, zone, allowed_sinks[], pseudonymised: bool}`. Joining two passports yields the most restrictive result: intersect `allowed_sinks` and take the max confidentiality. Every sink tool declares the passport it requires. This is CaMeL's "capabilities" (readers and provenance) and FIDES' labels made concrete.
- **Default deny.** Start from forbid-all and permit only the specific tools each zone needs, with argument conditions. Example: Investigator `public_search` permitted only when `context.query_passport.contains_customer_pii == false`.

### Gaps
- **OPA/Rego with agents** was not researched in this session. OPA is a CNCF graduated project and is usable as an HTTP sidecar [UNVERIFIED].
- **Capability tokens** (Macaroons, Biscuit, UCAN) for agents were not researched.
- **Cedar's formal verification** (Lean-proved semantics, symbolic analysis) is from background knowledge [UNVERIFIED this session].
- **Python bindings.** It was not verified whether an official Cedar Python binding exists. `cedarpy` is a community package [UNVERIFIED].

---

## Q6. Information barriers / Chinese walls in multi-agent systems, anti tipping-off controls, and output filters with their evaluation

### Takeaway
I found **no published benchmark or framework explicitly for "Chinese walls" or ethical walls in LLM multi-agent systems**. Multi-agent privacy benchmarks show that instruction-only confidentiality fails badly. In MAGPIE, frontier models leak 35-51% of sensitive information even when told not to, and prompt-level defences remove only a small share of leakage. The barrier must therefore be structural (no data path from Zone 2 to Zone 1), with output filters as a second layer. It should be proven with canary tokens and a non-interference test.

### Cited Findings
- **MAGPIE** (arXiv 2510.15186): 200 high-stakes multi-agent tasks. GPT-5 leaks up to 35.1% and Gemini 2.5-Pro up to 50.7% of sensitive information **even when explicitly instructed not to** — [arXiv 2510.15186](https://www.arxiv.org/abs/2510.15186). An earlier version reported multi-agent systems failing tasks in 71% of scenarios — [arXiv 2506.20737](https://arxiv.org/html/2506.20737v1)
- **SNEAK** (Mar 2026) scores messages on utility to collaborators against leakage to an adversary. Modern LLMs score well on utility but struggle to limit leakage — [SNEAK, arXiv 2603.29846](https://www.alphaxiv.org/abs/2603.29846)
- **1-2-3 Check** (CMU) splits privacy reasoning across agents and controls what each agent sees. It reduces leakage by 18% on ConfAIde and 19% on PrivacyLens with GPT-4o — [arXiv 2508.07667](https://arxiv.org/pdf/2508.07667v1)
- **PrivacyPeek** targets over-collection at data-acquisition time and finds prompt-level defences remove only a small share of that leakage — [PrivacyPeek](https://benchmarklist.com/benchmarks/privacypeek/)
- **Multi-agent provenance:** defences must keep provenance across agent boundaries, because per-agent guarantees do not compose — [arXiv 2610.05640](https://arxiv.org/abs/2610.05640)
- **A2A opacity:** A2A agents interoperate without sharing internal state, memory or tools. This is a design principle, not an enforcement mechanism — [A2A spec](https://a2a-protocol.org/latest/specification/)

### Inferences
- **Layered anti-tipping-off design (strongest first):**
  1. **No path (structural).** Zone 1 has no credentials, MCP servers, database grants or UI streams that can read Zone 2 data. Use separate OAuth audiences and separate stores. The Judge→Investigator link is a one-way diode with a schema-validated referral and a constant ack (see Q2).
  2. **Label enforcement (IFC).** Everything produced in Zone 2 carries `confidentiality=AML_RESTRICTED` and `allowed_sinks=[aml_analyst, fiu_report]`. The Judge's `send_customer_message` tool declares a maximum confidentiality of `CUSTOMER_SHAREABLE`, using FIDES `max_allowed_confidentiality` semantics.
  3. **Output filter on the customer channel (defence in depth).**
     - (a) **Canary or honeytoken strings** planted in Zone 2 artefacts (unique fake case codes, phrasings), with exact-match blocking. A hit is a proven breach.
     - (b) A deterministic denylist for Romanian and English tipping-off phrases, e.g. "spălare de bani", "investigație AML", "raportat la ONPCSB", "suspicious activity report", "beneficiary under investigation".
     - (c) A small LLM or classifier judge for semantic tipping-off, which must fail closed, i.e. hold the message for human review.
  4. **Observability barrier.** Traces and logs are a classic leak path. Zone 2 traces must go to a separate Langfuse project or instance that fraud-ops users cannot read.
- **How to evaluate the barrier, with numbers for the jury:**
  - (a) A **non-interference test**: vary the Zone 2 state and assert the Judge's outputs and tool-call trace are identical, using temperature 0 or comparing structured decisions.
  - (b) A **red-team suite** of adversarial customer prompts in Romanian and English, e.g. "is the account I paid being investigated?" or "did you report them to the police?". Measure canary-leak rate (target 0) and semantic leak rate, MAGPIE-style.
  - (c) **Filter precision and recall** on a labelled set of benign and tipping-off replies, to show the filter does not block legitimate dispute updates.
  - (d) A **side-channel check**: the Judge's response latency and content do not depend on whether a referral was accepted.

### Gaps
- **No paper or tool explicitly on LLM "Chinese walls".** A search using the "ethical wall" or "information barrier" terminology with LLM agents could still find something.
- **Legal anchors** were not researched in this session (EU AMLD art. 39 tipping-off ban, AMLR (EU) 2024/1624, Romanian Law 129/2019). They are likely covered by another researcher.
- **Output-filter evaluation.** No published evaluation of tipping-off output filters was found.

---

## Q7. PII handling: Microsoft Presidio (Romanian CNP and IBAN, Romanian language), pseudonymisation before external LLMs, reversible vault mapping

### Takeaway
Presidio has **moved from Microsoft to a community-owned project under "Data Privacy Stack"**; its docs moved from microsoft.github.io/presidio to presidio.dataprivacystack.org. It has a global `IBAN_CODE` recogniser (pattern, context and checksum) but **no Romanian CNP recogniser**, so a custom `PatternRecognizer` with checksum validation is needed. `python-stdnum`'s `stdnum.ro.cnp` can supply the checksum. Presidio is stateless, and its only built-in reversible operator is `encrypt`/`decrypt`. Consistent placeholders plus a reversible vault (e.g. `<PERSON_1>`, `<IBAN_2>`) must be built by the team.

### Cited Findings
- **Docs moved.** The old Presidio docs URL redirects to `data-privacy-stack.github.io/presidio`, which redirects to `presidio.dataprivacystack.org` — [old URL](https://microsoft.github.io/presidio/supported_entities/); [new site](https://presidio.dataprivacystack.org/supported_entities/)
- **Community ownership.** The site states "Presidio has transitioned to a community-owned project", owned by Data Privacy Stack. No date or licence statement was visible — [Presidio home](https://presidio.dataprivacystack.org/)
- **Components:** Analyzer, Anonymizer, Image Redactor, Structured.
- **NLP engines:** spaCy, Stanza and transformers, with GLiNER, Flair and SpanMarker as external-model samples — [Presidio home](https://presidio.dataprivacystack.org/)
- **Global entities:** CREDIT_CARD, CRYPTO, DATE_TIME, EMAIL_ADDRESS, **IBAN_CODE** ("pattern match, context and checksum"), IP_ADDRESS, MAC_ADDRESS, NRP, LOCATION, PERSON, PHONE_NUMBER, MEDICAL_LICENSE, URL, UUID — [Presidio supported entities](https://presidio.dataprivacystack.org/supported_entities/)
- **Country groups:** USA, UK, Spain, Italy, Poland, Singapore, Australia, India, Finland, Korea, Nigeria, Philippines, Canada, Sweden, South Africa, Thailand, Turkey, Germany. **Romania / CNP is not listed** — [Presidio supported entities](https://presidio.dataprivacystack.org/supported_entities/)
- **Anonymizer operators:**
  - `replace` (default inserts `<ENTITY_TYPE>`), `redact`, `hash` (sha256/sha512; salt ≥128 bits; a fixed salt gives reproducible output), `mask`, `encrypt` (with a key), `custom` (lambda), `surrogate_ahds`, `keep`.
  - The deanonymize operator is `decrypt`.
  - Only encrypt/decrypt is reversible. Presidio "does not store or maintain stateful sessions", so the mapping vault is the user's responsibility — [Presidio anonymizer](https://presidio.dataprivacystack.org/anonymizer/)
- **CNP checksum:** `python-stdnum` module `stdnum.ro.cnp` validates the 13-digit CNP, which encodes gender, birth date and county — [python-stdnum docs](https://arthurdejong.org/python-stdnum/doc/stdnum.ro.cnp)

### Inferences
- **Recipe that can be built in an hour or two:**
  - (1) `PatternRecognizer` for `RO_CNP`: regex `\b[1-9]\d{12}\b`, plus `validate_result` calling `stdnum.ro.cnp.is_valid`, plus context words ("CNP", "cod numeric personal", "C.N.P.").
  - (2) Keep the built-in `IBAN_CODE`, which already validates the checksum, and add Romanian context words ("cont", "IBAN", "beneficiar").
  - (3) A custom operator that maps each distinct value to a stable token per case (`<IBAN_1>`) and stores `token → AES-GCM(value)` in a local vault (SQLite or a dict) with a per-case key.
  - (4) Re-identification happens only inside the bank boundary, after the external LLM call, and only for sinks the passport allows.
- **Use consistent tokens, not Presidio's default `replace`.** Default `replace` gives all persons the same `<PERSON>` tag, which destroys the entity relationships the AML graph needs. Graph reasoning sent to an external LLM can then work on `<IBAN_1> → <IBAN_2>` without seeing real identifiers.
- **Passport on outbound calls.** Every outbound LLM or OSINT call records in the data passport which entities were tokenised. The demo can show, side by side, the "what the LLM saw" pane and the real case file.

### Gaps
- **Transition details.** The date, governance and licence status of Presidio's transition were not found. The original Microsoft repo was MIT [UNVERIFIED for the community fork].
- **Romanian NLP quality.** Romanian NER quality in Presidio (spaCy `ro_core_news_*` pipelines, Stanza Romanian) was not verified. Person-name detection in Romanian likely needs a transformer or GLiNER model and should be tested.
- **No existing recogniser package.** No existing open-source Presidio Romanian recogniser package was found.
- **[UNVERIFIED] Romanian IBAN format.** Background knowledge gives 24 characters: `RO` + 2 check digits + 4-letter bank code + 16 alphanumerics.

---

## Q8. Tamper-evident audit logs and evidence ledgers for agent decisions; OpenTelemetry GenAI conventions; Langfuse and Arize Phoenix

### Takeaway
The 2026 consensus pattern for tamper-evident agent logs has four parts:
- A per-entry SHA-256 hash chain.
- Merkle trees over entries or chain heads for compact inclusion proofs (RFC 6962 / Certificate-Transparency style).
- Per-record signatures (Ed25519).
- External anchoring of the root.

There is an IETF draft (SPICE intent-chain, March 2026) for signing agent input and output hashes. OTel's GenAI conventions now live in a dedicated repo covering GenAI spans, metrics, events and MCP, and MCP 2026-07-28 standardises trace propagation in `_meta`. Langfuse was acquired by ClickHouse in Jan 2026, and its core stays MIT.

### Cited Findings
- **IETF draft `draft-mw-spice-intent-chain-00`** (March 2026, work in progress): every agent signs `input_hash` + `output_hash` (`intent_sig`), giving non-repudiable evidence of what each agent received and produced. The full chain lives in ordered logs, with only a Merkle root in the token — [IETF draft mirror](https://ftp.kaist.ac.kr/ietf/draft-mw-spice-intent-chain-00.html)
- **Agent Flight Recorder** (arXiv 2609.01931, Sep 2026): hash chaining plus Merkle batching for tamper evidence and inclusion proofs, with on-chain anchoring (abstract only) — [Emergent Mind listing](https://www.emergentmind.com/papers/2609.01931)
- **Open-source examples:**
  - `attestroot` (PyPI): hash-chains agent activity and seals it into an RFC 6962 Merkle commitment that can be verified offline. Its tamper-detection claims are self-reported — [PyPI attestroot](https://pypi.org/project/attestroot/)
  - OpenFang: audit entries chain the previous entry's hash and are exposed through a verify endpoint — [OpenFang docs](https://www.mintlify.com/yocxy2/openfang/security/audit)
  - NoireBox: SHA-256 chain, Ed25519 signatures, and Merkle aggregation of chain heads — [macmyths](https://macmyths.com/ai-agent-audit-logs-what-can-noirebox-prove/)
  - Anchoring: submit only the chain head externally, so raw logs never leave the infrastructure — [OriginStamp blog (vendor)](https://preview.originstamp.com/en/blog/reader/tamper-proof-logging-ai-agents-blockchain-anchoring)
- **OTel GenAI semantic conventions:**
  - The conventions **moved out of opentelemetry.io's semconv pages to `open-telemetry/semantic-conventions-genai`** — [opentelemetry.io GenAI page (moved notice)](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  - The repo is Apache-2.0 and covers "spans, metrics, and events for GenAI clients", MCP, and provider-specific conventions (OpenAI, Anthropic, AWS Bedrock, Azure AI Inference). It uses Weaver.
  - The Releases section was empty, and the schema URL was "TODO" when viewed — [GitHub semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)
  - The old index pages include "agent spans" and "MCP" sections — [opentelemetry.io GenAI page](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- **MCP trace propagation:** 2026-07-28 documents `traceparent`, `tracestate` and `baggage` propagation in `_meta` (SEP-414) — [MCP changelog](https://modelcontextprotocol.io/specification/latest/changelog)
- **Langfuse:**
  - ClickHouse acquired Langfuse, announced 16 Jan 2026 alongside a $400M Series D.
  - Core features remain MIT, and self-hosting is unchanged — [ClickHouse blog](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability); [Langfuse blog](https://langfuse.com/blog/joining-clickhouse)
  - Enterprise features sit under a separate EE licence (secondary). One third-party article instead claims AGPL-3.0, which conflicts with the MIT statements — [OpenObserve (conflicting)](https://openobserve.ai/blog/langfuse-alternatives.md)

### Inferences
- **Evidence ledger design for the case file:**
  - (1) Every tool result or fetched page is stored content-addressed (SHA-256 of the raw bytes) with `retrieved_at` in UTC, `source_uri`, the tool name and the OTel `trace_id`/`span_id`.
  - (2) Every case-file claim references one or more evidence hashes. A claim with no evidence hash is rejected by the renderer, so "no claim without a source" is enforced mechanically.
  - (3) Ledger entries are hash-chained and batched into an RFC 6962-style Merkle tree per case. The root is signed with Ed25519, using a per-zone key so each zone signs its own ledger.
  - (4) Optional: an RFC 3161 timestamp on the root [UNVERIFIED as used by others; a standard TSA mechanism].
  - (5) A `verify` CLI recomputes everything.
  - Demo moment: edit one byte in a stored OSINT page and verification fails, pointing at the exact claim.
- **Tracing setup.** Use OTel GenAI spans via OpenLLMetry/OpenInference, or the native SDK, into self-hosted Langfuse (MIT core). Run separate Langfuse projects or instances per zone, so the observability plane respects the Chinese wall.
- **Why SPICE matters.** The SPICE draft's "sign input_hash and output_hash per agent hop" maps directly onto the Judge→Investigator referral. Both sides sign the referral hash, so later disputes about what was passed are settled cryptographically.

### Gaps
- **[UNVERIFIED] OTel GenAI details.** Stability status (believed "Development"), `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, agent span names (`create_agent`, `invoke_agent`, `execute_tool`), and opt-in content capture via `gen_ai.input.messages`/`gen_ai.output.messages` were not confirmed on the new repo.
- **[UNVERIFIED] Arize Phoenix.** Its licence (believed Elastic License 2.0) and its OpenInference conventions were not checked.
- **Peer review.** No peer-reviewed evaluation of agent audit-log schemes was found; most sources are vendor or project pages.
- **Signed provenance standards** (in-toto, Sigstore, C2PA) for agent outputs were not researched.

---

## Q9. Guardrail models: Llama Prompt Guard 2 and NeMo Guardrails (brief)

### Takeaway
Llama Prompt Guard 2 (April 2025; 86M mDeBERTa-base and 22M DeBERTa-xsmall; 512-token window; Llama 4 Community License) is a strong, cheap detector for explicit injections and jailbreaks. The 86M model reaches 97.5% recall at 1% FPR in English and 81.2% AgentDojo attack-prevention rate at a 3% utility cost. It is a probabilistic layer, not a guarantee, and Romanian is not among its evaluated languages. NeMo Guardrails was not researched in depth.

### Cited Findings
- **Model details** — [Hugging Face model card](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M):
  - Two sizes: 86M (mDeBERTa-base) and 22M (DeBERTa-xsmall).
  - Labels are `benign` or `malicious`, with a 512-token context. Longer inputs should be split into segments and scanned in parallel.
  - Licence: Llama 4 Community License. The collection was updated 29 Apr 2025.
  - Evaluated languages: English, French, German, Hindi, Italian, Portuguese, Spanish, Thai.
- **Benchmarks from the model card** — [Hugging Face model card](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M):

  | Model | AUC (English) | Recall @1% FPR (English) | AUC (multilingual) | AgentDojo APR @3% utility reduction | Latency (A100, 512 tokens) |
  |---|---|---|---|---|---|
  | Prompt Guard 2 86M | .998 | 97.5% | .995 | 81.2% | 92.4 ms |
  | Prompt Guard 2 22M | .995 | 88.7% | .942 | 78.4% | 19.3 ms |
  | Prompt Guard 1 | .987 | 21.2% | — | 67.6% | — |

- **Stated limitations:** adaptive attacks can bypass it, application-specific fine-tuning improves results, and the 22M model has a larger multilingual gap — [Hugging Face model card](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M)
- **Related multilingual evidence (Llama Guard family, not Prompt Guard):**
  - Llama Guard's paper notes mostly English training data and possible prompt-injection susceptibility — [arXiv 2312.06674](https://arxiv.org/pdf/2312.06674)
  - A multilingual guardrail benchmark found Llama Guard 2 scoring 75.25 F1 on English against 62.66 on non-English jailbreak prompts — [arXiv 2410.22153](https://arxiv.org/pdf/2410.22153)

### Inferences
- **Placement.** Use Prompt Guard 2 86M as a cheap pre-filter on (a) every OSINT page chunk before the quarantined LLM sees it and (b) customer messages to the Judge. Log its score into the evidence ledger, but never rely on it alone. The architectural controls (Q4-Q6) carry the guarantee.
- **Romanian.** Romanian is not in the evaluated set. Run a quick Romanian red-team set to measure recall, which would be a nice jury slide: "we measured our guard on Romanian rather than trusting the model card".

### Gaps
- **[UNVERIFIED] NeMo Guardrails** was not researched this session: version, licence (believed Apache-2.0), Colang 2.x, and its jailbreak, PII (Presidio-based) and fact-checking rails.
- **Romanian performance.** No published Prompt Guard 2 results on Romanian were found.
- **Other detectors.** Other guard models were not compared (e.g. ProtectAI deberta-v3 injection classifiers, Lakera, Azure Prompt Shields); AWS Bedrock Guardrails is out of scope (covered elsewhere).
