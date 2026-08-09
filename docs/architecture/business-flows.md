# Business Flows

This is an index of end-to-end business flows and the diagrams or contracts
that currently describe them. When a flow is not yet diagrammed, this file
records the gap without inventing an incomplete diagram.

## Proposal Intake and Lifecycle

- Public proposal submission:
  [PublicProposalSubmission API](../api_contracts/11PublicProposalSubmission-API.md).

![Public submission double opt-in](../diagrams/public-submission-double-opt-in.svg)

![Public proposal lifecycle](../diagrams/public-proposal-life-cycle.svg)

- Authenticated proposal submission:
  [Proposal phase - researcher actions](../api_contracts/02Proposal%20phase%20%E2%80%94%20researcher%20actions.md).
- Proposal origin identification: documented by
  [ADR 0001](./adr/0001-submission-channel.md).
- Proposal lifecycle:
  [Proposal phase - staff actions](../api_contracts/03Proposal%20phase%20%E2%80%94%20staff%20actions.md).

![Proposal lifecycle](../diagrams/proposal-life-cycle.svg)

- Document correction and attachments: covered across proposal API contracts and
  the public submission/amendment states above.
- Staff notifications triggered by proposal events:

![Notifications flow](../diagrams/notifications-flow.svg)

## Collection Use Projects

- Project lifecycle:
  [Project phase - researcher actions](../api_contracts/04Project%20phase%20%E2%80%94%20researcher%20actions.md),
  [Project phase - staff actions](../api_contracts/05Project%20phase%20%E2%80%94%20staff%20actions.md).

![Use of collections lifecycle](../diagrams/use-of-collections-life-cycle.svg)

- Object search and requested-object snapshots:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
  A dedicated end-to-end diagram for object selection is still to document.
- Reference number policy administration:

![Reference number policies](../diagrams/reference-number-policies.svg)

## In-Situ Visit, CIDOC-CRM, and Narrative

- In-situ visit to CIDOC/narrative flow:

![In-situ visit CIDOC narrative flow](../diagrams/in-situ-visit-cidoc-narrative-flow.svg)

- In-situ visit context map:

![In-situ visit context map](../diagrams/in-situ-visit-context-map.svg)

- CIDOC-CRM mapping:
  [InSituVisit-CIDOC-CRM API](../api_contracts/08InSituVisit-CIDOC-CRM.md).

![CIDOC-CRM in-situ visit record model](../diagrams/cidoc-crm-in-situ-visit-record-model.svg)

![CIDOC example in-situ visit](../diagrams/cidoc-example-in-situ-visit.svg)

- Narrative generation:
  [KG-RAG Narrative API](../api_contracts/09KG-RAG-Narrative.md).
- Report aggregation:
  [Reports InSituVisit API](../api_contracts/10Reports-InSituVisit.md).
- External publication of reports and JSON-LD:

![External publications flow](../diagrams/external-publications-flow.svg)

## Museum Questions

- Public question submission:
  [MuseumQuestions Public API](../api_contracts/13MuseumQuestions-Public-API.md).

![Museum questions public flow](../diagrams/museum-questions-public-flow.svg)

- Staff response:
  [MuseumQuestions Internal API](../api_contracts/14MuseumQuestions-Internal-API.md).

![Museum questions response flow](../diagrams/museum-questions-response-flow.svg)

## Administration

- Document templates:
  [DocumentTemplates API](../api_contracts/12DocumentTemplates-API.md).
- Collection data sources:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
- AI prompts:
  [AI Prompts Admin API](../api_contracts/16AI-Prompts-Admin-API.md).

![AI prompts lifecycle](../diagrams/ai-prompts-life-cycle.svg)

- Dashboard summary:
  [Dashboard Summary API](../api_contracts/17Dashboard-Summary-API.md).

![Dashboard summary flow](../diagrams/dashboard-summary-flow.svg)

- External publication administration:

![External publication administration](../diagrams/external-publications-flow.svg)
