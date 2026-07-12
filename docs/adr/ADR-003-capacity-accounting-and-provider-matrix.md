# ADR-003: Capacity Accounting And Provider Matrix

Date: 2026-07-12
Status: Accepted

## Decision

Provider selection is connector-specific: provider family, model, account scope, and execution mode are separate from the provider's capability descriptor. Capacity is represented by observed windows for requests, tokens, spend, concurrency, and subscription calls.

The `CapacityBroker` is the authority for reservations. A known exhausted, cooling, or unavailable connector is never eligible. A connector without an observation is explicitly `unknown`, remains eligible with a routing penalty, and is never treated as unlimited. Reservations are released on failure or timeout and committed only after a valid provider response.

HTTP adapters normalize recognized rate-limit headers. Provider errors and CLI output may create inferred observations, but inferred observations carry lower confidence and are never presented as exact quota. Capability values remain configured priors until a versioned benchmark measures them.

The default API monetary ceiling remains `$0.50`. Subscription CLI calls have no provider-reported marginal USD price and are recorded as `allocated_cost_unknown`; they are bounded by connector concurrency, run token budgets, and subscription-call limits. A benchmark must not compare that path as if subscription usage were free API spend.

## Provider Matrix

- OpenAI and Anthropic API adapters use their configured API keys and response metadata.
- Gemini uses AI Studio API keys or a future Vertex ADC connector; consumer OAuth is not reused.
- xAI and compatible local gateways use the chat-completions adapter.
- Ollama remains the local Llama/OSS path.
- Claude Code and Codex CLI are separate subprocess adapters and use credentials owned by their official CLIs.

No key, token, CLI auth file, or secret value is persisted by the orchestrator. Provider endpoints, model IDs, and environment-variable names are configuration; secrets remain environment/keychain state.

## Consequences

Routing can stop before an exhausted model call and can later hand work to another connector without changing task identity. Exact limit visibility is provider-dependent: Codex's official account surface can expose rate windows, while other subscription CLIs may provide only structured error or usage signals. The product reports that distinction rather than inventing a universal quota API.
