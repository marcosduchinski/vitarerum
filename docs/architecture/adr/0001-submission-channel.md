---
status: current
---

# ADR-0001 - Persist proposal submission channel

## Status

Accepted

## Context

Vitarerum accepts collection-use proposals through two paths:

- public submission, where requester name and email are provided before login;
- authenticated submission, where the requester identity is already known from
  the active user/session.

Before this decision, proposal origin could be inferred indirectly from the
presence of requester contact data. That inference is fragile because it depends
on incidental field shape rather than an explicit domain fact.

## Decision

Persist and expose the proposal submission channel explicitly, using values such
as `PUBLIC` and `AUTHENTICATED`.

Frontend code must treat the backend field as the source of truth and must not
derive the channel from requester contact fields.

## Alternatives Considered

- Infer the channel in the frontend from requester contact data. Rejected
  because it recreates the same fragile coupling that motivated the decision.
- Infer the channel in the backend response from nullable fields. Rejected
  because it keeps the fact implicit and makes future data migrations harder to
  reason about.
- Persist the channel explicitly. Chosen because it makes origin queryable,
  auditable, and stable across public and authenticated flows.

## Consequences

- Proposal records carry an explicit origin marker.
- API responses can expose the channel without asking consumers to reimplement
  inference.
- Backfills or migrations must set a channel for existing proposals.
- Future intake paths must decide their channel at creation time.

## References

- [SPEC-008 - Proposta de uso de colecoes](../../specs/008-proposta-uso-de-colecoes/spec.md)
- [SPEC-010 - Submissao publica](../../specs/010-submissao-publica/spec.md)

