---
status: current
---

# Business Flows

This is an index of end-to-end business flows, the diagrams that draw them and
the specifications that state their rules. When a flow is not yet diagrammed,
this file records the gap without inventing an incomplete diagram.

Endpoint-level HTTP documentation is the generated OpenAPI schema; what is
shared by every endpoint is in the
[cross-cutting contract](../api_contracts/README.md).

## Proposal Intake and Lifecycle

- Public proposal submission:
  [SPEC-010](../specs/010-submissao-publica/spec.md).

![Public submission double opt-in](../diagrams/public-submission-double-opt-in.svg)

![Public proposal lifecycle](../diagrams/public-proposal-life-cycle.svg)

- Authenticated proposal submission:
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md).
- Proposal origin identification: documented by
  [ADR 0001](./adr/0001-submission-channel.md).
- Proposal lifecycle:
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md).

![Proposal lifecycle](../diagrams/proposal-life-cycle.svg)

- Document correction and attachments: covered by
  [SPEC-008](../specs/008-proposta-uso-de-colecoes/spec.md) and the public
  submission/amendment states above.
- Staff notifications triggered by proposal events:

![Notifications flow](../diagrams/notifications-flow.svg)

## Collection Use Projects

- Project lifecycle:
  [SPEC-009](../specs/009-projeto-uso-de-colecoes/spec.md).

![Use of collections lifecycle](../diagrams/use-of-collections-life-cycle.svg)

- Object search and requested-object snapshots:
  [SPEC-014](../specs/014-catalogo-e-indice-de-objetos/spec.md).
  A dedicated end-to-end diagram for object selection is still to document.
- Reference number policy administration:

![Reference number policies](../diagrams/reference-number-policies.svg)

## In-Situ Visit, CIDOC-CRM, and Narrative

- In-situ visit to CIDOC/narrative flow:

![In-situ visit CIDOC narrative flow](../diagrams/in-situ-visit-cidoc-narrative-flow.svg)

- In-situ visit context map:

![In-situ visit context map](../diagrams/in-situ-visit-context-map.svg)

- CIDOC-CRM mapping:
  [SPEC-013](../specs/013-mapeamento-cidoc-crm/spec.md).

![CIDOC-CRM in-situ visit record model](../diagrams/cidoc-crm-in-situ-visit-record-model.svg)

![CIDOC example in-situ visit](../diagrams/cidoc-example-in-situ-visit.svg)

- Narrative generation:
  [SPEC-017](../specs/017-narrativa-museologica/spec.md).
- Report aggregation:
  [SPEC-015](../specs/015-relatorio-visita-in-situ/spec.md).
- External publication of reports and JSON-LD:

![External publications flow](../diagrams/external-publications-flow.svg)

## Museum Questions

- Public question submission:
  [SPEC-011](../specs/011-perguntas-ao-museu/spec.md).

![Museum questions public flow](../diagrams/museum-questions-public-flow.svg)

- Staff response: same spec, staff-facing requirements.

![Museum questions response flow](../diagrams/museum-questions-response-flow.svg)

## Administration

- Document templates:
  [SPEC-012](../specs/012-modelos-de-documento/spec.md).
- Collection data sources and catalog administration:
  [SPEC-014](../specs/014-catalogo-e-indice-de-objetos/spec.md).
- AI prompts:
  [SPEC-016](../specs/016-prompts-versionados/spec.md).

![AI prompts lifecycle](../diagrams/ai-prompts-life-cycle.svg)

- Dashboard summary: the `/p/dashboard` page is served by existing list
  endpoints. Dedicated summary endpoints are proposed but not implemented -
  see [Dashboard Summary API (proposed)](../proposals/17Dashboard-Summary-API.md)
  and [SPEC-021](../specs/021-resumos-de-painel/spec.md).

![Dashboard summary flow](../diagrams/dashboard-summary-flow.svg)

- External publication administration:

![External publication administration](../diagrams/external-publications-flow.svg)
