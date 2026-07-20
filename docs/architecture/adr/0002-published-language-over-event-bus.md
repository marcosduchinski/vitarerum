# ADR-0002 - Use published language over event bus for module integration

## Status

Accepted

## Context

Vitarerum is a modular monolith. Bounded contexts share one backend deployment,
but code dependencies are constrained by Clean Architecture layers and
`import-linter` contracts.

Vitarerum currently uses synchronous calls through published-language modules
such as `identity.public`, `use_of_collections.public`, `cidoc_crm.public`,
`museum_questions.public`, and `ai.*.public`.

Note: this ADR documents a decision retroactively from the current code,
`import-linter` contracts, and backend architecture rules. There is no known
formal debate record from the moment this choice originally emerged.

## Decision

Use synchronous published-language interfaces and narrow ACLs for cross-context
integration inside the backend monolith. Do not introduce Event Bus,
Outbox/Inbox, or Event Sourcing as the default integration model.

## Alternatives Considered

- Event Bus with Outbox/Inbox. Rejected for the current architecture because
  the main workflows are request/response, staff review, public intake,
  reporting, and read aggregation inside one deployable service.
- Direct imports into another context's internals. Rejected because they bypass
  context boundaries and are guarded by import-linter contracts.
- Synchronous published-language modules. Chosen because they keep boundaries
  explicit while matching the operational simplicity of the current monolith.

## Consequences

- Cross-context calls stay easy to trace in normal request handling.
- Published interfaces must remain small and intentional.
- The context map and import-linter contracts must be updated together when
  dependencies change.
- Asynchronous integration can still be introduced later for a specific need,
  but it should be justified by a new ADR.

## References

- [Backend architecture rules](../../../vitarerum-api/AGENTS.md)
- [Backend import-linter contracts](../../../vitarerum-api/pyproject.toml)
- [Context map](../context-map.puml)
