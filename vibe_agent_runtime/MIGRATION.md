# zhitouagent Runtime Migration

- Upstream: `zhitouagent`
- Commit: `99e84abaad965f75dd15cab2fcb0f3f61d30577b`
- License: MIT; the upstream `LICENSE` is copied to `vendor/LICENSE`.
- Scope: `agent/src` runtime closure, `agent/backtest`, bundled skills and
  Swarm presets.
- Adapter: QuantingAgents owns authentication, Mongo metadata, task lifecycle,
  SSE events, audit, and the configured runtime root.
- Excluded: Vibe's independent HTTP API, frontend, CLI/channel integrations,
  desktop files, tests, `.env`, secrets, user data, caches, and runtime output.
- Default governance disables shell, file mutation, skill mutation, order
  placement/cancellation, and broker write tools. The capability inventory
  reports those tools as unavailable instead of silently allowing them.

## Mapping

| Upstream area | QuantingAgents treatment |
| --- | --- |
| `src/agent`, `src/session` | Vendored directly; invoked through `vibe_agent_runtime.runtime` |
| `src/tools`, `src/skills`, `src/swarm`, `backtest`, `src/quantlib` | Vendored directly; capability discovery reports failures |
| `src/providers`, `src/config`, `src/memory`, `src/core` | Vendored directly; `VIBE_TRADING_HOME` is injected to the isolated runtime root |
| Vibe API routes/server/frontend/channels | Not migrated; QuantingAgents API and frontend remain authoritative |
| Auth, task center, audit, user paths | Existing QuantingAgents services and adapters |
