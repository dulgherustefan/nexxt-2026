# AWS / Amazon Bedrock stack for a production-grade multi-agent system with Claude (status as of 28 Oct 2026)

*Research date: 2026-10-28. Scope: AgentCore, Strands Agents, Bedrock Guardrails (including Automated Reasoning), Claude on Bedrock, Bedrock API keys, document/graph/vector services, durable orchestration, AWS MCP servers, FSI reference samples. Labels: **[GA]**, **[Preview]**, **[3rd-party]** (source is not AWS or Anthropic), **[Unverified]** (not confirmed against a primary source in this session). Anything under "Inferences" is my reasoning, not a sourced fact.*

---

## 1. Amazon Bedrock AgentCore: components, status, Gateway, Policy, session isolation, A2A, EU regions, pricing

### Takeaway
AgentCore now has 13 modular services. The core set (Runtime, Gateway, Memory, Identity, Code Interpreter, Browser, Observability) is joined by Policy (GA 3 Mar 2026) and Evaluations (GA 31 Mar 2026), and both of those are GA in Europe (Frankfurt). The 2026 additions (Harness, Registry, Optimization, Payments) are mostly still in preview. Gateway is the integration hub: OpenAPI, Smithy and Lambda become MCP tools, existing MCP servers can sit behind it, and A2A traffic can pass through. Policy then applies default-deny, Cedar-compatible rules to every tool call at the Gateway, which is the natural mechanism for a deterministic information barrier between two agent zones.

### Cited Findings

**Component inventory (current AWS docs)**
- AWS describes AgentCore as an agentic platform that works "with any open-source framework such as CrewAI, LangGraph, LlamaIndex, and Strands Agents and with any foundation model". The services can be used together or independently. The current list is Harness, Runtime, Memory, Gateway, Identity, Code Interpreter, Browser, Observability, Payments, Evaluations, Optimization, Policy and Registry. — [AgentCore docs: What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Harness**: "A managed agent loop that lets you define and invoke AI agents with a single API call." You specify the model, system prompt and tools inline. Each session runs in an isolated microVM with filesystem and shell access, and you can bring your own container image. It works with Amazon Bedrock, OpenAI, Gemini and any OpenAI-compatible provider, and supports remote MCP servers. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Runtime**: a serverless runtime with "fast cold starts", "extended runtime support for asynchronous agents" and "true session isolation", plus built-in identity and support for multi-agent workloads. It works with CrewAI, LangGraph, LlamaIndex, Google ADK, OpenAI Agents SDK and Strands, with any model including Claude, and with the MCP and A2A protocols. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Memory**: short-term (multi-turn) and long-term (cross-session) memory, "with the ability to not only share memory stores across agents but also learn from experiences". — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Gateway**: converts "your APIs, Lambda functions, and existing services into Model Context Protocol (MCP)-compatible tools" and can also connect to existing MCP servers. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Identity**: agent identity, access and authentication that works with existing IdPs such as Cognito, Okta, Microsoft Entra ID and Auth0. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Code Interpreter**: an isolated sandbox for Python, JavaScript and TypeScript. **Browser**: a managed cloud browser that works with Playwright and BrowserUse. **Observability**: tracing and monitoring in an OTEL-compatible format. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Payments**: microtransaction payments for paid APIs and MCP servers over the x402 protocol and the Machine Payments Protocol (MPP), with Coinbase CDP and Stripe (Privy) wallets. Not relevant to this use case. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Evaluations**: automated agent assessment over sessions, traces and spans from Strands Agents or LangGraph that are instrumented with OpenTelemetry or OpenInference. Results go to AgentCore Observability and CloudWatch. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Optimization**: "AI-generated recommendations, versioned configuration bundles, and A/B testing". It can optimize system prompts and tool descriptions, with traffic splitting through Gateway. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Policy**: "deterministic control to ensure agents operate within defined boundaries and business rules". Rules are written "using natural language or a policy language — Dogwood, which is compatible with Cedar". Policy integrates with Gateway "to intercept every tool call before execution", so you can define "which tools agents can access, what actions they can perform, and under what conditions". — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
  - **Registry**: a central catalog of agents, MCP servers, tools, skills and custom resources, with a governed publish, review and approve workflow and hybrid semantic and keyword search. — [same](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)

**Status timeline**
| Component | Status | Date / regions | Source |
|---|---|---|---|
| Policy | [Preview], then **[GA]** | Preview Dec 2025 (re:Invent). GA **3 Mar 2026** in 13 Regions: N. Virginia, Ohio, Oregon, Mumbai, Seoul, Singapore, Sydney, Tokyo, **Frankfurt**, Ireland, London, Paris, Stockholm | [What's New (Dec 2025 preview)](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-agentcore-policy-evaluations-preview); [What's New (GA)](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/) |
| Evaluations | [Preview], then **[GA]** | Preview Dec 2025. GA **31 Mar 2026** in 9 Regions: N. Virginia, Ohio, Oregon, Mumbai, Singapore, Sydney, Tokyo, **Frankfurt**, Ireland | [What's New (GA)](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available); [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/) |
| Harness | **[Preview]**, GA status in conflict | Public preview 22 Apr 2026, together with the AgentCore CLI and AgentCore skills. The AWS FAQ still says "preview". A third-party blog says it went GA at AWS Summit New York on 17 Jun 2026 | [What's New Apr 2026](https://aws.amazon.com/about-aws/whats-new/2026/04/agentcore-new-features-to-build-agents-faster/); [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/); [techpillow [3rd-party]](https://www.techpillow.co/blog/amazon-bedrock-agentcore-harness-ga-2026) |
| Registry ("AWS Agent Registry") | **[Preview]** | Announced Apr 2026. Indexes agents wherever they run and supports MCP and A2A | [What's New](https://aws.amazon.com/about-aws/whats-new/2026/04/aws-agent-registry-in-agentcore-preview/); [InfoQ](https://www.infoq.com/news/2026/04/aws-agent-registry-preview/) |
| Optimization | **[Preview]** (Recommendations reportedly GA) | Recommendations, batch evaluations and A/B tests entered public preview in Apr 2026. The July 2026 release notes reportedly list Recommendations as GA, but this was seen only in a search summary | [AgentCore release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html); [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/) |
| Payments | **[Preview]** | — | [FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/) |
| Runtime, Gateway, Memory, Identity, Code Interpreter, Browser, Observability | Not labeled preview in the current docs or FAQ (i.e., GA) | Original GA date not re-verified in this session (see Gaps) | [What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) |

**Runtime: isolation, duration, protocols**
- There are two compute types: **microVMs**, which are serverless with hardware-enforced isolation, and **Instances**, which are managed EC2 in your account. microVM sessions run for up to **8 hours** and Instance sessions for up to **14 days**. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- Each user interaction gets a dedicated compute environment. microVMs scale from zero to "hundreds of thousands of concurrent sessions". — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- Runtime supports bi-directional streaming, MCP and A2A. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)

**Gateway: how APIs, Lambdas and OpenAPI become MCP tools**
- Gateway is now described as "a fully managed AI gateway that provides a single, secure entry point for agentic traffic—connecting agents to tools, to other agents, and to large language models". It converts APIs, Lambda functions and existing services into MCP tools. It "fronts other agents and HTTP services through passthrough targets (including Agent-to-Agent (A2A) traffic)", and it "routes inference requests across multiple model providers through a unified, model-based routing endpoint". — [Gateway docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- "Gateway supports OpenAPI, Smithy, and Lambda as tool input types." It also offers 1-click integrations with Salesforce, Slack, Jira, Asana and Zendesk. — [Gateway docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- The docs list these capabilities:
  - **Security Guard**: OAuth authorization.
  - **Translation**: "Converts agent requests using protocols like Model Context Protocol (MCP) into API requests and Lambda invocations".
  - **Composition**: multiple sources behind a single endpoint.
  - **Secure Credential Exchange**: credentials injected per tool.
  - **Semantic Tool Selection**: lets agents "use thousands of tools while minimizing prompt size".
  - **Infrastructure Manager**: serverless, with built-in observability and auditing.

  — [Gateway docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- Gateway handles both inbound authentication (verifying agent identity) and outbound authentication (connecting to tools), including OAuth flows, token refresh and credential storage. — [Gateway docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- Supported auth methods are IAM, OAuth 2.1 and API keys. Gateway also offers semantic search, metadata-based tool filtering, **per-user rate limits** on requests, tokens and connection duration, and optional web ACLs. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)

**Policy: how it works**
- Policy "operates outside your agent code". Natural-language rules are "automatically converted to Cedar". Policies live in a policy engine attached to a Gateway, and the Gateway "intercepts agent-tool traffic and evaluates each request against the policies". — [What's New (GA, 3 Mar 2026)](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/)
- Policy **denies by default**. Natural language converts to Cedar or Dogwood. **Temporal policies** "evaluate the session's prior actions". Policy integrates with Bedrock Guardrails for prompt-injection and sensitive-data detection, and AWS says evaluation handles "thousands of requests per second". — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- A third-party article dated 17 Jun 2026 reports that Policy gained Bedrock Guardrails support. — [Classmethod [3rd-party]](https://dev.classmethod.jp/en/articles/20260617-amazon-bedrock-agentcore-policy-guardrails/)

**Evaluations**
- There are **13 built-in evaluators**, and custom evaluators are supported. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- The built-in evaluators cover correctness, helpfulness, tool selection accuracy, safety, goal success rate and context relevance. Evaluations can run online on live traffic or on demand for CI/CD regression testing (both seen via search summary). — [AWS News Blog](https://aws.amazon.com/blogs/aws/amazon-bedrock-agentcore-adds-quality-evaluations-and-policy-controls-for-deploying-trusted-ai-agents/); [What's New (GA)](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available)

**Memory, Identity, tools, Observability**
- **Memory**: encrypted, namespace-based storage with VPC support, and predefined or custom extraction strategies. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Identity**: OAuth 2.0 client-credentials (2LO) and authorization-code (3LO) flows, plus a token vault for credentials and API keys. Works with Cognito, Entra ID and Okta. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Code Interpreter** can reference S3 files at gigabyte scale. **Browser** has VM-level isolation, live viewing, session replay and CloudTrail logging. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- **Observability** is OpenTelemetry-compatible, with CloudWatch dashboards for traces, session count, latency, duration, token usage and error rates. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)

**Regions**
- AgentCore is "available in fifteen AWS Regions". The FAQ does not list them. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- Europe (Frankfurt) is explicitly listed for Policy ([GA post](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/)) and for Evaluations ([GA post](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available)).

**Pricing and data handling**
- Pricing is consumption-based, with no upfront commitments or minimum fees. — [What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- Runtime microVMs are billed per second on active CPU and memory, with memory billed at peak and **I/O wait free**. Instances are billed as the EC2 instance plus an AgentCore management fee. AgentCore is HIPAA eligible, FedRAMP is "being pursued", and the Bedrock SLA applies. — [AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)
- Data-use clause (relevant for a bank): "AgentCore may use and store your content to improve your service experience or performance. Such improvements would be for your use of AgentCore and not for other customers." — [What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)

### Inferences
- **Minimal hackathon core:** Strands agents on AgentCore Runtime, one Gateway (plus a Policy engine) per zone, Memory per zone, Observability, and optionally Evaluations. Harness would be faster to stand up, but its GA status is contradictory (FAQ says preview, a third-party says GA), so code-first Strands on Runtime is the lower-risk choice.
- **Information barrier via Gateway and Policy:**
  - Give each zone its own Gateway and its own default-deny policy engine, with separate inbound identities.
  - Zone 1 agents then cannot call Zone 2 tools. With semantic tool search scoped per gateway, they likely cannot even discover them.
  - Temporal policies ("evaluate the session's prior actions") could enforce sequencing, for example "the refund-execution tool only after the eligibility tool and an approval token". The exact policy syntax and schema were not verified.
- **Defense in depth:** keep separate IAM execution roles per Runtime, separate Memory resources (not just namespaces), separate KMS keys and data stores, and a one-way event channel from Zone 1 to Zone 2 (see section 10). Do not use A2A between zones; A2A is fine inside a zone.
- **Frankfurt:** Policy and Evaluations are GA in Frankfurt, and both operate on Gateway and Observability data. That suggests Runtime, Gateway and Observability are also available there, but it should be checked in the console.
- **Bank compliance:** the "may use and store your content" clause should be raised with AWS and the bank's compliance team, including whether AWS Organizations AI-services opt-out policies cover AgentCore. Not verified.

### Gaps
- I did not obtain the explicit list of the 15 AgentCore Regions, or the Regions for Harness, Registry, Optimization and Payments.
- Unit prices (Runtime vCPU-hour and GB-hour, Gateway per-request, Memory, Policy, Evaluations) were not verified; the pricing page was not fetched.
- The original GA date of the core services (I recall October 2025) was not re-verified.
- Runtime payload and idle-timeout limits are not stated in the FAQ.
- I did not research how Dogwood differs from Cedar, or whether natural-language policy authoring works in Romanian.
- Whether AgentCore's content-use clause can be opted out is unknown.

---

## 2. Strands Agents SDK: version, multi-agent patterns, MCP/A2A, Bedrock, structured output, hooks, OpenTelemetry

### Takeaway
Strands is very actively developed: Python v1.62.0 and TypeScript v1.22.0 were both released on 21 Oct 2026, alongside new "harness" packages. It covers all four multi-agent patterns (agents-as-tools, swarm, graph, workflow) plus A2A. It also has hooks and a now-public middleware system for deterministic controls, Pydantic structured output, native OpenTelemetry, and MCP tool support. AWS itself uses Strands on AgentCore Runtime for compliance-investigator agents.

### Cited Findings
- **Releases** (GitHub page fetched 28 Oct 2026; the page shows day and month only):

  | Release | Date |
  |---|---|
  | `python/v1.62.0` | 21 Oct |
  | `typescript/v1.22.0` | 21 Oct |
  | `harness-python/v0.3.2` | 22 Oct |
  | `harness-typescript/v0.3.1` | 21 Oct |
  | `harness-cli/v0.2.2` | 22 Oct, marked "Latest" |

  The releases come out as one monorepo-style stream. — [GitHub strands-agents releases](https://github.com/strands-agents/sdk-python/releases)
- **Recent release-note items:**
  - Invoke limits and usage accounting now span the whole agent tree, and subagents inherit the parent's interventions.
  - A swarm tool was added in Python and TypeScript (breaking in TypeScript).
  - Providers can enforce structured output when a model can't be forced to.
  - The Python **middleware** system is now public.
  - OpenTelemetry baggage propagation was ported to TypeScript.
  - `agent.cancel()` stops the event loop.

  — [GitHub releases](https://github.com/strands-agents/sdk-python/releases)
- **Multi-agent patterns:**
  - The official docs cover Agents-as-Tools, Swarm, Graph, Workflow and A2A. Graph uses developer-defined routing, while in Swarm the LLM decides the handoffs.
  - Workflow is only available as a tool from `strands-agents-tools`. Graph and Swarm ship in the core SDK.

  — [Strands multi-agent patterns docs](https://strandsagents.com/1.x/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns)
- The 1.0 announcement says the patterns can be nested, for example swarms inside graphs or agents used as tools. — [Strands Agents 1.0 blog](https://strandsagents.com/blog/strands-agents-1-0/)
- **A2A:** remote A2A agents work inside Graph workflows (Python only) and as tools for an orchestrator. A2AAgent is **not supported in Swarm** in either SDK, because swarm handoffs need capabilities the A2A protocol lacks. — [Strands A2A docs](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/index.md)
- **Structured output:** `structured_output_model` takes "Pydantic model type(s) for structured output". — [Strands API reference](https://strandsagents.com/latest/documentation/docs/api-reference/python/hooks/registry). v1.14.0 added "Structured Output as part of the agent loop". — [newreleases.io [3rd-party mirror of GitHub notes]](https://newreleases.io/project/github/strands-agents/harness-sdk/release/v1.14.0)
- **Hooks:** a hook provider is a class with a `register_hooks` method that Strands calls once at agent construction. Hooks can enforce deterministic rules instead of relying on system prompts. — [AWS re:Post article](https://repost.aws/articles/AR9OFGjcoCRAi1rfwb277ZFQ/using-strands-hooks-to-deterministically-control-your-agent)
- **OpenTelemetry:** Strands "natively integrates with OpenTelemetry". You install the otel extras. — [Strands traces docs](https://strandsagents.com/docs/user-guide/observability-evaluation/traces/). From v1.34.0 it can emit GenAI traces under either the legacy or the newer experimental semantic conventions. — [Splunk docs [3rd-party]](https://agent-observability-docs.splunk.com/sdk-api/third-party-integrations/opentelemetry-and-openinference/strands-agents)
- **MCP:** the `MCPClient` class wraps MCP servers (stdio or other transports) and exposes their tools to the agent. — [everydev.ai [3rd-party]](https://www.everydev.ai/tools/strands-agents)
- **AgentCore compatibility:** Strands traces are a supported input for AgentCore Evaluations. — [What is AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- **Production use at Amazon:** Amazon's compliance-screening investigator agents "are built on the Strands agent framework", use LLMs hosted on Amazon Bedrock, and are deployed on AgentCore Runtime. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/how-amazon-uses-ai-agents-to-support-compliance-screening-of-billions-of-transactions-per-day)

### Inferences
- **Zone 1 (dispute):** a **Graph** fits best, because the steps are fixed and auditable: intake → evidence extraction → deterministic eligibility and deadline rules → decision memo with structured output → Automated Reasoning check → human approval → refund execution → hand-off to the recovery track. Specialist sub-agents can be used via **agents-as-tools**.
- **Zone 2 (AML lead):** a Graph or a **Swarm** inside the zone suits open-ended beneficiary and network analysis. Do not connect the zones with A2A or Swarm; that would break the barrier.
- **Hooks and middleware** are where to put deterministic controls that Guardrails does not cover:
  - Call `ApplyGuardrail` on tool results, which Guardrails does not scan on its own (section 3).
  - Write an audit record for every tool call.
  - Add a local deny-list as a second layer beside AgentCore Policy.
- **Structured output** (Pydantic) for the decision memo gives a schema that a deterministic validator, Automated Reasoning and the approval UI can all consume.

### Gaps
- Repository naming is unclear: the fetched `sdk-python` releases page shows harness, python and typescript streams, and a third-party mirror refers to `strands-agents/harness-sdk`. The rename was not confirmed.
- I found no reliable detail on what the "Strands harness" is.
- I did not verify the semantics of Strands interrupts (human-in-the-loop) or how they interact with hooks.
- I did not verify Strands' default Bedrock model ID, or whether the Strands Anthropic provider can target the Bedrock Mantle endpoint.

---

## 3. Amazon Bedrock Guardrails: PII, prompt attacks, contextual grounding, Automated Reasoning checks

### Takeaway
- **PII:** built-in types include **INTERNATIONAL_BANK_ACCOUNT_NUMBER** and **SWIFT_CODE**. There is no Romanian CNP type, so use a custom regex (no lookaround).
- **Other filters:** prompt-attack filtering (jailbreak, prompt injection, and prompt leakage on the Standard tier) and contextual grounding checks.
- **Automated Reasoning:** GA in Frankfurt, Paris and Ireland, but English (US) only, detect mode only, no streaming, and source documents of at most 50,000 characters.
- **Critical agent caveat:** the PII filter does **not** inspect tool-call arguments, tool results or tool definitions.
- **Legal decisions:** Automated Reasoning can check an English decision statement against encoded rules, but only within the policy's variables and as a verification layer, not as the decision-maker.

### Cited Findings
**PII / sensitive-information filters**
- Built-in PII types:

  | Category | Types |
  |---|---|
  | General | ADDRESS, AGE, NAME, EMAIL, PHONE, USERNAME, PASSWORD, DRIVER_ID, LICENSE_PLATE, VEHICLE_IDENTIFICATION_NUMBER |
  | Finance | CREDIT_DEBIT_CARD_CVV, CREDIT_DEBIT_CARD_EXPIRY, CREDIT_DEBIT_CARD_NUMBER, PIN, **INTERNATIONAL_BANK_ACCOUNT_NUMBER**, **SWIFT_CODE** |
  | IT | IP_ADDRESS, MAC_ADDRESS, URL, AWS_ACCESS_KEY, AWS_SECRET_KEY |
  | Country-specific | US, Canada and UK types only. No EU or Romania-specific types |

  — [Guardrails sensitive information filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- **Actions:** BLOCK, ANONYMIZE (mask with the type name, e.g. `{NAME}`) or NONE (detect only), configurable separately for input and output. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- **Custom regex:** name 1–100 characters, pattern 1–500 characters, optional description 1–1000 characters, with the same actions. "A custom regex filter of sensitive information filters does not support a regex lookaround match." — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- **Tool-use caveat:** the filter evaluates text content only. It does **not** evaluate PII the model writes into tool-call arguments (`toolUse.input` / `tool_use`), PII in tool results (`toolResult`), or tool definitions. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- **Logs and traces:** masking does not apply to model invocation logs (the CloudWatch `input` field holds the original request), so AWS recommends CloudWatch Logs data protection. The guardrail trace `match` field also contains the original PII. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)
- **Detection model:** the filter is a probabilistic, context-dependent ML model and works better with more context. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)

**Prompt attacks, topics, grounding**
- **Content filters:** categories are Hate, Insults, Sexual, Violence, Misconduct and Prompt Attack, and they exclude reasoning content. "Prompt attacks" covers "jailbreaks, prompt injections, and prompt leakages (Standard tier only)". — [Guardrail components](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
- **Denied topics and word filters:** both exist. AWS's example is a banking assistant that avoids illegal investment advice. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
- **Contextual grounding checks:** flag responses that are not grounded in the source or are irrelevant to the query, for example in RAG. The Standard tier supports reasoning and conversational content, gives more consistent scores and supports more languages. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)
- **Invocation logs:** blocked content appears in plain text in model invocation logs if logging is enabled. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)

**Automated Reasoning checks**
- **What they do:**
  - They use formal logic to "detect factually incorrect statements … by mathematically proving that generated content contradicts your policy rules".
  - They "highlight unstated assumptions".
  - They give "mathematically verifiable explanations … citing the specific policy rules and variable assignments".
  - They are recommended for regulated industries, including financial services, and for compliance scenarios that need auditable responses.

  — [Automated Reasoning checks docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Building a policy from documents:**
  - Upload a source document. The service extracts formal logic rules and a schema of variables, and generates a **fidelity report** with coverage and accuracy scores that link each rule back to the source.
  - Test with generated scenarios and QnA tests.
  - Save an immutable version, attach it to a guardrail, and deploy via CloudFormation or CI/CD.
  - At runtime, call it through Converse, InvokeModel or the standalone `ApplyGuardrail` API.

  — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Detect mode only:** checks "return findings and feedback rather than blocking content". — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Regions:** "generally available" in US East (N. Virginia), US West (Oregon), US East (Ohio), **EU (Frankfurt)**, EU (Paris), EU (Ireland) and Asia Pacific (Sydney). — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Language:** "Automated Reasoning checks currently support English (US) only." — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Limitations:**
  - No prompt-injection protection; pair with content filters.
  - Encoded or obfuscated text (Base64, hex, percent-encoding) may cause "the entire submission" not to be evaluated.
  - No off-topic detection and no streaming.
  - A `VALID` result only covers statements captured by policy variables. AWS's example: a "fake doctor's note" can pass if no variable captures fakeness.

  — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Limits:**
  - Input documents are limited to **5 MB and 50,000 characters**; you can split them and merge the sections into one policy.
  - Latency grows with the number of variables.
  - Complex policies can return `TOO_COMPLEX`, and non-linear arithmetic may time out.
  - Each policy should cover one domain.

  — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Pricing:** charged per validation request "regardless of the result (for example, VALID, INVALID, TRANSLATION_AMBIGUOUS)". — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)
- **Cross-Region processing:** policy build, test and runtime validation use LLMs through cross-Region inference. Requests from Frankfurt, Paris or Ireland are processed "in any supported EU Region", and data "remains within the geographic boundary". — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)

### Inferences
- **Can Automated Reasoning verify an agent's legal decision? Yes, within limits.** A workable pattern:
  1. Encode an **English-language** rules document. Translate the relevant provisions of Legea 209/2019 and the C-70/25 "refund first, recover later" logic as the team states it; the legal content itself is outside this research.
  2. Define explicit variables, for example: transaction authorised (bool), reported in time (bool), payer fraud established (bool), refund executed by deadline (bool), recovery track opened (bool).
  3. Validate the agent's **English decision summary** with `ApplyGuardrail` before human approval.
  4. Treat `INVALID` or `TRANSLATION_AMBIGUOUS` as "route to human / regenerate".
- **Keep deadlines out of Automated Reasoning.** Compute dates and business days (the Romanian holiday calendar, the "end of next business day" cut-off) in deterministic code, and pass the results in as facts. Automated Reasoning should verify logic, not do calendar arithmetic, which risks `TOO_COMPLEX` or non-linear issues.
- **Use Automated Reasoning alongside a rules engine, not instead of it.** It is detect-only and scoped to its variables, so the deterministic rules layer (code) should remain the source of truth.
- **Tool I/O needs explicit guarding.** Because PII and other filters skip tool I/O, call `ApplyGuardrail` explicitly on:
  - tool results, such as core-banking lookups and OCR text from phishing screenshots;
  - outbound customer messages.

  A Strands hook is a natural place to do this.
- **Treat phishing artefacts as untrusted.** Text from phishing pages and screenshots is prompt-injection-prone. Run the prompt-attack filter on extracted text before an agent sees it, and remember that Automated Reasoning itself offers no injection protection.
- **Candidate custom regexes (untested, my construction):**
  - Romanian IBAN: `RO[0-9]{2}[A-Z]{4}[A-Z0-9]{16}`. The built-in `INTERNATIONAL_BANK_ACCOUNT_NUMBER` already exists.
  - CNP (13 digits; validate the checksum in code): `[1-9][0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{6}`.
- **Tipping-off control:** a denied topic on Zone 1 customer-facing output, covering AML investigations, suspicious-activity reports and beneficiary investigations, is a cheap extra safeguard.

### Gaps
- The Automated Reasoning GA date was not re-verified; I recall August 2025.
- Exact quotas (variables and rules per policy, policies per guardrail) are on the Bedrock quotas page, which I did not fetch.
- The full set of result types was not confirmed. Only VALID, INVALID, TRANSLATION_AMBIGUOUS and TOO_COMPLEX were seen in this session; SATISFIABLE, IMPOSSIBLE and NO_TRANSLATIONS are from memory.
- I did not verify whether the Standard-tier content, prompt-attack and grounding filters support **Romanian**; the supported-languages page was not fetched.
- I did not re-verify the input-tagging requirement for the prompt-attack filter, or the thresholds and limits for contextual grounding.

---

## 4. Claude models on Amazon Bedrock in 2026: models, EU inference and data residency, Messages API ("Mantle") vs InvokeModel/Converse, caching, tools

### Takeaway
As of 28 Oct 2026, Bedrock serves the Claude 5.x generation:
- Opus 5.5 (on Bedrock since 22 Sep 2026), Sonnet 5.5, Haiku 5.5, Opus 5 and Sonnet 5;
- Fable 5.1 and Fable 5;
- limited-access Mythos models;
- legacy 4.x models.

There are two access paths:
- the new **"Claude in Amazon Bedrock" Messages-API endpoint**, `https://bedrock-mantle.{region}.api.aws/anthropic/v1/messages`;
- **InvokeModel/Converse** on `bedrock-runtime`.

`eu-central-1` supports Global and EU routing on the Mantle endpoint, but not in-region-only routing. Regional or geographic routing costs about 10% more than global. Prompt caching (explicit breakpoints), tool use, structured outputs, citations and thinking are supported. Server-side tools, the Files API, Batches, the MCP connector and Agent Skills are not.

### Cited Findings
- **Opus 5.5 launch:** AWS published "Claude Opus 5.5 is now available on AWS" on **22 Sep 2026** and called it "the first of the Claude 5.5 model family".
  - Its runtime model ID is `global.anthropic.claude-opus-5-5`.
  - It is available through the Anthropic Messages API on `bedrock-runtime` and `bedrock-mantle`, and through Invoke and Converse on `bedrock-runtime`.
  - It is offered through **US, EU, AU, JP and Global** cross-Region inference profiles.
  - At launch, `bedrock-mantle` was listed in us-east-1 and ap-southeast-4.
  - The required IAM actions are `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`.

  — [AWS ML Blog, 22 Sep 2026](https://aws.amazon.com/blogs/machine-learning/claude-opus-5-5-is-now-available-on-aws/)
- **Opus 5.5 behaviour and price:** adaptive thinking is always on, and reasoning depth is set with an **effort** parameter. Per-token prices are lower than Opus 5, with "much cheaper cache reads"; no dollar figures were given. Claude Platform on AWS also offers Opus 5.5, but "in North America". — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/claude-opus-5-5-is-now-available-on-aws/)
- **Models on the Messages-API endpoint (Anthropic docs, current):**

  | Model | Model ID | Access |
  |---|---|---|
  | Claude Fable 5.1 | `anthropic.claude-fable-5-1` | Open |
  | Claude Mythos 5.1 | `anthropic.claude-mythos-5-1` | Verification required |
  | Claude Fable 5 | `anthropic.claude-fable-5` | Open |
  | Claude Mythos 5 | `anthropic.claude-mythos-5` | Verification required |
  | Claude Mythos Preview | `anthropic.claude-mythos-preview` | Invitation only |
  | Claude Opus 5.5 | `anthropic.claude-opus-5-5` | "See Access" criteria |
  | Claude Opus 5 | `anthropic.claude-opus-5` | "See Access" criteria |
  | Claude Opus 4.8 | `anthropic.claude-opus-4-8` | Open |
  | Claude Opus 4.7 | `anthropic.claude-opus-4-7` | Open |
  | Claude Sonnet 5.5 | `anthropic.claude-sonnet-5-5` | "See Access" criteria |
  | Claude Sonnet 5 | `anthropic.claude-sonnet-5` | Open |
  | Claude Haiku 5.5 | `anthropic.claude-haiku-5-5` | "See Access" criteria |
  | Claude Haiku 4.5 | `anthropic.claude-haiku-4-5` | Open |

  "Open" means open to all Bedrock customers; for the other models, check the criteria under model access in the Bedrock console. — [Anthropic docs: Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Mantle endpoint basics:**
  - The endpoint is `https://bedrock-mantle.{region}.api.aws/anthropic/v1/messages`. It uses standard SSE streaming and "the same request body shape as Anthropic's first-party API".
  - It runs on AWS-managed infrastructure with "zero operator access": Anthropic personnel cannot access the inference infrastructure.
  - The IAM action is `bedrock-mantle:CreateInference`.

  — [Anthropic docs: Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Mantle authentication:** three paths, in order of preference:
  1. A Bedrock service role (recommended).
  2. IAM assumed roles, with a 12-hour maximum session.
  3. Bearer tokens (12-hour maximum, "least preferred"). The token goes in the `x-api-key` header. A standard Anthropic client with `base_url=https://bedrock-mantle.{region}.api.aws/anthropic` and `api_key=<bearer token>` works, but supports "bearer-token authentication only".

  SigV4 needs the `AnthropicBedrockMantle` client. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Region and endpoint types:** Global routing carries no premium. "Regional endpoints carry a 10 percent pricing premium over global endpoints." EU geography routing uses an inference profile.

  | EU Region | Endpoint types |
  |---|---|
  | `eu-central-1` Frankfurt | Global, EU (**not** "In-region only") |
  | `eu-west-1` Ireland | Global, EU, In-region only |
  | `eu-north-1` Stockholm | Global, EU, In-region only |
  | eu-central-2, eu-south-1, eu-south-2, eu-west-2, eu-west-3 | Global, EU |

  Fable 5.1's regional endpoint is in us-east-1 only. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Quotas:** the default is 2M input tokens per minute. You can request up to 5M input TPM and 500k output TPM without Anthropic approval; RPM limits are set by AWS. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Features supported:** Messages API, **prompt caching**, thinking, **tool use** (including the bash, computer-use (beta versions), memory and text-editor tools), citations and **structured outputs**.
- **Not supported:**
  - the Files API and URL sources;
  - server-side tools (code execution, web search, web fetch, advisor);
  - Agent Skills, the MCP connector and programmatic tool calling;
  - Message Batches, Models, Admin and Usage endpoints;
  - Claude Managed Agents and server-side fallback;
  - automatic prompt caching via the top-level `cache_control` field (use explicit cache breakpoints instead);
  - the `computer_toolset_20260801` and `browser_toolset_20260801` toolsets.

  — [same](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **InvokeModel path:** on `bedrock-runtime`, the newer models (Fable 5.1 and 5, Opus 5.5 and 5, Sonnet 5.5 and 5, Haiku 5.5, Opus 4.8 and 4.7) "are reachable through `InvokeModel` … served by the same infrastructure as the Claude in Amazon Bedrock endpoint". For full feature parity, use the Messages endpoint. — [Anthropic docs: Claude on Amazon Bedrock (legacy)](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **Legacy ARN-versioned models** (Opus 4.6, Sonnet 4.6, Haiku 4.5 and older) need inference-profile IDs such as `global.`, `us.`, `eu.`, `jp.` or `apac.`. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **SDK pinning gotcha:** "The latest version of the SDK sends API version `2026-10-21` by default, including through Amazon Bedrock." The ARN-versioned models "don't support `2026-10-21` on Bedrock" and can return a 400 error, so pin the SDK version if you use them. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **Context window:** Fable 5.1 and 5, Opus 5.5, 5, 4.8, 4.7 and 4.6, Sonnet 5.5, 5 and 4.6, and Haiku 5.5 have a **1M-token context window** on Bedrock. Bedrock request payloads are limited to **20 MB**. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **Mid-conversation system messages:** available through InvokeModel for Fable 5.1 and 5, Opus 5.5, 5 and 4.8, Sonnet 5.5 and Haiku 5.5. They are not available on Sonnet 5. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **Bedrock docs (bedrock-runtime):** "Global endpoints … Carry no pricing premium". Regional CRIS endpoints "Are required for data residency and compliance requirements" and carry a 10% premium. Anthropic recommends logging activity on at least a 30-day rolling basis. — [same](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- **Logging:** Claude in Amazon Bedrock emits logs to CloudWatch and CloudTrail. — [Anthropic docs: Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- **Third-party reports:**
  - A test from Tokyo found a JP inference profile and a global profile for Opus 5.5, and reported **no Fast mode on Bedrock**. — [Classmethod [3rd-party]](https://dev.classmethod.jp/en/articles/bedrock-claude-opus-5-5/)
  - A blog reports a "not available for this account" error that was fixed via Anthropic's first-time-use form and Marketplace permissions. — [logeshwaran.org [3rd-party]](https://www.logeshwaran.org/2026/10/claude-opus-5-5-on-amazon-bedrock.html)

### Inferences
- **EU residency:**
  - From Frankfurt, use EU geo routing: the `eu.` profile on bedrock-runtime, or the EU endpoint type on Mantle. That keeps inference inside EU Regions at the +10% regional price.
  - If the bank requires **single-Region** processing, Mantle's "In-region only" is offered in Ireland and Stockholm, not Frankfurt.
  - Avoid `global.` profiles for customer data.
- **EU runtime model ID:** following the prefix convention, it is likely `eu.anthropic.claude-opus-5-5`. Check with `ListInferenceProfiles` in eu-central-1.
- **Possible model split:** Opus 5.5 for the orchestrator and legal reasoning in Zone 1; Sonnet 5.5 for worker agents and Zone 2 analysis; Haiku 5.5 for triage, classification and pre-screening.
  - Opus 5.5, Sonnet 5.5 and Haiku 5.5 have access criteria. If access is blocked during the hackathon, Sonnet 5, Opus 4.8 and Haiku 4.5 are "Open" fallbacks.
- **Prompt caching:** add explicit `cache_control` breakpoints on long static prefixes, such as the legal corpus and tool definitions, because automatic caching is not supported on Bedrock.
- **Search and browsing:** there are no server-side web search or fetch tools on Bedrock, so any web lookups (for example, checking phishing domains) need your own tools, AgentCore Browser, or a Gateway target.

### Gaps
- I did not find release dates for Sonnet 5.5 and Haiku 5.5 on Bedrock. The AWS blog of 22 Sep 2026 called Opus 5.5 the first of the 5.5 family, so they arrived between 22 Sep and 28 Oct 2026.
- No per-token prices were found.
- There is a **conflict** on Mantle Regions for Opus 5.5: at launch, AWS listed bedrock-mantle only in us-east-1 and ap-southeast-4, while Anthropic's current table lists eu-central-1 (Global, EU) for the endpoint in general. Confirm in the console that Opus 5.5 is enabled in eu-central-1.
- I did not verify feature parity of Converse for Claude 5.x (structured outputs, effort, caching).
- I did not research the exact behaviour of the Fable or Mythos models.

---

## 5. Amazon Bedrock API keys: authentication, short vs long-term, coverage, security

### Takeaway
Bedrock API keys are bearer tokens, set via the `AWS_BEARER_TOKEN_BEDROCK` environment variable or an `Authorization: Bearer` header. There are two kinds:
- **Short-term:** up to 12 hours, inheriting the generating principal's permissions; recommended for production.
- **Long-term:** an IAM user with a service-specific credential; AWS recommends it for exploration only.

Both are **Region-scoped**. They cover only Amazon Bedrock and Bedrock Runtime actions (plus the Mantle endpoint). They do **not** cover Agents for Bedrock (including Knowledge Base retrieval), Bedrock Data Automation or `InvokeModelWithBidirectionalStream`, and they almost certainly do not cover AgentCore.

### Cited Findings
- **Short-term keys** last "up to 12 hours (or the duration of your session, whichever is shorter)", inherit the generating principal's permissions, and are "Recommended for production use". **Long-term keys** last until a configured expiry, create an IAM user with attached policies, and are "Recommended only for exploration". — [Bedrock API keys docs](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
- **Usage:** set `AWS_BEARER_TOKEN_BEDROCK` (boto3 picks it up; the docs include a boto3 Converse example) or send `Authorization: Bearer <key>`. Short-term keys come from the `aws-bedrock-token-generator` libraries (Python, JS, Java), which handle caching and refresh. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
- **Region scope:** a long-term key "works only in the Region you generated it in". Otherwise requests fail with `Credential should be scoped to a valid region`. Short-term keys "Can be used only in the AWS Region from which you generated it." — [API keys docs](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html); [API keys reference](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-reference.html)
- **Coverage:** "Amazon Bedrock API keys are limited to Amazon Bedrock and Amazon Bedrock Runtime actions." They cannot be used with `InvokeModelWithBidirectionalStream`, with Agents for Amazon Bedrock or Agents for Amazon Bedrock Runtime operations, or with Data Automation (BDA) operations. — [API keys reference](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-reference.html)
- **IAM controls:**
  - `bedrock:CallWithBearerToken` with condition key `bedrock:bearerTokenType` (`SHORT_TERM` or `LONG_TERM`).
  - `bedrock-mantle:CallWithBearerToken` with `bedrock-mantle:bearerTokenType` for the Mantle endpoint.
  - `iam:CreateServiceSpecificCredential` with `iam:ServiceSpecificCredentialAgeDays` to cap the lifetime of long-term keys (example: 90 days).

  — [API keys docs](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
- **Revocation:** deactivate, reset or delete long-term keys (`UpdateServiceSpecificCredential`, `ResetServiceSpecificCredential`, `DeleteServiceSpecificCredential`). To revoke short-term keys, invalidate the session or deny `CallWithBearerToken`. — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
- **Audit:** "All API calls are logged in AWS CloudTrail. API keys are passed as authorization headers and are not logged." — [same](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
- **Anthropic's guidance:** for Claude in Amazon Bedrock, Anthropic ranks bearer tokens "least preferred" behind service roles and assumed roles, and recommends denying long-term tokens via the bearer-token-type condition. — [Anthropic docs](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)

### Inferences
- **What the existing key covers:** Claude calls on bedrock-runtime (Converse and InvokeModel) and on Mantle, and probably `ApplyGuardrail` and guardrail creation, since those are Bedrock or Bedrock Runtime actions, if the key's principal has the permissions.
- **What it does not cover:**
  - Knowledge Base `Retrieve` and `RetrieveAndGenerate`, which are Agents for Amazon Bedrock Runtime operations.
  - BDA.
  - Very likely AgentCore (a separate service namespace), Step Functions, Lambda, Neptune and S3.

  For anything beyond model calls and guardrails, the team needs IAM credentials or a role, for example an IAM Identity Center session or the role of a hackathon sandbox account.
- **Region check:** confirm the key was generated in **eu-central-1**, or whichever Region is used. A key from us-east-1 will not work in Frankfurt.
- **Hygiene:**
  - Keep the key in Secrets Manager or the environment, never in the repo.
  - Prefer short-term keys and set a deny on long-term key use after the hackathon.
  - Rotate or delete the key when the event ends.
  - Note that CloudTrail records the calls but not the key.
- **Strands:** the Strands Bedrock model provider uses boto3, so local Strands agents should be able to use the API key through `AWS_BEARER_TOKEN_BEDROCK`. This is inferred from the boto3 support shown in the AWS docs and was not tested with Strands.

### Gaps
- I did not verify which permissions the console's default long-term key includes (the CLI example attaches `AmazonBedrockLimitedAccess`), for example whether it allows creating guardrails or Automated Reasoning policies.
- I did not verify whether the AgentCore Gateway model-routing endpoint can use a Bedrock API key.

---

## 6. Document and data services: Bedrock Data Automation, Textract, Knowledge Bases GraphRAG, Neptune Analytics, S3 Vectors

### Takeaway
All the main building blocks exist, and most are confirmed in Frankfurt:
- **BDA** is GA in Frankfurt for documents, images, video and audio, but it is not callable with a Bedrock API key.
- **Knowledge Bases GraphRAG** with Neptune Analytics has been GA since March 2025, with S3 as the only data source.
- **Neptune Analytics** has more than 25 in-database graph algorithms (PageRank, Louvain, Leiden, WCC, Jaccard and others), callable from openCypher. They are a direct fit for Zone 2 mule-network analysis.
- **S3 Vectors** has been GA since Dec 2025, with up to 2 billion vectors per index; it supports semantic search but not hybrid search.

### Cited Findings
**Bedrock Data Automation (BDA)**
- BDA went GA in **Europe (Frankfurt)**, London, Ireland, Mumbai and Sydney in July 2025. — [What's New Jul 2025](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-bedrock-data-automation-additional-aws-regions/)
- An October 2025 update lists 8 Regions, including Frankfurt, and adds more video formats and faster image processing. — [What's New Oct 2025 (DE)](https://aws.amazon.com/de/about-aws/whats-new/2025/10/amazon-bedrock-data-automation-formats-video-images/)
- BDA extracts insights from unstructured multimodal content: documents, images, video and audio. — [BDA user guide](https://docs.aws.eu/bedrock/latest/userguide/bda.html)
- In Aug 2025, BDA added five more languages for documents. Which languages, and whether Romanian is among them, was not verified. — [What's New Aug 2025 (DE)](https://aws.amazon.com/de/about-aws/whats-new/2025/08/amazon-bedrock-data-automation-five-additional-languages-documents/)
- BDA operations are **not** usable with Bedrock API keys. — [API keys reference](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-reference.html)

**Knowledge Bases GraphRAG and Neptune Analytics**
- GraphRAG went GA on 7 Mar 2025, "in AWS Regions where Amazon Bedrock Knowledge Bases and Amazon Neptune Analytics are both available", with no extra charge beyond the underlying services. — [What's New Mar 2025](https://aws.amazon.com/about-aws/whats-new/2025/03/amazon-bedrock-knowledge-bases-graphrag-generally-available)
- Limitations: no autoscaling for the Neptune Analytics graphs, and GraphRAG "supports only Amazon S3 as a data source" (from a localized copy of the guide). Region lists differ between snapshots of the guide; one older copy lists Frankfurt, London, Ireland, Oregon, N. Virginia and Tokyo. — [KB GraphRAG docs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-build-graphs.html)
- Neptune Analytics expanded to 7 more Regions in Jan 2026: N. California, Seoul, Osaka, Hong Kong, Stockholm, Paris and São Paulo. — [What's New Jan 2026](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-neptune-analytics-generally-available-additional-regions)
- Neptune Analytics provides "over 25 optimized graph algorithms and variants", exposed as openCypher procedures (for example `CALL neptune.algo.pageRank(...)`):

  | Category | Algorithms | AWS-listed uses |
  |---|---|---|
  | Pathfinding | BFS, Single-Source Shortest Path, Top-K Source Shortest Path, Source-Target Shortest Path, EgoNet | — |
  | Centrality | Degree, PageRank, Closeness, Eigenvector | "Fraud ring/Collusion detection" |
  | Similarity | Common Neighbors, Total Neighbors, Jaccard, Overlap | Link prediction |
  | Community detection | WCC, SCC, Label Propagation, Louvain, Leiden | "Fraud ring identification" |
  | Vector similarity | HNSW ANN: Distance, Top-K | — |
  | Miscellaneous | Graph info, schema, degree distribution | — |

  You run them through `ExecuteOpenCypherQuery` or `aws neptune-graph execute-query`. — [Neptune Analytics algorithms](https://docs.aws.amazon.com/neptune-analytics/latest/userguide/algorithms.html)

**S3 Vectors**
- S3 Vectors went GA on 2 Dec 2025. It supports up to **2 billion vectors per index** (40x the preview), 10,000 indexes per vector bucket, and **14 Regions**. The Bedrock Knowledge Bases integration is GA. — [What's New Dec 2025](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-vectors-generally-available/)
- Vectors have 1–4,096 dimensions, and an account can have up to 10,000 vector buckets per Region. Metadata can total up to 40 KB per vector. — [S3 Vectors limitations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html)
- When used with Bedrock Knowledge Bases, custom metadata is limited to 1 KB and 35 keys per vector, and S3 Vectors supports semantic search but **not hybrid search**. — [S3 Vectors with Bedrock KB](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html)

### Inferences
- **BDA for evidence intake:** use it for phishing-page screenshots (image), recorded calls with the victim or fraudster (audio), and bank statements and ID documents. BDA output should pass through the prompt-attack filter and PII masking before agents see it (section 3). BDA requires IAM credentials, not the API key.
- **Zone 2 graph design:**
  - Model accounts, IBANs, devices, phones, IPs and counterparties in Neptune Analytics.
  - Use **WCC, Louvain or Leiden** to find mule clusters around the fraudulent beneficiary.
  - Use **PageRank or Degree** to rank hubs.
  - Use **Jaccard or Overlap** to find accounts that share devices or phones.
  - Use **vector similarity** for embedding-based look-alikes.

  The Neptune MCP server (section 8) or a Gateway Lambda target can expose these queries as tools.
- **Regulatory corpus:** use a KB on S3 Vectors as the cheapest store for Legea 209/2019, PSD2 or EBA texts and bank SOPs. If keyword precision matters, for example article numbers, add metadata filters or choose a vector store with hybrid search, because S3 Vectors has none.

### Gaps
- **Textract** was not researched in this session (regions, Romanian support).
- **GNN/ML on graphs:** I found no GNN capability in the Neptune Analytics algorithms page. Neptune ML for Neptune Database was not researched.
- I did not confirm Neptune Analytics availability in **Frankfurt**, the 14 S3 Vectors Regions, or the current GraphRAG Region list.
- I did not verify BDA support for Romanian documents or audio.

---

## 7. Durable orchestration: Step Functions, Lambda durable functions, EventBridge; long workflows with human approval

### Takeaway
Two production-grade options exist for human approval in long-running agent workflows:
- **Step Functions** with the `.waitForTaskToken` callback pattern, plus a newer direct AgentCore integration (June 2026, apparently preview).
- **Lambda durable functions** (GA since Dec 2025, in Frankfurt since Dec 2025). They use checkpointed steps and callbacks that can wait up to one year with no compute charge while suspended.

Both let an agent pipeline pause for an approver and resume deterministically.

### Cited Findings
- **Durable functions launch:** Lambda durable functions launched in Dec 2025 for "multi-step applications and AI workflows". Initially GA in US East (Ohio) with Python 3.13/3.14 and Node.js 22/24 (runtime detail via search summary). — [What's New Dec 2025](https://aws.amazon.com/about-aws/whats-new/2025/12/lambda-durable-multi-step-applications-ai-workflows/)
- **Region expansion:**
  - 18 Dec 2025: 14 more Regions, including **Europe (Frankfurt)**, Ireland, Milan, Stockholm and Spain. Features: checkpointing, automatic recovery, steps, and waits that "pause execution without incurring compute charges for on-demand functions". — [What's New 18 Dec 2025](https://aws.amazon.com/about-aws/whats-new/2025/12/lambda-durable-functions-14-additional-regions/)
  - Apr 2026: 16 more Regions and Java (17+) support. — [What's New Apr 2026](https://aws.amazon.com/about-aws/whats-new/2026/04/lambda-durable-functions-16-new-regions/)
  - 2026: the China Regions. — [amazonaws.cn](https://www.amazonaws.cn/en/new/2026/amazon-lambda-durable-functions-are-available/)
- **Wait duration:** "wait" and "callback" patterns can suspend execution "for up to one year", for example for human-in-the-loop AI workflows. — [Lambda durable functions product page](https://aws.amazon.com/lambda/lambda-durable-functions/)
- **Callback mechanics:** the function creates a callback, notifies the human with the callback ID, and suspends; the example uses a 24-hour timeout and a 2-hour heartbeat. The external system resumes it by calling `SendDurableExecutionCallbackSuccess` or `SendDurableExecutionCallbackFailure`. — [Lambda durable examples](https://docs.aws.amazon.com/lambda/latest/dg/durable-examples.html)
- **Step Functions human approval:** AWS has an official tutorial for a workflow that waits for human approval, using the task-token callback with email approve and reject links. — [Step Functions tutorial: human approval](https://docs.aws.eu/step-functions/latest/dg/tutorial-human-approval.html); [AWS Compute Blog: manual approval steps](https://aws.amazon.com/blogs/compute/implementing-serverless-manual-approval-steps-in-aws-step-functions-and-amazon-api-gateway/)
- **Step Functions to AgentCore:**
  - A June 2026 integration lets a Task state invoke an AgentCore Harness agent directly (`arn:aws:states:::bedrockagentcore:invoke…`). The call is request-response, so human approval goes in a separate SNS plus `.waitForTaskToken` state. — [Serverworks blog [3rd-party]](https://blog.serverworks.co.jp/sfn-agentcore-human-in-the-loop)
  - A mirror of an AWS announcement describes the integration as **preview** and mentions built-in approval steps to gate agent actions. — [AWS announcement mirror [Unverified]](https://ai-radar.vonikakv.people.aws.dev/reports/https-aws-amazon-com-about-aws-whats-new-2026-06-aws-step-functions-agentcore.html)
- **Community patterns** for approval gates on AI agents:
  - With Lambda durable functions — [DEV Community [3rd-party]](https://dev.to/_76130e67067eab4c8510/building-human-approval-gates-for-ai-agents-with-lambda-durable-functions-1eif)
  - Slack approval buttons on durable functions without Step Functions — [Classmethod [3rd-party]](https://dev.classmethod.jp/en/articles/lambda-durable-functions-slack-approval/)
  - Patterns for calling AgentCore agents asynchronously from serverless pipelines (Lambda dispatcher, direct Step Functions to AgentCore, durable functions) — [CloudThat [3rd-party]](https://www.cloudthat.com/resources/?p=79102); [AWS ML blog mirror: async patterns for AgentCore](https://aihub.hkuspace.hku.hk/?p=8080)

### Inferences
- **Recommended hackathon pattern:** a Step Functions Standard workflow per dispute case, or a durable Lambda if the team prefers code-first.
  1. Run deterministic steps: compute the deadline and run the rules engine.
  2. Invoke the AgentCore agent (synchronous call).
  3. Run Guardrails and the Automated Reasoning check.
  4. Wait for approval with `.waitForTaskToken` (or a durable callback), with a simple approver UI calling `SendTaskSuccess`.
  5. Execute the refund through a policy-gated Gateway tool.
  6. Emit an EventBridge event that starts the recovery track and, through a one-way channel, the Zone 2 lead.
- **Audit:** the Step Functions execution history and the approval token give a natural per-case record. Persist the approval decision together with a hash of the decision memo.
- **Choosing between them:** Step Functions gives a visual audit trail and native service integrations. Durable functions keep everything in Python or TypeScript code, which may be faster to build in a hackathon. Either is in Frankfurt.

### Gaps
- **EventBridge** was not researched in this session (routing patterns, cross-account buses for the zone barrier).
- I did not verify the official status and syntax of the Step Functions to AgentCore integration.
- I did not verify Step Functions costs for long waits; one low-quality study guide claim was excluded.
- I did not verify maximum durations and quotas for durable steps.
- Strands' in-agent interrupts were not verified as an approval mechanism.

---

## 8. AWS-provided MCP servers (awslabs/mcp and the AWS MCP Server) relevant to this system

### Takeaway
`awslabs/mcp` provides local stdio MCP servers that are directly useful here: Bedrock KB retrieval, Neptune, DynamoDB, Aurora PostgreSQL, Lambda-as-tool, AgentCore docs and AWS docs. There is also a remote, managed **AWS MCP Server (preview)** for general AWS API and docs access. AWS signals that the "Agent Toolkit for AWS" is the successor to the awslabs MCP servers.

### Cited Findings
- Relevant servers listed in the awslabs/mcp README (page truncated; not all servers seen). All entries — [github.com/awslabs/mcp](https://github.com/awslabs/mcp):

  | Server | Package or endpoint | Purpose |
  |---|---|---|
  | **AWS MCP Server (preview)** | Remote, hosted by AWS; via `mcp-proxy-for-aws`, endpoint `https://aws-mcp.us-east-1.api.aws/mcp` | AWS API access, docs, What's New and Getting Started content, pre-built "Agent SOPs". Uses IAM permissions, validates API calls syntactically, logs to CloudTrail |
  | AWS Knowledge MCP Server | Remote, `https://knowledge-mcp.global.api.aws` | AWS docs, API references, blogs, Well-Architected guidance |
  | Bedrock Knowledge Bases Retrieval | `awslabs.bedrock-kb-retrieval-mcp-server` | Query KBs with citations |
  | Amazon Neptune | `awslabs.amazon-neptune-mcp-server` | openCypher and Gremlin queries |
  | DynamoDB | `awslabs.dynamodb-mcp-server` | Design and data-modeling guidance; a read-only flag appears in the example config |
  | Aurora PostgreSQL | `awslabs.postgres-mcp-server` | Via the RDS Data API |
  | Aurora DSQL | `awslabs.aurora-dsql-mcp-server` | — |
  | Lambda Tool | `awslabs.lambda-tool-mcp-server` | Run Lambda functions as tools, including for private-resource access |
  | AgentCore | `awslabs.amazon-bedrock-agentcore-mcp-server` | AgentCore docs and best practices |
  | AWS Documentation | `awslabs.aws-documentation-mcp-server` | — |
  | AWS IaC | `awslabs.aws-iac-mcp-server` | CloudFormation and CDK; replaces the deprecated Cloud Control API server |
  | AWS Serverless | `awslabs.aws-serverless-mcp-server` | SAM |
  | S3 Tables | `awslabs.s3-tables-mcp-server` | — |
- Notes from the same README:
  - Local servers support **stdio only**.
  - SSE support was removed on 26 May 2025.
  - Several servers have `--allow-write` and `--allow-sensitive-data-access` flags that should stay off by default.
  - The "Agent Toolkit for AWS" is described as the successor to the awslabs MCP servers, plugins and skills.

### Inferences
- **Runtime tools in the agents:** the Neptune MCP server (Zone 2 graph queries) and the Bedrock KB retrieval server (regulatory corpus, Zone 1). In production, put them behind the zone's **AgentCore Gateway** as MCP targets, so Policy and auth apply, rather than letting agents reach them directly.
- **Builder tooling** (for the hackathon team's coding assistant, not for runtime agents): the AWS MCP Server, AWS Knowledge, AgentCore and IaC servers.
- **Configuration:** keep `--allow-sensitive-data-access` off and use read-only modes in the agent zones.

### Gaps
- The CloudWatch, Step Functions, CloudTrail, IAM, S3 or S3 Vectors and BDA MCP servers were not visible in the truncated README. A CloudWatch MCP server probably exists but was **not verified**.
- The AWS MCP Server GA status and Regions beyond the us-east-1 endpoint are not confirmed.
- I did not research the scope of the "Agent Toolkit for AWS".

---

## 9. AWS reference architectures and samples for agentic fraud, AML and financial services (2025–2026)

### Takeaway
I found no single official "agentic fraud dispute / AML" sample repo. The strongest AWS-authored references are:
- Amazon's own compliance-screening system (Strands investigator agents on AgentCore Runtime);
- a multi-agent KYC/KYB build on AgentCore (AWS for Industries);
- a re:Invent 2025 dev-track session on AML multi-agent orchestration with Strands;
- an AWS-partner cookbook for an evidence-grounded AML agent on Bedrock.

### Cited Findings
- **Amazon compliance screening:** a tiered system for screening "billions of transactions per day". The investigation tier runs specialised investigator agents built on Strands, with Bedrock-hosted LLMs, deployed on AgentCore Runtime. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/how-amazon-uses-ai-agents-to-support-compliance-screening-of-billions-of-transactions-per-day)
- **Multi-agent KYC/KYB:** AgentCore runs every module, including adverse-media screening across fraud and money-laundering topics. — [AWS for Industries blog](https://aws.amazon.com/blogs/industries/from-days-to-minutes-how-we-built-multi-agent-kyc-kyb-on-aws)
- **DEV326 session:** "Anti-Money Laundering multi-agent orchestration with AWS Strands", which argues that agentic workflows suit AML because of data complexity and the need for explainable decisions. — [DEV Community (AWS)](https://dev.to/aws/dev-track-spotlight-anti-money-laundering-multi-agent-orchestration-with-aws-strands-dev326-6p8)
- **Evidence-grounded AML agent:** a partner cookbook that analyses synthetic AML data with the OpenAI Agents SDK on Bedrock. Its default path uses a deterministic offline assessment. — [Cookbook](https://developers.openai.com/cookbook/examples/partners/aws/evidence_grounded_aml_agent_with_bedrock)
- **Partner showcases and products:** AWS partners demonstrated enterprise agent solutions on AgentCore ([APN Blog](https://aws.amazon.com/blogs/apn/aws-partners-demonstrate-enterprise-ai-agent-solutions-with-amazon-bedrock-agentcore)). AWS Marketplace also lists commercial AML and fraud-investigation agents on Bedrock and AgentCore from partners such as Reply, XenonStack, Compass UOL and HCLTech. These are products, not samples, and are seen only via search summary.
- **Community project:** a hackathon-style project with three agents (triage, investigation, report) on AgentCore Runtime for fraud-alert triage. — [Devpost [3rd-party]](https://devpost.com/software/ai-driven-multi-agent-fraud-alert-triage-system)

### Inferences
- The Amazon compliance blog is the closest real-world analogue for Zone 2, and the KYC/KYB blog for multi-agent decomposition on AgentCore. Both are worth citing in the pitch as evidence that the architecture is AWS-endorsed.
- The partner cookbook's deterministic offline fallback is a good pattern for a hackathon demo that must run reliably.

### Gaps
- I did not search the `aws-samples` GitHub organisation directly. There may be sample repos for AgentCore FSI, fraud or AML that this session missed.
- I found no AWS sample implementing an information barrier or tipping-off controls between agents.

---

## 10. Cross-cutting: how the services fit the two-zone design (from the objective)

### Takeaway
Every requirement maps to an existing, mostly GA, Frankfurt-available AWS capability:

| Requirement | Capability |
|---|---|
| Agent hosting | AgentCore Runtime |
| Tools | AgentCore Gateway |
| Information barrier | Policy, plus separate identities and resources per zone |
| PII and injection protection | Guardrails, applied explicitly to tool I/O |
| Deterministic rules | Code plus Automated Reasoning as a verifier |
| Human approval | Step Functions or Lambda durable functions |
| Audit trail | CloudTrail, Observability (OTel) and invocation logs |
| Models | Claude 5.5 via EU routing |

The main practical blocker is credentials. A Bedrock API key alone covers only the model and guardrail calls; AgentCore, BDA, Knowledge Bases, Step Functions and Neptune need IAM.

### Cited Findings
- **Barrier mechanics:** Policy enforces default-deny per tool call at the Gateway, with temporal policies ([AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)). Runtime gives each session dedicated microVM isolation ([AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)). Memory uses encrypted, namespace-based stores ([AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)).
- **PII and injection gaps to close:** Guardrails PII filters skip tool arguments and results ([Guardrails sensitive filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)). Prompt-attack filters exist ([Guardrail components](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html)). Policy integrates Guardrails for prompt-injection and sensitive-data detection ([AgentCore FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)).
- **Rules verification:** Automated Reasoning checks give auditable, rule-cited validation in Frankfurt, English only, detect mode ([AR docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html)).
- **Audit sources:**
  - CloudTrail logs all Bedrock API calls, including API-key calls ([API keys docs](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)).
  - Claude in Amazon Bedrock logs to CloudWatch and CloudTrail ([Anthropic docs](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)).
  - AgentCore Observability provides OTel traces ([FAQ](https://aws.amazon.com/bedrock/agentcore/faqs/)).
  - Invocation logs contain unmasked PII unless CloudWatch Logs data protection is used ([Guardrails sensitive filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html)).
- **EU availability confirmed in this session (Frankfurt):**
  - AgentCore Policy and Evaluations
  - Automated Reasoning checks
  - BDA
  - Lambda durable functions
  - the Claude Mantle endpoint (Global and EU types)

  Sources: [Policy GA](https://aws.amazon.com/about-aws/whats-new/2026/03/policy-amazon-bedrock-agentcore-generally-available/); [Evaluations GA](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available); [AR docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html); [BDA regions](https://aws.amazon.com/about-aws/whats-new/2025/07/amazon-bedrock-data-automation-additional-aws-regions/); [Durable functions regions](https://aws.amazon.com/about-aws/whats-new/2025/12/lambda-durable-functions-14-additional-regions/); [Anthropic regions table](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)

### Inferences
- **Reference wiring (my proposal):**
  - **Zone 1 (Dispute)**
    - Runtime A runs a Strands Graph under IAM role A.
    - Gateway A carries Policy engine A (default deny) and exposes these tools: core-banking read, refund execute (gated by approval), customer comms (Guardrail-filtered), KB retrieval on the regulatory corpus, and a deterministic rules engine Lambda.
    - Memory A, KMS key A and DynamoDB table A hold the zone's state.
    - Step Functions or durable Lambda handles the case lifecycle and the approval wait.
  - **Hand-off**
    - Zone 1 emits a minimal, schema-validated "beneficiary lead" event: beneficiary IBAN or account, amount, timestamps and case reference.
    - It goes on a one-way EventBridge bus or SQS queue whose resource policy only lets Zone 1 *put* and Zone 2 *read*.
    - Nothing flows back.
  - **Zone 2 (AML)**
    - Runtime B runs a Strands Graph or Swarm under IAM role B.
    - Gateway B carries Policy engine B and exposes Neptune Analytics graph tools (WCC, Louvain, PageRank, Jaccard), transaction history and a SAR-draft generator.
    - Output goes only to the AML analyst queue.
    - Zone 1 identities have no permissions on any Zone 2 resource.
  - **Tipping-off guard**
    - Zone 1 outbound communications pass a guardrail with denied topics for AML, SAR and investigation terms.
    - The Zone 1 agent never has Zone 2 data in its context or memory.
- **Deterministic core:**
  - The legal deadline ("end of next business day"), eligibility flags and amounts are computed in code.
  - The LLM drafts the explanation.
  - Automated Reasoning verifies that the English explanation is consistent with the encoded rules.
  - A human approves.
  - Only then does a policy-gated tool execute the refund.
  - The recovery track starts as a separate workflow.
- **Hackathon shortcuts if IAM access is limited:**
  - Run Strands agents locally or in a container, using the Bedrock API key for Claude and `ApplyGuardrail`.
  - Implement the Gateway and Policy barrier as local MCP servers plus a hook-based allow-list.
  - Present AgentCore Gateway, Policy and Runtime as the production deployment target.

  This is an inference about scope, not a tested setup.

### Gaps
- I did not research Romanian or EU-specific regulatory constraints on cloud or LLM use by banks, for example EBA outsourcing guidelines, DORA, or whether the bank already has an approved AWS landing zone.
- Search results surfaced AWS docs on a `docs.aws.eu` domain. This is possibly the AWS European Sovereign Cloud documentation; whether Claude or AgentCore are offered in that partition was not researched.
- I did not research the end-to-end latency and cost of chaining Guardrails, Automated Reasoning, Opus 5.5 and approval per case.
