# ChatGPT session wake binding

Development Bridge can bind a logical coordinator route to the physical ChatGPT conversation that invoked the MCP tool without exposing the physical conversation URL or identifier to model-visible content.

## Identity

ChatGPT supplies `_meta["openai/session"]` on tool calls. Development Bridge never stores that raw value in route state. It stores only a domain-separated SHA-256 fingerprint and uses it for server-side correlation.

A host-session fingerprint is unique to one active logical route. Binding the same physical ChatGPT conversation to a second active route fails closed with `HOST_SESSION_ALREADY_BOUND`.

## Binding states

`unbound`
: No active ChatGPT owner.

`x_bound`
: The route has generation/channel ownership and a hidden host-session fingerprint, but no physical ChatGPT URL. X/widget continuation delivery is available. Direct/browser delivery is unavailable.

`bound`
: The same route additionally has a physical ChatGPT target. X/widget and direct/browser delivery can both use the same generation/channel.

An existing `x_bound` route may be upgraded through the OOB route-control flow. For the same owner this adds the direct target without incrementing the route generation or changing the channel.

## Session recovery

MCP transport session IDs are not treated as durable ChatGPT identity. When a new MCP transport session arrives, Development Bridge may restore its in-memory route binding from exactly one matching host-session fingerprint. Zero matches preserve the existing unbound behavior; multiple matches fail closed.

## Route-control capability

The widget route-control bearer is persisted only as a domain-separated SHA-256 digest. The raw bearer is not written to disk. The capability is fenced by route generation and survives service restart. Its inactivity TTL is seven days and it refreshes only during the final 24 hours, avoiding steady write churn.

## Continuation delivery

A continuation payload becomes immutable after first claim. Retries retain the same frozen payload and SHA-256 identity. Transport delivery and model acknowledgement remain separate states; a continuation is complete only after `coordinator_ack`.

## Operational notes

- Mount the coordinator once per physical ChatGPT conversation.
- A direct target is optional for ordinary X/widget delivery.
- Use `Включить direct wake` only when autonomous browser/direct fallback is required.
- Route generation remains the authoritative stale-owner fence.
- Existing legacy routes without a host-session fingerprint remain compatible and continue to use their current explicit binding behavior.
