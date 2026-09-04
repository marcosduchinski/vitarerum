---
status: current
---

# Architecture Decision Records

ADRs capture durable architecture decisions that should outlive the work that
prompted them. An ADR is the compact
record of a decision that affects boundaries, public contracts, persistence,
security, or integration between bounded contexts.

## Rules

- Not every plan becomes an ADR.
- Prefer ADRs for decisions that constrain future work.
- Cite plans, code, contracts, or discussions as evidence.
- When documenting a decision retroactively from the current code shape, say so
  explicitly in the ADR.
- Supersede old ADRs instead of silently rewriting their conclusions.

## Records

- [ADR-0001 - Persist proposal submission channel](./0001-submission-channel.md)
- [ADR-0002 - Use published language over event bus for module integration](./0002-published-language-over-event-bus.md)

