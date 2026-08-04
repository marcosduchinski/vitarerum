# Business Flows

This is an index of end-to-end business flows and the diagrams or contracts
that currently describe them. When a flow is not yet diagrammed, this file
records the gap without inventing an incomplete diagram.

## Proposal Intake and Lifecycle

- Public proposal submission:
  [public-submission-double-opt-in.svg](../diagrams/public-submission-double-opt-in.svg),
  [public-proposal-life-cycle.svg](../diagrams/public-proposal-life-cycle.svg),
  [PublicProposalSubmission API](../api_contracts/11PublicProposalSubmission-API.md).
- Authenticated proposal submission:
  [Proposal phase - researcher actions](../api_contracts/02Proposal%20phase%20%E2%80%94%20researcher%20actions.md).
- Proposal origin identification: documented by
  [ADR 0001](./adr/0001-submission-channel.md).
- Proposal lifecycle:
  [proposal-life-cycle.svg](../diagrams/proposal-life-cycle.svg),
  [Proposal phase - staff actions](../api_contracts/03Proposal%20phase%20%E2%80%94%20staff%20actions.md).
- Document correction and attachments: covered across proposal API contracts and
  the public submission/amendment states in
  [public-proposal-life-cycle.svg](../diagrams/public-proposal-life-cycle.svg).
- Staff notifications triggered by proposal events:
  [notifications-flow.svg](../diagrams/notifications-flow.svg).

## Collection Use Projects

- Project lifecycle:
  [use-of-collections-life-cycle.svg](../diagrams/use-of-collections-life-cycle.svg),
  [Project phase - researcher actions](../api_contracts/04Project%20phase%20%E2%80%94%20researcher%20actions.md),
  [Project phase - staff actions](../api_contracts/05Project%20phase%20%E2%80%94%20staff%20actions.md).
- Object search and requested-object snapshots:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
  A dedicated end-to-end diagram for object selection is still to document.
- Reference number policy administration:
  [reference-number-policies.svg](../diagrams/reference-number-policies.svg).

## In-Situ Visit, CIDOC-CRM, and Narrative

- In-situ visit to CIDOC/narrative flow:
  [in-situ-visit-cidoc-narrative-flow.svg](../diagrams/in-situ-visit-cidoc-narrative-flow.svg).
- In-situ visit context map:
  [in-situ-visit-context-map.svg](../diagrams/in-situ-visit-context-map.svg).
- CIDOC-CRM mapping:
  [cidoc-crm-in-situ-visit-record-model.svg](../diagrams/cidoc-crm-in-situ-visit-record-model.svg),
  [cidoc-example-in-situ-visit.svg](../diagrams/cidoc-example-in-situ-visit.svg),
  [InSituVisit-CIDOC-CRM API](../api_contracts/08InSituVisit-CIDOC-CRM.md).
- Narrative generation:
  [KG-RAG Narrative API](../api_contracts/09KG-RAG-Narrative.md).
- Report aggregation:
  [Reports InSituVisit API](../api_contracts/10Reports-InSituVisit.md).
- External publication of reports and JSON-LD:
  [external-publications-flow.svg](../diagrams/external-publications-flow.svg).

## Museum Questions

- Public question submission:
  [museum-questions-public-flow.svg](../diagrams/museum-questions-public-flow.svg),
  [MuseumQuestions Public API](../api_contracts/13MuseumQuestions-Public-API.md).
- Staff response:
  [museum-questions-response-flow.svg](../diagrams/museum-questions-response-flow.svg),
  [MuseumQuestions Internal API](../api_contracts/14MuseumQuestions-Internal-API.md).
- AI triage:
  [museum-question-triage-flow.svg](../diagrams/museum-question-triage-flow.svg).

## Administration

- Document templates:
  [DocumentTemplates API](../api_contracts/12DocumentTemplates-API.md).
- Collection data sources:
  [CollectionDataSources Admin API](../api_contracts/15CollectionDataSources-Admin-API.md).
- AI prompts:
  [ai-prompts-life-cycle.svg](../diagrams/ai-prompts-life-cycle.svg),
  [AI Prompts Admin API](../api_contracts/16AI-Prompts-Admin-API.md).
- Dashboard summary:
  [dashboard-summary-flow.svg](../diagrams/dashboard-summary-flow.svg),
  [Dashboard Summary API](../api_contracts/17Dashboard-Summary-API.md).
- External publication administration:
  [external-publications-flow.svg](../diagrams/external-publications-flow.svg).
